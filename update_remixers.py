import json
import os
import re
import time
import urllib.parse
import urllib.request

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
if API_KEY in ("", "ТВОЙ_КЛЮЧ", "YOUR_API_KEY"):
    API_KEY = ""

REMIXERS_FILE = "remixers.json"
VIDEOS_FILE = "remix_videos.json"
MAX_VIDEOS_PER_CHANNEL = 100
USE_SEARCH_API = True

# Ключевые фразы и хэштеги для поиска и отбора роликов по песне «Парень удалой»
SONG_KEYWORDS = [
    "парень удалой",
    "пареньудалой",
    "удалой",
]


def api_get(endpoint: str, params: dict) -> dict:
    q_params = dict(params)
    q_params["key"] = API_KEY
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}?{urllib.parse.urlencode(q_params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_video_id(val: str) -> str:
    val = (val or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", val):
        return val
    for p in (
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
    ):
        m = re.search(p, val)
        if m:
            return m.group(1)
    return ""


def matches_song(video: dict) -> bool:
    haystack = " ".join([
        video.get("title") or "",
        video.get("description") or "",
        " ".join(video.get("tags") or []),
    ]).lower()
    return any(kw.lower() in haystack for kw in SONG_KEYWORDS)


def resolve_channel_id(entry: dict) -> str:
    url = (entry.get("url") or "").strip()
    m_ch = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_-]+)", url)
    if m_ch:
        return m_ch.group(1)

    handle = (entry.get("handle") or "").strip()
    if not handle:
        m_h = re.search(r"youtube\.com/(@[^/?#]+)", url)
        if m_h:
            handle = m_h.group(1)

    if handle:
        data = api_get("channels", {"part": "id", "forHandle": handle.lstrip("@")})
        items = data.get("items") or []
        if items:
            return items[0]["id"]

    return ""


def get_channels_meta(channel_ids: list[str]) -> dict[str, dict]:
    result = {}
    for i in range(0, len(channel_ids), 50):
        batch = [c for c in channel_ids[i:i + 50] if c]
        if not batch:
            continue
        data = api_get("channels", {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(batch),
        })
        for item in data.get("items") or []:
            cid = item["id"]
            snip = item.get("snippet") or {}
            thumbs = snip.get("thumbnails") or {}
            avatar = (
                (thumbs.get("high") or {}).get("url")
                or (thumbs.get("medium") or {}).get("url")
                or (thumbs.get("default") or {}).get("url")
                or ""
            )
            custom_url = snip.get("customUrl") or ""
            handle = custom_url if custom_url.startswith("@") else (f"@{custom_url}" if custom_url else "")
            uploads_pl = (
                ((item.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
                or ""
            )
            result[cid] = {
                "name": snip.get("title") or cid,
                "handle": handle,
                "url": f"https://www.youtube.com/{handle}" if handle else f"https://www.youtube.com/channel/{cid}",
                "avatar": avatar,
                "uploads_playlist": uploads_pl,
            }
    return result


def get_uploads_video_ids(playlist_id: str, max_items: int = MAX_VIDEOS_PER_CHANNEL) -> list[str]:
    if not playlist_id:
        return []
    ids = []
    page_token = ""
    while len(ids) < max_items:
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_items - len(ids)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = api_get("playlistItems", params)
        for it in data.get("items") or []:
            vid = (((it.get("contentDetails") or {}).get("videoId")) or "").strip()
            if vid and vid not in ids:
                ids.append(vid)
        page_token = data.get("nextPageToken") or ""
        if not page_token:
            break
    return ids


def search_song_video_ids_for_channels(target_cids: set[str], max_pages_per_query: int = 2) -> list[str]:
    found_ids = []
    queries = []
    for kw in SONG_KEYWORDS:
        q = f"#{kw.replace(' ', '')}" if " " not in kw else f'"{kw}"'
        if q not in queries:
            queries.append(q)

    for q in queries:
        page_token = ""
        for _ in range(max_pages_per_query):
            params = {
                "part": "snippet",
                "type": "video",
                "q": q,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            data = api_get("search", params)
            for item in data.get("items") or []:
                snip = item.get("snippet") or {}
                cid = (snip.get("channelId") or "").strip()
                vid = (((item.get("id") or {}).get("videoId")) or "").strip()
                if cid in target_cids and vid and vid not in found_ids:
                    found_ids.append(vid)
            page_token = data.get("nextPageToken") or ""
            if not page_token:
                break
        time.sleep(0.1)
    return found_ids


def get_videos_details(video_ids: list[str]) -> list[dict]:
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = [v for v in video_ids[i:i + 50] if v]
        if not batch:
            continue
        data = api_get("videos", {
            "part": "snippet,statistics",
            "id": ",".join(batch),
        })
        for item in data.get("items") or []:
            snip = item.get("snippet") or {}
            stats = item.get("statistics") or {}
            videos.append({
                "id": item["id"],
                "channelId": snip.get("channelId") or "",
                "title": snip.get("title") or "",
                "description": snip.get("description") or "",
                "tags": snip.get("tags") or [],
                "views": int(stats.get("viewCount") or 0),
                "likes": int(stats.get("likeCount") or 0),
            })
    return videos


def main():
    with open(REMIXERS_FILE, "r", encoding="utf-8") as f:
        entries = json.load(f)

    if not API_KEY:
        print("ВНИМАНИЕ: YOUTUBE_API_KEY не задан.")
        return

    cid_to_entries = {}
    for entry in entries:
        try:
            cid = resolve_channel_id(entry)
            if cid:
                cid_to_entries.setdefault(cid, []).append(entry)
            else:
                print(f"Не удалось определить channelId для: {entry.get('url')}")
        except Exception as e:
            print(f"Ошибка при определении канала {entry.get('url')}: {e}")

    meta_map = get_channels_meta(list(cid_to_entries.keys()))
    stats_by_cid = {cid: {"videos": 0, "views": 0, "likes": 0} for cid in cid_to_entries}

    explicit_ids = []
    if os.path.exists(VIDEOS_FILE):
        with open(VIDEOS_FILE, "r", encoding="utf-8") as f:
            raw_vids = json.load(f)
        for v in raw_vids:
            vid = extract_video_id(v.get("url") if isinstance(v, dict) else str(v))
            if vid and vid not in explicit_ids:
                explicit_ids.append(vid)

    if explicit_ids:
        v_details = get_videos_details(explicit_ids)
        for v in v_details:
            cid = v["channelId"]
            if cid not in stats_by_cid:
                continue
            stats_by_cid[cid]["videos"] += 1
            stats_by_cid[cid]["views"] += v["views"]
            stats_by_cid[cid]["likes"] += v["likes"]
    else:
        matched_by_cid = {cid: {} for cid in cid_to_entries}

        for cid, meta in meta_map.items():
            try:
                v_ids = get_uploads_video_ids(meta.get("uploads_playlist", ""), MAX_VIDEOS_PER_CHANNEL)
                v_details = get_videos_details(v_ids)
                for v in v_details:
                    if matches_song(v):
                        matched_by_cid[cid][v["id"]] = v
                time.sleep(0.1)
            except Exception as e:
                print(f"Ошибка при сборе статистики канала {cid}: {e}")

        if USE_SEARCH_API and cid_to_entries:
            try:
                search_vids = search_song_video_ids_for_channels(set(cid_to_entries.keys()))
                missing_ids = [
                    vid for vid in search_vids
                    if all(vid not in m_dict for m_dict in matched_by_cid.values())
                ]
                if missing_ids:
                    extra_details = get_videos_details(missing_ids)
                    for v in extra_details:
                        cid = v.get("channelId") or ""
                        if cid in matched_by_cid and matches_song(v):
                            matched_by_cid[cid][v["id"]] = v
            except Exception as e:
                print(f"Ошибка при поиске через YouTube Search API: {e}")

        for cid, v_map in matched_by_cid.items():
            matched_list = list(v_map.values())
            stats_by_cid[cid] = {
                "videos": len(matched_list),
                "views": sum(v["views"] for v in matched_list),
                "likes": sum(v["likes"] for v in matched_list),
            }
            cname = (meta_map.get(cid) or {}).get("name") or cid
            print(
                f"OK: {cname} | треков «Парень удалой»: {len(matched_list)} "
                f"| просмотров: {stats_by_cid[cid]['views']} | лайков: {stats_by_cid[cid]['likes']}"
            )

    output = []
    for cid, e_list in cid_to_entries.items():
        first = e_list[0] if e_list else {}
        meta = meta_map.get(cid, {})
        st = stats_by_cid.get(cid, {"videos": 0, "views": 0, "likes": 0})
        output.append({
            "name": meta.get("name") or first.get("name") or cid,
            "handle": meta.get("handle") or first.get("handle") or "",
            "url": meta.get("url") or first.get("url") or f"https://www.youtube.com/channel/{cid}",
            "platform": "YouTube",
            "channels": max(1, len(e_list)),
            "videos": st["videos"],
            "views": st["views"],
            "likes": st["likes"],
            "avatar": meta.get("avatar") or first.get("avatar") or "",
        })

    output.sort(key=lambda x: (x["views"], x["likes"], x["videos"]), reverse=True)
    for idx, row in enumerate(output, start=1):
        row["rank"] = idx

    with open(REMIXERS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Готово! Обновлено авторов: {len(output)}")


if __name__ == "__main__":
    main()
