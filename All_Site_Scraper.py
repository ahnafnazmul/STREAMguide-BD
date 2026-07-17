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
BLACKLIST_FILE = "blacklist.txt"
DELETELIST_FILE = "deletelist.txt"
CURRENT_DATE = datetime.datetime.now().strftime("%Y-%m-%d")

# -------------------------------------------------------------------
# ২. হেল্পার ফাংশনসমূহ
# -------------------------------------------------------------------
def load_txt_list(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    return []

def is_future_date(date_str):
    if not date_str or date_str == "N/A": return False
    try:
        input_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        return input_date > datetime.datetime.now().date()
    except Exception:
        return False

def get_image_with_backup(element):
    if not element: return "N/A"
    try:
        img_el = element if element.name == "img" else element.query_selector("img")
        if img_el:
            for attr in ["src", "data-src", "data-srcset", "srcset"]:
                val = img_el.get_attribute(attr)
                if val and val.startswith("http"): return val.split(" ")[0]
    except Exception:
        pass
    return "N/A"

def clean_error_msg(e):
    err_str = str(e).split('\n')[0]
    if "Timeout" in err_str: return "Timeout Error"
    if "net::ERR_" in err_str: return "Network Connection Error"
    if "Navigation" in err_str: return "Navigation Failed"
    return err_str[:25] + "..." if len(err_str) > 25 else err_str

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("টেলিগ্রাম ক্রেডেনশিয়াল মিসিং, মেসেজ স্কিপ করা হলো।")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"টেলিগ্রাম মেসেজ পাঠাতে ব্যর্থ: {e}")

