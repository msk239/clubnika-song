import json
import os
import re
import subprocess
import time
import urllib.request

REMIXERS_FILE = "remixers.json"
VIDEOS_FILE = "remix_videos.json"  # необязательный список конкретных URL/ID ремиксов
MAX_VIDEOS_PER_CHANNEL = 60


def run_yt_dlp_json(url: str, flat: bool = False) -> dict | None:
    cmd = [
        "yt-dlp",
        "--ignore-errors",
        "--no-warnings",
        "--skip-download",
        "--dump-single-json",
    ]
    if flat:
        cmd += ["--flat-playlist", "--playlist-end", str(MAX_VIDEOS_PER_CHANNEL)]
    cmd.append(url)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        out = (res.stdout or "").strip()
        if not out:
            return None
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
    except Exception as e:
        print(f"yt-dlp error for {url}: {e}")
    return None


def fetch_og_meta(url: str) -> tuple[str, str]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        m_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        m_img = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        return (m_title.group(1).strip() if m_title else "", m_img.group(1).strip() if m_img else "")
    except Exception:
        return ("", "")


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


def collect_channel_stats(entry: dict) -> dict:
    base_url = (entry.get("url") or "").strip().rstrip("/")
    shorts_url = base_url + "/shorts"

    playlist = run_yt_dlp_json(shorts_url, flat=True)
    if not playlist or not playlist.get("entries"):
        playlist = run_yt_dlp_json(base_url, flat=True)

    name = entry.get("name") or ""
    avatar = entry.get("avatar") or ""
    handle = entry.get("handle") or ""
    canon_url = base_url

    if playlist:
        name = playlist.get("channel") or playlist.get("uploader") or playlist.get("title") or name
        uploader_id = playlist.get("uploader_id") or ""
        if uploader_id.startswith("@"):
            handle = uploader_id
            canon_url = f"https://www.youtube.com/{handle}"

    og_name, og_avatar = fetch_og_meta(base_url)
    if og_name and (not name or name.endswith(" - Shorts")):
        name = og_name
    if og_avatar:
        avatar = og_avatar

    entries_list = (playlist or {}).get("entries") or []
    videos_count = 0
    total_views = 0
    total_likes = 0

    for item in entries_list:
        if not isinstance(item, dict):
            continue
        vid = item.get("id") or ""
        if not vid:
            continue

        # Получаем детальную статистику ролика (просмотры + лайки)
        v_url = f"https://www.youtube.com/shorts/{vid}"
        v_info = run_yt_dlp_json(v_url, flat=False)
        videos_count += 1
        if v_info:
            total_views += int(v_info.get("view_count") or item.get("view_count") or 0)
            total_likes += int(v_info.get("like_count") or 0)
        else:
            total_views += int(item.get("view_count") or 0)
        time.sleep(0.2)

    return {
        "name": name or handle or base_url.split("/")[-1],
        "handle": handle,
        "url": canon_url,
        "platform": "YouTube",
        "channels": entry.get("channels") or 1,
        "videos": videos_count,
        "views": total_views,
        "likes": total_likes,
        "avatar": avatar,
    }


def main():
    with open(REMIXERS_FILE, "r", encoding="utf-8") as f:
        entries = json.load(f)

    # Если задан remix_videos.json, считаем строго по указанным роликам
    explicit_ids = []
    if os.path.exists(VIDEOS_FILE):
        with open(VIDEOS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for x in raw:
            vid = extract_video_id(x.get("url") if isinstance(x, dict) else str(x))
            if vid and vid not in explicit_ids:
                explicit_ids.append(vid)

    if explicit_ids:
        by_channel = {}
        for vid in explicit_ids:
            v_info = run_yt_dlp_json(f"https://www.youtube.com/shorts/{vid}", flat=False)
            if not v_info:
                continue
            ch_url = v_info.get("channel_url") or v_info.get("uploader_url") or ""
            ch_name = v_info.get("channel") or v_info.get("uploader") or "Автор"
            uploader_id = v_info.get("uploader_id") or ""
            handle = uploader_id if uploader_id.startswith("@") else ""
            key = ch_url or ch_name
            st = by_channel.setdefault(
                key,
                {
                    "name": ch_name,
                    "handle": handle,
                    "url": ch_url or f"https://www.youtube.com/{handle}",
                    "platform": "YouTube",
                    "channels": 1,
                    "videos": 0,
                    "views": 0,
                    "likes": 0,
                    "avatar": "",
                },
            )
            st["videos"] += 1
            st["views"] += int(v_info.get("view_count") or 0)
            st["likes"] += int(v_info.get("like_count") or 0)
            if not st["avatar"] and st["url"]:
                _, av = fetch_og_meta(st["url"])
                st["avatar"] = av
        output = list(by_channel.values())
    else:
        output = []
        for entry in entries:
            if not entry.get("url"):
                continue
            row = collect_channel_stats(entry)
            print(f"OK: {row['name']} | роликов: {row['videos']} | просмотров: {row['views']} | лайков: {row['likes']}")
            output.append(row)

    output.sort(key=lambda x: (x.get("views", 0), x.get("likes", 0), x.get("videos", 0)), reverse=True)
    for idx, row in enumerate(output, start=1):
        row["rank"] = idx

    with open(REMIXERS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Готово! Обновлено авторов: {len(output)}")


if __name__ == "__main__":
    main()
