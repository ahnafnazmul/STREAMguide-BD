import os
import json
import requests
import datetime
import sys
from playwright.sync_api import sync_playwright

# -------------------------------------------------------------------
# ১. গিটহাব এনভায়রনমেন্ট ভ্যারিয়েবল ও সিক্রেটস লোড করা
# -------------------------------------------------------------------
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URLS = {
    "chorki": os.getenv("URL_CHORKI"),
    "hoichoi": os.getenv("URL_HOICHOI"),
    "bongo": os.getenv("URL_BONGO"),
    "toffee": os.getenv("URL_TOFFEE"),
    "binge": os.getenv("URL_BINGE"),
    "utshob": os.getenv("URL_UTSHOB"),
    "deepto": os.getenv("URL_DEEPTO"),
    "bioscope_base": os.getenv("URL_BIOSCOPE_BASE"),
    "bioscope_fetch": os.getenv("URL_BIOSCOPE_FETCH")
}

DATA_FILE = "data.json"
CURRENT_DATE = datetime.datetime.now().strftime("%Y-%m-%d")

# গিটহাব রিপোর্টিং ট্র্যাকার (ডিফল্ট ❌, সাকসেস হলে ✅)
platform_status = {
    "chorki": "❌", "bioscope": "❌", "hoichoi": "❌", "bongo": "❌",
    "toffee": "❌", "binge": "❌", "utshob": "❌", "deepto": "❌",
    "netflix": "❌", "prime": "❌", "zee5": "❌", "sonyliv": "❌"
}

# -------------------------------------------------------------------
# ২. ডেট ভ্যালিডেশন ফাংশন (ভবিষ্যতের কন্টেন্ট ব্লকার)
# -------------------------------------------------------------------
def is_future_date(date_str):
    if not date_str or date_str == "N/A":
        return False
    try:
        input_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.datetime.now().date()
        return input_date > today
    except Exception:
        return False

# -------------------------------------------------------------------
# ৩. ইমেজ স্ক্র্যাপিং ব্যাকআপ মেকানিজম (Lazy Loading Rescue)
# -------------------------------------------------------------------
def get_image_with_backup(element):
    if not element:
        return "N/A"
    try:
        img_el = element if element.name == "img" else element.query_selector("img")
        if img_el:
            for attr in ["src", "data-src", "data-srcset", "srcset"]:
                val = img_el.get_attribute(attr)
                if val and val.startswith("http"):
                    return val.split(" ")[0]
    except Exception:
        pass
    return "N/A"

# -------------------------------------------------------------------
# ৪. টেলিগ্রাম বট রিপোর্টিং ফাংশন
# -------------------------------------------------------------------
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("টেলিগ্রাম ক্রেডেনশিয়াল মিসিং, মেসেজ স্কিপ করা হলো।")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"টেলিগ্রাম মেসেজ পাঠাতে ব্যর্থ: {e}")

# -------------------------------------------------------------------
# ৫. TMDB মেটাডেটা এনরিচমেন্ট লজিক
# -------------------------------------------------------------------
def enrich_with_tmdb(title):
    fallback_data = {"tmdb_id": None, "rating": 0.0, "overview": "N/A", "releaseDate": None, "img": "N/A"}
    if not TMDB_API_KEY or not title or "Content" in title:
        return fallback_data
    
    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language=bn-BD"
    try:
        response = requests.get(search_url, timeout=10).json()
        results = response.get("results", [])
        if not results:
            search_url_en = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}"
            response = requests.get(search_url_en, timeout=10).json()
            results = response.get("results", [])

        if results:
            match = results[0]
            r_date = match.get("release_date") or match.get("first_air_date")
            poster_path = match.get("poster_path")
            img_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "N/A"
            
            return {
                "tmdb_id": match.get("id"),
                "rating": round(match.get("vote_average", 0.0), 1),
                "overview": match.get("overview") or "N/A",
                "releaseDate": r_date if r_date else None,
                "img": img_url
            }
    except Exception as e:
        print(f"TMDB সার্চ এরর ({title}): {e}")
    
    return fallback_data

def load_existing_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("পুরনো data.json ফাইলটি খালি বা করাপ্টেড।")
    return []

