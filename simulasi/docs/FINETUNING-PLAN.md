# Rencana Fine-Tuning Qwen 3.5 9B — Model Inferensi Sidang MK

## 1. Latar Belakang & Tujuan

### Problem Statement
Model LLM generik (Qwen, Claude, dll) menghasilkan respons yang **terlalu formal, kaku, dan tidak natural** dibandingkan bahasa aktual sidang Mahkamah Konstitusi Indonesia. Risalah sidang menunjukkan bahwa:
- Hakim menggunakan bahasa **semi-formal** dengan sentuhan personal ("Ya, gitu, ya.", "Enggak bisa, enggak bisa menanggapi.")
- Kuasa Hukum mencampur bahasa hukum teknis dengan **bahasa percakapan natural**
- Ada struktur dialog khas: `NOMOR. PERAN: NAMA [TIMESTAMP]`
- Pemohon sering menggunakan sapaan keagamaan multi-kultur: "Assalamualaikum wr. wb., om swastiastu, namo buddhaya, shalom"
- Hakim menggunakan teknik **Socratic questioning** yang sangat spesifik

### Tujuan Fine-Tuning
1. **Tata bahasa**: Menghasilkan respons yang sesuai dengan bahasa aktual sidang MK
2. **Gaya bicara**: Mencerminkan masing-masing peran (Hakim, Pemohon, Pemerintah, Ahli)
3. **Struktur argumentasi**: Mengikuti pola argumentasi hukum konstitusi Indonesia
4. **Pengetahuan domain**: Memahami terminologi, prosedur, dan preseden MK secara internal
5. **Mengurangi halusinasi**: Model lebih "tahu" batas-batas pengetahuan hukumnya

---

## 2. Analisis Data Tersedia

### Data Mentah

| Sumber | Volume | Format | Kualitas |
|--------|--------|--------|----------|
| Putusan PDF | 200+ file | PDF → 463K chunks | Teks formal, struktur baku |
| Risalah Sidang PDF | 200+ file | PDF → 715K chunks | Dialog natural, transkrip real-time |
| UUD 1945 | 1 file | JSON | Teks resmi, bersih |
| Intelligence Banks | 4+ collections | ChromaDB | Hasil pipeline RAG (ratio, attack, concern, survive) |
| System Prompts | 10+ prompt | Python/text | Definisi persona per agen |

### Total: ~1.18 juta chunks (~715K risalah + 463K putusan)

### Data Prioritas untuk Fine-Tuning

**Tier 1 — Data Emas (wajib):**
- Risalah sidang (715K chunks) → sumber utama untuk belajar tata bahasa sidang
- System prompts → instruktur persona per agen

**Tier 2 — Data Pengetahuan (penting):**
- Putusan MK (463K chunks) → pengetahuan hukum, ratio decidendi, preseden
- UUD 1945 → referensi batu uji

**Tier 3 — Data Sintetik (pelengkap):**
- Intelligence banks → pola argumentasi yang terbukti efektif
- Contoh simulasi dari `results/` (jika ada transcript tersimpan)

---

## 3. Strategi Dataset Preparation

### 3.1. Format Dataset — Multi-Task Fine-Tuning

Kita akan membuat **4 jenis dataset** yang dilatihkan secara simultan:

#### Dataset A: Hearing Dialogue Completion (Chat Format)
**Sumber**: Risalah sidang (715K chunks)
**Tujuan**: Model belajar melanjutkan dialog sidang secara natural
**Format**:
```json
{
  "conversations": [
    {"role": "system", "content": "Anda adalah Hakim Konstitusi pada Mahkamah Konstitusi RI..."},
    {"role": "user", "content": "KONTEKS: Perkara Nomor 19/PUU-XXII/2024 tentang pengujian UU No. 1/2022 tentang HKPD.\nPemohon baru saja menyampaikan legal standing..."},
    {"role": "assistant", "content": "Saudara Pemohon, saya perlu mengklarifikasi sesuatu. Dalam Pasal 51 ayat (1) UU MK, Saudara menyebut memiliki hak konstitusional yang dirugikan. Bisa dijelaskan, hak konstitusional yang mana tepatnya? Apakah ini terkait dengan kebebasan berusaha dalam Pasal 28G ayat (2) UUD 1945, atau Pasal 28D? Karena dalam pengujian sebelumnya, Putusan Nomor 52/PUU-VIII/2010, Mahkamah sudah pernah menolak argumen serupa. Apa yang membuat kasus Saudara berbeda?"}
  ]
}
```

