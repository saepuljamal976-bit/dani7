import os
import json
import feedparser
import google.generativeai as genai
from supabase import create_client

# 1. KONEKSI
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

# 2. SUMBER RSS (Domain Antara diperbaiki & tambah Sindonews)
RSS_URLS = [
    "https://www.antaranews.com/rss/ekonomi-bursa-dan-valas.xml",
    "https://ekbis.sindonews.com/rss",
    "https://www.cnbcindonesia.com/market/rss"
]

print("🚀 === MEMULAI BOT BERITAMOLOGY ===")

for url in RSS_URLS:
    print(f"\n📡 Scraping: {url}")
    try:
        # Trik: feedparser langsung buka URL tanpa lewat requests.get
        feed = feedparser.parse(url)
        print(f"-> Ditemukan {len(feed.entries)} artikel.")

        for entry in feed.entries[:3]:
            title = getattr(entry, 'title', '')
            link = getattr(entry, 'link', '')

            if not title or not link:
                continue

            print(f"🔎 Memproses: {title[:35]}...")

            # Cek Duplikat
            try:
                check = supabase.table("berita").select("id").eq("source_url", link).execute()
                if check.data:
                    print("   ⏭️ Sudah ada di DB, skip.")
                    continue
            except Exception as e:
                print(f"   ⚠️ Cek DB error: {e}")

            summary_text = title
            bullets_list = ["Berita pasar saham terbaru.", "Pantau pergerakan emiten terkait.", "Data diperbarui otomatis."]
            sentiment_val = "neutral"
            tickers_list = []

            # Olah dengan AI
            if model:
                try:
                    prompt = f'Analisis berita: "{title}". Output JSON murni: {{"tickers":[], "summary":"Ringkasan singkat","bullets":["Poin 1","Poin 2"],"sentiment":"neutral"}}'
                    ai_res = model.generate_content(prompt)
                    clean = ai_res.text.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean)
                    summary_text = data.get("summary", summary_text)
                    bullets_list = data.get("bullets", bullets_list)
                    sentiment_val = data.get("sentiment", "neutral")
                    tickers_list = data.get("tickers", [])
                    print("   🤖 AI Berhasil.")
                except Exception as ai_err:
                    print(f"   ⚠️ AI Bypass: {ai_err}")

            # Simpan ke Supabase
            try:
                supabase.table("berita").insert({
                    "title": title,
                    "summary": summary_text,
                    "bullets": bullets_list,
                    "tickers": tickers_list,
                    "category": "Saham Indo",
                    "sentiment": sentiment_val,
                    "source_url": link,
                    "is_active": True
                }).execute()
                print("   ✅ SUCCESS SAVED TO SUPABASE!")
            except Exception as ins_err:
                print(f"   ❌ Gagal Simpan: {ins_err}")

    except Exception as err:
        print(f"❌ Feed Error: {err}")

print("\n🎉 === BOT SELESAI ===")
