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

# ওটিটি সাইটের ইউআরএল (ভ্যারিয়েবল থেকে)
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

# -------------------------------------------------------------------
# ২. টেলিগ্রাম বট রিপোর্টিং ফাংশন
# -------------------------------------------------------------------
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("টেলিগ্রাম ক্রেডেনশিয়াল মিসিং, মেসেজ স্কিপ করা হলো।")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"টেলিগ্রাম মেসেজ পাঠাতে ব্যর্থ: {e}")

# -------------------------------------------------------------------
# ৩. TMDB মেটাডেটা এনরিচমেন্ট লজিক (Fallback & Details)
# -------------------------------------------------------------------
def enrich_with_tmdb(title):
    fallback_data = {"tmdb_id": None, "rating": "N/A", "overview": "N/A", "releaseDate": None}
    if not TMDB_API_KEY or not title:
        return fallback_data
    
    # TMDB তে সার্চ করা
    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language=bn-BD"
    try:
        response = requests.get(search_url, timeout=10).json()
        results = response.get("results", [])
        if not results:
            # বাংলা বর্ণমালায় না পাওয়া গেলে গ্লোবাল সার্চ (English)
            search_url_en = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}"
            response = requests.get(search_url_en, timeout=10).json()
            results = response.get("results", [])

        if results:
            match = results[0]
            # মুভি বা সিরিজের রিলিজ ডেট খোঁজা
            r_date = match.get("release_date") or match.get("first_air_date")
            
            return {
                "tmdb_id": match.get("id"),
                "rating": match.get("vote_average", "N/A"),
                "overview": match.get("overview") or "N/A",
                "releaseDate": r_date if r_date else None
            }
    except Exception as e:
        print(f"TMDB সার্চ এরর ({title}): {e}")
    
    return fallback_data

# -------------------------------------------------------------------
# ৪. পুরনো ডেটা লোড ও ক্যাশ প্রোটেকশন লজিক (Level 2 & Level 3 Rescue)
# -------------------------------------------------------------------
def load_existing_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("পুরনো data.json ফাইলটি করাপ্টেড, ব্যাকআপ রিকভারি ট্রাই করা হচ্ছে।")
    return []

