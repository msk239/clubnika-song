import json
import os
import re
import urllib.parse
import urllib.request

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
if API_KEY in ("", "ТВОЙ_КЛЮЧ", "YOUR_API_KEY"):
    API_KEY = ""

CHANNEL_HANDLE = "msk239"
OUTPUT_FILE = "channel_analytics.json"
SHORTS_MAX_SECONDS = 180


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


def main():
    if not API_KEY:
        print("ВНИМАНИЕ: YOUTUBE_API_KEY не задан.")
        return

    handle_clean = CHANNEL_HANDLE.lstrip("@")
    ch_data = api_get("channels", {
        "part": "snippet,statistics,contentDetails",
        "forHandle": handle_clean,
    })
    items = ch_data.get("items") or []
    if not items:
        print(f"Канал @{handle_clean} не найден.")
        return

    ch = items[0]
    cid = ch["id"]
    snip = ch.get("snippet") or {}
    ch_title = (snip.get("title") or "").strip() or cid
    custom_url = (snip.get("customUrl") or "").strip()
    if custom_url:
        channel_url = f"https://www.youtube.com/{custom_url.lstrip('/')}"
    else:
        channel_url = f"https://www.youtube.com/@{handle_clean}"
    avatar_url = extract_avatar_url(snip)
    uploads_pl = (((ch.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")) or ""

    video_ids = []
    page_token = ""
    while True:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_pl,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        pl_data = api_get("playlistItems", params)
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
        v_data = api_get("videos", {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(batch),
        })
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
        "channel": ch_title,
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

    report = {
        "summary": summary,
        "videos": sorted(videos_out, key=lambda x: x["views"], reverse=True),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Канал: {ch_title} ({channel_url})")
    print(f"Всего видео: {summary['total_videos']} | Shorts: {summary['shorts_count']} | Горизонтальных: {summary['horizontal_count']}")
    print(f"Всего просмотров: {summary['total_views']} | Всего лайков: {summary['total_likes']}")
    print(f"Shorts — просмотров: {summary['shorts_views']} | лайков: {summary['shorts_likes']}")
    print(f"Горизонтальные — просмотров: {summary['horizontal_views']} | лайков: {summary['horizontal_likes']}")
    print(f"Отчёт сохранён в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
