import csv
import html
import io
import json
import re
import urllib.request

STREAMER_NAME = "nikaclub"
SHEET_ID = "1-ADetubVcKM3FZUtfURoKnuKE4NODFRcPlroKk5dvl8"
SHEET_GID = "0"


def fetch_text(url: str, extra_headers=None) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, text/html, */*",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^a-zа-я0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def get_ssl_songs():
    # 1. Пробуем API v1
    try:
        profile = json.loads(fetch_text(f"https://api.streamersonglist.com/v1/streamers/{STREAMER_NAME}"))
        streamer_id = profile["id"]
        songs = []
        current = 0
        size = 250
        while True:
            data = json.loads(
                fetch_text(
                    f"https://api.streamersonglist.com/v1/streamers/{streamer_id}/songs?size={size}&current={current}"
                )
            )
            items = data.get("items") or []
            for s in items:
                title = (s.get("title") or "").strip()
                if title:
                    songs.append(
                        {
                            "title": title,
                            "artist": (s.get("artist") or "Неизвестный исполнитель").strip(),
                            "timesPlayed": int(s.get("timesPlayed") or 0),
                            "inSsl": True,
                            "inSheet": False,
                        }
                    )
            total = int(data.get("total") or len(items))
            current += 1
            if len(songs) >= total or not items:
                break
        if songs:
            return songs
    except Exception as e:
        print("SSL API error:", e)

    # 2. Запасной вариант: пробуем достать JSON или строки с публичной страницы
    page_html = fetch_text(f"https://www.streamersonglist.com/t/{STREAMER_NAME}/songs")
    print("SSL page length:", len(page_html))

    # Ищем встроенные JSON-объекты с "title" и "artist"
    matches = re.findall(r'\{"id":\d+,"title":"([^"]+)","artist":"([^"]+)"[^}]*\}', page_html)
    songs = []
    for title_raw, artist_raw in matches:
        title = html.unescape(title_raw).strip()
        artist = html.unescape(artist_raw).strip()
        if title:
            songs.append(
                {
                    "title": title,
                    "artist": artist or "Неизвестный исполнитель",
                    "timesPlayed": 0,
                    "inSsl": True,
                    "inSheet": False,
                }
            )
    if not songs:
        raise RuntimeError("Не удалось получить песни со StreamerSongList (возможно, API требует токен или данные грузятся динамически)")
    return songs


def parse_sheet_csv(raw_csv: str):
    if raw_csv.lstrip().startswith("<!DOCTYPE html") or "<html" in raw_csv[:300].lower():
        raise RuntimeError("Таблица вернула HTML вместо CSV (проверьте доступ по ссылке)")

    reader = csv.reader(io.StringIO(raw_csv))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []

    start_idx = 0
    artist_col = -1
    title_col = -1
    header = [c.strip().lower() for c in rows[0]]
    for idx, h in enumerate(header):
        if re.search(r"(артист|исполнитель|artist|автор|группа)", h):
            artist_col = idx
        if re.search(r"(песня|название|трек|title|song|композиция)", h):
            title_col = idx

    if artist_col != -1 or title_col != -1:
        start_idx = 1

    songs = []
    for r in rows[start_idx:]:
        r = [c.strip() for c in r]
        artist = ""
        title = ""
        if artist_col != -1 and title_col != -1:
            artist = r[artist_col] if artist_col < len(r) else ""
            title = r[title_col] if title_col < len(r) else ""
        else:
            non_empty = [c for c in r if c and not re.fullmatch(r"\d+", c)]
            if len(non_empty) >= 2:
                artist, title = non_empty[0], non_empty[1]
            elif len(non_empty) == 1:
                parts = re.split(r"\s+[—–-]\s+", non_empty[0], maxsplit=1)
                if len(parts) == 2:
                    artist, title = parts[0], parts[1]
                else:
                    title, artist = non_empty[0], "Из таблицы"

        if title:
            songs.append(
                {
                    "title": title,
                    "artist": artist or "Из таблицы",
                    "timesPlayed": 0,
                    "inSsl": False,
                    "inSheet": True,
                }
            )
    return songs


def get_sheet_songs():
    urls = [
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}",
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={SHEET_GID}",
    ]
    last_err = None
    for u in urls:
        try:
            raw = fetch_text(u)
            songs = parse_sheet_csv(raw)
            print(f"Sheet loaded from {u}: {len(songs)} rows")
            return songs
        except Exception as e:
            last_err = e
            print("Sheet attempt error:", u, "->", e)
    raise RuntimeError(f"Не удалось загрузить Google Таблицу: {last_err}")


def main():
    merged = {}
    ssl_count = 0
    sheet_count = 0

    try:
        ssl_songs = get_ssl_songs()
        ssl_count = len(ssl_songs)
        for s in ssl_songs:
            key = f"{norm(s['artist'])}|{norm(s['title'])}"
            merged[key] = s
    except Exception as e:
        print("SSL final error:", e)

    try:
        sheet_songs = get_sheet_songs()
        sheet_count = len(sheet_songs)
        for s in sheet_songs:
            na = norm(s["artist"])
            nt = norm(s["title"])
            k1 = f"{na}|{nt}"
            k2 = f"{nt}|{na}"
            if k1 in merged:
                merged[k1]["inSheet"] = True
            elif k2 in merged:
                merged[k2]["inSheet"] = True
            else:
                merged[k1] = s
    except Exception as e:
        print("Sheet final error:", e)

    payload = {
        "sslCount": ssl_count,
        "sheetCount": sheet_count,
        "totalUnique": len(merged),
        "songs": list(merged.values()),
    }

    with open("songs.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Saved songs.json: total={len(merged)}, ssl={ssl_count}, sheet={sheet_count}")


if __name__ == "__main__":
    main()