#### Dataset B: Role-Specific Argument Generation
**Sumber**: System prompts + Intelligence Banks + Risalah
**Tujuan**: Model menghasilkan argumen spesifik per peran
**Format**:
```json
{
  "instruction": "Anda adalah Kuasa Hukum Pemohon. Pemerintah membantah dengan argumen open legal policy. Berikan tanggapan dengan tata bahasa sidang MK yang natural.",
  "input": "ARGUMEN PEMERINTAH: Norma yang diuji merupakan kebijakan hukum terbuka yang menjadi ranah legislator. MK tidak boleh menggantikan kebijakan DPR dengan kebijakannya sendiri.\n\nSURVIVE BANK: Pemohon berhasil ketika membedakan antara norma dan implementasi administratif.",
  "output": "Yang Mulia, kami mohon izin untuk menanggapi. Pertama-tama, kami ingin menggarisbawahi bahwa yang kami uji di sini bukanlah kebijakan hukum terbuka secara umum, melainkan norma spesifik yang dampaknya langsung merugikan hak konstitusional kami. Jadi ini bukan soal MK mau menggantikan DPR, tetapi MK sedang menjalankan kewenangan konstitusionalnya berdasarkan Pasal 24C ayat (1) UUD 1945. Kalau kita lihat dalam Putusan MK Nomor .../PUU-.../..., Mahkamah sendiri sudah menegaskan bahwa ada batas antara open legal policy yang benar-benar teknis dan norma yang menyentuh hak konstitusional warga negara. Nah, dalam kasus ini, norma yang diuji jelas melampaui batas open legal policy karena..."
}
```

#### Dataset C: Legal Draft Generation
**Sumber**: Putusan MK + Draft permohonan (dari intelligence banks)
**Tujuan**: Model menyusun dokumen hukum formal PUU
**Format**: `instruction` (perintah revisi/susun draft) + `input` (draft awal + intelligence banks) + `output` (naskah permohonan formal)

#### Dataset D: Legal Knowledge Q&A
**Sumber**: UUD 1945 + Putusan MK + System prompts
**Tujuan**: Model menjawab pertanyaan hukum konstitusi dengan benar
**Format**: Q&A tentang pasal UUD, preseden MK, prosedur persidangan

### 3.2. Pipeline Pembuatan Dataset

