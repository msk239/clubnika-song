import csv, html, io, json, re, urllib.request

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


def norm(s: str) -> str:
    s = clean_label(s).lower().replace("ё", "е")
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^a-zа-я0-9]", "", s)
    return s.strip()


def extract_songs_from_json_obj(obj, out: list):
    if isinstance(obj, dict):
        title = obj.get("title") or obj.get("songTitle")
        artist = obj.get("artist") or obj.get("artistName")
        if isinstance(title, str) and title.strip() and isinstance(artist, str) and artist.strip():
            plays = obj.get("timesPlayed") or obj.get("plays") or 0
            try:
                plays_int = int(plays)
            except Exception:
                plays_int = 0
            out.append({
                "title": clean_label(title),
                "artist": clean_label(artist),
                "timesPlayed": plays_int,
                "inSsl": True,
                "inSheet": False,
            })
        for v in obj.values():
            extract_songs_from_json_obj(v, out)
    elif isinstance(obj, list):
        for item in obj:
            extract_songs_from_json_obj(item, out)


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
            }
        }
        return rows;
    }""")


def get_ssl_songs():
    from playwright.sync_api import sync_playwright

    captured = []
    all_dom_rows = []
    api_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        def handle_response(resp):
            url = resp.url
            ctype = (resp.headers.get("content-type") or "").lower()
            if "streamersonglist" in url and ("api" in url or "json" in ctype or "song" in url.lower()):
                if len(api_urls) < 15 and url not in api_urls:
                    api_urls.append(url)
            if "json" in ctype or "song" in url.lower():
                try:
                    data = resp.json()
                    extract_songs_from_json_obj(data, captured)
                except Exception:
                    pass

        page.on("response", handle_response)
        page.goto(SSL_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)

        # Прокручиваем вниз, чтобы прогрузился футер и пагинация
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)

        # Собираем подсказки о кнопках пагинации внизу страницы
        pag_hints = page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('button, a, [role="button"]'));
            return els
              .map(el => ({
                tag: el.tagName.toLowerCase(),
                text: (el.innerText || '').trim().slice(0, 30),
                aria: el.getAttribute('aria-label') || '',
                cls: (el.className || '').toString().slice(0, 60)
              }))
              .filter(x => /next|prev|page|pagin|›|»|chevron|right|2/i.test(x.text + ' ' + x.aria + ' ' + x.cls))
              .slice(0, 20);
        }""")
        print("SSL api_urls:", api_urls)
        print("SSL pagination hints:", pag_hints)

        seen_pages = set()
        for page_num in range(1, 25):
            rows = read_dom_table_rows(page)
            sig = tuple((r["title"], r["artist"]) for r in rows[:5])
            all_dom_rows.extend(rows)

            if sig in seen_pages and page_num > 1:
                break
            seen_pages.add(sig)

            # Пробуем найти кнопку следующей страницы по aria-label или тексту
            clicked = False
            candidates = page.locator(
                'button[aria-label*="next" i], a[aria-label*="next" i], button[aria-label*="Next" i], a[aria-label*="Next" i], button:has-text("›"), a:has-text("›"), button:has-text("»"), a:has-text("»")'
            )
            for idx in range(candidates.count()):
                btn = candidates.nth(idx)
                try:
                    if btn.is_visible() and btn.is_enabled():
                        txt = (btn.inner_text() or "").strip()
                        if txt in ("", "›", "»", ">", "Next"):
                            btn.click()
                            page.wait_for_timeout(1200)
                            clicked = True
                            break
                except Exception:
                    continue

            if not clicked:
                break

        browser.close()

    merged_ssl = {}
    for s in captured:
        if s["title"]:
            k = f"{norm(s['artist'])}|{norm(s['title'])}"
            if k not in merged_ssl:
                merged_ssl[k] = s

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
    print(f"SSL loaded: captured={len(captured)}, dom_rows={len(all_dom_rows)}, unique={len(songs)}")
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
            k1, k2 = f"{na}|{nt}", f"{nt}|{na}"
            if k1 in merged:
                merged[k1]["inSheet"] = True
            elif k2 in merged:
                merged[k2]["inSheet"] = True
            elif nt in by_title:
                for mk in by_title[nt]:
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
