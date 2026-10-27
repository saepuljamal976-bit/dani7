import os
import json
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import google.generativeai as genai

# Load Environment Variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# Header wajib untuk API BEI/IDX agar tidak terblokir
IDX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.idx.co.id/",
    "Accept": "application/json, text/plain, */*"
}

# DAFTAR PORTAL MEDIA FINANSIAL
NEWS_FEEDS = [
    {"url": "https://www.cnbcindonesia.com/market/rss", "category": "Saham"},
    {"url": "https://www.cnbcindonesia.com/news/rss", "category": "Makro"},
    {"url": "https://investasi.kontan.co.id/rss", "category": "Saham"},
    {"url": "https://nasional.kontan.co.id/rss", "category": "Moneter"},
    {"url": "https://market.bisnis.com/rss", "category": "Saham"},
    {"url": "https://finansial.bisnis.com/rss", "category": "Fiskal"},
    {"url": "https://www.investor.id/rss/market", "category": "Saham"},
    {"url": "https://finance.detik.com/rss", "category": "Makro"},
    {"url": "https://www.antaranews.com/rss/ekonomi", "category": "Fiskal"},
]

def analyze_with_gemini(title, content=""):
    prompt = f"""
    Kamu adalah analis pasar modal Indonesia handal. Analisis berita/pengumuman berikut:
    Judul: "{title}"
    Isi: "{content}"

    Berikan output HANYA format JSON valid tanpa markdown kode (```json):
    {{
        "summary": "Rangkuman 1-2 kalimat padat & jelas.",
        "tickers": ["BBCA"], 
        "sentiment": "positive", 
        "bullets": ["Poin penting 1", "Poin penting 2", "Poin penting 3"]
    }}
    Catatan:
    - sentiment: "positive", "negative", atau "neutral".
    - tickers diisi kode saham terkait (misal ["BBCA"]). Jika tidak ada, isi [].
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        print(f"Error AI: {e}")
        return {"summary": title, "tickers": [], "sentiment": "neutral", "bullets": ["Berita bursa terbaru."]}

def fetch_idx_announcements():
    """Narik Keterbukaan Informasi & Pengumuman Resmi BEI Direct API"""
    url = "[https://www.idx.co.id/primary/Announcement/GetAnnouncementSearch?indexFrom=1&pageSize=5&locale=id-id](https://www.idx.co.id/primary/Announcement/GetAnnouncementSearch?indexFrom=1&pageSize=5&locale=id-id)"
    items = []
    try:
        res = requests.get(url, headers=IDX_HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for row in data.get("Results", []):
                title = row.get("JudulPengumuman") or row.get("Title", "")
                code = row.get("PengumumanKode") or row.get("NoPengumuman", "")
                emiten = row.get("KodeEmiten", "")
                link = f"[https://www.idx.co.id/id/berita/pengumuman-detail/?id=](https://www.idx.co.id/id/berita/pengumuman-detail/?id=){code}" if code else "[https://www.idx.co.id](https://www.idx.co.id)"
                if title:
                    full_title = f"[{emiten}] {title}" if emiten else title
                    items.append({"title": full_title, "link": link, "category": "Pengumuman BEI", "emiten": emiten})
    except Exception as e:
        print(f"⚠️ Skip API Pengumuman BEI: {e}")
    return items

def fetch_idx_news():
    """Narik Berita Resmi Portal Bursa (IDX Direct API)"""
    url = "[https://www.idx.co.id/primary/News/GetNewsSearch?indexFrom=1&pageSize=5&locale=id-id](https://www.idx.co.id/primary/News/GetNewsSearch?indexFrom=1&pageSize=5&locale=id-id)"
    items = []
    try:
        res = requests.get(url, headers=IDX_HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for row in data.get("Results", []):
                title = row.get("Title", "")
                item_id = row.get("ItemId", "")
                link = f"[https://www.idx.co.id/id/berita/berita-detail/?id=](https://www.idx.co.id/id/berita/berita-detail/?id=){item_id}" if item_id else "[https://www.idx.co.id](https://www.idx.co.id)"
                if title:
                    items.append({"title": title, "link": link, "category": "IDX"})
    except Exception as e:
        print(f"⚠️ Skip API Berita IDX: {e}")
    return items

def save_item(title, link, category, emiten=""):
    existing = supabase.table("berita").select("id").eq("source_url", link).execute()
    if existing.data:
        print(f"⏩ Sudah ada di DB: {title[:30]}...")
        return

    print(f"✨ Bedah [{category}]: {title[:40]}...")
    ai_result = analyze_with_gemini(title)

    tickers = ai_result.get("tickers", [])
    if emiten and emiten not in tickers:
        tickers.append(emiten)

    row = {
        "title": title,
        "summary": ai_result.get("summary", title),
        "category": category,
        "tickers": tickers,
        "sentiment": ai_result.get("sentiment", "neutral"),
        "bullets": ai_result.get("bullets", []),
        "source_url": link,
        "is_active": True
    }
    supabase.table("berita").insert(row).execute()
    print(f"✅ Tersimpan [{category}]: {title[:30]}...")

if __name__ == "__main__":
    print("🚀 Bot Scraper Kombinasi: Direct BEI/IDX + 9 Portal Media...")
    
    # 1. TARIK LANGSUNG DARI API BEI & IDX
    for item in fetch_idx_announcements():
        save_item(item["title"], item["link"], item["category"], item.get("emiten", ""))
        
    for item in fetch_idx_news():
        save_item(item["title"], item["link"], item["category"])

    # 2. TARIK DARI SEMUA PORTAL MEDIA FINANSIAL
    media_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for feed in NEWS_FEEDS:
        try:
            res = requests.get(feed["url"], headers=media_headers, timeout=10)
            soup = BeautifulSoup(res.content, "xml")
            items = soup.find_all("item")

            for item in items[:2]: # 2 berita terupdate per media
                title = item.title.text.strip() if item.title else ""
                link = item.link.text.strip() if item.link else ""
                if title and link:
                    save_item(title, link, feed["category"])
        except Exception as e:
            print(f"⚠️ Skip media feed {feed['url']}: {e}")