```
┌─────────────────────────────────────────────────────────────┐
│                    PIPELINE DATASET FINE-TUNING              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: EXTRACT & CLEAN                                     │
│  ├── Risalah PDF → Parse dialog per-nomor perkara            │
│  │   ├── Identifikasi pembicara: [NOMOR. PERAN: NAMA]       │
│  │   ├── Filter chunk yang terlalu pendek (<50 kata)         │
│  │   ├── Gabungkan chunk per-sesi sidang (bukan per-chunk)   │
│  │   └── Bersihkan artefak OCR, karakter Unicode aneh       │
│  ├── Putusan PDF → Extract per-bagian                        │
│  │   ├── Identitas perkara                                   │
│  │   ├── Dalil Pemohon                                       │
│  │   ├── Jawab Pemerintah                                    │
│  │   ├── Pertimbangan hakim                                  │
│  │   └── Amar putusan                                        │
│  └── UUD 1945 → Struktur per-pasal                           │
│                                                              │
│  Step 2: GENERATE TRAINING PAIRS                             │
│  ├── Dataset A: Risalah → Multi-turn conversation pairs      │
│  │   ├── Input: System prompt + konteks perkara + history    │
│  │   ├── Output: Respons aktual dari transkrip sidang        │
│  │   └── Target: 50K-100K conversation pairs                 │
│  ├── Dataset B: Argument Generation per-role                 │
│  │   ├── Input: System prompt + argumen lawan + bank data    │
│  │   ├── Output: Argumen aktual dari risalah atau sintetik   │
│  │   └── Target: 20K-50K instruction pairs                   │
│  ├── Dataset C: Legal Draft                                  │
│  │   ├── Input: Draft awal + intelligence banks              │
│  │   ├── Output: Draft revisi formal                         │
│  │   └── Target: 5K-10K pairs                                │
│  └── Dataset D: Legal Knowledge Q&A                          │
│      ├── Input: Pertanyaan hukum konstitusi                  │
│      ├── Output: Jawaban berbasis putusan/UUD                │
│      └── Target: 10K-20K pairs                               │
│                                                              │
│  Step 3: QUALITY FILTERING                                   │
│  ├── Auto-filter: Hapus pasangan kosong, duplikat, terlalu   │
│  │   pendek                                                  │
│  ├── LLM-as-judge: Gunakan Claude/GPT-4 untuk menilai       │
│  │   kualitas 10% sample                                     │
│  └── Manual review: Tim hukum review 500-1000 samples        │
│                                                              │
│  Step 4: FORMAT CONVERT                                      │
│  ├── → ChatML format (Qwen native)                           │
│  ├── → Split train/val/test (85/10/5)                        │
│  └── → Shuffle & balance per-task distribution               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.3. Ukuran Dataset Target

| Dataset | Target Samples | Estimasi Tokens | Prioritas |
|---------|---------------|-----------------|-----------|
| A: Hearing Dialogue | 50,000 | ~25M tokens | Tertinggi |
| B: Role Argument | 30,000 | ~15M tokens | Tinggi |
| C: Legal Draft | 5,000 | ~10M tokens | Sedang |
| D: Legal Q&A | 15,000 | ~5M tokens | Sedang |
| **Total** | **100,000** | **~55M tokens** | |

> **Catatan**: Untuk 9B model, 55M tokens training data sudah sangat memadai. Recommended minimum adalah 10M tokens.

---

## 4. Arsitektur Fine-Tuning

### 4.1. Metode: LoRA + Unsloth (Recommended)

```
Base Model: Qwen 3.5 9B (atau Qwen 2.5 9B-Instruct)
     │
     ▼
┌────────────────────────────────────────────┐
│         Unsloth + LoRA Fine-Tuning         │
├────────────────────────────────────────────┤
│  • LoRA Rank: 32-64 (sesuaikan VRAM)      │
│  • LoRA Alpha: 64-128                      │
│  • Target Modules: q_proj, k_proj, v_proj, │
│    o_proj, gate_proj, up_proj, down_proj   │
│  • Learning Rate: 1e-4 → cosine decay      │
│  • Batch Size: 4-8 (tergantung VRAM)       │
│  • Gradient Accumulation: 8-16             │
│  • Epochs: 2-3 (hindari overfitting)       │
│  • Max Seq Length: 4096-8192               │
│  • Warmup: 10% total steps                 │
│  • Weight Decay: 0.01                      │
└────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────┐
│         Merge & Export                      │
├────────────────────────────────────────────┤
│  • Merge LoRA weights ke base model        │
│  • Export: GGUF (q4_k_m) untuk LM Studio  │
│  • Export: safetensors untuk deployment     │
│  • Upload ke HuggingFace (opsional)        │
└────────────────────────────────────────────┘
```

### 4.2. Mengapa LoRA + Unsloth?

| Faktor | Alasan |
|--------|--------|
| **LoRA** | Hanya fine-tune adapter (~0.1% params), VRAM efficient, training cepat |
| **Unsloth** | Sudah ter-install (lihat `unslothreference.txt`), 2x lebih cepat, hemat VRAM 60% |
| **Qwen 3.5 9B** | Sweet spot: cukup besar untuk quality, cukup kecil untuk inference lokal |
| **GGUF export** | Langsung bisa di-load di LM Studio yang sudah dipakai project ini |

### 4.3. Hardware Requirements

| Komponen | Minimum | Recommended |
|----------|---------|-------------|
| GPU VRAM | 12 GB (RTX 3060/4060) | 24 GB (RTX 3090/4090) |
| System RAM | 32 GB | 64 GB |
| Storage | 100 GB free | 200 GB (NVMe SSD) |
| Training Time | ~24-48 jam (12GB) | ~8-16 jam (24GB) |

> **Catatan**: Jika VRAM terbatas (12GB), gunakan 4-bit quantization + LoRA rank 16. Jika 24GB, bisa full bf16 + LoRA rank 64.

---

## 5. Implementation Steps

### Phase 0: Persiapan Environment (1-2 hari)
```
0.1. Verifikasi GPU & VRAM tersedia
0.2. Install Unsloth: pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
0.3. Install dependencies: pip install trl peft accelerate bitsandbytes
0.4. Download Qwen 3.5 9B base model dari HuggingFace
0.5. Setup wandb/sweep untuk experiment tracking
```

### Phase 1: Dataset Preparation (3-5 hari)
```
1.1. Buat script: simulasi/finetuning/extract_risalah_dialogs.py
     ─ Parse risalah chunks → multi-turn conversations
     ─ Identifikasi pembicara (regex pattern)
     ─ Group per-sesi sidang (bukan per-chunk)
     ─ Output: risalah_conversations.jsonl

