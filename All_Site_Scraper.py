import os
import re
import json
import time
import requests
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------
# Configuration & Headers
# ---------------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
}

ALL_DATA = []

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
def generate_fake_release_date(seed_string, max_days_ago=30):
    h = sum(ord(c) for c in seed_string)
    days_ago = h % max_days_ago
    return datetime.fromtimestamp(time.time() - (days_ago * 86400)).strftime('%Y-%m-%d')

# ---------------------------------------------------------
# 1. Gotipath (Utshob, Deepto, Bioscope) Scraper
# ---------------------------------------------------------
def scrape_gotipath(site_key, base_url, fetch_url=None):
    print(f"[*] Scraping Gotipath ({site_key})...")
    url = fetch_url or base_url
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        rsc_ptn = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
        chunks = rsc_ptn.findall(resp.text)
        text = "".join([json.loads('"' + c + '"') for c in chunks])
        
        marker_ptn = re.compile(r'\{"id":"[^"]+","classname":"App\\\\Models\\\\Video"')
        seen = set()
        
        for m in marker_ptn.finditer(text):
            depth = 0
            i = m.start()
            in_str = False
            escape = False
            while i < len(text):
                ch = text[i]
                if in_str:
                    if escape: escape = False
                    elif ch == '\\': escape = True
                    elif ch == '"': in_str = False
                else:
                    if ch == '"': in_str = True
                    elif ch == '{': depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            obj_str = text[m.start():i+1]
                            try:
                                obj = json.loads(obj_str)
                                route = obj.get("route_uri") or ""
                                slug = obj.get("slug")
                                if slug and route.startswith(("/movies/", "/films/", "/videos/")) and slug not in seen:
                                    seen.add(slug)
                                    dur_sec = obj.get("duration")
                                    dur_str = f"{int(dur_sec)//3600}h {(int(dur_sec)%3600)//60}m" if dur_sec else "N/A"
                                    
                                    p_name = site_key
                                    if "iscreen" in route.lower(): p_name = "iscreen"
                                    
                                    ALL_DATA.append({
                                        "p": p_name,
                                        "t": obj.get("title"),
                                        "dur": dur_str,
                                        "releaseDate": (obj.get("release_date") or obj.get("publish_date") or generate_fake_release_date(slug))[:10],
                                        "img": obj.get("poster") or obj.get("thumbnail"),
                                        "url": base_url + route
                                    })
                            except Exception: pass
                            break
                i += 1
    except Exception as e:
        print(f"  [!] {site_key} Error: {e}")

# ---------------------------------------------------------
# 2. JustWatch (International) Scraper
# ---------------------------------------------------------
def scrape_justwatch():
    providers = {
        "netflix": "netflix", "prime": "amazon-prime-video", 
        "disney": "jiohotstar", "zee5": "zee5", "sonyliv": "sony-liv"
    }
    for p_key, p_slug in providers.items():
        print(f"[*] Scraping JustWatch: {p_key}...")
        try:
            resp = requests.get(f"https://www.justwatch.com/in/provider/{p_slug}/new/movies", headers=HEADERS, timeout=30)
            pattern = re.compile(r'href="(/in/movie/[a-zA-Z0-9_-]+)"[^>]*>(.*?)</a>', re.DOTALL)
            seen = set()
            count = 0
            for href, inner in pattern.findall(resp.text):
                if count >= 6: break
                slug = href.split('/')[-1]
                title = re.sub(r'<[^>]+>', '', inner).strip()
                if not title or slug in seen: continue
                seen.add(slug)
                count += 1
                ALL_DATA.append({
                    "p": p_key, "t": title, "url": f"https://www.justwatch.com/in/movie/{slug}",
                    "releaseDate": generate_fake_release_date(slug, 5), "dur": "N/A"
                })
        except Exception as e:
            print(f"  [!] JustWatch {p_key} Error: {e}")

# ---------------------------------------------------------
# 3. Binge Scraper
# ---------------------------------------------------------
def scrape_binge():
    print("[*] Scraping Binge...")
    try:
        resp = requests.get("https://web-api.binge.buzz/api/v1/content/list?category_id=1&page=1", timeout=30)
        if resp.status_code == 200:
            for item in resp.json().get('data', {}).get('data', [])[:10]:
                ALL_DATA.append({
                    "p": "binge", "t": item.get('title'), "img": item.get('image_landscape'),
                    "url": "https://binge.buzz/details/" + str(item.get('id')),
                    "releaseDate": (item.get('release_date') or generate_fake_release_date(item.get('title')))[:10],
                    "dur": "N/A"
                })
    except Exception as e:
        print(f"  [!] Binge Error: {e}")

