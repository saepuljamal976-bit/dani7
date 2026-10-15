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

# Inisialisasi AI Gemini
ai_model = None
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        for model_name in ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro']:
            try:
                ai_model = genai.GenerativeModel(model_name)
                print(f"🤖 Connected Gemini AI Model: {model_name}")
                break
            except Exception:
                continue
    except Exception as e:
        print(f"⚠️ Gagal inisialisasi Gemini: {e}")

total_saved = 0

# ==============================================================================
# JALUR 1: DIRECT SCRAPING KETERBUKAAN INFORMASI BEI / IDX (ZERO LAG / KILAT)
# ==============================================================================
print("\n⚡ === JALUR 1: SCRAPING KETERBUKAAN INFORMASI BEI (IDX DIRECT) ===")

def fetch_idx_announcements():
    global total_saved
    url = "https://www.idx.co.id/primary/NewsAnnouncement/GetAnnouncement?indexFrom=1&pageSize=5&lang=id"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.idx.co.id/"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            replies = data.get("Replies", [])
            print(f"   -> Ditemukan {len(replies)} pengumuman resmi BEI terbaru.")

            for item in replies:
                title = item.get("JudulPengumuman", "").strip()
                ticker = item.get("KodeEmiten", "").strip()
                pengumuman_id = str(item.get("ID", ""))
                link = f"https://www.idx.co.id/id/berita/pengumuman/{pengumuman_id}"

                if not title:
                    continue

                full_title = f"[{ticker}] {title}" if ticker else title
                print(f"🔎 Processing BEI Direct: {full_title[:50]}...")

                # Cek Duplikat di Supabase
                check = supabase.table("berita").select("id").eq("source_url", link).execute()
                if check.data:
                    print("   ⏭️ Sudah ada di DB (Skip).")
                    continue

                # Default Values
                summary_text = f"Pengumuman Resmi BEI dari emiten {ticker}: {title}"
                bullets_list = [
                    "Keterbukaan Informasi Resmi dari Bursa Efek Indonesia (BEI).",
                    f"Kode Emiten Terkait: {ticker}" if ticker else "Pengumuman pasar modal resmi.",
                    "Data diolah otomatis oleh Beritamology Engine."
                ]
                sentiment_val = "neutral"
                tickers_list = [ticker] if ticker else []
                action_signal = "Watchlist"
                risk_score = 3

                # Analisis AI Gemini untuk Pengumuman BEI
                if ai_model:
                    try:
                        prompt = f'''
                        Kamu adalah Head of Research & Chief Analyst Pasar Modal Indonesia (BEI).
                        Analisis Pengumuman Resmi Bursa Efek Indonesia berikut: "{full_title}"

                        TUGAS ANALISIS ANALIS INSTITUSI:
                        1. "tickers": Kode saham 4 huruf besar jika ada, misal ["{ticker}"].
                        2. "summary": Rangkuman 1-2 kalimat objektif mengenai dampak nyata ke emiten.
                        3. "bullets": Tulis tepat 3 poin analisis tajam:
                           - Poin 1: Dampak langsung ke pendapatan/operasional/sentimen emiten.
                           - Poin 2: Horizon Waktu (Reaksi Instan 1-3 hari ATAU Dampak Jangka Panjang).
                           - Poin 3: Risiko utama yang wajib diwaspadai investor.
                        4. "sentiment": "positive", "negative", atau "neutral".
                        5. "action_signal": "Bullish", "Watchlist", atau "Caution".
                        6. "risk_score": Skala 1-10.
                        7. "is_pompom": false (karena ini pengumuman resmi legal).

                        Output WAJIB berupa JSON murni tanpa markdown:
                        {{
                            "tickers": ["{ticker}"],
                            "summary": "...",
                            "bullets": ["...", "...", "..."],
                            "sentiment": "positive",
                            "action_signal": "Bullish",
                            "risk_score": 3,
                            "is_pompom": false
                        }}
                        '''
                        ai_res = ai_model.generate_content(prompt)
                        clean_res = ai_res.text.replace("```json", "").replace("```", "").strip()
                        ai_data = json.loads(clean_res)

                        summary_text = ai_data.get("summary", summary_text)
                        bullets_list = ai_data.get("bullets", bullets_list)
                        sentiment_val = ai_data.get("sentiment", "neutral")
                        tickers_list = ai_data.get("tickers", tickers_list)
                        action_signal = ai_data.get("action_signal", "Watchlist")
                        risk_score = ai_data.get("risk_score", 3)

                        bullets_list.append(f"📊 Signal AI: {action_signal} | Risk Index: {risk_score}/10")
                    except Exception as ai_err:
                        print(f"   ⚠️ AI Bypass BEI: {ai_err}")

                # Simpan ke Supabase
                payload = {
                    "title": full_title,
                    "summary": summary_text,
                    "bullets": bullets_list,
                    "tickers": tickers_list,
                    "category": "Pengumuman BEI",
                    "sentiment": sentiment_val,
                    "source_url": link,
                    "is_active": True
                }
                supabase.table("berita").insert(payload).execute()
                print("   ✅ SUCCESS SAVED BEI DIRECT TO DB!")
                total_saved += 1

        else:
            print(f"   ⚠️ BEI API Response Status: {res.status_code}")
    except Exception as e:
        print(f"   ❌ BEI Scraping Error: {e}")