1.2. Buat script: simulasi/finetuning/extract_putusan_sections.py
     ─ Parse putusan chunks → terstruktur per bagian
     ─ Output: putusan_structured.jsonl

1.3. Buat script: simulasi/finetuning/generate_training_data.py
     ─ Generate Dataset A (hearing dialogue)
     ─ Generate Dataset B (role argument)
     ─ Generate Dataset C (legal draft)
     ─ Generate Dataset D (legal Q&A)
     ─ Output: train.jsonl, val.jsonl, test.jsonl

1.4. Buat script: simulasi/finetuning/quality_filter.py
     ─ Auto-filter sampah (terlalu pendek, duplikat, encoding error)
     ─ LLM-as-judge sampling review
     ─ Output: filtered dataset

1.5. Buat script: simulasi/finetuning/format_chatml.py
     ─ Convert ke ChatML format (Qwen native)
     ─ Tambah system prompt per-peran
     ─ Split train/val/test
```

### Phase 2: Training (2-3 hari)
```
2.1. Buat script: simulasi/finetuning/train.py
     ─ Config LoRA (rank, alpha, target_modules)
     ─ Config training (lr, batch_size, epochs)
     ─ Load model + tokenizer
     ─ Training loop dengan Unsloth SFTTrainer
     ─ Logging ke wandb

2.2. Run training:
     python simulasi/finetuning/train.py \
       --model "unsloth/Qwen3.5-9B-Instruct" \
       --dataset "simulasi/finetuning/data/train.jsonl" \
       --output "simulasi/finetuning/output/qwen-mk-simulasi" \
       --epochs 3 \
       --lora-rank 32 \
       --batch-size 4 \
       --lr 1e-4

2.3. Monitor training:
     ─ Loss curve (train vs val)
     ─ Per-task loss breakdown
     ─ Early stopping jika val loss naik
```

### Phase 3: Evaluation & Iteration (2-3 hari)
```
3.1. Buat script: simulasi/finetuning/evaluate.py
     ─ Benchmark: BLEU, ROUGE (automatis)
     ─ Human evaluation: legal accuracy, naturalness (manual)
     ─ A/B test: base model vs fine-tuned (dalam simulasi)
     ─ Per-role evaluation: score per persona

3.2. Evaluasi metrik:
     ─ Naturalness score (1-5): Seberapa natural bahasa sidang?
     ─ Legal accuracy (1-5): Apakah terminologi hukum benar?
     ─ Role consistency (1-5): Apakah sesuai persona peran?
     ─ Hallucination rate: Berapa % kutipan yang salah?

3.3. Iterasi berdasarkan evaluasi:
     ─ Jika naturalness rendah → tambah data risalah
     ─ Jika legal accuracy rendah → tambah data putusan
     ─ Jika hallucination tinggi → tambah data Q&A + stricter filtering
```

### Phase 4: Deployment (1-2 hari)
```
4.1. Merge LoRA weights:
     python simulasi/finetuning/merge_and_export.py \
       --base "unsloth/Qwen3.5-9B-Instruct" \
       --lora "simulasi/finetuning/output/qwen-mk-simulasi" \
       --export-gguf \
       --quantization q4_k_m

