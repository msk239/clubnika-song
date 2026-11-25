import json
import os
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

REMIXERS_FILE = "remixers.json"
VIDEOS_FILE = "remix_videos.json"
MAX_VIDEOS_PER_CHANNEL = 30


def run_yt_dlp_json(url: str, flat: bool = False) -> dict | None:
    cmd = [
        "yt-dlp",
        "--ignore-errors",
        "--no-warnings",
        "--skip-download",
        "--dump-single-json",
        "--extractor-args",
        "youtube:player_client=web,mweb",
    ]
    if flat:
        cmd += ["--flat-playlist", "--playlist-end", str(MAX_VIDEOS_PER_CHANNEL)]
    cmd.append(url)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.stderr and "ERROR" in res.stderr:
            err_lines = [ln for ln in res.stderr.splitlines() if "ERROR" in ln][:2]
            print(f"  [stderr] {url}: {' | '.join(err_lines)}")
        out = (res.stdout or "").strip()
        if not out:
            return None
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
    except Exception as e:
        print(f"  [exception] {url}: {e}")
    return None


def fetch_og_meta(url: str) -> tuple[str, str, str]:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        m_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        m_img = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        m_cid = re.search(r'"channelId":"(UC[A-Za-z0-9_-]+)"', html) or re.search(
            r'youtube\.com/channel/(UC[A-Za-z0-9_-]+)', html
        )
        return (
            m_title.group(1).strip() if m_title else "",
            m_img.group(1).strip() if m_img else "",
            m_cid.group(1).strip() if m_cid else "",
        )
    except Exception:
        return ("", "", "")


def fetch_rss_video_ids(channel_id: str) -> list[str]:
    if not channel_id:
        return []
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        ns = {"yt": "http://www.youtube.com/xml/schemas/2015"}
        ids = []
        for el in root.findall(".//yt:videoId", ns):
            if el.text and el.text.strip():
                ids.append(el.text.strip())
        return ids[:MAX_VIDEOS_PER_CHANNEL]
    except Exception as e:
        print(f"  [rss] {channel_id}: {e}")
        return []


def collect_channel_stats(entry: dict) -> dict:
    base_url = (entry.get("url") or "").strip().rstrip("/")
    og_name, og_avatar, channel_id = fetch_og_meta(base_url)

    m_ch = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_-]+)", base_url)
    if m_ch and not channel_id:
        channel_id = m_ch.group(1)

    playlist = run_yt_dlp_json(base_url + "/shorts", flat=True)
    if not playlist or not playlist.get("entries"):
        playlist = run_yt_dlp_json(base_url + "/videos", flat=True)

    name = entry.get("name") or og_name or ""
    avatar = og_avatar or entry.get("avatar") or ""
    handle = entry.get("handle") or ""
    canon_url = base_url

    if playlist:
        name = playlist.get("channel") or playlist.get("uploader") or name
        uploader_id = playlist.get("uploader_id") or ""
        if uploader_id.startswith("@"):
            handle = uploader_id
            canon_url = f"https://www.youtube.com/{handle}"

    video_ids = []
    for item in (playlist or {}).get("entries") or []:
        if isinstance(item, dict) and item.get("id"):
            vid = item["id"]
            if vid not in video_ids:
                video_ids.append(vid)

    if not video_ids and channel_id:
        video_ids = fetch_rss_video_ids(channel_id)

    print(f"Канал {name or base_url}: найдено ID роликов = {len(video_ids)}")

    videos_count = 0
    total_views = 0
    total_likes = 0

    for vid in video_ids[:MAX_VIDEOS_PER_CHANNEL]:
        v_info = run_yt_dlp_json(f"https://www.youtube.com/watch?v={vid}", flat=False)
        videos_count += 1
        if v_info:
            total_views += int(v_info.get("view_count") or 0)
            total_likes += int(v_info.get("like_count") or 0)
        time.sleep(0.15)

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

    output = []
    for entry in entries:
        if not entry.get("url"):
            continue
        row = collect_channel_stats(entry)
        print(f"ИТОГ: {row['name']} | роликов: {row['videos']} | просмотров: {row['views']} | лайков: {row['likes']}")
        output.append(row)

    output.sort(key=lambda x: (x.get("views", 0), x.get("likes", 0), x.get("videos", 0)), reverse=True)
    for idx, row in enumerate(output, start=1):
        row["rank"] = idx

    with open(REMIXERS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
