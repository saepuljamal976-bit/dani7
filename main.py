import os
import json
import requests
import feedparser
import google.generativeai as genai
from supabase import create_client

# ==========================================
# 1. KONFIGURASI KUNCI API & KONEKSI
# ==========================================
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

genai.configure(api_key=GEMINI_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# ==========================================
# 2. SUMBER BERITA KREDIBEL (RSS FEEDS)
# ==========================================
RSS_URLS = [
    "https://www.cnbcindonesia.com/market/rss",      # CNBC Indonesia Market & Saham
    "https://investasi.kontan.co.id/rss",            # Kontan Investasi & Action Emiten
    "https://market.bisnis.com/rss",                 # Bisnis.com Market
    "https://antara-news.com/rss/ekonomi.xml"        # Antara Ekonomi & Makro Policy
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_active_topics():
    """Mengambil daftar topik/isu panas yang sedang AKTIF dari Supabase"""
    try:
        res = supabase.table("topik_panas").select("id, ticker, judul_isu").eq("status", "aktif").execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Peringatan: Gagal mengambil topik_panas (mungkin tabel belum dibuat): {e}")
        return []

def parse_and_process():
    print("🚀 === MEMULAI BOT BERITAMOLOGY ===")
    
    # Ambil topik panas aktif sebagai referensi Gemini AI
    active_topics = get_active_topics()
    print(f"Topik Aktif Saat Ini: {len(active_topics)} topik.")

    for url in RSS_URLS:
        print(f"\n📡 Membaca RSS Feed: {url}")
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            feed = feedparser.parse(response.content)
            print(f"-> Ditemukan {len(feed.entries)} artikel.")

            for entry in feed.entries[:4]:  # Ambil 4 berita paling gres per sumber
                title = entry.title
                link = entry.link

                # 1. Cek Duplikasi Berita di Supabase
                check = supabase.table("berita").select("id").eq("source_url", link).execute()
                if check.data:
                    print(f"⏭️  [Abaikan] Berita sudah ada: {title[:40]}...")
                    continue

                # 2. Prompt Gemini AI - Story Threading & Tagging Saham
                prompt = f"""
                Kamu adalah Analis Beritamology Finansial & Pasar Saham Indonesia (IDX)/Crypto.
                
                Analisis berita berikut:
                Judul Berita: "{title}"
                
                Daftar Topik Panas Aktif di Database saat ini:
                {json.dumps(active_topics, ensure_ascii=False)}

                Tugasmu:
                1. Identifikasi Kode Saham (Ticker IDX 4 huruf kapital, contoh: BBCA, FORU, GOTO, BMRI) atau Crypto (contoh: BTC, ETH). Jika tidak ada emiten spesifik, isi [].
                2. Buat ringkasan super padat 1-2 kalimat.
                3. Buat 3 poin utama (bullet points).
                4. Tentukan sentimen: "green" (bullish/positif), "red" (bearish/negatif), atau "neutral".
                5. Tentukan kategori: "Saham Indo", "Crypto", "Makro Ekonomi", atau "Global".
                6. Tentukan apakah ini Berita Panas / Hype / Impact Besar (is_hot = true/false).
                7. Analisis Alur Cerita (Story Threading):
                   - Jika berita ini BERHUBUNGAN/KELANJUTAN dari salah satu "Topik Panas Aktif" di atas, kembalikan:
                     "topic_action": "match", "matched_topic_id": <id_topik_terkait>
                   - Jika berita ini adalah ISU PANAS BARU yang punya alur cerita penting (misal: akuisisi, merger, rights issue, konflik direksi, laporan keuangan meledak), kembalikan:
                     "topic_action": "new", "new_topic_title": "<Judul Ringkas Isu Panas>", "new_topic_desc": "<Deskripsi singkat isu>"
                   - Jika hanya berita harian biasa tanpa alur khusus, kembalikan:
                     "topic_action": "none"

                Wajib Output JSON murni (TANPA tanda ```json):
                {{
                  "tickers": ["FORU"],
                  "summary": "Ringkasan cerita...",
                  "bullets": ["Poin 1", "Poin 2", "Poin 3"],
                  "sentiment": "green",
                  "category": "Saham Indo",
                  "is_hot": true,
                  "topic_action": "new",
                  "matched_topic_id": null,
                  "new_topic_title": "Rumor Akuisisi FORU",
                  "new_topic_desc": "Perusahaan B dikabarkan akan mengambil alih saham mayoritas FORU.",
                  "supersede_old_topics": true
                }}
                """

                try:
                    ai_res = model.generate_content(prompt)
                    clean_text = ai_res.text.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean_text)

                    tickers = data.get("tickers", [])
                    topic_id = None
                    topic_action = data.get("topic_action", "none")

                    # 3. Logika Penanganan Alur Cerita (Topik Panas)
                    if topic_action == "match" and data.get("matched_topic_id"):
                        topic_id = data.get("matched_topic_id")
                        print(f"🔗 [Thread Match] Berita dimasukkan ke Topik ID: {topic_id}")

                    elif topic_action == "new" and tickers and data.get("new_topic_title"):
                        main_ticker = tickers[0]
                        
                        # Jika isu baru ini menggantikan isu lama untuk saham yang sama, tutup isu lama
                        if data.get("supersede_old_topics", False):
                            supabase.table("topik_panas").update({"status": "selesai"}).eq("ticker", main_ticker).eq("status", "aktif").execute()
                            print(f"📦 Isu lama untuk {main_ticker} diubah menjadi 'selesai'.")

                        # Buat Topik Panas Baru
                        new_topic = supabase.table("topik_panas").insert({
                            "ticker": main_ticker,
                            "judul_isu": data.get("new_topic_title"),
                            "deskripsi_isu": data.get("new_topic_desc", ""),
                            "status": "aktif",
                            "is_hot": data.get("is_hot", True)
                        }).execute()

                        if new_topic.data:
                            topic_id = new_topic.data[0]["id"]
                            print(f"🔥 [Topik Panas Baru] Dibuat untuk {main_ticker}: '{data.get('new_topic_title')}' (ID: {topic_id})")

                    # 4. Simpan Berita ke Tabel `berita`
                    supabase.table("berita").insert({
                        "title": title,
                        "summary": data.get("summary", ""),
                        "bullets": data.get("bullets", []),
                        "tickers": tickers,
                        "category": data.get("category", "Saham Indo"),
                        "sentiment": data.get("sentiment", "neutral"),
                        "source_url": link,
                        "topik_id": topic_id,
                        "is_active": True
                    }).execute()

                    print(f"✅ [BERHASIL SAVED] {title[:50]}... | Tickers: {tickers}")

                except Exception as ai_err:
                    print(f"⚠️  Gagal memproses AI/JSON pada '{title[:30]}...': {ai_err}")

        except Exception as feed_err:
            print(f"❌ Gagal mengambil RSS feed {url}: {feed_err}")

    print("\n🎉 === BOT BERITAMOLOGY SELESAI BEKERJA ===")

if __name__ == "__main__":
    parse_and_process()
