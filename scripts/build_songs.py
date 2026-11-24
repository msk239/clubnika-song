import csv, html, io, json, re, unicodedata, urllib.request

SSL_URL = "https://streamersonglist.com/t/nikaclub/songs"
SHEET_ID = "1-ADetubVcKM3FZUtfURoKnuKE4NODFRcPlroKk5dvl8"
SHEET_GID = "0"


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/csv,text/plain,application/json,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8-sig", errors="replace")


def clean_label(s: str) -> str:
    s = html.unescape(s or "").strip()
    s = re.sub(r"^\s*NEW\s+", "", s, flags=re.I)
    s = re.sub(r"\s+NEW\s*$", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def strip_diacritics(s: str) -> str:
    # Убираем диакритику (č -> c, š -> s и т.д.), сохраняя кириллицу и ё/е
    normed = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in normed if not unicodedata.combining(ch))


def norm(s: str) -> str:
    s = clean_label(s).lower().replace("ё", "е")
    s = strip_diacritics(s)
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^a-zа-я0-9]", "", s)
    return s.strip()


def norm_artist_core(s: str) -> str:
    # Убираем "feat." / "ft." / "и " и лишние хвосты для более мягкого сравнения артиста
    s = norm(s)
    s = re.split(r"(?:feat|ft|prod|remix)", s)[0]
    return s.strip()


def read_dom_table_rows(page):
    return page.evaluate("""() => {
        const rows = [];
        const trs = document.querySelectorAll('table tbody tr');
        for (const tr of trs) {
            const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
            if (cells.length >= 2) {
                const link = tr.querySelector('a[href*="/songs/"]');
                const title = (link ? link.innerText : cells[0] || '').trim();
                let artist = (cells[1] || '').trim();
                if (link && artist.startsWith(title)) {
                    artist = artist.slice(title.length).trim();
                }
                const lastCell = cells[cells.length - 1] || '0';
                const playsMatch = lastCell.match(/\\d+/);
                const plays = playsMatch ? parseInt(playsMatch[0], 10) : 0;
                if (title) rows.push({ title, artist: artist || 'Неизвестный исполнитель', timesPlayed: plays });
            } else {
                const link = tr.querySelector ? tr.querySelector('a[href*="/songs/"]') : null;
                if (link) {
                    const title = (link.innerText || '').trim();
                    const fullText = (tr.innerText || '').trim().split('\\n').map(x => x.trim()).filter(Boolean);
                    const artist = fullText.find(x => x !== title && !/заказать/i.test(x)) || 'Неизвестный исполнитель';
                    if (title) rows.push({ title, artist, timesPlayed: 0 });
                }
            }
        }
        if (!rows.length) {
            for (const link of document.querySelectorAll('a[href*="/songs/"]')) {
                const title = (link.innerText || '').trim();
                const parent = link.closest('tr, li, div[class*="row"], div[class*="item"]') || link.parentElement;
                const lines = (parent ? parent.innerText : '').split('\\n').map(x => x.trim()).filter(Boolean);
                const artist = lines.find(x => x !== title && !/заказать/i.test(x)) || 'Неизвестный исполнитель';
                if (title) rows.push({ title, artist, timesPlayed: 0 });
            }
        }
        return rows;
    }""")


