import json
import os
import requests
import datetime

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "YOUR_TMDB_KEY_IF_LOCAL")
DATA_FILE = "data.json"
CURRENT_DATE = datetime.datetime.now().strftime("%Y-%m-%d")

def fix_and_clean_database():
    if not os.path.exists(DATA_FILE):
        print("data.json ফাইলটি পাওয়া যায়নি!")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        database = json.load(f)

    cleaned_database = []
    fixed_count = 0
    removed_count = 0

    print(f"টোটাল কন্টেন্ট স্ক্যান করা হচ্ছে: {len(database)}")

    for item in database:
        # ১. ভবিষ্যতের ডেট ফিল্টার (যেমন ২০৩১ বা কারেন্ট ডেটের চেয়ে বড় হলে রিমুভ)
        r_date = item.get("releaseDate")
        if r_date and r_date > CURRENT_DATE:
            print(f"❌ ভবিষ্যতের কন্টেন্ট রিমুভ করা হলো: {item['t']} ({r_date})")
            removed_count += 1
            continue

        # ২. নো-ইমেজ বা ডেটা মিসিং থাকলে TMDB থেকে রিকভারি
        if not item.get("img") or item["img"] == "N/A" or "No Image" in item.get("img", ""):
            print(f"🔍 ইমেজ নেই, TMDB থেকে খোঁজা হচ্ছে: {item['t']}")
            search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={item['t']}"
            try:
                res = requests.get(search_url, timeout=10).json().get("results", [])
                if res:
                    match = res[0]
                    poster_path = match.get("poster_path")
                    if poster_path:
                        item["img"] = f"https://image.tmdb.org/t/p/w500{poster_path}"
                    
                    # ডেটও যদি ফিক্স করা লাগে
                    if not item.get("releaseDate") or item["releaseDate"] == CURRENT_DATE:
                        tmdb_date = match.get("release_date") or match.get("first_air_date")
                        if tmdb_date and tmdb_date <= CURRENT_DATE:
                            item["releaseDate"] = tmdb_date
                    
                    # মেটাডেটা রিকভারি
                    item["rating"] = match.get("vote_average", item.get("rating", "N/A"))
                    item["overview"] = match.get("overview", item.get("overview", "N/A"))
                    fixed_count += 1
                    print(f"✅ সফলভাবে ফিক্সড: {item['t']}")
            except Exception as e:
                print(f"TMDB রিকভারি এরর: {e}")

        cleaned_database.append(item)

    # ফিক্সড ডেটা সেভ করা
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned_database, f, ensure_ascii=False, indent=2)

    print("\n=== ক্লিনিং রিপোর্ট ===")
    print(f"টোটাল কন্টেন্ট বাকি আছে: {len(cleaned_database)}")
    print(f"ভবিষ্যতের কন্টেন্ট ডিলিট হয়েছে: {removed_count}টি")
    print(f"ছবি ও ডেট ফিক্স করা হয়েছে: {fixed_count}টি")

if __name__ == "__main__":
    fix_and_clean_database()