import json
import os
import re
import urllib.parse
import urllib.request

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
if API_KEY in ("", "ТВОЙ_КЛЮЧ", "YOUR_API_KEY"):
    API_KEY = ""

REMIXERS_FILE = "remixers.json"
CHANNEL_ANALYTICS_FILE = "channel_analytics.json"
OUTPUT_FILE = "creators_analytics.json"
SHORTS_MAX_SECONDS = 180
MAX_VIDEOS_PER_CREATOR = 200


def api_get(endpoint: str, params: dict) -> dict:
    q_params = dict(params)
    q_params["key"] = API_KEY
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urllib.parse.urlencode(q_params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_iso_duration_seconds(duration: str) -> int:
    if not duration:
        return 0
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration.strip())
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def is_short_video(item: dict) -> bool:
    snip = item.get("snippet") or {}
    cd = item.get("contentDetails") or {}
    sec = parse_iso_duration_seconds(cd.get("duration") or "")
    text = f"{snip.get('title') or ''} {snip.get('description') or ''}".lower()
    if "#shorts" in text:
        return True
    return 0 < sec <= SHORTS_MAX_SECONDS


def extract_avatar_url(snip: dict) -> str:
    thumbs = snip.get("thumbnails") or {}
    for key in ("high", "medium", "default"):
        info = thumbs.get(key) or {}
        url = (info.get("url") or "").strip()
        if url:
            return url
    return ""


def resolve_channel(creator: dict) -> dict | None:
    handle = (creator.get("handle") or creator.get("channel_handle") or "").strip().lstrip("@")
    channel_id = (creator.get("channel_id") or "").strip()

    if handle:
        try:
            data = api_get("channels", {
                "part": "snippet,statistics,contentDetails",
                "forHandle": handle,
            })
            items = data.get("items") or []
            if items:
                return items[0]
        except Exception:
            pass

    if channel_id:
        try:
            data = api_get("channels", {
                "part": "snippet,statistics,contentDetails",
                "id": channel_id,
            })
            items = data.get("items") or []
            if items:
                return items[0]
        except Exception:
            pass

    query = handle or (creator.get("name") or "").strip()
    if query:
        try:
            s_data = api_get("search", {
                "part": "snippet",
                "q": query,
                "type": "channel",
                "maxResults": 1,
            })
            s_items = s_data.get("items") or []
            if s_items:
                found_id = (((s_items[0].get("snippet") or {}).get("channelId")) or s_items[0].get("id") or "").strip()
                if found_id:
                    c_data = api_get("channels", {
                        "part": "snippet,statistics,contentDetails",
                        "id": found_id,
                    })
                    c_items = c_data.get("items") or []
                    if c_items:
                        return c_items[0]
        except Exception:
            pass

    return None