def get_ssl_songs():
    from playwright.sync_api import sync_playwright

    all_dom_rows = []
    max_seen = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto(SSL_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        stall_rounds = 0
        for _ in range(100):
            rows = read_dom_table_rows(page)
            all_dom_rows.extend(rows)
            cur_count = len(rows)

            if cur_count > max_seen:
                max_seen = cur_count
                stall_rounds = 0
            else:
                stall_rounds += 1

            if stall_rounds >= 4:
                break

            page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/songs/"]');
                const last = links.length ? links[links.length - 1] : null;
                if (last) last.scrollIntoView({ behavior: 'instant', block: 'end' });
                window.scrollTo(0, document.documentElement.scrollHeight);
                for (const el of document.querySelectorAll('*')) {
                    if (el.scrollHeight > el.clientHeight + 20) {
                        el.scrollTop = el.scrollHeight;
                    }
                }
            }""")

            grew = False
            for _ in range(9):
                page.wait_for_timeout(500)
                after_count = page.evaluate("() => document.querySelectorAll('a[href*=\"/songs/\"]').length")
                if after_count > cur_count:
                    grew = True
                    break

            if not grew and cur_count == max_seen:
                continue

        browser.close()

    merged_ssl = {}
    for r in all_dom_rows:
        t = clean_label(r["title"])
        a = clean_label(r["artist"]) or "Неизвестный исполнитель"
        if not t:
            continue
        key = f"{norm(a)}|{norm(t)}"
        if key not in merged_ssl:
            merged_ssl[key] = {
                "title": t,
                "artist": a,
                "timesPlayed": r["timesPlayed"],
                "inSsl": True,
                "inSheet": False,
            }
        elif r["timesPlayed"] > merged_ssl[key].get("timesPlayed", 0):
            merged_ssl[key]["timesPlayed"] = r["timesPlayed"]

    songs = list(merged_ssl.values())
    print(f"SSL loaded: max_dom_rows={max_seen}, unique={len(songs)}")
    if not songs:
        raise RuntimeError("SSL songs list is empty after page render")
    return songs


def parse_csv_songs(raw: str):
    if raw.lstrip().startswith("<!DOCTYPE html") or "<html" in raw[:300].lower():
        raise RuntimeError("Sheet returned HTML")
    rows = [r for r in csv.reader(io.StringIO(raw)) if any(c.strip() for c in r)]
    if not rows:
        return []
    start, acol, tcol = 0, -1, -1
    for i, h in enumerate(c.strip().lower() for c in rows[0]):
        if re.search(r"(артист|исполнитель|artist|автор|группа)", h):
            acol = i
        if re.search(r"(песня|название|трек|title|song|композиция)", h):
            tcol = i
    if acol != -1 or tcol != -1:
        start = 1
    out = []
    for r in rows[start:]:
        r = [clean_label(c) for c in r]
        if acol != -1 and tcol != -1:
            a = r[acol] if acol < len(r) else ""
            t = r[tcol] if tcol < len(r) else ""
        else:
            ne = [c for c in r if c and not re.fullmatch(r"\d+", c)]
            if len(ne) >= 2:
                a, t = ne[0], ne[1]
            elif len(ne) == 1:
                p = re.split(r"\s+[—–-]\s+", ne[0], maxsplit=1)
                a, t = (p[0], p[1]) if len(p) == 2 else ("Из таблицы", ne[0])
            else:
                a, t = "", ""
        if t:
            out.append({
                "title": t,
                "artist": a or "Из таблицы",
                "timesPlayed": 0,
                "inSsl": False,
                "inSheet": True,
            })
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


def similar_enough(a: str, b: str) -> bool:
    if not a or not b or a == b:
        return a == b
    if min(len(a), len(b)) >= 5 and (a in b or b in a):
        return True
    # Проверка на 1-2 отличия для коротких/опечаточных строк (например cru vs cry)
    if abs(len(a) - len(b)) <= 2 and max(len(a), len(b)) >= 6:
        diffs = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
        return diffs <= 2
    return False


def main():
    merged = {}
    by_title = {}
    ssl_c = 0
    sheet_c = 0

    try:
        ssl_s = get_ssl_songs()
        ssl_c = len(ssl_s)
        for s in ssl_s:
            na, nt = norm(s["artist"]), norm(s["title"])
            key = f"{na}|{nt}"
            merged[key] = s
            if nt:
                by_title.setdefault(nt, []).append(key)
    except Exception as e:
        print("SSL final err:", e)

    try:
        sh_s = get_sheet_songs()
        sheet_c = len(sh_s)
        for s in sh_s:
            na, nt = norm(s["artist"]), norm(s["title"])
            ac = norm_artist_core(s["artist"])
            k1, k2 = f"{na}|{nt}", f"{nt}|{na}"

            matched_keys = []
            if k1 in merged:
                matched_keys.append(k1)
            elif k2 in merged:
                matched_keys.append(k2)
            elif nt in by_title:
                matched_keys.extend(by_title[nt])
            else:
                # Ищем среди существующих записей совпадение по артисту и близкое название
                for mk, existing in merged.items():
                    ea_core = norm_artist_core(existing["artist"])
                    et = norm(existing["title"])
                    if ac and ea_core and ac == ea_core and similar_enough(nt, et):
                        matched_keys.append(mk)

            if matched_keys:
                for mk in matched_keys:
                    merged[mk]["inSheet"] = True
            else:
                merged[k1] = s
    except Exception as e:
        print("Sheet final err:", e)

    payload = {
        "sslCount": ssl_c,
        "sheetCount": sheet_c,
        "totalUnique": len(merged),
        "songs": list(merged.values()),
    }
    with open("songs.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Done: total={len(merged)}, ssl={ssl_c}, sheet={sheet_c}")


if __name__ == "__main__":
    main()