def enrich_with_tmdb(title):
    fallback = {"tmdb_id": None, "rating": 0.0, "overview": "N/A", "releaseDate": None, "img": "N/A"}
    if not TMDB_API_KEY or not title: return fallback
    try:
        res = requests.get(f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language=bn-BD", timeout=10).json().get("results", [])
        if not res:
            res = requests.get(f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}", timeout=10).json().get("results", [])
        if res:
            m = res[0]
            r_date = m.get("release_date") or m.get("first_air_date")
            p_path = m.get("poster_path")
            return {
                "tmdb_id": m.get("id"),
                "rating": round(m.get("vote_average", 0.0), 1),
                "overview": m.get("overview") or "N/A",
                "releaseDate": r_date if r_date else None,
                "img": f"https://image.tmdb.org/t/p/w500{p_path}" if p_path else "N/A"
            }
    except Exception:
        pass
    return fallback

def load_existing_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception:
            print("পুরনো data.json ফাইলটি করাপ্টেড।")
    return []

# -------------------------------------------------------------------
# ৩. মূল স্ক্র্যাপিং মেকানিজম
# -------------------------------------------------------------------
def scrape_platforms(target="all"):
    print(f"[{CURRENT_DATE}] 🚀 স্ক্র্যাপিং প্রসেস শুরু হচ্ছে...", flush=True)
    existing_data = load_existing_data()
    
    delete_kws = load_txt_list(DELETELIST_FILE)
    if delete_kws:
        initial_len = len(existing_data)
        existing_data = [i for i in existing_data if not any(dk in i.get("t", "").lower() for dk in delete_kws)]
        print(f"🗑️ Deletelist অনুযায়ী {initial_len - len(existing_data)} টি আইটেম রিমুভ করা হয়েছে।", flush=True)
        with open(DELETELIST_FILE, "w", encoding="utf-8") as f: f.write("")

    existing_urls = {item["url"] for item in existing_data if "url" in item}
    global_blacklist = load_txt_list(BLACKLIST_FILE)
    new_contents = []
    
    providers_list = ["chorki", "bioscope", "hoichoi", "bongo", "toffee", "binge", "utshob", "deepto", "netflix", "prime", "zee5", "sonyliv"]
    p_stats = {p: {"new": 0, "merged": 0, "error": None, "status": "success"} for p in providers_list}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0")
        page = context.new_page()
        page.set_default_timeout(60000)

        # --- লোকাল প্ল্যাটফর্মগুলো ---
        local_platforms = {"chorki": "a[href*='/show'], a[href*='/movie']", 
                           "hoichoi": "a[href*='/play/'], a[href*='/shows/'], a[href*='/movies/']",
                           "bongo": "a[href*='/watch/']"}
        
        for plat, selector in local_platforms.items():
            if target in ["all", plat] and URLS.get(plat):
                print(f"🔍 {plat.capitalize()} স্ক্র্যাপ করা হচ্ছে...", flush=True)
                try:
                    page.goto(URLS[plat], wait_until="domcontentloaded")
                    for _ in range(4): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2000)
                    for card in page.query_selector_all(selector):
                        href = card.get_attribute("href")
                        if href:
                            full_url = href if href.startswith("http") else f"{URLS[plat].split('.com')[0]}.com{href}" if ".com" in URLS[plat] else f"https://www.{plat}.net{href}"
                            if full_url in existing_urls:
                                p_stats[plat]["merged"] += 1
                            else:
                                title = card.get_attribute("title") or card.inner_text().split("\n")[0].strip() or (card.query_selector("img").get_attribute("alt") if card.query_selector("img") else "")
                                if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                                    new_contents.append({"p": plat, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": get_image_with_backup(card)})
                except Exception as e:
                    print(f"❌ {plat} Error: {e}", flush=True)
                    p_stats[plat].update({"status": "fail", "error": clean_error_msg(e)})

        # --- TOFFEE ---
        if target in ["all", "toffee"] and URLS.get("toffee"):
            print("🔍 Toffee স্ক্র্যাপ করা হচ্ছে...", flush=True)
            try:
                page.goto(URLS["toffee"], wait_until="domcontentloaded")
                for _ in range(3): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2000)
                for card in page.query_selector_all("a[href*='/movies/'], a[href*='/series/'], a[href*='/drama/']"):
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://toffeelive.com{href}"
                        if full_url in existing_urls:
                            p_stats["toffee"]["merged"] += 1
                        else:
                            title = card.inner_text().split("\n")[0].strip()
                            if title and not title.replace("_","").isalnum() and not any(bk in title.lower().strip() for bk in global_blacklist):
                                new_contents.append({"p": "toffee", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": get_image_with_backup(card)})
            except Exception as e:
                print(f"❌ Toffee Error: {e}", flush=True)
                p_stats["toffee"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- GOTIPATH (UTSHOB & DEEPTO) ---
        for plat in ["utshob", "deepto"]:
            if target in ["all", plat] and URLS.get(plat):
                print(f"🔍 {plat.capitalize()} স্ক্র্যাপ করা হচ্ছে...", flush=True)
                try:
                    page.goto(URLS[plat], wait_until="domcontentloaded")
                    for _ in range(4): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2500)
                    for link in page.query_selector_all("a[href*='/watch/'], a[href*='/films/'], a[href*='/shows/']"):
                        href = link.get_attribute("href")
                        if href:
                            full_url = href if href.startswith("http") else f"{URLS[plat]}{href}"
                            if full_url in existing_urls:
                                p_stats[plat]["merged"] += 1
                            else:
                                title = link.inner_text().split("\n")[0].strip()
                                if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                                    new_contents.append({"p": plat, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": get_image_with_backup(link)})
                except Exception as e:
                    print(f"❌ {plat} Error: {e}", flush=True)
                    p_stats[plat].update({"status": "fail", "error": clean_error_msg(e)})

        # --- BIOSCOPE ---
        if target in ["all", "bioscope"] and URLS.get("bioscope_fetch"):
            print("🔍 Bioscope স্ক্র্যাপ করা হচ্ছে...", flush=True)
            try:
                page.goto(URLS["bioscope_fetch"], wait_until="domcontentloaded")
                for _ in range(3): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2000)
                for link in page.query_selector_all("a[href*='/watch/'], a[href*='/movies/'], a[href*='/videos/']"):
                    href = link.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"{URLS.get('bioscope_base', '')}{href}"
                        if full_url in existing_urls:
                            p_stats["bioscope"]["merged"] += 1
                        else:
                            title = link.inner_text().split("\n")[0].strip()
                            if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                                new_contents.append({"p": "bioscope", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": get_image_with_backup(link)})
            except Exception as e:
                print(f"❌ Bioscope Error: {e}", flush=True)
                p_stats["bioscope"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- BINGE (API) ---
        if target in ["all", "binge"] and URLS.get("binge"):
            print("🔍 Binge API স্ক্র্যাপ করা হচ্ছে...", flush=True)
            try:
                res = requests.get(URLS["binge"], timeout=15).json()
                for item in res.get("data", {}).get("contents", []):
                    full_url = f"https://binge.buzz/watch/{item.get('slug')}"
                    if full_url in existing_urls:
                        p_stats["binge"]["merged"] += 1
                    else:
                        title = item.get("title")
                        if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                            new_contents.append({"p": "binge", "t": title, "url": full_url, "native_date": item.get("release_date"), "dur": item.get("duration", "N/A"), "img": item.get("thumb_image", "N/A")})
            except Exception as e:
                print(f"❌ Binge Error: {e}", flush=True)
                p_stats["binge"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- JUSTWATCH INTERNATIONAL (NETWORK INTERCEPTION FIX) ---
        # এই রুট ইন্টারসেপ্টর জাস্টওয়াচের ভারী ছবি এবং CSS ব্লক করে দেবে, যাতে পেজ লোড ফাস্ট হয়।
        def block_heavy_assets(route):
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
                route.abort()
            else:
                route.continue_()
                
        page.route("**/*", block_heavy_assets) # ব্লকার চালু

        jw_providers = {"netflix": "nfx", "prime": "amp", "zee5": "ze5", "sonyliv": "slv"}
        for p_slug, p_code in jw_providers.items():
            if target in ["all", p_slug]:
                print(f"⚡ JustWatch ({p_slug}) ফাস্ট-মোডে স্ক্র্যাপ করা হচ্ছে...", flush=True)
                try:
                    page.goto(f"https://www.justwatch.com/in/provider/{p_slug}/new", wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_selector(".title-list-grid__item", timeout=30000)
                    for _ in range(4): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(1500)
                    for item in page.query_selector_all(".title-list-grid__item a.title-list-grid__item--link")[:40]:
                        href = item.get_attribute("href")
                        full_url = f"https://www.justwatch.com{href}"
                        if full_url in existing_urls:
                            p_stats[p_slug]["merged"] += 1
                        else:
                            title_el = item.query_selector("img")
                            title = title_el.get_attribute("alt") if title_el else ""
                            if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                                new_contents.append({"p": p_code, "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": "N/A"})
                except Exception as e:
                    print(f"❌ JustWatch ({p_slug}) Error: {e}", flush=True)
                    p_stats[p_slug].update({"status": "fail", "error": clean_error_msg(e)})
                    
        page.unroute("**/*", block_heavy_assets) # ব্লকার বন্ধ

        browser.close()

    # -------------------------------------------------------------------
    # ৪. মেটাডেটা প্রসেসিং (TMDB)
    # -------------------------------------------------------------------
    processed_items = []
    rev_prov = {"nfx": "netflix", "amp": "prime", "ze5": "zee5", "slv": "sonyliv"}

    for item in new_contents:
        if any(bk in item["t"].lower().strip() for bk in global_blacklist): continue
        print(f"🔄 মেটাডেটা প্রসেস করা হচ্ছে: {item['t']} ({item['p']})", flush=True)
        
        tmdb = enrich_with_tmdb(item["t"])
        final_date = item["native_date"] or tmdb["releaseDate"] or CURRENT_DATE
        if is_future_date(final_date): continue
        
        final_img = item["img"] if item["img"] and item["img"] != "N/A" else tmdb["img"]
        processed_items.append({
            "p": item["p"], "t": item["t"], "dur": item["dur"], "releaseDate": final_date,
            "img": final_img, "url": item["url"], "tmdb_id": tmdb["tmdb_id"],
            "rating": tmdb["rating"], "overview": tmdb["overview"], "scraped_at": CURRENT_DATE
        })
        
        p_name = rev_prov.get(item["p"], item["p"])
        if p_name in p_stats:
            p_stats[p_name]["new"] += 1

    # -------------------------------------------------------------------
    # ৫. ডাটাবেজ আপডেট
    # -------------------------------------------------------------------
    updated_data = processed_items + existing_data
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)
    print(f"✅ ডাটাবেজ আপডেট সম্পন্ন। মোট কন্টেন্ট: {len(updated_data)}", flush=True)

    # -------------------------------------------------------------------
    # ৬. টেলিগ্রাম রিপোর্ট (সঠিক লজিক সহ)
    # -------------------------------------------------------------------
    alert_msg = "Hello Boss, This Is Your Admin,\nReporting Scheduled Update:\n\n"
    
    for p in providers_list:
        display = "Prime Video" if p == "prime" else p.capitalize()
        s = p_stats[p]
        
        if s["status"] == "fail":
            sign = f"❌ ({s['error']})"
        else:
            if s["new"] == 0 and s["merged"] == 0:
                sign = "✅"
            elif s["new"] == 0 and s["merged"] > 0:
                # যদি নতুন না থাকে কিন্তু পুরনো মার্জ হয়, তাও জাস্ট ✅ দেখাবে
                sign = "✅"
            elif s["new"] > 0 and s["merged"] > 0:
                sign = f"🔰 {s['new']}, 🔁 {s['merged']}"
            else:
                sign = f"🔰 {s['new']}"
                
        alert_msg += f"{display}: {sign}\n"
        
    alert_msg += "\nNew Contents List:\n"
    
    if processed_items:
        for idx, item in enumerate(processed_items, 1):
            alert_msg += f"{idx}. {item['t']}\n"
    else:
        alert_msg += "No new content found in this session.\n"
        
    alert_msg += f"\nTotal contents in our database now: {len(updated_data)}"
    
    send_telegram_message(alert_msg)
    print("🚀 সব প্রসেস শেষ! টেলিগ্রাম রিপোর্ট সেন্ড করা হয়েছে।", flush=True)

if __name__ == "__main__":
    target_p = sys.argv[1] if len(sys.argv) > 1 else "all"
    scrape_platforms(target_p)