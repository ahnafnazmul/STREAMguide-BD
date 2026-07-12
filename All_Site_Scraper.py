import os
import re
import json
import time
import requests
from datetime import datetime, timezone

# Playwright এখন ডায়নামিক সাইটগুলোর (Chorki, Hoichoi, Bongo, Toffee) জন্য ব্যবহার করা হবে
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
    """যেসব প্ল্যাটফর্ম রিলিজ ডেট দেয় না, তাদের জন্য একটি ফেইক ডেট তৈরি করা"""
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
                    if escape:
                        escape = False
                    elif ch == '\\':
                        escape = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == '{':
                        depth += 1
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
                                    if "iscreen" in route.lower():
                                        p_name = "iscreen"
                                    
                                    ALL_DATA.append({
                                        "p": p_name,
                                        "t": obj.get("title"),
                                        "dur": dur_str,
                                        "releaseDate": (obj.get("release_date") or obj.get("publish_date") or generate_fake_release_date(slug))[:10],
                                        "img": obj.get("poster") or obj.get("thumbnail"),
                                        "url": base_url + route
                                    })
                            except Exception:
                                pass
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
                if count >= 6:
                    break
                slug = href.split('/')[-1]
                title = re.sub(r'<[^>]+>', '', inner).strip()
                if not title or slug in seen:
                    continue
                seen.add(slug)
                count += 1
                
                ALL_DATA.append({
                    "p": p_key,
                    "t": title,
                    "url": f"https://www.justwatch.com/in/movie/{slug}",
                    "releaseDate": generate_fake_release_date(slug, 5),
                    "dur": "N/A"
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
                    "p": "binge",
                    "t": item.get('title'),
                    "img": item.get('image_landscape'),
                    "url": "https://binge.buzz/details/" + str(item.get('id')),
                    "releaseDate": (item.get('release_date') or generate_fake_release_date(item.get('title')))[:10],
                    "dur": "N/A"
                })
    except Exception as e:
        print(f"  [!] Binge Error: {e}")

# ---------------------------------------------------------
# 4. Playwright Scraper (The Ultimate Human Emulator)
# ---------------------------------------------------------
def scrape_dynamic_sites():
    print("[*] Starting Playwright for Dynamic Sites (Chorki, Hoichoi, Bongo, Toffee)...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # সিকিউরিটি বাইপাস করার জন্য শক্তিশালী কনটেক্সট
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=HEADERS["User-Agent"],
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
            )
            page = context.new_page()

            # --- Chorki ---
            print("  -> Chorki")
            try:
                page.goto("https://www.chorki.com/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000) # ইমেজ লোড হওয়ার জন্য ৩ সেকেন্ড অপেক্ষা
                cards = page.locator('a[href*="/movie/"], a[href*="/series/"]').all()
                seen_c = set()
                for card in cards[:20]:
                    href = card.get_attribute('href')
                    if not href or href in seen_c: continue
                    seen_c.add(href)
                    title = href.split('/')[-1].replace('-', ' ').title()
                    img_tag = card.locator('img').first
                    img = img_tag.get_attribute('src') if img_tag else None
                    if img:
                        full_url = href if href.startswith('http') else "https://www.chorki.com" + href
                        ALL_DATA.append({"p": "chorki", "t": title.strip(), "img": img, "url": full_url, "releaseDate": generate_fake_release_date(href, 14), "dur": "N/A"})
            except Exception as e: print(f"  [!] Chorki Error: {e}")

            # --- Hoichoi ---
            print("  -> Hoichoi")
            try:
                page.goto("https://www.hoichoi.tv/bn", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                cards = page.locator('a[href*="/movies/"], a[href*="/shows/"]').all()
                seen_h = set()
                for card in cards[:20]:
                    href = card.get_attribute('href')
                    if not href or href in seen_h: continue
                    seen_h.add(href)
                    title = href.split('/')[-1].replace('-', ' ').title()
                    img_tag = card.locator('img').first
                    img = img_tag.get_attribute('src') if img_tag else None
                    if img:
                        full_url = href if href.startswith('http') else "https://www.hoichoi.tv" + href
                        ALL_DATA.append({"p": "hoichoi", "t": title.strip(), "img": img, "url": full_url, "releaseDate": generate_fake_release_date(href, 20), "dur": "N/A"})
            except Exception as e: print(f"  [!] Hoichoi Error: {e}")

            # --- Bongo BD ---
            print("  -> Bongo BD")
            try:
                page.goto("https://bongobd.com/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                cards = page.locator('a[href^="/watch/"]').all()
                seen_b = set()
                for card in cards[:20]:
                    href = card.get_attribute('href')
                    if not href or href in seen_b: continue
                    seen_b.add(href)
                    title = card.get_attribute('aria-label') or href.split('?')[0].split('/')[-1].replace('-', ' ').title()
                    img_tag = card.locator('img').first
                    img = img_tag.get_attribute('src') if img_tag else None
                    if img:
                        full_url = href if href.startswith('http') else "https://bongobd.com" + href
                        ALL_DATA.append({"p": "bongo", "t": title.strip(), "img": img, "url": full_url, "releaseDate": generate_fake_release_date(href, 10), "dur": "N/A"})
            except Exception as e: print(f"  [!] Bongo Error: {e}")

            # --- Toffee ---
            print("  -> Toffee")
            try:
                page.goto("https://toffeelive.com/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                cards = page.locator('a[href*="/movies/"], a[href*="/series/"], a[href*="/drama/"]').all()
                seen_t = set()
                for card in cards[:20]:
                    href = card.get_attribute('href')
                    if not href or href in seen_t: continue
                    seen_t.add(href)
                    title = href.split('/')[-1].replace('-', ' ').title()
                    img_tag = card.locator('img').first
                    img = img_tag.get_attribute('src') if img_tag else None
                    if img:
                        full_url = href if href.startswith('http') else "https://toffeelive.com" + href
                        ALL_DATA.append({"p": "toffee", "t": title.strip(), "img": img, "url": full_url, "releaseDate": generate_fake_release_date(href, 12), "dur": "N/A"})
            except Exception as e: print(f"  [!] Toffee Error: {e}")

            browser.close()
    except Exception as e:
        print(f"  [!] Playwright initialization failed: {e}")

# ---------------------------------------------------------
# Main Execution
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting STREAMguide Master Scraper...")
    
    # API ভিত্তিক স্ক্র্যাপার
    scrape_gotipath("utshob", "https://www.utshob.live")
    scrape_gotipath("deepto", "https://www.deeptoplay.com")
    scrape_gotipath("bioscope", "https://www.bioscopeplus.com", "https://www.bioscopeplus.com/en/new-and-upcoming")
    scrape_justwatch()
    scrape_binge()
    
    # ব্রাউজার/ডায়নামিক স্ক্র্যাপার (The Human Emulator)
    scrape_dynamic_sites()
    
    # ডেটা সেভ করা
    if ALL_DATA:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(ALL_DATA, f, ensure_ascii=False, indent=2)
        print(f"\n🎉 Successfully saved {len(ALL_DATA)} titles to data.json!")
    else:
        print("\n⚠️ No data was scraped!")