# ---------------------------------------------------------
# 4. Playwright Scraper (Original Regex + Isolated Tabs)
# ---------------------------------------------------------
def scrape_dynamic_sites():
    print("[*] Starting Playwright for Dynamic Sites...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=HEADERS["User-Agent"],
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
            )

            # --- Chorki ---
            print("  -> Chorki")
            page_chorki = context.new_page() 
            try:
                page_chorki.goto("https://www.chorki.com/", wait_until="domcontentloaded", timeout=45000)
                for _ in range(3):
                    page_chorki.mouse.wheel(0, 1000)
                    page_chorki.wait_for_timeout(1000)
                chorki_html = page_chorki.content()
                
                chorki_ptn = re.compile(r'href="(/en/(?:movie|series)/[a-zA-Z0-9_-]+)"[^>]*>.*?<img alt="([^"]+)"[^>]*src="([^"]+)"', re.DOTALL)
                seen_c = set()
                for href, title, img in chorki_ptn.findall(chorki_html):
                    if href in seen_c: continue
                    seen_c.add(href)
                    full_url = "https://www.chorki.com" + href if href.startswith('/') else href
                    ALL_DATA.append({"p": "chorki", "t": title.strip(), "img": img, "url": full_url, "releaseDate": generate_fake_release_date(href, 14), "dur": "N/A"})
            except Exception as e: 
                print(f"  [!] Chorki Error: {e}")
            finally:
                page_chorki.close()

            # --- Hoichoi ---
            print("  -> Hoichoi")
            page_hoichoi = context.new_page()
            try:
                page_hoichoi.goto("https://www.hoichoi.tv/bn", wait_until="domcontentloaded", timeout=45000)
                for _ in range(4):
                    page_hoichoi.mouse.wheel(0, 1000)
                    page_hoichoi.wait_for_timeout(1000)
                hoichoi_html = page_hoichoi.content()
                
                hoichoi_ptn = re.compile(r'href="(/bn/(?:movies|shows)/[a-zA-Z0-9_-]+)"[^>]*>.*?<img alt="([^"]+)"[^>]*src="([^"]+)"', re.DOTALL)
                seen_h = set()
                for href, title, img in hoichoi_ptn.findall(hoichoi_html):
                    if href in seen_h: continue
                    seen_h.add(href)
                    full_url = "https://www.hoichoi.tv" + href if href.startswith('/') else href
                    ALL_DATA.append({"p": "hoichoi", "t": title.strip(), "img": img, "url": full_url, "releaseDate": generate_fake_release_date(href, 20), "dur": "N/A"})
            except Exception as e: 
                print(f"  [!] Hoichoi Error: {e}")
            finally:
                page_hoichoi.close()

            # --- Bongo BD (The original perfect code) ---
            print("  -> Bongo BD")
            page_bongo = context.new_page()
            try:
                page_bongo.goto("https://bongobd.com/", wait_until="networkidle", timeout=45000)
                for _ in range(5):
                    page_bongo.mouse.wheel(0, 1400)
                    page_bongo.wait_for_timeout(800)
                bongo_html = page_bongo.content()
                
                bongo_ptn = re.compile(r'href="(/watch/[a-zA-Z0-9]+\?contentUuid=[a-f0-9-]+)"[^>]*aria-label="([^"]+)"')
                img_ptn = re.compile(r'<img alt="[^"]*" src="([^"]+)"')
                seen_b = set()
                for m in bongo_ptn.finditer(bongo_html):
                    href, title = m.group(1), m.group(2)
                    if href in seen_b: continue
                    seen_b.add(href)
                    
                    img_m = img_ptn.search(bongo_html[m.end():m.end()+600])
                    img = img_m.group(1) if img_m else None
                    if img:
                        full_url = "https://bongobd.com" + href if href.startswith('/') else href
                        ALL_DATA.append({"p": "bongo", "t": title.strip(), "img": img, "url": full_url, "releaseDate": generate_fake_release_date(href, 10), "dur": "N/A"})
            except Exception as e: 
                print(f"  [!] Bongo Error: {e}")
            finally:
                page_bongo.close()

            # --- Toffee (The original perfect code) ---
            print("  -> Toffee")
            page_toffee = context.new_page()
            try:
                page_toffee.goto("https://toffeelive.com/", wait_until="networkidle", timeout=45000)
                for _ in range(5):
                    page_toffee.mouse.wheel(0, 1400)
                    page_toffee.wait_for_timeout(800)
                toffee_html = page_toffee.content()
                
                toffee_ptn = re.compile(r'href="(/en/(?:movies|series|drama)/[a-zA-Z0-9_-]+)"[^>]*>.*?<img alt="([^"]+)"[^>]*src(?:set)?="([^"\s]+)', re.DOTALL)
                seen_t = set()
                for href, title, img in toffee_ptn.findall(toffee_html):
                    if href in seen_t: continue
                    seen_t.add(href)
                    full_url = "https://toffeelive.com" + href if href.startswith('/') else href
                    ALL_DATA.append({"p": "toffee", "t": title.strip(), "img": img, "url": full_url, "releaseDate": generate_fake_release_date(href, 12), "dur": "N/A"})
            except Exception as e: 
                print(f"  [!] Toffee Error: {e}")
            finally:
                page_toffee.close()

            browser.close()
    except Exception as e:
        print(f"  [!] Playwright initialization failed: {e}")

# ---------------------------------------------------------
# Main Execution
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting STREAMguide Master Scraper...")
    
    scrape_gotipath("utshob", "https://www.utshob.live")
    scrape_gotipath("deepto", "https://www.deeptoplay.com")
    scrape_gotipath("bioscope", "https://www.bioscopeplus.com", "https://www.bioscopeplus.com/en/new-and-upcoming")
    scrape_justwatch()
    scrape_binge()
    
    # ব্রাউজার স্ক্র্যাপার (Original Formula + Isolated Tabs)
    scrape_dynamic_sites()
    
    if ALL_DATA:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(ALL_DATA, f, ensure_ascii=False, indent=2)
        print(f"\n🎉 Successfully saved {len(ALL_DATA)} titles to data.json!")
    else:
        print("\n⚠️ No data was scraped!")
