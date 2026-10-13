import os
import json
import requests
import feedparser
import google.generativeai as genai
from supabase import create_client

# 1. KONEKSI SUPABASE & GEMINI AI
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: Secrets Supabase belum terpasang.")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Inisialisasi AI Gemini dengan fallback beberapa nama model aktif
ai_model = None
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    for m_name in ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.0-flash', 'gemini-1.5-pro']:
        try:
            ai_model = genai.GenerativeModel(m_name)
            print(f"🤖 Connected to Gemini AI: {m_name}")
            break
        except Exception:
            continue

# 2. DAFTAR 10 MEDIA FINANSIAL & PASAR MODAL INDONESIA TIER-1 (Bebas Hoax)
SOURCES = [
    {
        "name": "IDX Channel (Resmi BEI)",
        "url": "https://www.idxchannel.com/market-news/rss"
    },
    {
        "name": "Kontan Investasi",
        "url": "https://investasi.kontan.co.id/rss"
    },
    {
        "name": "CNBC Indonesia Market",
        "url": "https://www.cnbcindonesia.com/market/rss"
    },
    {
        "name": "Bisnis.com Market",
        "url": "https://market.bisnis.com/rss"
    },
    {
        "name": "Antara Bursa & Valas",
        "url": "https://www.antaranews.com/rss/ekonomi-bursa-dan-valas.xml"
    },
    {
        "name": "Investor Daily (Investor.id)",
        "url": "https://investor.id/rss"
    },
    {
        "name": "Detik Finance Bursa",
        "url": "https://finance.detik.com/bursa-dan-valas/rss"
    },
    {
        "name": "CNN Indonesia Ekonomi",
        "url": "https://www.cnnindonesia.com/ekonomi/rss"
    },
    {
        "name": "Sindonews Ekbis",
        "url": "https://ekbis.sindonews.com/rss"
    },
    {
        "name": "Republika Ekonomi",
        "url": "https://ekonomi.republika.co.id/rss"
    }
]

# Header Browser Lengkap untuk bypass proteksi server
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
})

print("\n🚀 === MEMULAI BOT BERITAMOLOGY (PASAR MODAL INDONESIA) ===")

total_saved = 0

for src in SOURCES:
    print(f"\n📡 Scraping: {src['name']} ({src['url']})")
    try:
        # Ambil konten RSS
        response = session.get(src['url'], timeout=10)
        
        if response.status_code != 200:
            print(f"   ⚠️ HTTP {response.status_code}, mencoba parse alternatif...")
            feed = feedparser.parse(src['url'])
        else:
            feed = feedparser.parse(response.content)

        entries = feed.entries
        print(f"   -> Ditemukan {len(entries)} artikel.")

        for entry in entries[:2]:  # Ambil 2 artikel paling baru per media
            title = getattr(entry, 'title', '').strip()
            link = getattr(entry, 'link', '').strip()

            if not title or not link:
                continue

            print(f"\n🔎 Memproses: {title[:40]}...")

            # 1. Cek Duplikat di Supabase
            try:
                check = supabase.table("berita").select("id").eq("source_url", link).execute()
                if check.data:
                    print("   ⏭️ Sudah ada di DB (Skip).")
                    continue
            except Exception as e:
                print(f"   ⚠️ Cek DB Error: {e}")

            # Defaults jika AI offline
            summary_text = title
            bullets_list = [
                f"Sumber berita resmi: {src['name']}.",
                "Pantau pergerakan emiten & IHSG terkait.",
                "Data diolah secara otomatis oleh Beritamology."
            ]
            sentiment_val = "neutral"
            tickers_list = []

            # 2. Analisis dengan AI Gemini (Khusus Saham BEI/IDX)
            if ai_model:
                try:
                    prompt = f'''
                    Kamu adalah Analis Senior Pasar Modal Indonesia (BEI/IDX).
                    Analisis judul berita saham berikut: "{title}"

                    Instruksi:
                    1. Identifikasi ticker kode saham Indonesia 4 huruf jika ada (contoh: ["BBCA", "TLKM", "BMRI"]). Jika tidak ada, isi [].
                    2. Buat rangkuman singkat (maksimal 2 kalimat).
                    3. Buat 3 poin utama (bullet points).
                    4. Tentukan sentimen terhadap pasar/emiten: "positive", "negative", atau "neutral".

                    Output WAJIB berupa JSON murni tanpa format markdown:
                    {{"tickers": ["KODE"], "summary": "Rangkuman...", "bullets": ["Poin 1", "Poin 2", "Poin 3"], "sentiment": "positive"}}
                    '''
                    
                    ai_res = ai_model.generate_content(prompt)
                    clean_res = ai_res.text.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean_res)

                    summary_text = data.get("summary", summary_text)
                    bullets_list = data.get("bullets", bullets_list)
                    sentiment_val = data.get("sentiment", "neutral")
                    tickers_list = data.get("tickers", [])
                    print("   🤖 Gemini AI Sukses Menganalisis.")
                except Exception as ai_err:
                    print(f"   ⚠️ AI Bypass: {ai_err}")

            # 3. Simpan ke Supabase
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
                total_saved += 1
            except Exception as ins_err:
                print(f"   ❌ Gagal simpan ke Supabase: {ins_err}")

    except Exception as err:
        print(f"   ❌ Error saat mengambil dari {src['name']}: {err}")

print(f"\n🎉 === BOT SELESAI! Total {total_saved} Berita Baru Tersimpan di Supabase ===")
