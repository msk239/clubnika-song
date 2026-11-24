import csv, html, io, json, re, urllib.request

STREAMER_NAME = "nikaclub"
SHEET_ID = "1-ADetubVcKM3FZUtfURoKnuKE4NODFRcPlroKk5dvl8"
SHEET_GID = "0"

def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8-sig", errors="replace")

def norm(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^a-zа-я0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get_ssl_songs():
    try:
        prof = json.loads(fetch_text(f"https://api.streamersonglist.com/v1/streamers/{STREAMER_NAME}"))
        sid = prof["id"]
        songs, cur, size = [], 0, 250
        while True:
            data = json.loads(fetch_text(f"https://api.streamersonglist.com/v1/streamers/{sid}/songs?size={size}&current={cur}"))
            items = data.get("items") or []
            for s in items:
                t = (s.get("title") or "").strip()
                if t:
                    songs.append({"title": t, "artist": (s.get("artist") or "Неизвестный исполнитель").strip(), "timesPlayed": int(s.get("timesPlayed") or 0), "inSsl": True, "inSheet": False})
            cur += 1
            if len(songs) >= int(data.get("total") or len(items)) or not items:
                break
        if songs:
            return songs
    except Exception as e:
        print("SSL API error:", e)
    page = fetch_text(f"https://www.streamersonglist.com/t/{STREAMER_NAME}/songs")
    print("SSL page len:", len(page))
    matches = re.findall(r'\{"id":\d+,"title":"([^"]+)","artist":"([^"]+)"[^}]*\}', page)
    songs = [{"title": html.unescape(t).strip(), "artist": html.unescape(a).strip() or "Неизвестный исполнитель", "timesPlayed": 0, "inSsl": True, "inSheet": False} for t, a in matches if t.strip()]
    if not songs:
        raise RuntimeError("SSL parse failed")
    return songs

def parse_csv_songs(raw):
    if raw.lstrip().startswith("<!DOCTYPE html") or "<html" in raw[:300].lower():
        raise RuntimeError("Sheet returned HTML")
    rows = [r for r in csv.reader(io.StringIO(raw)) if any(c.strip() for c in r)]
    if not rows:
        return []
    start, acol, tcol = 0, -1, -1
    for i, h in enumerate(c.strip().lower() for c in rows[0]):
        if re.search(r"(артист|исполнитель|artist|автор|группа)", h): acol = i
        if re.search(r"(песня|название|трек|title|song|композиция)", h): tcol = i
    if acol != -1 or tcol != -1:
        start = 1
    out = []
    for r in rows[start:]:
        r = [c.strip() for c in r]
        if acol != -1 and tcol != -1:
            a, t = r[acol] if acol < len(r) else "", r[tcol] if tcol < len(r) else ""
        else:
            ne = [c for c in r if c and not re.fullmatch(r"\d+", c)]
            if len(ne) >= 2: a, t = ne[0], ne[1]
            elif len(ne) == 1:
                p = re.split(r"\s+[—–-]\s+", ne[0], maxsplit=1)
                a, t = (p[0], p[1]) if len(p) == 2 else ("Из таблицы", ne[0])
            else: a, t = "", ""
        if t:
            out.append({"title": t, "artist": a or "Из таблицы", "timesPlayed": 0, "inSsl": False, "inSheet": True})
    return out

def get_sheet_songs():
    urls = [
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}",
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={SHEET_GID}",
    ]
    last = None
    for u in urls:
        try:
            s = parse_csv_songs(fetch_text(u))
            print(f"Sheet ok {u}: {len(s)}")
            return s
        except Exception as e:
            last = e
            print("Sheet err:", u, e)
    raise RuntimeError(f"Sheet failed: {last}")

def main():
    merged, ssl_c, sheet_c = {}, 0, 0
    try:
        ssl_s = get_ssl_songs()
        ssl_c = len(ssl_s)
        for s in ssl_s:
            merged[f"{norm(s['artist'])}|{norm(s['title'])}"] = s
    except Exception as e:
        print("SSL final err:", e)
    try:
        sh_s = get_sheet_songs()
        sheet_c = len(sh_s)
        for s in sh_s:
            na, nt = norm(s["artist"]), norm(s["title"])
            k1, k2 = f"{na}|{nt}", f"{nt}|{na}"
            if k1 in merged: merged[k1]["inSheet"] = True
            elif k2 in merged: merged[k2]["inSheet"] = True
            else: merged[k1] = s
    except Exception as e:
        print("Sheet final err:", e)
    payload = {"sslCount": ssl_c, "sheetCount": sheet_c, "totalUnique": len(merged), "songs": list(merged.values())}
    with open("songs.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Done: total={len(merged)}, ssl={ssl_c}, sheet={sheet_c}")

if __name__ == "__main__":
    main()
