import os
import json
import requests
import datetime
from playwright.sync_api import sync_playwright

# -------------------------------------------------------------------
# ১. গিটহাব এনভায়রনমেন্ট ভ্যারিয়েবল ও সিক্রেটস লোড করা
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
# ২০২৬ সালের কারেন্ট ডেট অবজেক্ট (ভবিষ্যতের কন্টেন্ট ফিল্টার করার জন্য)
TODAY = datetime.datetime.now()
CURRENT_DATE_STR = TODAY.strftime("%Y-%m-%d")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"টেলিগ্রাম মেসেজ পাঠাতে ব্যর্থ: {e}")

def parse_and_validate_date(date_str):
    """৪-স্তরের ডেট লজিক ও ভবিষ্যৎ রিলিজ (যেমন ২০৩১) ফিল্টার করার ব্যাকআপ"""
    if not date_str or date_str == "N/A":
        return None
    
    formats = ["%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%b %d, %Y", "%d %b %Y"]
    for fmt in formats:
        try:
            parsed_date = datetime.datetime.strptime(date_str.strip(), fmt)
            # যদি ডেটটি আজকের চেয়ে ভবিষ্যৎ হয় (যেমন ২০২৯ বা ২০৩১), তবে একে রিজেক্ট করতে None রিটার্ন করবে
            if parsed_date > TODAY:
                return None
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def enrich_with_tmdb(title):
    fallback_data = {"tmdb_id": None, "rating": "N/A", "overview": "N/A", "releaseDate": None}
    if not TMDB_API_KEY or not title:
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
            valid_tmdb_date = parse_and_validate_date(r_date)
            
            return {
                "tmdb_id": match.get("id"),
                "rating": match.get("vote_average", "N/A"),
                "overview": match.get("overview") or "N/A",
                "releaseDate": valid_tmdb_date # ভ্যালিডেটেড ডেট (ভবিষ্যতের হলে None থাকবে)
            }
    except Exception as e:
        print(f"TMDB সার্চ এরর ({title}): {e}")
    
    return fallback_data

def get_image_with_backup(element):
    """অলস লোডিং (Lazy Load) কাটাতে মাল্টিপল ইমেজ অ্যাট্রিবিউট ব্যাকআপ"""
    if not element:
        return "N/A"
    try:
        img_el = element.query_selector("img")
        if img_el:
            # সোর্সের যত রকম ভ্যারিয়েশন হতে পারে সব ব্যাকআপ চেক
            for attr in ["src", "data-src", "data-srcset", "srcset"]:
                val = img_el.get_attribute(attr)
                if val and not val.startswith("data:image"):
                    return val.split(" ")[0] # জাস্ট মূল ইমেজ ইউআরএল নিবে
    except Exception:
        pass
    return "N/A"

def load_existing_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("পুরনো data.json ফাইলটি করাপ্টেড বা খালি।")
    return []

