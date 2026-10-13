import os
import json
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

# Inisialisasi AI Gemini Secara Otomatis dari Model yang Aktif
ai_model = None
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # Cari model yang aktif dan mendukung generateContent
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        # Prioritaskan model flash/pro yang tersedia
        selected_model = None
        for pref in ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']:
            matching = [m for m in available_models if pref in m]
            if matching:
                selected_model = matching[0]
                break
        
        if not selected_model and available_models:
            selected_model = available_models[0]
            
        if selected_model:
            ai_model = genai.GenerativeModel(selected_model)
            print(f"🤖 Connected Gemini AI Model: {selected_model}")
    except Exception as e:
        print(f"⚠️ Gagal inisialisasi Gemini: {e}")

# 2. DAFTAR SUMBER BERITA FINANSIAL TIER-1 (Jalur Direct + Google News RSS Bypass 403)
SOURCES = [
    {
        "name": "Detik Finance Bursa",
        "url": "https://finance.detik.com/bursa-dan-valas/rss"
    },
    {
        "name": "Sindonews Ekbis",
        "url": "https://ekbis.sindonews.com/rss"
    },
    {
        "name": "IDX Channel",
        "url": "https://news.google.com/rss/search?q=site:idxchannel.com+saham&hl=id&gl=ID&ceid=ID:id"
    },
    {
        "name": "Kontan Investasi",
        "url": "https://news.google.com/rss/search?q=site:investasi.kontan.co.id&hl=id&gl=ID&ceid=ID:id"
    },
    {
        "name": "CNBC Indonesia Market",
        "url": "https://news.google.com/rss/search?q=site:cnbcindonesia.com/market&hl=id&gl=ID&ceid=ID:id"
    },
    {
        "name": "Bisnis.com Market",
        "url": "https://news.google.com/rss/search?q=site:market.bisnis.com&hl=id&gl=ID&ceid=ID:id"
    },
    {
        "name": "Investor.id Pasar Modal",
        "url": "https://news.google.com/rss/search?q=site:investor.id+saham&hl=id&gl=ID&ceid=ID:id"
    },
    {
        "name": "Antara Ekonomi",
        "url": "https://news.google.com/rss/search?q=site:antaranews.com/ekonomi&hl=id&gl=ID&ceid=ID:id"
    }
]

print("\n🚀 === MEMULAI BOT BERITAMOLOGY (SAHAM INDONESIA) ===")

total_saved = 0

for src in SOURCES:
    print(f"\n📡 Scraping: {src['name']}")
    try:
        feed = feedparser.parse(src['url'])
        entries = feed.entries
        print(f"   -> Ditemukan {len(entries)} artikel.")

        for entry in entries[:2]:  # Ambil 2 berita terbaru per sumber
            title = getattr(entry, 'title', '').strip()
            link = getattr(entry, 'link', '').strip()

            if not title or not link:
                continue

            # Bersihkan akhiran nama media dari judul jika ada (contoh: "... - CNBC Indonesia")
            if " - " in title:
                title_clean = title.rsplit(" - ", 1)[0]
            else:
                title_clean = title

            print(f"🔎 Memproses: {title_clean[:45]}...")

            # 1. Cek Duplikat di Supabase
            try:
                check = supabase.table("berita").select("id").eq("source_url", link).execute()
                if check.data:
                    print("   ⏭️ Sudah ada di Database (Skip).")
                    continue
            except Exception as e:
                print(f"   ⚠️ Cek DB Error: {e}")

            summary_text = title_clean
            bullets_list = [
                f"Sumber berita resmi dari {src['name']}.",
                "Pantau pergerakan emiten & IHSG terkait.",
                "Data diolah secara otomatis oleh Beritamology."
            ]
            sentiment_val = "neutral"
            tickers_list = []

            # 2. Analisis Berita dengan Gemini AI
            if ai_model:
                try:
                    prompt = f'''
                    Kamu adalah Analis Senior Pasar Modal Indonesia (BEI/IDX).
                    Analisis judul berita saham berikut: "{title_clean}"

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

            # 3. Simpan Ke Supabase
            try:
                supabase.table("berita").insert({
                    "title": title_clean,
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
                print(f"   ❌ Gagal Simpan: {ins_err}")

    except Exception as err:
        print(f"   ❌ Error pada {src['name']}: {err}")

print(f"\n🎉 === BOT SELESAI! Total {total_saved} Berita Baru Tersimpan di Supaba
