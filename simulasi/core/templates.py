"""
Template Kasus Umum - Simulasi Sidang MK
==========================================
Pre-built templates untuk jenis kasus yang sering diuji di Mahkamah Konstitusi.
"""

CASE_TEMPLATES = [
    {
        "id": "ketenagakerjaan",
        "title": "UU Ketenagakerjaan",
        "category": "Ekonomi & Sosial",
        "description": "PHK, pesangon, hak buruh",
        "norma_di_uji": "Pasal 156 ayat (4) UU No. 13 Tahun 2003 tentang Ketenagakerjaan",
        "batu_uji": ["Pasal 28D ayat (1)", "Pasal 28H ayat (2)"],
        "draft": """PERMOHONAN PENGUJIAN UNDANG-UNDANG

Yang Terhormat Ketua dan Para Hakim Konstitusi Mahkamah Konstitusi Republik Indonesia

I. IDENTITAS PEMOHON
Nama: [Nama Pemohon]
Pekerjaan: Karyawan Swasta
Alamat: [Alamat]

II. KEWENANGAN MAHKAMAH
Berdasarkan Pasal 24C ayat (1) UUD 1945 dan Pasal 51 ayat (1) UU No. 24 Tahun 2003 tentang Mahkamah Konstitusi.

III. NORMA YANG DIUJI
Pasal 156 ayat (4) UU No. 13 Tahun 2003 tentang Ketenagakerjaan yang berbunyi: "Dalam hal pengadilan memutuskan bahwa PHK tidak sah, maka pengusaha wajib mempekerjakan kembali sebagaimana semula."

IV. BATU UJI
- Pasal 28D ayat (1) UUD 1945: Setiap orang berhak atas pengakuan, jaminan, perlindungan, dan kepastian hukum yang adil serta perlakuan yang sama di hadapan hukum.
- Pasal 28H ayat (2) UUD 1945: Setiap orang berhak mendapat kemudahan dan perlakuan khusus untuk memperoleh kesempatan dan manfaat yang sama guna mencapai persamaan dan keadilan.

V. POSITA
1. Pasal 156 ayat (4) UU Ketenagakerjaan tidak memberikan opsi kompensasi finansial sebagai alternatif pemulihan hak pekerja yang di-PHK secara tidak sah.
2. Dalam praktiknya, hubungan kerja yang sudah retak tidak mungkin dipulihkan secara efektif melalui reintegrasi paksa.
3. Negara lain seperti Jerman dan Prancis memberikan opsi kompensasi finansial yang lebih adil bagi pekerja.

VI. PETITUM
Mohon agar Mahkamah Konstitusi menyatakan Pasal 156 ayat (4) UU No. 13 Tahun 2003 bertentangan dengan UUD 1945 dan tidak mempunyai kekuatan hukum mengikat.""",
        "tips": [
            "Fokus pada kerugian konkret yang Anda alami akibat PHK",
            "Jelaskan mengapa reintegrasi tidak realistis dalam konteks hubungan kerja modern",
            "Gunakan data komparatif dari negara lain yang memberikan opsi kompensasi",
            "Antisipasi argumen Pemerintah soal open legal policy dalam pengaturan ketenagakerjaan"
        ]
    },
    {
        "id": "kesehatan",
        "title": "UU Kesehatan",
        "category": "Hak Asasi",
        "description": "Hak pasien, vaksinasi wajib, otonomi tubuh",
        "norma_di_uji": "Pasal 93 UU No. 17 Tahun 2023 tentang Kesehatan",
        "batu_uji": ["Pasal 28A", "Pasal 28I ayat (1)"],
        "draft": """PERMOHONAN PENGUJIAN UNDANG-UNDANG

Yang Terhormat Ketua dan Para Hakim Konstitusi Mahkamah Konstitusi Republik Indonesia

I. IDENTITAS PEMOHON
Nama: [Nama Pemohon]
Pekerjaan: Warga Negara
Alamat: [Alamat]

II. KEWENANGAN MAHKAMAH
Berdasarkan Pasal 24C ayat (1) UUD 1945 dan Pasal 51 ayat (1) UU No. 24 Tahun 2003.

III. NORMA YANG DIUJI
Pasal 93 UU No. 17 Tahun 2023 tentang Kesehatan yang mewajibkan vaksinasi bagi seluruh penduduk dengan ancaman sanksi administratif.

IV. BATU UJI
- Pasal 28A UUD 1945: Setiap orang berhak untuk hidup serta berhak mempertahankan hidup dan kehidupannya.
- Pasal 28I ayat (1) UUD 1945: Hak untuk tidak disiksa, hak kewarganegaraan, hak untuk tidak diperbudak, hak untuk diakui sebagai pribadi di hadapan hukum, dan hak untuk beragama adalah hak asasi manusia yang tidak dapat dikurangi.

V. POSITA
1. Kewajiban vaksinasi tanpa pengecualian untuk alasan medis atau keagamaan melanggar hak atas otonomi tubuh.
2. Sanksi administratif yang berat berpotensi mendiskriminasi kelompok rentan.
3. Prinsip informed consent dalam kedokteran mengharuskan hak menolak tindakan medis.

VI. PETITUM
Mohon agar Mahkamah Konstitusi menyatakan Pasal 93 UU No. 17 Tahun 2023 bertentangan dengan UUD 1945.""",
        "tips": [
            "Kuatkan argumen dengan prinsip informed consent dan hak atas otonomi tubuh",
            "Rujuk standar internasional seperti ICCPR dan Piagam Hak Asasi Eropa",
            "Antisipasi argumen Pemerintah tentang kepentingan kesehatan masyarakat (public health)",
            "Bedakan antara pembatasan hak yang proporsional dan diskriminatif"
        ]
    },
    {
        "id": "pemilu",
        "title": "UU Pemilu",
        "category": "Politik",
        "description": "Threshold parlemen, syarat calon, hak politik",
        "norma_di_uji": "Pasal 222 UU No. 7 Tahun 2017 tentang Pemilihan Umum",
        "batu_uji": ["Pasal 6A ayat (2)", "Pasal 28E ayat (3)"],
        "draft": """PERMOHONAN PENGUJIAN UNDANG-UNDANG

Yang Terhormat Ketua dan Para Hakim Konstitusi Mahkamah Konstitusi Republik Indonesia

I. IDENTITAS PEMOHON
Nama: [Nama Partai Politik]
Status: Partai Politik Peserta Pemilu
Alamat: [Alamat]

II. KEWENANGAN MAHKAMAH
Berdasarkan Pasal 24C ayat (1) UUD 1945 dan Pasal 51 ayat (1) UU No. 24 Tahun 2003.

III. NORMA YANG DIUJI
Pasal 222 UU No. 7 Tahun 2017 tentang Pemilihan Umum yang menetapkan presidential threshold 20% kursi DPR atau 25% suara sah nasional.

IV. BATU UJI
- Pasal 6A ayat (2) UUD 1945: Pasangan calon Presiden dan Wakil Presiden diusulkan oleh partai politik atau gabungan partai politik peserta pemilihan umum.
- Pasal 28E ayat (3) UUD 1945: Setiap orang berhak atas kebebasan berserikat, berkumpul, dan mengeluarkan pendapat.

V. POSITA
1. Presidential threshold membatasi hak konstitusional partai politik untuk mengusung calon presiden.
2. Threshold ini tidak dikenal dalam UUD 1945 dan merupakan penambahan syarat yang tidak konstitusional.
3. MK dalam putusan sebelumnya telah menyatakan threshold konstitusional dengan pertimbangan yang kini tidak lagi relevan.

VI. PETITUM
Mohon agar Mahkamah Konstitusi menyatakan Pasal 222 UU No. 7 Tahun 2017 bertentangan dengan UUD 1945.""",
        "tips": [
            "Rujuk putusan MK sebelumnya soal threshold (Putusan No. 55/PUU-XV/2017)",
            "Bandingkan dengan argumen hak konstitusional partai dan prinsip demokrasi",
            "Analisis dampak threshold terhadap partisipasi politik partai kecil",
            "Antisipasi argumen Pemerintah soal stabilitas pemerintahan"
        ]
    },
    {
        "id": "ite",
        "title": "UU ITE",
        "category": "Hak Asasi",
        "description": "Pasal karet, kebebasan berpendapat, kriminalisasi pers",
        "norma_di_uji": "Pasal 27 ayat (3) UU No. 11 Tahun 2008 jo. UU No. 19 Tahun 2016",
        "batu_uji": ["Pasal 28E ayat (2)", "Pasal 28F"],
        "draft": """PERMOHONAN PENGUJIAN UNDANG-UNDANG

Yang Terhormat Ketua dan Para Hakim Konstitusi Mahkamah Konstitusi Republik Indonesia

I. IDENTITAS PEMOHON
Nama: [Nama Pemohon]
Pekerjaan: Jurnalis / Warga Negara
Alamat: [Alamat]

II. KEWENANGAN MAHKAMAH
Berdasarkan Pasal 24C ayat (1) UUD 1945 dan Pasal 51 ayat (1) UU No. 24 Tahun 2003.

III. NORMA YANG DIUJI
Pasal 27 ayat (3) UU No. 11 Tahun 2008 tentang Informasi dan Transaksi Elektronik sebagaimana diubah dengan UU No. 19 Tahun 2016.

IV. BATU UJI
- Pasal 28E ayat (2) UUD 1945: Setiap orang berhak atas kebebasan meyakini kepercayaan, menyatakan pikiran dan sikap, sesuai hati nuraninya.
- Pasal 28F UUD 1945: Setiap orang berhak untuk berkomunikasi dan memperoleh informasi untuk mengembangkan pribadi dan lingkungan sosialnya.

V. POSITA
1. Frasa "yang dapat menimbulkan rasa kebencian atau permusuhan" bersifat multi-tafsir dan elastis sehingga berpotensi menjadi pasal karet.
2. Norma ini berpotensi kriminalisasi kebebasan berpendapat dan pers.
3. Tidak ada ukuran objektif yang jelas untuk membedakan kritik sah dengan tindak pidana.

VI. PETITUM
Mohon agar Mahkamah Konstitusi menyatakan Pasal 27 ayat (3) UU ITE bertentangan dengan UUD 1945.""",
        "tips": [
            "Tekankan prinsip kepastian hukum dan void for vagueness doctrine",
            "Tunjukkan contoh kasus kriminalisasi pers dan akademisi menggunakan pasal ini",
            "Rujuk putusan MK tentang uji materi UU ITE sebelumnya",
            "Bandingkan dengan perlindungan kebebasan berpendapat di negara demokrasi lain"
        ]
    },
    {
        "id": "perpajakan",
        "title": "UU Perpajakan",
        "category": "Ekonomi & Sosial",
        "description": "Sengketa pajak, hak wajib pajak, kepastian hukum",
        "norma_di_uji": "Pasal 13 ayat (1) huruf e UU No. 6 Tahun 1983 jo. UU No. 7 Tahun 2021",
        "batu_uji": ["Pasal 23A", "Pasal 28D ayat (1)"],
        "draft": """PERMOHONAN PENGUJIAN UNDANG-UNDANG

Yang Terhormat Ketua dan Para Hakim Konstitusi Mahkamah Konstitusi Republik Indonesia

I. IDENTITAS PEMOHON
Nama: [Nama Perusahaan/Wajib Pajak]
NPWP: [Nomor NPWP]
Alamat: [Alamat]

II. KEWENANGAN MAHKAMAH
Berdasarkan Pasal 24C ayat (1) UUD 1945 dan Pasal 51 ayat (1) UU No. 24 Tahun 2003.

III. NORMA YANG DIUJI
Pasal 13 ayat (1) huruf e UU No. 6 Tahun 1983 tentang Ketentuan Umum dan Tata Cara Perpajakan sebagaimana diubah terakhir dengan UU No. 7 Tahun 2021.

IV. BATU UJI
- Pasal 23A UUD 1945: Pajak dan pungutan lain yang bersifat memaksa untuk keperluan negara diatur dengan undang-undang.
- Pasal 28D ayat (1) UUD 1945: Setiap orang berhak atas kepastian hukum yang adil.

V. POSITA
1. Pasal yang memberikan kewenangan fiskus menetapkan kewajiban pajak tanpa pembuktian yang memadai melanggar prinsip kepastian hukum.
2. Beban pembuktian yang tidak seimbang merugikan hak wajib pajak.
3. Perbandingan dengan sistem perpajakan negara lain yang lebih melindungi hak wajib pajak.

VI. PETITUM
Mohon agar Mahkamah Konstitusi menyatakan Pasal 13 ayat (1) huruf e UU KUP bertentangan dengan UUD 1945.""",
        "tips": [
            "Fokus pada aspek kepastian hukum dan due process dalam penentuan kewajiban pajak",
            "Dokumentasikan bukti kerugian konkret akibat ketidakpastian norma",
            "Rujuk putusan MK tentang sengketa pajak sebelumnya",
            "Antisipasi argumen Pemerintah soal penerimaan negara dan kepentingan fiskal"
        ]
    },
    {
        "id": "pertanahan",
        "title": "UU Pertanahan",
        "category": "Hak Asasi",
        "description": "Hak ulayat, pengadaan tanah, masyarakat adat",
        "norma_di_uji": "Pasal 66 UU No. 11 Tahun 2020 tentang Cipta Kerja",
        "batu_uji": ["Pasal 18B ayat (2)", "Pasal 28H ayat (1)"],
        "draft": """PERMOHONAN PENGUJIAN UNDANG-UNDANG

Yang Terhormat Ketua dan Para Hakim Konstitusi Mahkamah Konstitusi Republik Indonesia

I. IDENTITAS PEMOHON
Nama: [Nama Masyarakat Adat/Kepala Suku]
Status: Perwakilan Masyarakat Adat
Alamat: [Alamat]

II. KEWENANGAN MAHKAMAH
Berdasarkan Pasal 24C ayat (1) UUD 1945 dan Pasal 51 ayat (1) UU No. 24 Tahun 2003.

III. NORMA YANG DIUJI
Pasal 66 UU No. 11 Tahun 2020 tentang Cipta Kerja yang mengatur pengadaan tanah untuk kepentingan umum.

IV. BATU UJI
- Pasal 18B ayat (2) UUD 1945: Negara mengakui dan menghormati kesatuan-kesatuan masyarakat hukum adat serta hak-hak tradisionalnya sepanjang masih hidup dan sesuai dengan perkembangan masyarakat dan prinsip Negara Kesatuan Republik Indonesia.
- Pasal 28H ayat (1) UUD 1945: Setiap orang berhak hidup sejahtera lahir dan batin, bertempat tinggal, dan mendapatkan lingkungan hidup yang baik dan sehat.

V. POSITA
1. Pengadaan tanah tanpa pengakuan hak ulayat masyarakat adat melanggar Pasal 18B ayat (2) UUD 1945.
2. Kompensasi yang tidak adil dan proses yang tidak partisipatif merugikan masyarakat adat.
3. UU Ciptaker tidak memberikan perlindungan khusus bagi tanah adat.

VI. PETITUM
Mohon agar Mahkamah Konstitusi menyatakan Pasal 66 UU Ciptaker bertentangan dengan UUD 1945.""",
        "tips": [
            "Dokumentasikan bukti keberadaan masyarakat adat dan sejarah penguasaan tanah adat",
            "Rujuk putusan MK tentang hak ulayat (Putusan No. 35/PUU-X/2012)",
            "Jelaskan dampak pengadaan tanah terhadap kehidupan masyarakat adat",
            "Antisipasi argumen Pemerintah soal kepentingan umum dan pembangunan"
        ]
    }
]


def get_all_templates():
    """Ambil semua template (tanpa draft lengkap untuk list view)."""
    return [
        {
            "id": t["id"],
            "title": t["title"],
            "category": t["category"],
            "description": t["description"],
            "norma_di_uji": t["norma_di_uji"],
            "batu_uji": t["batu_uji"],
        }
        for t in CASE_TEMPLATES
    ]


def get_template_by_id(template_id: str):
    """Ambil template lengkap berdasarkan ID."""
    for t in CASE_TEMPLATES:
        if t["id"] == template_id:
            return t
    return None
