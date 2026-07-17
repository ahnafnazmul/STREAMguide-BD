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

# প্ল্যাটফর্ম ট্র্যাকিং ডিকশনারি (টেলিগ্রাম রিপোর্টের সিরিয়াল বজায় রাখার জন্য)
platform_status = {
    "chorki": "❌", "bioscope": "❌", "hoichoi": "❌", "bongo": "❌",
    "toffee": "❌", "binge": "❌", "utshob": "❌", "deepto": "❌",
    "netflix": "❌", "prime": "❌", "zee5": "❌", "sonyliv": "❌"
}

platform_display_names = {
    "chorki": "Chorki", "bioscope": "Bioscope", "hoichoi": "Hoichoi", "bongo": "Bongo",
    "toffee": "Toffee", "binge": "Binge", "utshob": "Utshob", "deepto": "Deepto",
    "nfx": "Netflix", "amp": "Prime Video", "ze5": "Zee5", "slv": "SonyLIV"
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
        img_el = element.query_selector("img")
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
            print("পুরনো data.json ফাইলটি করাপ্টেড বা ফাঁকা।")
    return []

# -------------------------------------------------------------------
# ৬. মূল স্ক্র্যাপিং মেকানিজম (ডাইনামিক ও টার্গেটেড ফিল্টারসহ)
# -------------------------------------------------------------------
def scrape_platforms(target="all"):
    existing_data = load_existing_data()
    existing_urls = {item["url"] for item in existing_data if "url" in item}
    new_contents = []
    
    # যদি আমরা কোনো সিঙ্গেল প্ল্যাটফর্ম রান করি, তবে ওই সাইটের স্ট্যাটাস আগে থেকেই রিসেট হবে
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

        # --- CHORKI SCRAPER (লেটেস্ট ইউআরএল ফিক্সড সিলেক্টর) ---
        if (target == "all" or target == "chorki") and URLS["chorki"]:
            try:
                page.goto(URLS["chorki"], wait_until="domcontentloaded")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                page.wait_for_timeout(2000)
                
                # চরকির নতুন ডাইনামিক /show এবং /movie কার্ড টার্গেট করা
                cards = page.query_selector_all("a[href*='/show'], a[href*='/movie']")
                for card in cards:
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://www.chorki.com{href}"
                        if full_url not in existing_urls:
                            img_el = card.query_selector("img")
                            title = "Chorki Content"
                            if img_el:
                                title = img_el.get_attribute("alt") or img_el.get_attribute("title") or title
                            
                            img_src = get_image_with_backup(card)
                            new_contents.append({"p": "chorki", "t": title.strip(), "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["chorki"] = "✅"
            except Exception as e:
                print(f"Chorki স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- HOICHOI SCRAPER ---
        if (target == "all" or target == "hoichoi") and URLS["hoichoi"]:
            try:
                page.goto(URLS["hoichoi"], wait_until="domcontentloaded")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                cards = page.query_selector_all("a[href*='/play/'], a[href*='/shows/'], a[href*='/movies/']")
                for card in cards:
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://www.hoichoi.tv{href}"
                        if full_url not in existing_urls:
                            title = card.get_attribute("title") or card.inner_text().split("\n")[0].strip() or "Hoichoi Content"
                            img_src = get_image_with_backup(card)
                            new_contents.append({"p": "hoichoi", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["hoichoi"] = "✅"
            except Exception as e:
                print(f"Hoichoi স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BONGO SCRAPER ---
        if (target == "all" or target == "bongo") and URLS["bongo"]:
            try:
                page.goto(URLS["bongo"], wait_until="domcontentloaded")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                cards = page.query_selector_all("a[href*='/watch/']")
                for card in cards:
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://bongobd.com{href}"
                        if full_url not in existing_urls:
                            title = card.inner_text().split("\n")[0].strip() or "Bongo Content"
                            img_src = get_image_with_backup(card)
                            new_contents.append({"p": "bongo", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["bongo"] = "✅"
            except Exception as e:
                print(f"Bongo স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- TOFFEE SCRAPER ---
        if (target == "all" or target == "toffee") and URLS["toffee"]:
            try:
                page.goto(URLS["toffee"], wait_until="domcontentloaded")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/3)")
                cards = page.query_selector_all("a[href*='/movies/'], a[href*='/series/'], a[href*='/drama/']")
                for card in cards:
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://toffeelive.com{href}"
                        if full_url not in existing_urls:
                            title = card.inner_text().split("\n")[0].strip() or "Toffee Content"
                            img_src = get_image_with_backup(card)
                            new_contents.append({"p": "toffee", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                platform_status["toffee"] = "✅"
            except Exception as e:
                print(f"Toffee স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- UTSHOB & DEEPTO (GOTIPATH PLATFORMS) ---
        for plat in ["utshob", "deepto"]:
            if (target == "all" or target == plat) and URLS[plat]:
                try:
                    page.goto(URLS[plat], wait_until="domcontentloaded")
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                    links = page.query_selector_all("a[href*='/watch/'], a[href*='/films/'], a[href*='/shows/']")
                    for link in links:
                        href = link.get_attribute("href")
                        if href:
                            full_url = href if href.startswith("http") else f"{URLS[plat]}{href}"
                            if full_url not in existing_urls:
                                title = link.inner_text().split("\n")[0].strip() or f"{plat.capitalize()} Content"
                                img_src = get_image_with_backup(link)
                                new_contents.append({"p": plat, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": img_src})
                    platform_status[plat] = "✅"
                except Exception as e:
                    print(f"{plat.capitalize()} স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BIOSCOPE SPECIAL ---
        if (target == "all" or target == "bioscope") and URLS["bioscope_fetch"] and URLS["bioscope_base"]:
            try:
                page.goto(URLS["bioscope_fetch"], wait_until="domcontentloaded")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                links = page.query_selector_all("a[href*='/watch/'], a[href*='/movies/'], a[href*='/videos/']")
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"{URLS['bioscope_base']}{href}"
                        if full_url not in existing_urls:
                            title = link.inner_text().split("\n")[0].strip() or "Bioscope Content"
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
                                "p": "binge", "t": item.get("title", "Binge Content"), "url": full_url,
                                "native_date": item.get("release_date"), "dur": item.get("duration", "N/A"),
                                "img": item.get("thumb_image", "N/A")
                            })
                    platform_status["binge"] = "✅"
                else:
                    print(f"Binge API রেসপন্স কোড এরর: {res.status_code}")
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
                            title = title_el.get_attribute("alt") if title_el else f"{p_slug.capitalize()} Content"
                            new_contents.append({"p": p_code, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": "N/A"})
                    
                    # জাস্টওয়াচের প্রোপ্রাইটারি কোড ম্যাপ করে স্ট্যাটাস ওয়ান করা
                    for k in platform_status.keys():
                        if p_slug in k or k in p_slug:
                            platform_status[k] = "✅"
                except Exception as e:
                    print(f"JustWatch ({p_slug}) স্ক্র্যাপিং ব্যর্থ: {e}")

        browser.close()

    # -------------------------------------------------------------------
    # ৭. মেটাডেটা প্রসেসিং ও Multi-tiered Fallback Strategy প্রয়োগ
    # -------------------------------------------------------------------
    processed_new_items = []
    
    for item in new_contents:
        print(f"প্রসেস করা হচ্ছে: {item['t']} ({item['p']})")
        tmdb = enrich_with_tmdb(item["t"])
        
        # ৪-স্তরের ফলব্যাক ডেট লজিক
        final_date = item["native_date"]
        if not final_date or final_date == "N/A":
            final_date = tmdb["releaseDate"]
        if not final_date:
            final_date = CURRENT_DATE

        # কড়া ফিল্টার: যদি ডেট ভবিষ্যতের হয়, তবে স্কিপ (রিজেক্ট)
        if is_future_date(final_date):
            print(f"⚠️ ভবিষ্যতের কন্টেন্ট স্কিপ করা হলো: {item['t']} ({final_date})")
            continue

        # ইমেজের ব্যাকআপ লজিক
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
    # ৮. ডেটা মার্জিং ও সেভিং (পুরনো ডেটা অক্ষুণ্ণ রাখা)
    # -------------------------------------------------------------------
    # যদি গিটহাব ম্যানুয়াল রান নির্দিষ্ট সাইটের জন্য হয়, তবে শুধু বাকি সাইটগুলোর স্ট্যাটাস পুরনো জেসন দেখে আপডেট হবে
    if target != "all":
        for old_item in existing_data:
            op = old_item.get("p")
            for k, v in providers.items():
                if op == v and platform_status[k] == "❌":
                    platform_status[k] = "✅"
            if op in platform_status and platform_status[op] == "❌":
                platform_status[op] = "✅"

    updated_data = processed_new_items + existing_data
    
    # ডেটা ফাইল রাইট করা
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)

    # -------------------------------------------------------------------
    # ৯. এক্সিকিউটিভ টেলিগ্রাম মেসেজ ফরম্যাট
    # -------------------------------------------------------------------
    alert_msg = "Hello Boss, This Is Your Admin,\nReporting Scheduled Update:\n\n\n"
    
    # প্ল্যাটফর্মগুলোর নামের সিরিয়াল অনুযায়ী সাজানো
    order = ["chorki", "bioscope", "hoichoi", "bongo", "toffee", "binge", "utshob", "deepto", "netflix", "prime", "zee5", "sonyliv"]
    for p in order:
        display = "Prime Video" if p == "prime" else p.capitalize()
        alert_msg += f"{display} {platform_status[p]}\n"
        
    alert_msg += f"\nContent Added: {len(processed_new_items)} Totals after Merging with old data\n\n"
    alert_msg += "Contents Name:\n"
    
    if processed_new_items:
        for idx, item in enumerate(processed_new_items[:10], 1):
            alert_msg += f"{idx}. {item['t']}\n"
        if len(processed_new_items) > 10:
            alert_msg += f"...এবং আরও {len(processed_new_items) - 10}টি কন্টেন্ট।\n"
    else:
        alert_msg += "No new content found.\n"
        
    alert_msg += f"\nTotal contents in our database now: {len(updated_data)}"
    
    send_telegram_message(alert_msg)
    print("টেলিগ্রাম স্টেটমেন্ট রিপোর্ট পাঠানো হয়েছে সফলভাবে!")

if __name__ == "__main__":
    # কমান্ড লাইন আর্গুমেন্ট রিসিভ করার লজিক
    target_p = sys.argv[1] if len(sys.argv) > 1 else "all"
    scrape_platforms(target_p)