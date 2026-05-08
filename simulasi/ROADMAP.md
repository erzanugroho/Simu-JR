# Roadmap Simulasi Judicial Review (AI vs AI)

Berikut adalah daftar fitur esensial yang akan dikembangkan pada fase selanjutnya untuk melengkapi arsitektur dasar simulasi sidang Mahkamah Konstitusi:

## Fase 2 (STATUS: SELESAI — 2026-04-25)

### 1. Dissenting Opinion — ✅ IMPLEMENTED
Sistem tidak hanya menghasilkan satu skor agregat, tetapi memungkinkan **Dissenting Opinion** atau **Concurring Opinion** secara eksplisit. Jika dari 3 Hakim Panel terdapat ketidaksepakatan (misal 2 setuju, 1 menolak), sistem akan melakukan *generate* dokumen Dissenting Opinion khusus dari Hakim yang menolak, memberikan wawasan mendalam terkait celah argumen pengguna.

### 2. Agen Pihak Terkait (Related Parties) & Amicus Curiae — ✅ IMPLEMENTED
Menambahkan agen baru ke dalam orkestrasi sidang:
*   **Pihak Terkait:** Membela undang-undang dari perspektif pihak ketiga yang kepentingannya terpengaruh secara langsung (hak privat/sipil).
*   **Amicus Curiae Agent:** Memberikan pandangan netral dan akademis berdasarkan literatur jurnal hukum atau praktik internasional.

### 3. Anti-Hallucination & Citation Checker (Validator Dalil) — ✅ IMPLEMENTED
Sebuah agen *Middleware* khusus yang bertugas mengecek setiap kutipan putusan atau undang-undang yang diucapkan oleh agen lain (Pemohon, Pemerintah, Hakim). Jika terdeteksi halusinasi (salah nomor putusan atau salah redaksi pasal), validator akan memaksa agen tersebut merevisi dalilnya sebelum argumen dicatat di *transcript*.

## Fase 3 (STATUS: SELESAI — 2026-04-25)

### 4. Sesi Keterangan Ahli (Ronde Ekstra) — ✅ IMPLEMENTED
Menambahkan **Ronde 2B: Pemeriksaan Ahli**. Pengguna dapat meng-input teori hukum (misal teori Hans Kelsen atau Jimly Asshiddiqie). Agen *Ahli Pemohon* dan *Ahli Pemerintah* akan berdebat murni di tataran teori konstitusi, dengan database RAG literatur akademis.

### 5. Batasan Waktu (Word/Token Limiter) Presisi — ✅ IMPLEMENTED
Menambahkan instruksi *strict token limiter* pada agen. Jika jawaban LLM terlalu bertele-tele atau melebihi limit, Hakim akan memotong argumen dengan peringatan (interupsi), memaksa *user* maupun agen untuk berargumen lugas dan *to the point* layaknya sidang MK asli.

### 6. Auto-Suggestion Batu Uji (UUD 1945 Mapper) — ✅ IMPLEMENTED
Peningkatan pada modul *Preprocessor*. AI akan membaca *Draft Input* pengguna dan menyarankan penambahan pasal-pasal UUD 1945 lain yang relevan sebagai "Batu Uji" yang mungkin terlewat oleh pengguna (misal menyarankan Pasal 28E atau 28G).

## Fase 4: Mode Interaktif & Pengalaman Pengguna (STATUS: SELESAI — 2026-04-25)

### 7. Mode Manusia vs AI — ✅ IMPLEMENTED
Pengguna dapat memilih untuk berperan langsung sebagai **Pemohon** (human mode). Ketika giliran Pemohon tiba, sistem menampilkan panel input dan menunggu argumen dari pengguna (timeout 10 menit). Tersedia di antarmuka web (panel input bawah layar) maupun CLI (`--mode human`).

### 8. Umpan Balik Terstruktur dari Hakim — ✅ IMPLEMENTED
Setelah RPH, setiap hakim memberikan **umpan balik terstruktur** dalam format JSON yang mencakup: skor potensi perbaikan, kelemahan utama, rekomendasi konkret per aspek (Legal Standing, Substansi, Batu Uji, Formil), saran revisi petitum, dan prioritas perbaikan. Feedback diagregasi dan ditampilkan di panel kanan.

### 9. Progress Tracker Lintas Simulasi — ✅ IMPLEMENTED
Sistem melacak perkembangan skor dari simulasi ke simulasi dan menyimpannya ke `results/progress_history.json`. Di antarmuka web, modal "Tracker Progres" menampilkan grafik bar trend skor, perbandingan dengan simulasi sebelumnya per dimensi, dan tabel riwayat lengkap. Di CLI, cetak ringkasan delta skor setelah setiap simulasi.

## Fase 5: Peningkatan Realisme & Kualitas (Belum Dikerjakan)

### 10. RAG yang Lebih Kaya
Tambahkan sumber ke database vektor:
- Risalah DPR (pembahasan UU) — memperkuat argumen Pemerintah soal ratio legis
- Jurnal hukum akademis (JHRI, Jurnal MK) — untuk Amicus Curiae dan Ahli
- ICCPR/ECHR case law — referensi komparatif internasional

### 11. Persona Hakim Berbeda
Beri setiap hakim "ideologi" berbeda:
- **Hakim Formalis:** hanya mengikuti teks konstitusi secara literal
- **Hakim Progresif:** living constitution, responsif terhadap perkembangan sosial
- **Hakim Positivis:** deference kuat kepada legislator, judicial self-restraint
Ini akan membuat dissenting opinion jauh lebih realistis dan tajam.

### 12. Re-ranking RAG dengan Cross-Encoder
Hasil RAG saat ini hanya menggunakan dense embedding. Tambahkan:
- Cross-encoder re-ranking untuk meningkatkan relevansi konteks
- Hybrid search (BM25 + dense) untuk ketepatan nomor putusan
- Ini langsung mengurangi risiko halusinasi kutipan secara signifikan
