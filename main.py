import os
import json
import requests
import feedparser
import google.generativeai as genai
from supabase import create_client

# 1. KONEKSI
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

genai.configure(api_key=GEMINI_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 2. SUMBER RSS
RSS_URLS = [
    "https://www.cnbcindonesia.com/market/rss",
    "https://investasi.kontan.co.id/rss",
    "https://market.bisnis.com/rss"
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

print("🚀 === MEMULAI BOT BERITAMOLOGY ===")

for url in RSS_URLS:
    print(f"\n📡 Scraping: {url}")
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        feed = feedparser.parse(res.content)
        print(f"-> Ditemukan {len(feed.entries)} artikel.")

        for entry in feed.entries[:3]:
            title = entry.title
            link = entry.link

            # Cek Duplikat
            check = supabase.table("berita").select("id").eq("source_url", link).execute()
            if check.data:
                print(f"⏭️  [Ada] {title[:30]}...")
                continue

            # Default Data (Jika AI Error, data ini yang dipakai)
            summary_text = title
            bullets_list = ["Berita pasar keuangan terkini.", "Pantau pergerakan harga saham terkait.", "Data diperbarui otomatis."]
            sentiment_val = "neutral"
            tickers_list = []

            # Coba Olah Pakai AI
            try:
                prompt = f"""Analisis berita saham ini: "{title}".
                Output Wajib JSON murni:
                {{
                  "tickers": ["KODE_SAHAM_JIKA_ADA"],
                  "summary": "Ringkasan 1 kalimat",
                  "bullets": ["Poin 1", "Poin 2", "Poin 3"],
                  "sentiment": "green/red/neutral"
                }}"""
                
                ai_res = model.generate_content(prompt)
                clean = ai_res.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean)
                
                summary_text = data.get("summary", summary_text)
                bullets_list = data.get("bullets", bullets_list)
                sentiment_val = data.get("sentiment", "neutral")
                tickers_list = data.get("tickers", [])
                print(f"🤖 AI Success untuk: {title[:30]}...")
            except Exception as e:
                print(f"⚠️ AI Bypass (Tetap Simpan): {e}")

            # Tetap Simpan ke Supabase Apapun Yang Terjadi
            insert_res = supabase.table("berita").insert({
                "title": title,
                "summary": summary_text,
                "bullets": bullets_list,
                "tickers": tickers_list,
                "category": "Saham Indo",
                "sentiment": sentiment_val,
                "source_url": link,
                "is_active": True
            }).execute()

            print(f"✅ SUCCESS SAVED: {title[:40]}...")

    except Exception as err:
        print(f"❌ Feed Error: {err}")

print("\n🎉 === BOT SELESAI ===")