def main():
    if not API_KEY:
        print("ВНИМАНИЕ: YOUTUBE_API_KEY не задан.")
        return

    if not os.path.exists(REMIXERS_FILE):
        print(f"Файл {REMIXERS_FILE} не найден.")
        return

    with open(REMIXERS_FILE, "r", encoding="utf-8") as f:
        raw_remixers = json.load(f)

    if isinstance(raw_remixers, dict):
        creators = raw_remixers.get("creators") or raw_remixers.get("remixers") or raw_remixers.get("items") or []
    elif isinstance(raw_remixers, list):
        creators = raw_remixers
    else:
        creators = []

    own_channel_id = ""
    if os.path.exists(CHANNEL_ANALYTICS_FILE):
        try:
            with open(CHANNEL_ANALYTICS_FILE, "r", encoding="utf-8") as f:
                own_data = json.load(f)
            own_channel_id = (((own_data.get("summary") or {}).get("channel_id")) or "").strip()
        except Exception:
            pass

    creators_out = []

    for creator in creators:
        if not isinstance(creator, dict):
            continue
        display_name = (creator.get("name") or creator.get("title") or creator.get("handle") or "Автор").strip()
        handle_clean = (creator.get("handle") or creator.get("channel_handle") or "").strip().lstrip("@")

        ch = resolve_channel(creator)
        if not ch:
            print(f"Пропуск {display_name}: канал не найден")
            continue

        cid = (ch.get("id") or "").strip()
        if own_channel_id and cid == own_channel_id:
            print(f"Пропуск {display_name}: свой канал уже есть в channel_analytics.json")
            continue

        snip = ch.get("snippet") or {}
        ch_title = (snip.get("title") or "").strip() or display_name
        custom_url = (snip.get("customUrl") or "").strip()
        if custom_url:
            channel_url = f"https://www.youtube.com/{custom_url.lstrip('/')}"
        elif handle_clean:
            channel_url = f"https://www.youtube.com/@{handle_clean}"
        else:
            channel_url = f"https://www.youtube.com/channel/{cid}"

        avatar_url = extract_avatar_url(snip) or (creator.get("avatar") or creator.get("avatar_url") or "").strip()
        uploads_pl = (((ch.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")) or ""

        video_ids = []
        page_token = ""
        while uploads_pl and len(video_ids) < MAX_VIDEOS_PER_CREATOR:
            remain = MAX_VIDEOS_PER_CREATOR - len(video_ids)
            params = {
                "part": "contentDetails",
                "playlistId": uploads_pl,
                "maxResults": min(50, remain),
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                pl_data = api_get("playlistItems", params)
            except Exception as e:
                print(f"Ошибка чтения плейлиста {ch_title}: {e}")
                break
            for it in pl_data.get("items") or []:
                vid = (((it.get("contentDetails") or {}).get("videoId")) or "").strip()
                if vid and vid not in video_ids:
                    video_ids.append(vid)
            page_token = pl_data.get("nextPageToken") or ""
            if not page_token:
                break

        videos_out = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            try:
                v_data = api_get("videos", {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(batch),
                })
            except Exception as e:
                print(f"Ошибка чтения видео {ch_title}: {e}")
                continue
            for v in v_data.get("items") or []:
                v_snip = v.get("snippet") or {}
                stats = v.get("statistics") or {}
                cd = v.get("contentDetails") or {}
                sec = parse_iso_duration_seconds(cd.get("duration") or "")
                short_flag = is_short_video(v)
                views = int(stats.get("viewCount") or 0)
                likes = int(stats.get("likeCount") or 0)
                vid = v["id"]
                videos_out.append({
                    "id": vid,
                    "title": v_snip.get("title") or "",
                    "type": "shorts" if short_flag else "horizontal",
                    "duration_sec": sec,
                    "published_at": v_snip.get("publishedAt") or "",
                    "views": views,
                    "likes": likes,
                    "url": f"https://www.youtube.com/shorts/{vid}" if short_flag else f"https://www.youtube.com/watch?v={vid}",
                })

        shorts_list = [v for v in videos_out if v["type"] == "shorts"]
        horiz_list = [v for v in videos_out if v["type"] == "horizontal"]

        summary = {
            "name": display_name,
            "channel": ch_title,
            "handle": f"@{handle_clean}" if handle_clean else "",
            "channel_id": cid,
            "channel_url": channel_url,
            "avatar_url": avatar_url,
            "total_videos": len(videos_out),
            "shorts_count": len(shorts_list),
            "horizontal_count": len(horiz_list),
            "total_views": sum(v["views"] for v in videos_out),
            "total_likes": sum(v["likes"] for v in videos_out),
            "shorts_views": sum(v["views"] for v in shorts_list),
            "shorts_likes": sum(v["likes"] for v in shorts_list),
            "horizontal_views": sum(v["views"] for v in horiz_list),
            "horizontal_likes": sum(v["likes"] for v in horiz_list),
        }

        creators_out.append({
            "summary": summary,
            "videos": sorted(videos_out, key=lambda x: x["views"], reverse=True),
        })
        print(f"Готово: {ch_title} | видео: {len(videos_out)} | просмотров: {summary['total_views']}")

    report = {
        "creators": creators_out,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Сохранено авторов: {len(creators_out)} в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