fetch_idx_announcements()


# ==============================================================================
# JALUR 2: SCRAPING MEDIA FINANSIAL INDONESIA (ANTI-HOAX & ANTI-POMPOM)
# ==============================================================================
print("\n📡 === JALUR 2: SCRAPING MEDIA FINANSIAL INDONESIA (RSS) ===")

SOURCES = [
    {"name": "Detik Finance Bursa", "url": "https://finance.detik.com/bursa-dan-valas/rss"},
    {"name": "Sindonews Ekbis", "url": "https://ekbis.sindonews.com/rss"},
    {"name": "IDX Channel News", "url": "https://news.google.com/rss/search?q=site:idxchannel.com+saham&hl=id&gl=ID&ceid=ID:id"},
    {"name": "Kontan Investasi", "url": "https://news.google.com/rss/search?q=site:investasi.kontan.co.id&hl=id&gl=ID&ceid=ID:id"},
    {"name": "CNBC Indonesia Market", "url": "https://news.google.com/rss/search?q=site:cnbcindonesia.com/market&hl=id&gl=ID&ceid=ID:id"},
    {"name": "Bisnis.com Market", "url": "https://news.google.com/rss/search?q=site:market.bisnis.com&hl=id&gl=ID&ceid=ID:id"},
    {"name": "Investor.id Pasar Modal", "url": "https://news.google.com/rss/search?q=site:investor.id+saham&hl=id&gl=ID&ceid=ID:id"},
    {"name": "Antara Ekonomi", "url": "https://news.google.com/rss/search?q=site:antaranews.com/ekonomi&hl=id&gl=ID&ceid=ID:id"},
    {"name": "CNN Indonesia Ekonomi", "url": "https://news.google.com/rss/search?q=site:cnnindonesia.com/ekonomi+saham&hl=id&gl=ID&ceid=ID:id"},
    {"name": "Republika Ekonomi", "url": "https://news.google.com/rss/search?q=site:ekonomi.republika.co.id+saham&hl=id&gl=ID&ceid=ID:id"}
]

