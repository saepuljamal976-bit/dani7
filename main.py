prompt = f'''
Kamu adalah Head of Research & Chief Analyst Pasar Modal Indonesia (BEI).
Analisis berita atau pengumuman saham berikut secara objektif dan mendalam: "{title_clean}"

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
