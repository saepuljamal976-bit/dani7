# Pastikan judul dibersihkan dulu sebelum dipanggil prompt AI
title_clean = title.strip()

# Baru panggil prompt AI Gemini
prompt = f'Analisis berita atau pengumuman saham berikut secara objektif dan mendalam: "{title_clean}"'