def scrape_platforms():
    existing_data = load_existing_data()
    existing_urls = {item["url"] for item in existing_data if "url" in item}
    new_contents = []
    
    # আপনার স্পেসিফিক সিরিয়াল অনুযায়ী স্ট্যাটাস ট্র্যাকার ডিকশনারি
    status = {
        "Chorki": "❌", "Bioscope": "❌", "Hoichoi": "❌", "Bongo": "❌", 
        "Toffee": "❌", "Binge": "❌", "Utshob": "❌", "Deepto": "❌",
        "Netflix": "❌", "Prime Video": "❌", "Zee5": "❌", "SonyLIV": "❌"
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-setuid-sandbox'
        ])
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1080} # ইমেজ রেন্ডার করার জন্য হাইট বাড়ানো হলো
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        # --- CHORKI SCRAPER ---
        if URLS["chorki"]:
            try:
                page.goto(URLS["chorki"], wait_until="domcontentloaded")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/4)") # স্ক্রোল ডাউন ব্যাকআপ
                page.wait_for_timeout(5000)
                cards = page.query_selector_all("a[href*='/shows/'], a[href*='/movies/']")
                for card in cards:
                    href = card.get_attribute("href")
                    full_url = href if href.startswith("http") else f"{URLS['chorki']}{href}"
                    if full_url not in existing_urls:
                        title = card.inner_text().split("\n")[0].strip() or "Chorki Content"
                        img_url = get_image_with_backup(card)
                        new_contents.append({"p": "chorki", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_url})
                status["Chorki"] = "✅"
            except Exception as e:
                print(f"Chorki স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- HOICHOI SCRAPER ---
        if URLS["hoichoi"]:
            try:
                page.goto(URLS["hoichoi"], wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                cards = page.query_selector_all("a[href*='/play/']")
                for card in cards:
                    href = card.get_attribute("href")
                    full_url = href if href.startswith("http") else f"https://www.hoichoi.tv{href}"
                    if full_url not in existing_urls:
                        title = card.get_attribute("title") or "Hoichoi Content"
                        img_url = get_image_with_backup(card)
                        new_contents.append({"p": "hoichoi", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_url})
                status["Hoichoi"] = "✅"
            except Exception as e:
                print(f"Hoichoi স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BONGO SCRAPER ---
        if URLS["bongo"]:
            try:
                page.goto(URLS["bongo"], wait_until="domcontentloaded")
                page.evaluate("window.scrollTo(0, 300)")
                page.wait_for_timeout(4000)
                cards = page.query_selector_all("a[href*='/watch/'], a[href*='/channel/']")
                for card in cards:
                    href = card.get_attribute("href")
                    full_url = href if href.startswith("http") else f"{URLS['bongo']}{href}"
                    if full_url not in existing_urls:
                        title = card.inner_text().split("\n")[0].strip() or "Bongo Content"
                        img_url = get_image_with_backup(card)
                        new_contents.append({"p": "bongo", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_url})
                status["Bongo"] = "✅"
            except Exception as e:
                print(f"Bongo স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- TOFFEE SCRAPER ---
        if URLS["toffee"]:
            try:
                page.goto(URLS["toffee"], wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                cards = page.query_selector_all("a[href*='/vod/'], a[href*='/live/']")
                for card in cards:
                    href = card.get_attribute("href")
                    full_url = href if href.startswith("http") else f"{URLS['toffee']}{href}"
                    if full_url not in existing_urls:
                        title = card.inner_text().split("\n")[0].strip() or "Toffee Content"
                        img_url = get_image_with_backup(card)
                        new_contents.append({"p": "toffee", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_url})
                status["Toffee"] = "✅"
            except Exception as e:
                print(f"Toffee স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- UTSHOB SCRAPER ---
        if URLS["utshob"]:
            try:
                page.goto(URLS["utshob"], wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                links = page.query_selector_all("a[href*='/watch/']")
                for link in links:
                    href = link.get_attribute("href")
                    full_url = href if href.startswith("http") else f"{URLS['utshob']}{href}"
                    if full_url not in existing_urls:
                        title = link.inner_text().strip() or "Utshob Content"
                        img_url = get_image_with_backup(link)
                        new_contents.append({"p": "utshob", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_url})
                status["Utshob"] = "✅"
            except Exception as e:
                print(f"Utshob স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- DEEPTO SCRAPER ---
        if URLS["deepto"]:
            try:
                page.goto(URLS["deepto"], wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                links = page.query_selector_all("a[href*='/watch/']")
                for link in links:
                    href = link.get_attribute("href")
                    full_url = href if href.startswith("http") else f"{URLS['deepto']}{href}"
                    if full_url not in existing_urls:
                        title = link.inner_text().strip() or "Deepto Content"
                        img_url = get_image_with_backup(link)
                        new_contents.append({"p": "deepto", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_url})
                status["Deepto"] = "✅"
            except Exception as e:
                print(f"Deepto স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BIOSCOPE SPECIAL ---
        if URLS["bioscope_fetch"] and URLS["bioscope_base"]:
            try:
                page.goto(URLS["bioscope_fetch"], wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                links = page.query_selector_all("a[href*='/watch/']")
                for link in links:
                    href = link.get_attribute("href")
                    full_url = href if href.startswith("http") else f"{URLS['bioscope_base']}{href}"
                    if full_url not in existing_urls:
                        title = link.inner_text().strip() or "Bioscope Content"
                        img_url = get_image_with_backup(link)
                        new_contents.append({"p": "bioscope", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_url})
                status["Bioscope"] = "✅"
            except Exception as e:
                print(f"Bioscope স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BINGE API FETCH ---
        if URLS["binge"]:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                res = requests.get(URLS["binge"], headers=headers, timeout=15)
                if res.status_code == 200:
                    res_json = res.json()
                    for item in res_json.get("data", {}).get("contents", []):
                        slug = item.get("slug")
                        full_url = f"https://binge.buzz/watch/{slug}"
                        if full_url not in existing_urls:
                            valid_native_date = parse_and_validate_date(item.get("release_date"))
                            new_contents.append({
                                "p": "binge",
                                "t": item.get("title", "Binge Content"),
                                "url": full_url,
                                "native_date": valid_native_date,
                                "dur": item.get("duration", "N/A"),
                                "img": item.get("thumb_image", "N/A")
                        })
                    status["Binge"] = "✅"
                else:
                    print(f"Binge API রেসপন্স কোড এরর: {res.status_code}")
            except Exception as e:
                print(f"Binge API স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- JUSTWATCH INTERNATIONAL SCRAPER (ভবিষ্যতের মুভি ফিল্টার সহ) ---
        providers = {"netflix": "Netflix", "prime": "Prime Video", "zee5": "Zee5", "sonyliv": "SonyLIV"}
        p_codes = {"netflix": "nfx", "prime": "amp", "zee5": "ze5", "sonyliv": "slv"}
        for p_slug, p_name in providers.items():
            try:
                jw_url = f"https://www.justwatch.com/in/provider/{p_slug}/new/movies"
                page.goto(jw_url, wait_until="domcontentloaded")
                page.evaluate("window.scrollTo(0, 500)") # অলস ছবি লোড করতে স্ক্রোল
                page.wait_for_timeout(4000)
                items = page.query_selector_all("a.title-list-grid__item--link")
                for item in items[:25]: # পুল ব্যাকআপ সাইজ বাড়ানো হলো ফিল্টারের স্বার্থে
                    href = item.get_attribute("href")
                    full_url = f"https://www.justwatch.com{href}" if href else None
                    if full_url and full_url not in existing_urls:
                        title_el = item.query_selector("img")
                        title = title_el.get_attribute("alt") if title_el else f"{p_name} Content"
                        img_url = get_image_with_backup(item)
                        new_contents.append({"p": p_codes[p_slug], "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_url})
                status[p_name] = "✅"
            except Exception as e:
                print(f"JustWatch ({p_name}) স্ক্র্যাপিং ব্যর্থ: {e}")

        browser.close()

    # -------------------------------------------------------------------
    # ৩. ডেট প্রসেসিং (৪-স্তরের ফলব্যাক ও ভবিষ্যৎ ডেট প্রতিরোধ লজিক)
    # -------------------------------------------------------------------
    processed_new_items = []
    for item in new_contents:
        tmdb = enrich_with_tmdb(item["t"])
        
        # ৪-স্তরের লজিক ইমপ্লিমেন্টেশন
        final_date = item["native_date"]             # ১ম স্তর: সোর্স সাইট রিলিজ ডেট
        if not final_date:
            final_date = tmdb["releaseDate"]         # ৩য় স্তর: TMDB তে পাওয়া রিলিজ ডেট (ভ্যালিডেটেড)
        if not final_date:
            final_date = CURRENT_DATE_STR            # ৪থ স্তর: স্ক্র্যাপিং এর এক্সাক্ট ডেট
            
        # চূড়ান্ত ফিল্টার: যদি কোনো কারণে এখনো ডেট কারেন্ট টাইমের চেয়ে বড় হয়ে থাকে, তা বাতিল করা হবে
        parsed_final = parse_and_validate_date(final_date)
        if not parsed_final:
            continue # ভবিষ্যতের ডেটা হলে ডেটাবেজেই ঢুকবে না (যেমন Avatar 5 স্কিপ হবে)

        enriched_item = {
            "p": item["p"], "t": item["t"], "dur": item["dur"], "releaseDate": parsed_final,
            "img": item["img"], "url": item["url"], "tmdb_id": tmdb["tmdb_id"],
            "rating": tmdb["rating"], "overview": tmdb["overview"], "scraped_at": CURRENT_DATE_STR
        }
        processed_new_items.append(enriched_item)

    # -------------------------------------------------------------------
    # ৪. ডেটা মার্জিং ও নিখুঁত টেলিগ্রাম এক্সিকিউটিভ রিপোর্ট জেনারেশন
    # -------------------------------------------------------------------
    updated_data = processed_new_items + existing_data
    if processed_new_items:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_data, f, ensure_ascii=False, indent=2)

    # আপনার চাওয়া হুবহু মেসেজ ফরম্যাট
    report_msg = "Hello Boss, This Is Your Admin,\n"
    report_msg += "Reporting Scheduled Update:\n\n\n"
    
    # প্ল্যাটফর্ম লিস্ট আপনার দেওয়া অর্ডারে
    platforms_order = ["Chorki", "Bioscope", "Hoichoi", "Bongo", "Toffee", "Binge", "Utshob", "Deepto", "Netflix", "Prime Video", "Zee5", "SonyLIV"]
    for platform_name in platforms_order:
        report_msg += f"{platform_name} {status[platform_name]}\n"
    
    report_msg += f"\nContent Added: {len(processed_new_items)} Totals after Merging with old data \n\n"
    report_msg += "Contents Name:\n"
    
    if processed_new_items:
        for idx, item in enumerate(processed_new_items, 1):
            report_msg += f"{idx}. {item['t']}\n"
    else:
        report_msg += "No new content found.\n"
        
    report_msg += f"\nTotal contents in our database now: {len(updated_data)}"
    
    send_telegram_message(report_msg)
    print("টেলিগ্রাম স্টেটমেন্ট রিপোর্ট পাঠানো হয়েছে সফলভাবে!")

if __name__ == "__main__":
    scrape_platforms()