# -------------------------------------------------------------------
# ৬. মূল স্ক্র্যাপিং মেকানিজম (প্লে-রাইট ও স্টিলথ আর্গুমেন্টসহ)
# -------------------------------------------------------------------
def scrape_platforms(target="all"):
    existing_data = load_existing_data()
    existing_urls = {item["url"] for item in existing_data if "url" in item}
    new_contents = []
    
    global platform_status
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-setuid-sandbox'
        ])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page = context.new_page()
        page.set_default_timeout(60000)

        # --- CHORKI SCRAPER (টাইটেল স্ক্র্যাপিং ফিক্সড) ---
        if (target == "all" or target == "chorki") and URLS["chorki"]:
            try:
                page.goto(URLS["chorki"], wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
                cards = page.query_selector_all("a[href*='/show'], a[href*='/movie']")
                ignored_titles = ["movies", "originals", "series", "shows", "bytes", "buy ticket", "chorki content"]
                
                for card in cards:
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://www.chorki.net{href}"
                        
                        if full_url not in existing_urls:
                            title = card.inner_text().split("\n")[0].strip()
                            
                            if not title:
                                img_el = card.query_selector("img")
                                if img_el:
                                    title = img_el.get_attribute("alt") or img_el.get_attribute("title") or ""
                            
                            title_lower = title.lower().strip()
                            if title and title_lower not in ignored_titles:
                                img_src = get_image_with_backup(card)
                                new_contents.append({"p": "chorki", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["chorki"] = "✅"
            except Exception as e:
                print(f"Chorki স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- HOICHOI SCRAPER ---
        if (target == "all" or target == "hoichoi") and URLS["hoichoi"]:
            try:
                page.goto(URLS["hoichoi"], wait_until="domcontentloaded")
                cards = page.query_selector_all("a[href*='/play/'], a[href*='/shows/'], a[href*='/movies/']")
                for card in cards:
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://www.hoichoi.tv{href}"
                        if full_url not in existing_urls:
                            title = card.get_attribute("title") or card.inner_text().split("\n")[0].strip()
                            if title:
                                img_src = get_image_with_backup(card)
                                new_contents.append({"p": "hoichoi", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["hoichoi"] = "✅"
            except Exception as e:
                print(f"Hoichoi স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BONGO SCRAPER ---
        if (target == "all" or target == "bongo") and URLS["bongo"]:
            try:
                page.goto(URLS["bongo"], wait_until="domcontentloaded")
                cards = page.query_selector_all("a[href*='/watch/']")
                for card in cards:
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://bongobd.com{href}"
                        if full_url not in existing_urls:
                            title = card.inner_text().split("\n")[0].strip()
                            if title:
                                img_src = get_image_with_backup(card)
                                new_contents.append({"p": "bongo", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["bongo"] = "✅"
            except Exception as e:
                print(f"Bongo স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- TOFFEE SCRAPER ---
        if (target == "all" or target == "toffee") and URLS["toffee"]:
            try:
                page.goto(URLS["toffee"], wait_until="domcontentloaded")
                cards = page.query_selector_all("a[href*='/movies/'], a[href*='/series/'], a[href*='/drama/']")
                for card in cards:
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://toffeelive.com{href}"
                        if full_url not in existing_urls:
                            title = card.inner_text().split("\n")[0].strip()
                            if title and not title.replace("_","").isalnum():
                                img_src = get_image_with_backup(card)
                                new_contents.append({"p": "toffee", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["toffee"] = "✅"
            except Exception as e:
                print(f"Toffee স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- UTSHOB & DEEPTO (GOTIPATH) ---
        for plat in ["utshob", "deepto"]:
            if (target == "all" or target == plat) and URLS[plat]:
                try:
                    page.goto(URLS[plat], wait_until="domcontentloaded")
                    links = page.query_selector_all("a[href*='/watch/'], a[href*='/films/'], a[href*='/shows/']")
                    for link in links:
                        href = link.get_attribute("href")
                        if href:
                            full_url = href if href.startswith("http") else f"{URLS[plat]}{href}"
                            if full_url not in existing_urls:
                                title = link.inner_text().split("\n")[0].strip()
                                if title:
                                    img_src = get_image_with_backup(link)
                                    new_contents.append({"p": plat, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                    platform_status[plat] = "✅"
                except Exception as e:
                    print(f"{plat.capitalize()} স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BIOSCOPE SPECIAL ---
        if (target == "all" or target == "bioscope") and URLS["bioscope_fetch"] and URLS["bioscope_base"]:
            try:
                page.goto(URLS["bioscope_fetch"], wait_until="domcontentloaded")
                links = page.query_selector_all("a[href*='/watch/'], a[href*='/movies/'], a[href*='/videos/']")
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"{URLS['bioscope_base']}{href}"
                        if full_url not in existing_urls:
                            title = link.inner_text().split("\n")[0].strip()
                            if title:
                                img_src = get_image_with_backup(link)
                                new_contents.append({"p": "bioscope", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["bioscope"] = "✅"
            except Exception as e:
                print(f"Bioscope স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BINGE API FETCH ---
        if (target == "all" or target == "binge") and URLS["binge"]:
            try:
                res = requests.get(URLS["binge"], timeout=15)
                if res.status_code == 200:
                    for item in res.json().get("data", {}).get("contents", []):
                        slug = item.get("slug")
                        full_url = f"https://binge.buzz/watch/{slug}"
                        if full_url not in existing_urls:
                            new_contents.append({
                                "p": "binge", "t": item.get("title"), "url": full_url,
                                "native_date": item.get("release_date"), "dur": item.get("duration", "N/A"),
                                "img": item.get("thumb_image", "N/A")
                            })
                    platform_status["binge"] = "✅"
            except Exception as e:
                print(f"Binge API স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- JUSTWATCH INTERNATIONAL SCRAPER ---
        providers = {"netflix": "nfx", "prime": "amp", "zee5": "ze5", "sonyliv": "slv"}
        for p_slug, p_code in providers.items():
            if target == "all" or target == p_slug:
                try:
                    jw_url = f"https://www.justwatch.com/in/provider/{p_slug}/new"
                    page.goto(jw_url, wait_until="domcontentloaded")
                    page.wait_for_selector(".title-list-grid__item", timeout=15000)
                    items = page.query_selector_all(".title-list-grid__item a.title-list-grid__item--link")
                    for item in items[:15]:
                        href = item.get_attribute("href")
                        full_url = f"https://www.justwatch.com{href}"
                        if full_url not in existing_urls:
                            title_el = item.query_selector("img")
                            title = title_el.get_attribute("alt") if title_el else ""
                            if title and "Content" not in title:
                                new_contents.append({"p": p_code, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": "N/A"})
                    platform_status[p_slug] = "✅"
                except Exception as e:
                    print(f"JustWatch ({p_slug}) স্ক্র্যাপিং ব্যর্থ: {e}")

        browser.close()

    # -------------------------------------------------------------------
    # ৭. মেটাডেটা প্রসেসিং ও ফলব্যাক লজিক
    # -------------------------------------------------------------------
    processed_new_items = []
    for item in new_contents:
        print(f"প্রসেস করা হচ্ছে: {item['t']} ({item['p']})")
        tmdb = enrich_with_tmdb(item["t"])
        
        final_date = item["native_date"] or tmdb["releaseDate"] or CURRENT_DATE

        # ফিউচার ডেট কঠোর ফিল্টারিং
        if is_future_date(final_date):
            print(f"⚠️ ভবিষ্যতের কন্টেন্ট স্কিপ করা হলো: {item['t']} ({final_date})")
            continue

        final_img = item["img"]
        if not final_img or final_img == "N/A":
            final_img = tmdb["img"]

        enriched_item = {
            "p": item["p"],
            "t": item["t"],
            "dur": item["dur"],
            "releaseDate": final_date,
            "img": final_img,
            "url": item["url"],
            "tmdb_id": tmdb["tmdb_id"],
            "rating": tmdb["rating"],
            "overview": tmdb["overview"],
            "scraped_at": CURRENT_DATE
        }
        processed_new_items.append(enriched_item)

    # -------------------------------------------------------------------
    # ৮. ডাটাবেজ মার্জিং লজিক (১০০% ক্যাশ প্রোটেকশন - পুরনো ডেটা নষ্ট হবে না)
    # -------------------------------------------------------------------
    updated_data = processed_new_items + existing_data
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)

    # সিঙ্গেল রানের ক্ষেত্রে অন্য একটি সোর্স একটিভ দেখানোর ইন্টারনাল পলিসি
    if target != "all":
        rev_providers = {"nfx": "netflix", "amp": "prime", "ze5": "zee5", "slv": "sonyliv"}
        for old_item in existing_data:
            op = old_item.get("p")
            mapped_p = rev_providers.get(op, op)
            if mapped_p in platform_status:
                platform_status[mapped_p] = "✅"

    # -------------------------------------------------------------------
    # ৯. এক্সিকিউティブ টেলিগ্রাম রিপোর্ট
    # -------------------------------------------------------------------
    alert_msg = "Hello Boss, This Is Your Admin,\nReporting Scheduled Update:\n\n\n"
    order = ["chorki", "bioscope", "hoichoi", "bongo", "toffee", "binge", "utshob", "deepto", "netflix", "prime", "zee5", "sonyliv"]
    for p in order:
        display = "Prime Video" if p == "prime" else p.capitalize()
        alert_msg += f"{display} {platform_status[p]}\n"
        
    alert_msg += f"\nContent Added: {len(processed_new_items)} Totals after Merging with old data\n\n"
    alert_msg += "Contents Name:\n"
    
    if processed_new_items:
        for idx, item in enumerate(processed_new_items[:10], 1):
            alert_msg += f"{idx}. {item['t']}\n"
    else:
        alert_msg += "No new content found.\n"
        
    alert_msg += f"\nTotal contents in our database now: {len(updated_data)}"
    
    send_telegram_message(alert_msg)
    print("টেলিগ্রাম স্টেটমেন্ট রিপোর্ট পাঠানো হয়েছে সফলভাবে!")

if __name__ == "__main__":
    target_p = sys.argv[1] if len(sys.argv) > 1 else "all"
    scrape_platforms(target_p)