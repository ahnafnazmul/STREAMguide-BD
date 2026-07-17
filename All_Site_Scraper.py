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
    if not date_str or date_str == "N/A":
        return False
    try:
        input_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        return input_date > datetime.datetime.now().date()
    except Exception:
        return False

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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"টেলিগ্রাম মেসেজ পাঠাতে ব্যর্থ: {e}")

def enrich_with_tmdb(title):
    fallback = {"tmdb_id": None, "rating": 0.0, "overview": "N/A", "releaseDate": None, "img": "N/A"}
    if not TMDB_API_KEY or not title:
        return fallback
    search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={title}&language=bn-BD"
    try:
        res = requests.get(search_url, timeout=10).json().get("results", [])
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
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("পুরনো data.json ফাইলটি করাপ্টেড।")
    return []

# -------------------------------------------------------------------
# ৩. মূল স্ক্র্যাপিং মেকানিজম
# -------------------------------------------------------------------
def scrape_platforms(target="all"):
    existing_data = load_existing_data()
    
    # ডিলিট-লিস্ট লজিক
    delete_kws = load_txt_list(DELETELIST_FILE)
    if delete_kws:
        existing_data = [i for i in existing_data if not any(dk in i.get("t", "").lower() for dk in delete_kws)]
        with open(DELETELIST_FILE, "w", encoding="utf-8") as f: f.write("")

    existing_urls = {item["url"] for item in existing_data if "url" in item}
    global_blacklist = load_txt_list(BLACKLIST_FILE)
    new_contents = []
    
    providers_list = ["chorki", "bioscope", "hoichoi", "bongo", "toffee", "binge", "utshob", "deepto", "netflix", "prime", "zee5", "sonyliv"]
    
    # স্ট্যাটাস ট্র্যাকার
    p_stats = {p: {"new": 0, "merged": 0, "error": None, "status": "success"} for p in providers_list}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0")
        page = context.new_page()
        page.set_default_timeout(90000)

        # --- CHORKI ---
        if target in ["all", "chorki"] and URLS["chorki"]:
            try:
                page.goto(URLS["chorki"], wait_until="domcontentloaded")
                for _ in range(4): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2500)
                for card in page.query_selector_all("a[href*='/show'], a[href*='/movie']"):
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://www.chorki.net{href}"
                        if full_url in existing_urls:
                            p_stats["chorki"]["merged"] += 1
                        else:
                            title = card.inner_text().split("\n")[0].strip() or (card.query_selector("img").get_attribute("alt") if card.query_selector("img") else "")
                            if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                                new_contents.append({"p": "chorki", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": get_image_with_backup(card)})
            except Exception as e:
                p_stats["chorki"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- HOICHOI ---
        if target in ["all", "hoichoi"] and URLS["hoichoi"]:
            try:
                page.goto(URLS["hoichoi"], wait_until="domcontentloaded")
                for _ in range(4): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2000)
                for card in page.query_selector_all("a[href*='/play/'], a[href*='/shows/'], a[href*='/movies/']"):
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://www.hoichoi.tv{href}"
                        if full_url in existing_urls:
                            p_stats["hoichoi"]["merged"] += 1
                        else:
                            title = card.get_attribute("title") or card.inner_text().split("\n")[0].strip()
                            if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                                new_contents.append({"p": "hoichoi", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": get_image_with_backup(card)})
            except Exception as e:
                p_stats["hoichoi"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- BONGO ---
        if target in ["all", "bongo"] and URLS["bongo"]:
            try:
                page.goto(URLS["bongo"], wait_until="domcontentloaded")
                for _ in range(4): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2000)
                for card in page.query_selector_all("a[href*='/watch/']"):
                    href = card.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://bongobd.com{href}"
                        if full_url in existing_urls:
                            p_stats["bongo"]["merged"] += 1
                        else:
                            title = card.inner_text().split("\n")[0].strip()
                            if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                                new_contents.append({"p": "bongo", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": get_image_with_backup(card)})
            except Exception as e:
                p_stats["bongo"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- TOFFEE ---
        if target in ["all", "toffee"] and URLS["toffee"]:
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
                p_stats["toffee"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- GOTIPATH (UTSHOB & DEEPTO) ---
        for plat in ["utshob", "deepto"]:
            if target in ["all", plat] and URLS[plat]:
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
                    p_stats[plat].update({"status": "fail", "error": clean_error_msg(e)})

        # --- BIOSCOPE ---
        if target in ["all", "bioscope"] and URLS.get("bioscope_fetch"):
            try:
                page.goto(URLS["bioscope_fetch"], wait_until="domcontentloaded")
                for _ in range(3): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2000)
                for link in page.query_selector_all("a[href*='/watch/'], a[href*='/movies/'], a[href*='/videos/']"):
                    href = link.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"{URLS['bioscope_base']}{href}"
                        if full_url in existing_urls:
                            p_stats["bioscope"]["merged"] += 1
                        else:
                            title = link.inner_text().split("\n")[0].strip()
                            if title and not any(bk in title.lower().strip() for bk in global_blacklist):
                                new_contents.append({"p": "bioscope", "t": title, "url": full_url, "native_date": None, "dur": "N/A", "img": get_image_with_backup(link)})
            except Exception as e:
                p_stats["bioscope"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- BINGE ---
        if target in ["all", "binge"] and URLS["binge"]:
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
                p_stats["binge"].update({"status": "fail", "error": clean_error_msg(e)})

        # --- JUSTWATCH INTERNATIONAL ---
        jw_providers = {"netflix": "nfx", "prime": "amp", "zee5": "ze5", "sonyliv": "slv"}
        for p_slug, p_code in jw_providers.items():
            if target in ["all", p_slug]:
                try:
                    page.goto(f"https://www.justwatch.com/in/provider/{p_slug}/new", wait_until="commit", timeout=60000)
                    page.wait_for_selector(".title-list-grid__item", timeout=45000)
                    for _ in range(4): page.evaluate("window.scrollBy(0, window.innerHeight)"); page.wait_for_timeout(2500)
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
                    p_stats[p_slug].update({"status": "fail", "error": clean_error_msg(e)})

        browser.close()

    # -------------------------------------------------------------------
    # ৪. মেটাডেটা প্রসেসিং
    # -------------------------------------------------------------------
    processed_items = []
    rev_prov = {"nfx": "netflix", "amp": "prime", "ze5": "zee5", "slv": "sonyliv"}

    for item in new_contents:
        if any(bk in item["t"].lower().strip() for bk in global_blacklist): continue
        tmdb = enrich_with_tmdb(item["t"])
        final_date = item["native_date"] or tmdb["releaseDate"] or CURRENT_DATE
        if is_future_date(final_date): continue
        
        final_img = item["img"] if item["img"] and item["img"] != "N/A" else tmdb["img"]
        processed_items.append({
            "p": item["p"], "t": item["t"], "dur": item["dur"], "releaseDate": final_date,
            "img": final_img, "url": item["url"], "tmdb_id": tmdb["tmdb_id"],
            "rating": tmdb["rating"], "overview": tmdb["overview"], "scraped_at": CURRENT_DATE
        })
        
        # সফলভাবে অ্যাড হওয়া কাউন্ট আপডেট
        p_name = rev_prov.get(item["p"], item["p"])
        if p_name in p_stats:
            p_stats[p_name]["new"] += 1

    # -------------------------------------------------------------------
    # ৫. ডাটাবেজ আপডেট
    # -------------------------------------------------------------------
    updated_data = processed_items + existing_data
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, ensure_ascii=False, indent=2)

    # -------------------------------------------------------------------
    # ৬. টেলিগ্রাম রিপোর্ট (নতুন লজিক ও ইমোজি সহ)
    # -------------------------------------------------------------------
    alert_msg = "Hello Boss, This Is Your Admin,\nReporting Scheduled Update:\n\n"
    
    for p in providers_list:
        display = "Prime Video" if p == "prime" else p.capitalize()
        s = p_stats[p]
        
        if s["status"] == "fail":
            sign = f"❌ ({s['error']})"
        else:
            if s["new"] == 0:
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

if __name__ == "__main__":
    target_p = sys.argv[1] if len(sys.argv) > 1 else "all"
    scrape_platforms(target_p)