# -------------------------------------------------------------------
# ৫. মূল স্ক্র্যাপিং মেকানিজম (Playwright & API Fetch)
# -------------------------------------------------------------------
def scrape_platforms():
    existing_data = load_existing_data()
    # ডুপ্লিকেট চেকিংয়ের জন্য ইউআরএল এর একটি সেট তৈরি
    existing_urls = {item["url"] for item in existing_data if "url" in item}
    
    new_contents = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36").new_page()

        # --- CHORKI SCRAPER ---
        if URLS["chorki"]:
            try:
                page.goto(URLS["chorki"], timeout=60000)
                page.wait_for_load_state("networkidle")
                # ডাইনামিক গ্রিড বা কন্টেন্ট কার্ড খোঁজা
                cards = page.query_selector_all("a[href*='/shows/'], a[href*='/movies/']")
                for card in cards:
                    href = card.get_attribute("href")
                    full_url = href if href.startswith("http") else f"{URLS['chorki']}{href}"
                    if full_url not in existing_urls:
                        title = card.inner_text().split("\n")[0].strip() or "Chorki Content"
                        new_contents.append({"p": "chorki", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": "N/A"})
            except Exception as e:
                print(f"Chorki স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- HOICHOI SCRAPER ---
        if URLS["hoichoi"]:
            try:
                page.goto(URLS["hoichoi"], timeout=60000)
                cards = page.query_selector_all("a[href*='/play/']")
                for card in cards:
                    href = card.get_attribute("href")
                    full_url = href if href.startswith("http") else f"https://www.hoichoi.tv{href}"
                    if full_url not in existing_urls:
                        title = card.get_attribute("title") or "Hoichoi Content"
                        new_contents.append({"p": "hoichoi", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": "N/A"})
            except Exception as e:
                print(f"Hoichoi স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- GOTIPATH PLATFORMS (Utshob, Deepto, Bioscope) ---
        for plat in ["utshob", "deepto"]:
            if URLS[plat]:
                try:
                    page.goto(URLS[plat], timeout=60000)
                    links = page.query_selector_all("a[href*='/watch/']")
                    for link in links:
                        href = link.get_attribute("href")
                        full_url = href if href.startswith("http") else f"{URLS[plat]}{href}"
                        if full_url not in existing_urls:
                            title = link.inner_text().strip() or f"{plat.capitalize()} Content"
                            new_contents.append({"p": plat, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": "N/A"})
                except Exception as e:
                    print(f"{plat.capitalize()} স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BIOSCOPE SPECIAL ---
        if URLS["bioscope_fetch"] and URLS["bioscope_base"]:
            try:
                page.goto(URLS["bioscope_fetch"], timeout=60000)
                links = page.query_selector_all("a[href*='/watch/']")
                for link in links:
                    href = link.get_attribute("href")
                    full_url = href if href.startswith("http") else f"{URLS['bioscope_base']}{href}"
                    if full_url not in existing_urls:
                        title = link.inner_text().strip() or "Bioscope Content"
                        new_contents.append({"p": "bioscope", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": "N/A"})
            except Exception as e:
                print(f"Bioscope স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- BINGE API FETCH ---
        if URLS["binge"]:
            try:
                res = requests.get(URLS["binge"], timeout=15).json()
                for item in res.get("data", {}).get("contents", []):
                    slug = item.get("slug")
                    full_url = f"https://binge.buzz/watch/{slug}"
                    if full_url not in existing_urls:
                        new_contents.append({
                            "p": "binge",
                            "t": item.get("title", "Binge Content"),
                            "url": full_url,
                            "native_date": item.get("release_date"),
                            "dur": item.get("duration", "N/A"),
                            "img": item.get("thumb_image", "N/A")
                        })
            except Exception as e:
                print(f"Binge API স্ক্র্যাপিং ব্যর্থ: {e}")

        # --- JUSTWATCH INTERNATIONAL SCRAPER ---
        providers = {"netflix": "nfx", "prime": "amp", "zee5": "ze5", "sonyliv": "slv"}
        for p_slug, p_code in providers.items():
            try:
                jw_url = f"https://www.justwatch.com/in/provider/{p_slug}/new/movies"
                page.goto(jw_url, timeout=60000)
                page.wait_for_selector(".title-list-grid__item")
                items = page.query_selector_all(".title-list-grid__item a.title-list-grid__item--link")
                for item in items[:15]: # প্রতি প্ল্যাটফর্ম থেকে লেটেস্ট ১৫টি করে নেবে
                    href = item.get_attribute("href")
                    full_url = f"https://www.justwatch.com{href}"
                    if full_url not in existing_urls:
                        title_el = item.query_selector("img")
                        title = title_el.get_attribute("alt") if title_el else f"{p_slug.capitalize()} Content"
                        new_contents.append({"p": p_code, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": "N/A"})
            except Exception as e:
                print(f"JustWatch ({p_slug}) স্ক্র্যাপিং ব্যর্থ: {e}")

        browser.close()

    # -------------------------------------------------------------------
    # ৬. মেটাডেটা প্রসেসিং ও Multi-tiered Fallback Strategy প্রয়োগ
    # -------------------------------------------------------------------
    processed_new_items = []
    
    for item in new_contents:
        print(f"প্রসেস করা হচ্ছে: {item['t']} ({item['p']})")
        # TMDB থেকে অ্যাডভান্সড ডেটা ও ডেট খোঁজা
        tmdb = enrich_with_tmdb(item["t"])
        
        # Fallback লজিক নির্ধারণ: ১. ওটিটি ডেট -> ২. TMDB ডেট -> ৩. কারেন্ট রান টাইম স্ট্যাম্প
        final_date = item["native_date"]
        if not final_date or final_date == "N/A":
            final_date = tmdb["releaseDate"]
        if not final_date:
            final_date = CURRENT_DATE

        enriched_item = {
            "p": item["p"],
            "t": item["t"],
            "dur": item["dur"],
            "releaseDate": final_date,
            "img": item["img"],
            "url": item["url"],
            "tmdb_id": tmdb["tmdb_id"],
            "rating": tmdb["rating"],
            "overview": tmdb["overview"],
            "scraped_at": CURRENT_DATE
        }
        processed_new_items.append(enriched_item)

    # -------------------------------------------------------------------
    # ৭. ডেটা মার্জিং ও সেভিং (পুরনো ডেটা অক্ষুণ্ণ রাখা)
    # -------------------------------------------------------------------
    if processed_new_items:
        # নতুন ডেটাগুলোকে তালিকার শুরুতে রেখে পুরনো ডেটা পরে অ্যাপেন্ড করা হবে (Latest First)
        updated_data = processed_new_items + existing_data
        
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_data, f, ensure_ascii=False, indent=2)
            
        # টেলিগ্রামে অ্যালার্ট পাঠানো
        alert_msg = f"🚀 *STREAMguide নতুন কন্টেন্ট আপডেট!*\n\n"
        for i in processed_new_items[:10]: # সর্বোচ্চ ১০টি কন্টেন্টের লিস্ট বটের মাধ্যমে পাঠাবে
            alert_msg += f"🎬 *{i['t']}* ({i['p'].upper()})\n📅 ডেট: {i['releaseDate']} | ⭐ রেটিং: {i['rating']}\n🔗 [লিংক দেখুন]({i['url']})\n\n"
        
        if len(processed_new_items) > 10:
            alert_msg += f"➕ আরও {len(processed_new_items) - 10}টি কন্টেন্ট ব্যাকএন্ডে যুক্ত করা হয়েছে।"
            
        send_telegram_message(alert_msg)
        print(f"সফলভাবে {len(processed_new_items)}টি নতুন কন্টেন্ট যোগ করা হয়েছে!")
    else:
        print("নতুন কোনো রিলিজ খুঁজে পাওয়া যায়নি। ডেটাবেজ আপ-টু-ডেট আছে।")

if __name__ == "__main__":
    scrape_platforms()