4.2. Deploy ke LM Studio:
     ─ Load GGUF di LM Studio
     ─ Update .env: LLM_MODEL_NAME=qwen-mk-simulasi
     ─ Test dengan simulasi penuh

4.3. Update config:
     ─ simulasi/.env → ganti model name
     ─ simulasi/config.yaml → sesuaikan parameter
     ─ simulasi/core/system_prompts.py → bisa disederhanakan (karena model sudah "tahu" persona)
```

---

## 6. Directory Structure yang Dihasilkan

```
simulasi/
├── finetuning/                      # ← SELURUH FINE-TUNING CODE
│   ├── __init__.py
│   ├── extract_risalah_dialogs.py   # Parser risalah → conversations
│   ├── extract_putusan_sections.py  # Parser putusan → structured sections
│   ├── generate_training_data.py    # Generator 4 dataset types
│   ├── quality_filter.py            # Auto quality filtering
│   ├── format_chatml.py             # Convert → ChatML format
│   ├── train.py                     # Main training script (Unsloth + LoRA)
│   ├── evaluate.py                  # Evaluation pipeline
│   ├── merge_and_export.py          # Merge LoRA + export GGUF
│   ├── config.py                    # Training hyperparameters
│   ├── data/                        # Generated datasets
│   │   ├── train.jsonl
│   │   ├── val.jsonl
│   │   ├── test.jsonl
│   │   └── README.md               # Dataset documentation
│   ├── output/                      # Model checkpoints
│   │   └── qwen-mk-simulasi/
│   ├── logs/                        # Training logs
│   └── README.md                    # Fine-tuning documentation
```

---

## 7. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| Overfitting | Model menghafal, bukan generalisasi | 2-3 epochs, early stopping, dropout 0.05 |
| Data noise (OCR error) | Model belajar dari teks salah | Quality filter + manual review |
| Catastrophic forgetting | Model lupa kemampuan bahasa umum | LoRA (bukan full fine-tune), mixing data umum |
| Hallucination tetap tinggi | Model mengarang kutipan | Validator agent tetap dipakai, post-filter |
| VRAM tidak cukup | Training gagal | 4-bit quantization, gradient checkpointing, smaller rank |
| Dataset bias (hanya 2024) | Model kurang general ke era lain | Tambah putusan 2003-2023 yang sudah tersedia |

---

## 8. Alternatif & Fallback

### Jika Qwen 3.5 9B belum tersedia:
- Gunakan **Qwen 2.5 9B-Instruct** (stabil, banyak LoRA community)
- Atau **Qwen 2.5 14B** jika VRAM 24GB tersedia

### Jika VRAM tidak cukup untuk 9B:
- **Option A**: Fine-tune Qwen 2.5 3B (hanya 8GB VRAM, quality lebih rendah)
- **Option B**: Cloud training (Google Colab Pro, Lambda Labs, Vast.ai)
- **Option C**: QLoRA 4-bit (bisa training 9B di 12GB VRAM)

### Jika dataset terlalu besar untuk proses:
- Sampling: Ambil 20% risalah terbaik (prioritas 2023-2024)
- Stratified sampling per-tahun dan per-jenis perkara

---

## 9. Estimasi Timeline

| Phase | Durasi | Deliverable |
|-------|--------|-------------|
| Phase 0: Environment | 1-2 hari | Environment ready |
| Phase 1: Dataset | 3-5 hari | 100K training samples |
| Phase 2: Training | 2-3 hari | Fine-tuned model |
| Phase 3: Evaluation | 2-3 hari | Evaluation report |
| Phase 4: Deployment | 1-2 hari | Model deployed di LM Studio |
| **Total** | **9-15 hari** | **Production-ready model** |

---

## 10. Langkah Selanjutnya (Immediate Actions)

1. **Verifikasi model**: Cek apakah Qwen 3.5 9B sudah tersedia di HuggingFace, atau gunakan Qwen 2.5 9B-Instruct
2. **Verifikasi hardware**: Cek VRAM GPU (`nvidia-smi`) untuk menentukan LoRA config
3. **Mulai Phase 0**: Setup environment dan install dependencies
4. **Mulai Phase 1**: Buat script parser risalah → conversations

---

*Document created: 2026-05-02*
*Author: Simulasi MK Development Team*
*Status: PLANNING*