for src in SOURCES:
    print(f"\n📡 Scraping: {src['name']}")
    try:
        feed = feedparser.parse(src['url'])
        entries = feed.entries

        for entry in entries[:2]:
            title = getattr(entry, 'title', '').strip()
            link = getattr(entry, 'link', '').strip()

            if not title or not link:
                continue

            title_clean = title.rsplit(" - ", 1)[0] if " - " in title else title
            print(f"🔎 Memproses Media: {title_clean[:40]}...")

            try:
                check = supabase.table("berita").select("id").eq("source_url", link).execute()
                if check.data:
                    print("   ⏭️ Sudah ada di DB (Skip).")
                    continue
            except Exception as e:
                print(f"   ⚠️ DB Check Error: {e}")

            summary_text = title_clean
            bullets_list = [
                f"Sumber berita resmi dari {src['name']}.",
                "Pantau pergerakan emiten & IHSG terkait.",
                "Data diolah secara otomatis oleh Beritamology."
            ]
            sentiment_val = "neutral"
            tickers_list = []
            action_signal = "Watchlist"
            risk_score = 5

            if ai_model:
                try:
                    prompt = f'''
                    Kamu adalah Head of Research & Chief Analyst Pasar Modal Indonesia (BEI).
                    Analisis berita saham berikut secara objektif dan mendalam: "{title_clean}"

                    ATURAN FILTER ANTI-POMPOM & HOAX:
                    - Jika judul menggunakan kata sensasional (contoh: "siap ARA", "terbang ke langit", "target gila-gilaan", "rumor dicaplok") TANPA didukung keterbukaan informasi resmi BEI:
                      * Set "is_pompom": true
                      * Set "action_signal": "Caution"
                      * Set "risk_score": 8 atau lebih tinggi.

                    TUGAS ANALISIS ANALIS INSTITUSI:
                    1. "tickers": Kode saham 4 huruf besar (misal ["BBCA"]). Jika berita makro/umum, isi [].
                    2. "summary": Rangkuman 1-2 kalimat objektif mengenai dampak nyata ke emiten.
                    3. "bullets": Tulis tepat 3 poin analisis tajam:
                       - Poin 1: Dampak langsung ke pendapatan/operasional/sentimen emiten.
                       - Poin 2: Horizon Waktu (Reaksi Instan 1-3 hari ATAU Dampak Jangka Panjang).
                       - Poin 3: Risiko utama yang wajib diwaspadai investor.
                    4. "sentiment": "positive", "negative", atau "neutral".
                    5. "action_signal": "Bullish", "Watchlist", atau "Caution".
                    6. "risk_score": Skala 1-10 (1 = Sangat Aman, 10 = Risiko Tinggi/Spekulatif).

                    Output WAJIB berupa JSON murni tanpa markdown:
                    {{
                        "tickers": ["KODE"],
                        "summary": "...",
                        "bullets": ["...", "...", "..."],
                        "sentiment": "positive",
                        "action_signal": "Bullish",
                        "risk_score": 3,
                        "is_pompom": false
                    }}
                    '''
                    ai_res = ai_model.generate_content(prompt)
                    clean_res = ai_res.text.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean_res)

                    summary_text = data.get("summary", summary_text)
                    bullets_list = data.get("bullets", bullets_list)
                    sentiment_val = data.get("sentiment", "neutral")
                    tickers_list = data.get("tickers", [])
                    action_signal = data.get("action_signal", "Watchlist")
                    risk_score = data.get("risk_score", 5)
                    is_pompom = data.get("is_pompom", False)

                    if is_pompom:
                        bullets_list.insert(0, "⚠️ PERINGATAN AI: Berita terindikasi kata-kata sensasional / rumor spekulatif.")

                    bullets_list.append(f"📊 Signal AI: {action_signal} | Risk Index: {risk_score}/10")
                except Exception as ai_err:
                    print(f"   ⚠️ AI Bypass: {ai_err}")

            try:
                payload = {
                    "title": title_clean,
                    "summary": summary_text,
                    "bullets": bullets_list,
                    "tickers": tickers_list,
                    "category": "Saham Indo",
                    "sentiment": sentiment_val,
                    "source_url": link,
                    "is_active": True
                }
                supabase.table("berita").insert(payload).execute()
                print("   ✅ SUCCESS SAVED MEDIA TO DB!")
                total_saved += 1
            except Exception as ins_err:
                print(f"   ❌ Gagal Simpan: {ins_err}")

    except Exception as err:
        print(f"   ❌ Error pada {src['name']}: {err}")

print(f"\n🎉 === BOT SELESAI! Total {total_saved} Berita & Pengumuman BEI Tersimpan ===")
