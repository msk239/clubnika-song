import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
if API_KEY in ("", "ТВОЙ_КЛЮЧ", "YOUR_API_KEY"):
    API_KEY = ""

REMIXERS_FILE = "remixers.json"
VIDEOS_FILE = "remix_videos.json"

SSL_CTX = ssl.create_default_context()


def http_get(url: str, retries: int = 3) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25, context=SSL_CTX) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(1.2 * (attempt + 1))
    raise last_err


def fetch_json(url: str) -> dict:
    return json.loads(http_get(url))


def extract_yt_initial_data(html: str) -> dict:
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
    if not m:
        m = re.search(r"ytInitialData\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def parse_human_number(text: str) -> int:
    if not text:
        return 0
    s = str(text).lower().replace("\xa0", " ").replace(",", ".").strip()
    m = re.search(r"([\d.]+)\s*(тыс|k|млн|m|млрд|b)?", s)
    if not m:
        digits = re.sub(r"\D", "", s)
        return int(digits) if digits else 0
    num = float(m.group(1))
    unit = m.group(2) or ""
    if unit in ("тыс", "k"):
        num *= 1_000
    elif unit in ("млн", "m"):
        num *= 1_000_000
    elif unit in ("млрд", "b"):
        num *= 1_000_000_000
    return int(round(num))


def walk_dict(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk_dict(v)
    elif isinstance(node, list):
        for it in node:
            yield from walk_dict(it)


def scrape_channel_no_api(url: str) -> dict:
    clean_url = url.rstrip("/")
    html = http_get(clean_url + "/shorts")
    data = extract_yt_initial_data(html)
    if not data:
        html = http_get(clean_url)
        data = extract_yt_initial_data(html)

    name = ""
    avatar = ""
    handle = ""

    m_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if m_title:
        name = m_title.group(1).strip()

    m_img = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if m_img:
        avatar = m_img.group(1).strip()

    m_can = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    canonical = m_can.group(1).strip() if m_can else clean_url
    m_h = re.search(r"youtube\.com/(@[^/?#]+)", canonical) or re.search(r"youtube\.com/(@[^/?#]+)", clean_url)
    if m_h:
        handle = m_h.group(1)

    # Собираем уникальные ролики со страницы /shorts или /videos
    seen_ids = set()
    videos_count = 0
    total_views = 0

    for obj in walk_dict(data):
        # Карточки Shorts (reelItemRenderer / shortsLockupViewModel)
        if "reelItemRenderer" in obj:
            r = obj["reelItemRenderer"]
            vid = r.get("videoId")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                videos_count += 1
                v_txt = ((r.get("viewCountText") or {}).get("simpleText")
                         or ((r.get("accessibility") or {}).get("accessibilityData") or {}).get("label", ""))
                total_views += parse_human_number(v_txt)
        elif "shortsLockupViewModel" in obj:
            s = obj["shortsLockupViewModel"]
            on_tap = (((s.get("onTap") or {}).get("innertubeCommand") or {}).get("reelWatchEndpoint") or {})
            vid = on_tap.get("videoId")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                videos_count += 1
                v_txt = ((s.get("overlayMetadata") or {}).get("secondaryText") or {}).get("content", "")
                total_views += parse_human_number(v_txt)
        elif "videoRenderer" in obj:
            v = obj["videoRenderer"]
            vid = v.get("videoId")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                videos_count += 1
                v_txt = ((v.get("viewCountText") or {}).get("simpleText") or "")
                total_views += parse_human_number(v_txt)

    return {
        "name": name or handle or canonical.split("/")[-1],
        "handle": handle,
        "url": canonical or clean_url,
        "avatar": avatar,
        "videos": videos_count,
        "views": total_views,
        "likes": 0,
    }


def main():
    with open(REMIXERS_FILE, "r", encoding="utf-8") as f:
        entries = json.load(f)

    output = []
    for entry in entries:
        url = (entry.get("url") or "").strip()
        if not url:
            continue
        try:
            info = scrape_channel_no_api(url)
            print(f"OK: {info['name']} | роликов: {info['videos']} | просмотров: {info['views']}")
            output.append({
                "name": info["name"] or entry.get("name") or url,
                "handle": info["handle"] or entry.get("handle") or "",
                "url": info["url"] or url,
                "platform": "YouTube",
                "channels": entry.get("channels") or 1,
                "videos": info["videos"],
                "views": info["views"],
                "likes": info["likes"],
                "avatar": info["avatar"] or entry.get("avatar") or "",
            })
        except Exception as e:
            print(f"Ошибка для {url}: {e}")
            output.append(entry)

    output.sort(key=lambda x: (x.get("views", 0), x.get("likes", 0), x.get("videos", 0)), reverse=True)
    for idx, row in enumerate(output, start=1):
        row["rank"] = idx

    with open(REMIXERS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Готово! Обновлено авторов: {len(output)}")


if __name__ == "__main__":
    main()
