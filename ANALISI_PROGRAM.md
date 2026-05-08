# 📘 DOKUMENTASI LENGKAP: Simulasi Sidang Mahkamah Konstitusi (AI vs AI)

> File ini dibuat untuk analisis eksternal oleh Agent AI.
> Proyek: Simulasi Sidang MK — Pengujian Undang-Undang (Judicial Review)
> Tanggal Pembuatan Dokumen: 2026-04-25

---

## 📑 DAFTAR ISI

1. [Ikhtisar Proyek](#1-ikhtisar-proyek)
2. [Struktur Direktori](#2-struktur-direktori)
3. [Konfigurasi](#3-konfigurasi)
4. [Dependensi](#4-dependensi)
5. [Backend (Python)](#5-backend-python)
   - 5.1 Entry Point (main.py)
   - 5.2 Web Server (server.py)
   - 5.3 Orchestrator (core/orchestrator.py)
   - 5.4 Agents (core/agents.py)
   - 5.5 Utils (core/utils.py)
   - 5.6 Preprocessor (core/preprocessor.py)
6. [RAG Module](#6-rag-module)
   - 6.1 Retriever (rag/retriever.py)
   - 6.2 Pasal API (rag/pasal_api.py)
   - 6.3 Extract & Chunk (rag/extract_and_chunk.py)
   - 6.4 Create Vector DB (rag/create_vector_db.py)
7. [Frontend](#7-frontend)
   - 7.1 HTML (static/index.html)
   - 7.2 CSS (static/style.css)
   - 7.3 JavaScript (static/app.js)
8. [Tools & Pipeline](#8-tools--pipeline)
9. [Roadmap](#9-roadmap)
10. [Alur Simulasi Sidang](#10-alur-simulasi-sidang)

---

## 1. IKHtisar Proyek

**Nama Proyek:** Simulasi Sidang MK — Pengujian Undang-Undang (Judicial Review)  
**Tujuan:** Mensimulasikan sidang pengujian undang-undang di Mahkamah Konstitusi dengan agen AI yang berperan sebagai Pemohon, Pemerintah, dan Panel Hakim.  
**Fitur Utama:**
- Simulasi multi-ronde sesuai hukum acara MK (Pemeriksaan Pendahuluan → Perbaikan → Ahli → Pokok Perkara → Kesimpulan & RPH)
- RAG dari 1.1M+ chunks putusan & risalah MK
- Mode AI vs AI dan Manusia vs AI
- Dissenting/Concurring Opinion
- Validator Dalil (Anti-Hallucination)
- Progress Tracker lintas simulasi
- Umpan balik terstruktur dari Hakim
- Web UI real-time dengan SSE streaming

---

## 2. STRUKTUR DIREKTORI

```
e:\Simu JR\
├── simulasi\                          # Root aplikasi utama
│   ├── main.py                        # Entry point CLI
│   ├── server.py                      # FastAPI web server
│   ├── config.yaml                    # Konfigurasi aplikasi
│   ├── requirements.txt               # Dependensi Python
│   ├── .env.example                   # Template environment variables
│   ├── ROADMAP.md                     # Daftar fitur & rencana
│   ├── check_rag.py                   # Health check RAG
│   ├── extract_uud.py                 # Ekstraktor UUD 1945 PDF → JSON
│   │
│   ├── core\                          # Modul inti (agents & orchestrator)
│   │   ├── __init__.py
│   │   ├── agents.py                  # Definisi semua agent AI
│   │   ├── orchestrator.py            # Alur simulasi sidang
│   │   ├── utils.py                   # Utilitas (PDF extraction)
│   │   └── preprocessor.py            # Preprocessing draft permohonan
│   │
│   ├── rag\                           # Retrieval-Augmented Generation
│   │   ├── __init__.py
│   │   ├── retriever.py               # Query interface ChromaDB
│   │   ├── pasal_api.py               # Client API pasal.id
│   │   ├── extract_and_chunk.py       # PDF → chunks → JSONL
│   │   ├── create_vector_db.py        # JSONL → ChromaDB embeddings
│   │   ├── rag_chunks.jsonl           # Database chunks mentah
│   │   └── chroma_db\                 # Vector database ChromaDB
│   │
│   └── static\                        # Frontend web
│       ├── index.html                 # Halaman utama
│       ├── app.js                     # Logic frontend
│       └── style.css                  # Styling
│
├── download_putusan_pdf.py            # Downloader PDF paralel
├── download_risalah_pipeline.py       # Pipeline download risalah
├── extract_pdf_links.py               # Ekstraktor link PDF
├── putusan_pdf\                       # Folder PDF putusan MK
├── risalah_pdf\                       # Folder PDF risalah DPR
├── UUD45_SatuNaskah.pdf               # Sumber UUD 1945
└── ANALISI_PROGRAM.md                 # File ini
```

---

## 3. KONFIGURASI

### config.yaml

```yaml
# ============================================
# Konfigurasi Simulasi Sidang MK
# ============================================

simulation:
  jumlah_hakim: 3            # Panel hakim (3, 5, 7, atau 9)
  jumlah_simulasi: 3         # Default N simulasi per run
  mode: sequential           # sequential | parallel

llm:
  base_url: "http://192.168.1.102:1234/v1"
  api_key: "not-needed-for-local"
  model_name: "local-model"
  temperature_hakim: 0.1     # Deterministik untuk hakim
  temperature_pihak: 0.7     # Lebih kreatif untuk para pihak

rag:
  db_path: "rag/chroma_db"
  collection_name: "mk_knowledge_base"
  embedding_model: "all-MiniLM-L6-v2"
  n_results: 7               # Jumlah chunk yang di-retrieve per query
  score_threshold: 0.5       # Minimum similarity score (0-1, lower = more similar for L2)

memory:
  max_history: 20            # Maks pesan di memory agent (sliding window)
  summarize_after: 15        # Trigger summarization setelah N pesan

scoring:
  legal_standing: 25
  kerugian_konstitusional: 20
  substansi_argumen: 30
  konsistensi_putusan: 15
  kelengkapan_formil: 10
```

### .env.example

```bash
# === LLM Configuration ===
LLM_BASE_URL=http://192.168.1.102:1234/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL_NAME=local-model

# === API Keys (opsional) ===
# PASAL_ID_API_KEY=your_key_here

# === ChromaDB ===
CHROMA_DB_PATH=E:\Simu JR\simulasi\rag\chroma_db
CHROMA_COLLECTION_NAME=mk_knowledge_base
PASAL_API_TOKEN=your_pasal_id_token_here
```

---

## 4. DEPENDENSI

### requirements.txt

```
# === Core Dependencies ===
openai>=1.0.0           # AsyncOpenAI client (LM Studio / Ollama compatible)
anthropic>=0.9.0        # AsyncAnthropic client (Claude APIs)
chromadb>=0.4.0         # Vector database
sentence-transformers   # Embedding models
PyMuPDF                 # PDF extraction (fitz)
langchain-text-splitters # Text chunking
pymupdf
python-docx

# === Configuration ===
python-dotenv           # .env file support
pyyaml                  # config.yaml parser

# === Utilities ===
tqdm                    # Progress bars
requests                # HTTP client
rank-bm25               # Hybrid search support
```

---

## 5. BACKEND (PYTHON)

### 5.1 Entry Point — main.py

File ini adalah entry point untuk menjalankan simulasi via command line (CLI).

```python
"""
Simulasi Sidang Mahkamah Konstitusi (MK) — Entry Point
========================================================
Menjalankan N simulasi sidang pengujian undang-undang (Judicial Review)
dengan agen AI yang berperan sebagai Pemohon, Pemerintah, dan Panel Hakim.
Setiap agen didukung oleh RAG dari 1.1M+ chunks putusan & risalah MK.
"""

import asyncio
import argparse
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any

from core.orchestrator import SimulationOrchestrator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

PROGRESS_FILE = os.path.join("results", "progress_history.json")


def load_progress_history():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_progress_entry(scores, draft_excerpt):
    history = load_progress_history()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "draft_excerpt": draft_excerpt[:100],
        "total": scores.get("total", 0),
        "amar": scores.get("amar", "ditolak"),
        "dimensions": {k: scores.get(k, 0) for k in [
            "legal_standing", "kerugian_konstitusional",
            "substansi_argumen", "konsistensi_putusan", "kelengkapan_formil"
        ]}
    }
    history.append(entry)
    history = history[-20:]
    os.makedirs("results", exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    return history


def print_progress_tracker(history):
    if len(history) < 2:
        return
    prev = history[-2]
    curr = history[-1]
    print(f"\n{'='*60}")
    print("  PROGRESS TRACKER")
    print(f"{'='*60}")
    delta = curr.get("total", 0) - prev.get("total", 0)
    arrow = "+" if delta >= 0 else ""
    print(f"  Skor: {curr.get('total', 0):.1f}/100  ({arrow}{delta:.1f} vs sebelumnya)")
    print(f"  Amar: {curr.get('amar')} | Sebelumnya: {prev.get('amar')}")
    dim_labels = {
        "legal_standing": "Legal Standing",
        "kerugian_konstitusional": "Kerugian Konstitusional",
        "substansi_argumen": "Substansi Argumen",
        "konsistensi_putusan": "Konsistensi Putusan",
        "kelengkapan_formil": "Kelengkapan Formil"
    }
    for key, label in dim_labels.items():
        c = curr.get("dimensions", {}).get(key, 0)
        p = prev.get("dimensions", {}).get(key, 0)
        d = c - p
        arrow2 = "+" if d >= 0 else ""
        icon = "^" if d > 0 else ("v" if d < 0 else "-")
        print(f"  {icon} {label.ljust(28)}: {c:.1f}  ({arrow2}{d:.1f})")

    if len(history) >= 3:
        print(f"\n  Tren (terakhir {min(len(history), 5)} simulasi):")
        for h in history[-5:]:
            t = h.get("total", 0)
            bar = "#" * int(t / 5)
            print(f"    {bar} {t:.0f}")
    print(f"{'='*60}")


async def cli_human_input_callback(prompt: str, rag_context: str, agent_name: str) -> str:
    print(f"\n{'='*60}")
    print("  [GILIRAN ANDA SEBAGAI PEMOHON]")
    print(f"{'='*60}")
    # Tampilkan konteks pertanyaan (600 karakter pertama)
    print(f"Konteks:\n{prompt[:600]}")
    print(f"\nMasukkan argumen Anda (ketik argumen, lalu tekan Enter):")
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, input, "> ")
    return response


def print_final_verdict(results: List[Dict[str, Any]]):
    """Menampilkan hasil akhir agregat dari seluruh simulasi."""
    print("\n" + "═" * 60)
    print("  🏛️  HASIL VERDICT AGGREGATOR")
    print("═" * 60)

    dimensions = {
        "legal_standing": 25,
        "kerugian_konstitusional": 20,
        "substansi_argumen": 30,
        "konsistensi_putusan": 15,
        "kelengkapan_formil": 10
    }

    valid_results = [r for r in results if "error" not in r.get("scores", {})]

    if not valid_results:
        print("❌ Tidak ada data scoring valid yang bisa diagregasi.")
        return

    # Agregasi lintas simulasi
    dim_totals = {d: 0 for d in dimensions}
    total_score = 0
    all_amars = []
    all_catatan = []

    for r in valid_results:
        scores = r["scores"]
        for d in dimensions:
            dim_totals[d] += scores.get(d, 0)
        total_score += scores.get("total", 0)
        all_amars.append(scores.get("amar", "ditolak"))
        all_catatan.extend(scores.get("catatan_hakim", []))

    n = len(valid_results)
    avg_total = total_score / n

    # Voting amar lintas simulasi
    from collections import Counter
    amar_count = Counter(all_amars)
    final_amar = amar_count.most_common(1)[0][0]

    print(f"\n  📊 Simulasi valid: {n}/{len(results)}")
    print(f"  📈 Skor rata-rata: {avg_total:.1f}/100")

    # Amar
    amar_emoji = {"dikabulkan": "✅", "ditolak": "❌", "tidak_dapat_diterima": "⛔"}
    print(f"\n  ⚖️  AMAR PUTUSAN: {amar_emoji.get(final_amar, '❓')} {final_amar.upper()}")
    print(f"     Voting: {dict(amar_count)}")

    # Heatmap kelemahan
    print(f"\n  🔥 HEATMAP KELEMAHAN (Skor Rata-rata per Dimensi):")
    for dim, max_val in dimensions.items():
        avg_dim = dim_totals[dim] / n
        percent = (avg_dim / max_val) * 100
        bar_len = int(percent / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        status = "🟢" if percent >= 70 else "🟡" if percent >= 40 else "🔴"
        print(f"    {status} {dim.ljust(28)}: {avg_dim:.1f}/{max_val} ({percent:.0f}%) [{bar}]")

    # Saran hakim
    if all_catatan:
        print(f"\n  💡 CATATAN DARI PANEL HAKIM:")
        for cat in all_catatan[:10]:  # Limit 10 catatan
            print(f"    • {cat}")

    # Dissenting Opinions (ROADMAP Fase 2 #1)
    all_dissenting = []
    for r in valid_results:
        all_dissenting.extend(r.get("dissenting_opinions", []))
    if all_dissenting:
        print(f"\n  ⚖️  DISSENTING / CONCURRING OPINIONS ({len(all_dissenting)} total):")
        for op in all_dissenting:
            icon = "❗" if op["type"] == "Dissenting Opinion" else "💬"
            print(f"\n  {icon} {op['type']} — {op['hakim']}")
            print(f"     Amar Hakim: {op['amar_hakim']} | Amar Mayoritas: {op['amar_mayoritas']}")
            # Tampilkan 3 baris pertama opinion
            lines = op.get("opinion", "").split("\n")[:3]
            for line in lines:
                if line.strip():
                    print(f"     {line.strip()}")

    print("\n" + "═" * 60)


async def run_simulations(n: int, draft_input: str, sequential: bool = True, mode: str = "ai"):
    """Menjalankan N simulasi sidang MK."""
    run_mode_label = "Sekuensial" if sequential else "Paralel"
    print(f"\n🚀 Memulai {n} simulasi ({run_mode_label}, mode={mode})...\n")

    human_callback = cli_human_input_callback if mode == "human" else None

    orchestrators = [
        SimulationOrchestrator(
            i + 1,
            mode=mode,
            human_input_callback=human_callback
        )
        for i in range(n)
    ]
    results = []

    if sequential:
        for orch in orchestrators:
            res = await orch.run_full_simulation(draft_input)
            results.append(res)
    else:
        # PERINGATAN: Paralel bisa membebani VRAM/API
        tasks = [orch.run_full_simulation(draft_input) for orch in orchestrators]
        results = await asyncio.gather(*tasks)

    # Simpan transcript lengkap
    os.makedirs("results", exist_ok=True)
    output_path = "results/all_simulations.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n📝 Transcript simulasi disimpan di: {output_path}")

    # Tampilkan verdict
    print_final_verdict(results)

    # Progress tracker
    valid = [r for r in results if "error" not in r.get("scores", {})]
    if valid:
        avg_scores = valid[0]["scores"]  # Gunakan hasil simulasi pertama yang valid
        history = save_progress_entry(avg_scores, draft_input[:100])
        print_progress_tracker(history)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="🏛️ Simulasi Sidang MK — Pengujian Undang-Undang (AI vs AI)"
    )
    parser.add_argument(
        "--n", type=int, default=3,
        help="Jumlah simulasi yang dijalankan (default: 3)"
    )
    parser.add_argument(
        "--parallel", action="store_true",
        help="Jalankan secara paralel (AWAS VRAM!)"
    )
    parser.add_argument(
        "--draft", type=str, default=None,
        help="Path ke file .txt berisi draft permohonan (opsional)"
    )
    parser.add_argument(
        "--mode", choices=["ai", "human"], default="ai",
        help="Mode simulasi: 'ai' (default) atau 'human' (Anda berperan sebagai Pemohon)"
    )
    args = parser.parse_args()

    # Input draft
    if args.draft and os.path.exists(args.draft):
        with open(args.draft, "r", encoding="utf-8") as f:
            draft = f.read()
        print(f"📄 Draft dimuat dari: {args.draft}")
    else:
        draft = (
            "Pemohon mengajukan pengujian Pasal 28 ayat (1) UU No. 11 Tahun 2008 "
            "tentang Informasi dan Transaksi Elektronik (UU ITE). "
            "Pemohon adalah seorang jurnalis investigasi yang merasa hak kebebasan "
            "berpendapat dan kebebasan pers yang dijamin Pasal 28E ayat (2) dan "
            "Pasal 28F UUD 1945 terancam oleh ketentuan tersebut. "
            "Kerugian aktual berupa pemanggilan oleh kepolisian karena mempublikasikan "
            "artikel kritik terhadap kebijakan pejabat daerah di media daring. "
            "Pemohon berpendapat frasa 'menyebarkan berita bohong' dalam pasal tersebut "
            "bersifat multi-tafsir (overbreadth) dan berpotensi menjadi alat kriminalisasi "
            "terhadap kebebasan berekspresi."
        )
        print("📄 Menggunakan draft contoh (UU ITE)")

    asyncio.run(run_simulations(args.n, draft, sequential=not args.parallel, mode=args.mode))
```

### 5.2 Web Server — server.py

FastAPI backend yang menyajikan UI dan streaming transcript sidang secara real-time via SSE (Server-Sent Events).

```python
"""
Web Server — Simulasi Sidang MK
=================================
FastAPI backend yang menyajikan UI dan streaming transcript sidang secara real-time.
"""

import asyncio
import json
import logging
import os
import sys
import time
import shutil
from typing import Dict, Any, List

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Setup path agar bisa import modul lokal
sys.path.insert(0, os.path.dirname(__file__))

from core.agents import PemohonAgent, PemerintahAgent, HakimAgent
from core.orchestrator import SimulationOrchestrator
from core.utils import extract_text_from_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Simulasi Sidang MK", version="1.0")
active_simulations: Dict[str, asyncio.Task] = {}

# Queue for human input in interactive mode
human_input_queue: asyncio.Queue = asyncio.Queue()

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    """Extract text from uploaded file (PDF, DOCX, TXT, MD)."""
    try:
        # Create temp directory if not exists
        temp_dir = Path(__file__).parent / "temp_uploads"
        temp_dir.mkdir(exist_ok=True)
        
        file_path = str(temp_dir / file.filename)
        logger.info(f"📂 Menerima file untuk ekstraksi: {file.filename} -> {file_path}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        text = extract_text_from_file(file_path, file.filename)
        logger.info(f"📝 Hasil ekstraksi ({len(text)} karakter)")
        
        # Cleanup
        os.remove(file_path)
        
        if not text.strip():
            return JSONResponse({"error": "Gagal mengekstrak teks atau file kosong"}, status_code=400)
            
        return {"text": text}
    except Exception as e:
        return JSONResponse({"error": f"Error: {str(e)}"}, status_code=500)

@app.post("/api/chat-revision")
async def chat_revision(request: Request):
    """Chat dengan AI untuk meminta revisi draf berdasarkan transcript."""
    body = await request.json()
    message = body.get("message", "")
    draft = body.get("draft", "")
    transcript = body.get("transcript", [])
    llm_config = body.get("llm_config", {})

    if not message:
        return JSONResponse({"error": "Pesan tidak boleh kosong"}, status_code=400)

    # Buat agent sementara untuk handle chat
    agent = PemohonAgent(llm_config=llm_config)
    
    # Format context untuk chat
    transcript_text = "\n".join([f"[{t['round']}] {t['speaker']}: {t['content'][:200]}..." for t in transcript[-10:]])
    
    prompt = f"""\
Anda adalah konsultan hukum ahli Mahkamah Konstitusi. 
Berikut adalah draf permohonan saat ini:
\"\"\"
{draft}
\"\"\"

Berikut adalah ringkasan jalannya persidangan simulasi:
\"\"\"
{transcript_text}
\"\"\"

User bertanya: "{message}"

Berikan saran perbaikan draf yang taktis dan mendalam berdasarkan kritik hakim atau bantahan pemerintah dalam sidang. 
Jika diminta merevisi teks, berikan potongan teks yang disarankan.
Jawablah dengan nada profesional dan membantu.
"""

    try:
        response = await agent.generate_response(prompt)
        return {"response": response}
    except Exception as e:
        logging.error(f"Chat error: {e}")
        return JSONResponse({"error": f"Gagal mendapatkan respon dari AI: {str(e)}"}, status_code=500)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve halaman utama."""
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.post("/api/simulate")
async def run_simulation(request: Request):
    """
    Endpoint untuk menjalankan simulasi.
    Mengembalikan SSE stream dari transcript secara real-time.
    """
    body = await request.json()
    draft = body.get("draft", "")
    jumlah_hakim = body.get("jumlah_hakim", 3)
    llm_config = body.get("llm_config", {})
    mode = body.get("mode", "ai")

    logger.info(f"🚀 Memulai simulasi dengan provider: {llm_config.get('provider')}, model: {llm_config.get('model_name')}, mode: {mode}")

    if not draft.strip():
        return JSONResponse({"error": "Draft permohonan tidak boleh kosong"}, status_code=400)

    # Validasi API Key jika menggunakan Claude
    if llm_config.get("provider") == "claude" and not llm_config.get("api_key"):
        return JSONResponse({"error": "API Key Claude diperlukan untuk menggunakan provider ini"}, status_code=400)

    async def event_stream():
        """Generator SSE — kirim setiap interaksi ke client secara real-time menggunakan queue."""
        q = asyncio.Queue()
        orch = StreamingOrchestrator(
            q=q,
            simulation_id=1,
            jumlah_hakim=jumlah_hakim,
            llm_config=llm_config,
            human_input_queue=human_input_queue if mode == "human" else None
        )

        # Kirim event "started"
        provider_name = llm_config.get("provider", "local").upper()
        yield _sse_event("status", {"message": f"Simulasi dimulai ({provider_name})...", "phase": "init"})

        # Jalankan simulasi di background
        task = asyncio.create_task(orch.run_full_simulation_streaming(draft))
        active_simulations["current"] = task  # Simplify for now
        
        # Loop membaca antrian dan mengirimkannya sebagai SSE stream langsung
        while True:
            try:
                # Wait 15 seconds max. If no event, send a keep-alive ping
                event = await asyncio.wait_for(q.get(), timeout=15.0)
                if event == "DONE":
                    break
                yield event
            except asyncio.TimeoutError:
                # Detak jantung agar browser tidak memutuskan koneksi
                yield ": keep-alive\n\n"

        # Tunggu task selesai dan kirim hasil final
        try:
            result = await task
            yield _sse_event("scores", result.get("scores", {}))
            yield _sse_event("individual_scores", result.get("individual_scores", []))
            # Kirim dissenting opinions jika ada (ROADMAP Fase 2 #1)
            if result.get("dissenting_opinions"):
                yield _sse_event("dissenting_opinions", result.get("dissenting_opinions", []))
            # Kirim feedback jika ada (ROADMAP Fase 4 #8)
            if result.get("feedback"):
                yield _sse_event("feedback", result.get("feedback", {}))
            yield _sse_event("status", {"message": "Simulasi selesai", "phase": "done"})
        except asyncio.CancelledError:
            logger.warning("⚠️ Simulasi dibatalkan di server.")
            yield _sse_event("status", {"message": "Simulasi dibatalkan", "phase": "stopped"})
        finally:
            active_simulations.pop("current", None)
            
        yield _sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/stop")
async def stop_simulation():
    """Endpoint untuk menghentikan simulasi yang sedang berjalan."""
    task = active_simulations.get("current")
    if task and not task.done():
        task.cancel()
        logger.info("🛑 Simulasi dibatalkan paksa.")
        return {"status": "stopping"}
    return {"status": "no_active_simulation"}


@app.post("/api/human_input")
async def receive_human_input(request: Request):
    """Terima input dari manusia (mode interaktif) dan masukkan ke queue."""
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "Input tidak boleh kosong"}, status_code=400)
    human_input_queue.put_nowait(text)
    return {"status": "ok"}


@app.get("/api/progress")
async def get_progress():
    """Ambil riwayat progres simulasi dari file."""
    path = Path(__file__).parent / "results" / "progress_history.json"
    if not path.exists():
        return {"history": []}
    try:
        return {"history": json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return {"history": []}


@app.post("/api/progress")
async def save_progress(request: Request):
    """Simpan entri progres simulasi ke file."""
    body = await request.json()
    path = Path(__file__).parent / "results" / "progress_history.json"
    path.parent.mkdir(exist_ok=True)
    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    history.append(body)
    history = history[-20:]
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "total": len(history)}

@app.get("/api/health")
async def health(url: str = None):
    """Health check & RAG/LLM status."""
    rag_status = "unavailable"
    rag_vectors = 0
    try:
        from rag.retriever import RAGRetriever
        r = RAGRetriever()
        stats = r.get_stats()
        rag_status = "connected"
        rag_vectors = stats["total_vectors"]
    except Exception as e:
        rag_status = f"error: {str(e)[:100]}"

    # LLM connectivity check
    llm_status = "unknown"
    check_url = url or os.getenv("LLM_BASE_URL", "http://192.168.1.102:1234/v1")
    
    try:
        import httpx
        # Coba panggil models endpoint (standard OpenAI spec)
        async with httpx.AsyncClient() as client:
            # Pastikan URL berakhir dengan /v1 jika tidak ada
            base = check_url.rstrip("/")
            test_url = f"{base}/models" if "/v1" in base else f"{base}/v1/models"
            
            resp = await client.get(test_url, timeout=5.0)
            if resp.status_code == 200:
                llm_status = "connected"
            else:
                llm_status = f"status: {resp.status_code}"
    except httpx.ConnectError:
        llm_status = "connection_refused"
    except httpx.TimeoutException:
        llm_status = "timeout"
    except Exception as e:
        llm_status = f"error: {str(e)[:50]}"

    return {
        "status": "ok",
        "rag": rag_status,
        "rag_vectors": rag_vectors,
        "llm": llm_status,
        "llm_url": check_url
    }


def _sse_event(event_type: str, data: Any) -> str:
    """Format SSE event string."""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


class StreamingOrchestrator(SimulationOrchestrator):
    """
    Extends orchestrator untuk mengumpulkan SSE events
    dan memasukannya ke Queue agar bisa langsung di-stream ke browser.
    """

    def __init__(self, q: asyncio.Queue, *args, human_input_queue=None, **kwargs):
        # Tambahkan callback untuk handle chunks dari agent
        kwargs["on_chunk_callback"] = self._on_agent_chunk
        # Jika human_input_queue disediakan, aktifkan mode manusia
        if human_input_queue is not None:
            kwargs["mode"] = "human"
            kwargs["human_input_callback"] = self._human_input_handler
        super().__init__(*args, **kwargs)
        self.q = q
        self.human_input_queue = human_input_queue

    async def _on_agent_chunk(self, speaker: str, chunk: str):
        """Kirim potongan teks (chunk) ke frontend via SSE."""
        self.q.put_nowait(
            _sse_event("transcript_chunk", {
                "speaker": speaker,
                "content": chunk
            })
        )

    async def _human_input_handler(self, prompt: str, rag_context: str, agent_name: str) -> str:
        """Handler untuk menunggu input manusia via queue."""
        self.q.put_nowait(_sse_event("waiting_for_human", {
            "prompt": prompt[:1200],
            "agent_name": agent_name
        }))
        try:
            response = await asyncio.wait_for(self.human_input_queue.get(), timeout=600.0)
            return response
        except asyncio.TimeoutError:
            return "[Waktu habis — Pemohon tidak memberikan respons]"

    def _log_interaction(self, round_name: str, speaker: str, content: str, validation_result=None):
        """Override: log + dorong SSE event ke Queue seketika."""
        super()._log_interaction(round_name, speaker, content, validation_result)
        self.q.put_nowait(
            _sse_event("transcript", {
                "round": round_name,
                "speaker": speaker,
                "content": content,
                "timestamp": time.time()
            })
        )

    async def run_full_simulation_streaming(self, draft_input: str) -> Dict[str, Any]:
        """Jalankan simulasi penuh, dorong status ke Queue seketika."""
        result = {}
        try:
            self.q.put_nowait(_sse_event("status", {"message": "Ronde 1: Pemeriksaan Pendahuluan", "phase": "round1"}))
            await self.run_round_1_pendahuluan(draft_input)

            self.q.put_nowait(_sse_event("status", {"message": "Ronde 2: Perbaikan Permohonan", "phase": "round2"}))
            await self.run_round_2_perbaikan()

            self.q.put_nowait(_sse_event("status", {"message": "Ronde 2B: Pemeriksaan Ahli", "phase": "round2b"}))
            await self.run_round_2b_ahli()

            self.q.put_nowait(_sse_event("status", {"message": "Ronde 3: Pokok Perkara", "phase": "round3"}))
            await self.run_round_3_pokok_perkara()

            self.q.put_nowait(_sse_event("status", {"message": "Ronde 4: Kesimpulan & RPH", "phase": "round4"}))
            result = await self.run_round_4_kesimpulan()

            self.q.put_nowait(_sse_event("status", {"message": "Umpan Balik Hakim", "phase": "feedback"}))
            feedback = await self.run_round_5_feedback()
            result["feedback"] = feedback
            if feedback:
                self.q.put_nowait(_sse_event("feedback", feedback))
        except Exception as e:
            logger.error(f"Error during simulation: {e}")
            result = {"error": str(e)}
        finally:
            self.q.put_nowait("DONE")

        return result


if __name__ == "__main__":
    import uvicorn
    print("\n>>> Simulasi Sidang MK -- Web Server")
    print("    Buka browser: http://localhost:8080\n")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
```

### 5.3 Orchestrator — core/orchestrator.py

Mengatur alur sidang pengujian undang-undang sesuai hukum acara MK. File terpanjang (905 baris) dengan 5 ronde simulasi.

**Kelas utama:** `SimulationOrchestrator`

**Alur Ronde:**
1. **Ronde 1:** Pemeriksaan Pendahuluan (Legal Standing)
2. **Ronde 2:** Perbaikan Permohonan (opsional)
3. **Ronde 2B:** Pemeriksaan Ahli — Baru
4. **Ronde 3:** Pokok Perkara + Pihak Terkait + Amicus Curiae
5. **Ronde 4:** Kesimpulan & RPH + Dissenting Opinion
6. **Ronde 5:** Umpan Balik Terstruktur dari Hakim

**Fitur Baru:**
- Validator Dalil (Anti-Hallucination)
- Word Limiter + Interupsi Hakim
- Pasal.id API integration untuk teks pasal asli

```python
"""
Simulation Orchestrator — Sidang MK
=====================================
Mengatur alur sidang pengujian undang-undang (PUU) sesuai hukum acara MK.
Setiap ronde meng-query RAG untuk memperkaya argumen agents dengan referensi hukum.

Alur Sidang (ROADMAP terintegrasi):
  Ronde 1  → Pemeriksaan Pendahuluan (Legal Standing)
  Ronde 2  → Perbaikan Permohonan (opsional)
  Ronde 2B → Pemeriksaan Ahli — BARU (ROADMAP Fase 3 #4)
  Ronde 3  → Pokok Perkara + Pihak Terkait + Amicus Curiae — DIPERLUAS (ROADMAP Fase 2 #2)
  Ronde 4  → Kesimpulan & RPH + Dissenting Opinion — DIPERLUAS (ROADMAP Fase 2 #1)

Fitur Baru:
  - Validator Dalil (Anti-Hallucination) sebelum pencatatan transcript (ROADMAP Fase 2 #3)
  - Word Limiter + Interupsi Hakim per respons agen (ROADMAP Fase 3 #5)
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional

from .agents import (
    PemohonAgent, PemerintahAgent, HakimAgent,
    PihakTerkaitAgent, AmicusCuriaeAgent,
    AhliPemohonAgent, AhliPemerintahAgent,
    ValidatorAgent
)
from rag.pasal_api import pasal_api

# Import retriever — graceful fallback jika DB belum ada
try:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from rag.retriever import RAGRetriever
    RAG_AVAILABLE = True
except Exception as e:
    RAG_AVAILABLE = False
    logging.warning(f"⚠️ RAG tidak tersedia: {e}. Simulasi berjalan tanpa referensi hukum.")

logger = logging.getLogger(__name__)


class SimulationOrchestrator:
    """Orkestrator utama yang mengatur alur sidang MK."""

    def __init__(
        self,
        simulation_id: int,
        jumlah_hakim: int = 3,
        llm_config: Dict[str, Any] = None,
        on_chunk_callback: Any = None,
        include_pihak_terkait: bool = True,
        include_amicus: bool = True,
        include_ahli: bool = True,
        enable_validator: bool = True,
        mode: str = "ai",
        human_input_callback: Optional[Any] = None
    ):
        self.simulation_id = simulation_id
        self.llm_config = llm_config or {}
        self.on_chunk_callback = on_chunk_callback
        self.include_pihak_terkait = include_pihak_terkait
        self.include_amicus = include_amicus
        self.include_ahli = include_ahli
        self.enable_validator = enable_validator
        self.mode = mode
        self.human_input_callback = human_input_callback

        # === Agen Inti ===
        self.pemohon = PemohonAgent(llm_config=self.llm_config)
        self.pemerintah = PemerintahAgent(llm_config=self.llm_config)
        self.panel_hakim = [HakimAgent(i + 1, llm_config=self.llm_config) for i in range(jumlah_hakim)]

        # === Agen Baru (ROADMAP Fase 2 & 3) ===
        self.pihak_terkait = PihakTerkaitAgent(llm_config=self.llm_config) if include_pihak_terkait else None
        self.amicus_curiae = AmicusCuriaeAgent(llm_config=self.llm_config) if include_amicus else None
        self.ahli_pemohon = AhliPemohonAgent(llm_config=self.llm_config) if include_ahli else None
        self.ahli_pemerintah = AhliPemerintahAgent(llm_config=self.llm_config) if include_ahli else None
        self.validator = ValidatorAgent(llm_config=self.llm_config) if enable_validator else None

        # Inisialisasi RAG retriever (shared across rounds)
        self.retriever = None
        if RAG_AVAILABLE:
            try:
                self.retriever = RAGRetriever()
                stats = self.retriever.get_stats()
                logger.info(f"📚 RAG terhubung: {stats['total_vectors']:,} vectors")
            except Exception as e:
                logger.warning(f"⚠️ RAG init gagal: {e}")
                self.retriever = None

        self.transcript: List[Dict[str, str]] = []
        self.draft_context: str = ""  # Disimpan setelah ronde 1
        self.dissenting_opinions: List[Dict[str, str]] = []  # ROADMAP Fase 2 #1

    async def _generate_agent_response(self, agent: Any, prompt: str, rag_context: str = "") -> str:
        """Helper untuk memanggil generate_response dengan streaming callback jika tersedia."""
        # Mode manusia: jika pemohon dan callback tersedia, gunakan input manusia
        if (self.mode == "human"
                and hasattr(agent, "role")
                and agent.role == "pemohon"
                and self.human_input_callback):
            response = await self.human_input_callback(prompt, rag_context, agent.name)
            # Simpan ke memori agen
            if hasattr(agent, "memory"):
                agent.memory.append({"role": "assistant", "content": response})
                # Trim memori agar tidak terlalu panjang
                if len(agent.memory) > 20:
                    agent.memory = agent.memory[-20:]
            return response

        if self.on_chunk_callback:
            # Pastikan callback dibungkus untuk menyertakan info speaker
            async def chunk_handler(chunk):
                await self.on_chunk_callback(agent.name, chunk)

            return await agent.generate_response(prompt, rag_context=rag_context, on_chunk=chunk_handler)
        else:
            return await agent.generate_response(prompt, rag_context=rag_context)

    def _log_interaction(self, round_name: str, speaker: str, content: str,
                         validation_result: Optional[Dict] = None):
        """Catat setiap interaksi ke transcript dan console."""
        # Tampilkan validasi jika ada peringatan (ROADMAP Fase 2 #3)
        display_content = content
        if validation_result and validation_result.get("verdict") != "LOLOS":
            verdict = validation_result.get("verdict", "")
            warnings = validation_result.get("suspicious_citations", [])
            warning_text = (
                f"\n\n⚠️  [VALIDATOR DALIL — {verdict}] "
                f"Potensi halusinasi terdeteksi:\n"
                + "\n".join(f"  • {w}" for w in warnings)
            )
            display_content = content + warning_text

        # Gunakan safe print untuk mencegah UnicodeEncodeError di Windows Console
        try:
            print(f"\n[{round_name}] {speaker}:\n{display_content}\n" + "-" * 60)
        except UnicodeEncodeError:
            safe_content = display_content.encode('ascii', 'replace').decode('ascii')
            print(f"\n[{round_name}] {speaker}:\n{safe_content}\n" + "-" * 60)

        entry: Dict[str, Any] = {
            "round": round_name,
            "speaker": speaker,
            "content": content
        }
        if validation_result and validation_result.get("verdict") != "LOLOS":
            entry["validation_warning"] = validation_result
        self.transcript.append(entry)

    async def _validated_log(self, round_name: str, speaker: str, content: str):
        """
        Wrapper: validasi kutipan terlebih dahulu, lalu catat ke transcript.
        Hanya aktif jika enable_validator=True (ROADMAP Fase 2 #3).
        """
        validation_result = None
        if self.validator and self.enable_validator:
            try:
                validation_result = await self.validator.validate(content)
                if validation_result.get("verdict") != "LOLOS":
                    logger.warning(
                        f"[VALIDATOR] {speaker} — {validation_result.get('verdict')}: "
                        f"{validation_result.get('suspicious_citations', [])}"
                    )
            except Exception as e:
                logger.warning(f"[VALIDATOR] Gagal memvalidasi: {e}")
        self._log_interaction(round_name, speaker, content, validation_result)

    def _get_rag_context(self, query: str, role: str = "umum") -> str:
        """Query RAG dan kembalikan formatted context. Kosong jika RAG tidak tersedia."""
        if not self.retriever:
            return ""
        try:
            context = self.retriever.query_for_agent(query, agent_role=role)
            if context:
                logger.info(f"📎 RAG context ditemukan untuk {role} ({len(context)} chars)")
            return context
        except Exception as e:
            logger.warning(f"RAG query error: {e}")
            return ""

    async def _fetch_uu_context_from_api(self, draft: str) -> str:
        """Ekstrak nama UU/Pasal dari draft dan cari teks aslinya di pasal.id API."""
        queries = []
        # Cari pola 'Pasal X UU Y'
        pasal_matches = re.finditer(r'(Pasal\s+\d+[a-zA-Z]*(?:\s+ayat\s*\(\d+\))?.*?UU[A-Za-z0-9\s\.\-]+)', draft, re.IGNORECASE)
        for m in pasal_matches:
            queries.append(m.group(1).strip())
        
        # Fallback: cari pola 'UU No X Tahun Y'
        if not queries:
            uu_matches = re.finditer(r'(UU|Undang-Undang)\s+(?:No\.?\s*|Nomor\s*)?\d+\s+Tahun\s+\d{4}', draft, re.IGNORECASE)
            for m in uu_matches:
                queries.append(m.group(0).strip())
                
        # Deduplikasi dan batasi maks 2 query agar tidak spam
        queries = list(set(queries))[:2]
        
        if not queries:
            return ""
            
        logger.info(f"🔍 Mengambil teks pasal asli dari pasal.id untuk: {queries}")
        context_parts = []
        for q in queries:
            res = await pasal_api.search(q, limit=3)
            if res and not res.get("error") and res.get("results"):
                for item in res["results"]:
                    # Hanya ambil hasil yang relevansinya di atas threshold (0.4)
                    if item.get("score", 0) > 0.4:
                        meta = item.get("metadata", {})
                        work = item.get("work", {})
                        snippet = item.get("snippet", "")
                        context_parts.append(
                            f"[{work.get('title')} - {meta.get('node_type', 'Bagian').title()} {meta.get('node_number', '')}]\n\"{snippet}\""
                        )
                        
        if context_parts:
            return "\n\n=== REFERENSI PASAL (pasal.id API) ===\n" + "\n\n".join(context_parts)
        return ""

    # ================================================================
    # RONDE 1: PEMERIKSAAN PENDAHULUAN
    # ================================================================
    async def run_round_1_pendahuluan(self, draft_input: str):
        """
        Sidang Pendahuluan — Majelis Hakim menguji legal standing Pemohon.
        Panel 3 hakim secara bergiliran menanyakan aspek legal standing.
        """
        round_name = "Ronde 1: Pemeriksaan Pendahuluan"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Tarik data dari API Pasal (jika ditemukan referensi UU di draf)
        api_context = await self._fetch_uu_context_from_api(draft_input)
        self.draft_context = draft_input + api_context

        # RAG: cari putusan terkait topik yang sama
        rag_ctx_hakim = self._get_rag_context(
            f"legal standing pemohon pengujian {draft_input[:200]}",
            role="hakim"
        )
        if api_context:
            rag_ctx_hakim += api_context

        # Hakim Ketua membuka sidang & menanyakan legal standing
        hakim_q = await self._generate_agent_response(
            self.panel_hakim[0],
            f"Sidang dibuka. Berikut adalah ringkasan permohonan Pemohon:\n\n"
            f"\"{draft_input}\"\n\n"
            f"Sebagai Hakim Ketua, tanyakan secara kritis mengenai KEDUDUKAN HUKUM (Legal Standing) Pemohon. "
            f"Fokus pada: kualifikasi pemohon, hak konstitusional yang dirugikan, "
            f"dan hubungan kausal kerugian dengan berlakunya UU.",
            rag_context=rag_ctx_hakim
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, hakim_q)

        # RAG: cari preseden untuk pemohon
        rag_ctx_pemohon = self._get_rag_context(
            f"legal standing dikabulkan {draft_input[:200]}",
            role="pemohon"
        )
        if api_context:
            rag_ctx_pemohon += api_context

        # Pemohon menjawab legal standing
        pemohon_a = await self._generate_agent_response(
            self.pemohon,
            f"Majelis Hakim bertanya:\n\"{hakim_q}\"\n\n"
            f"Jelaskan legal standing Anda secara meyakinkan. "
            f"Buktikan 5 syarat Pasal 51 ayat (1) UU MK. "
            f"Sebutkan kerugian konstitusional yang spesifik dan aktual.",
            rag_context=rag_ctx_pemohon
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_a)

        # Hakim 2 menguji kelemahan legal standing
        hakim_q2 = await self._generate_agent_response(
            self.panel_hakim[1],
            f"Pemohon baru saja menjawab mengenai legal standing:\n\"{pemohon_a[:500]}\"\n\n"
            f"Berikan satu pertanyaan tajam yang menguji KELEMAHAN legal standing tersebut. "
            f"Apakah kerugian benar-benar spesifik? Apakah ada hubungan kausal yang jelas?",
            rag_context=rag_ctx_hakim
        )
        await self._validated_log(round_name, self.panel_hakim[1].name, hakim_q2)

        # Pemohon merespons pertanyaan lanjutan
        pemohon_a2 = await self._generate_agent_response(
            self.pemohon,
            f"Hakim bertanya lanjutan:\n\"{hakim_q2}\"\n\n"
            f"Jawab dengan bukti tambahan dan penguatan argumen legal standing Anda.",
            rag_context=rag_ctx_pemohon
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_a2)

    # ================================================================
    # RONDE 2: PERBAIKAN PERMOHONAN (opsional / advisory)
    # ================================================================
    async def run_round_2_perbaikan(self):
        """
        Sidang Perbaikan — Majelis memberikan nasihat perbaikan permohonan.
        Dalam MK asli, pemohon diberi 14 hari untuk memperbaiki.
        Di simulasi ini, hakim memberikan catatan perbaikan.
        """
        round_name = "Ronde 2: Perbaikan Permohonan"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Hakim Ketua memberikan nasihat perbaikan
        nasihat = await self._generate_agent_response(
            self.panel_hakim[0],
            f"Berdasarkan pemeriksaan pendahuluan sebelumnya, berikan NASIHAT PERBAIKAN "
            f"kepada Pemohon. Sebutkan secara spesifik bagian mana dari permohonan yang "
            f"perlu diperjelas atau dilengkapi (misal: batu uji, posita, petitum).\n"
            f"Berikan dalam format daftar bernomor yang ringkas."
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, nasihat)

        # Pemohon merespons perbaikan
        perbaikan = await self._generate_agent_response(
            self.pemohon,
            f"Majelis Hakim memberikan nasihat perbaikan:\n\"{nasihat}\"\n\n"
            f"Sampaikan perbaikan dan penajaman argumen Anda berdasarkan nasihat tersebut."
        )
        await self._validated_log(round_name, self.pemohon.name, perbaikan)

    # ================================================================
    # RONDE 2B: PEMERIKSAAN AHLI (ROADMAP Fase 3 #4) — BARU
    # ================================================================
    async def run_round_2b_ahli(self):
        """
        Sidang Pemeriksaan Ahli — Ronde tambahan setelah Perbaikan Permohonan.
        Ahli Pemohon dan Ahli Pemerintah berdebat di tataran teori konstitusi.
        Hakim menguji keduanya dengan pertanyaan akademis.
        (ROADMAP Fase 3 #4)
        """
        if not self.include_ahli or not self.ahli_pemohon or not self.ahli_pemerintah:
            logger.info("⏭️ Ronde 2B (Ahli) dilewati — agen ahli tidak aktif.")
            return

        round_name = "Ronde 2B: Pemeriksaan Ahli"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Hakim Ketua membuka sesi ahli
        hakim_pembuka = await self._generate_agent_response(
            self.panel_hakim[0],
            f"Sidang memasuki sesi Pemeriksaan Ahli. "
            f"Persilakan Ahli Pemohon untuk memberikan keterangan teori mengenai "
            f"konstitusionalitas norma yang diuji. "
            f"Konteks perkara: {self.draft_context[:300]}"
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, hakim_pembuka)

        # Ahli Pemohon memberikan keterangan
        rag_ctx_ahli = self._get_rag_context(
            f"teori konstitusi pengujian norma {self.draft_context[:200]}",
            role="pemohon"
        )
        ahli_p_ket = await self._generate_agent_response(
            self.ahli_pemohon,
            f"Hakim Ketua mempersilakan Anda:\n\"{hakim_pembuka}\"\n\n"
            f"Berikan keterangan ahli Anda. Fokus pada:\n"
            f"1. Teori konstitusi yang mendukung posisi Pemohon\n"
            f"2. Doktrin hukum internasional yang relevan\n"
            f"3. Mengapa norma yang diuji tidak proporsional atau melanggar prinsip konstitusional",
            rag_context=rag_ctx_ahli
        )
        await self._validated_log(round_name, self.ahli_pemohon.name, ahli_p_ket)

        # Hakim menguji Ahli Pemohon
        hakim_uji_ahli_p = await self._generate_agent_response(
            self.panel_hakim[1],
            f"Ahli Pemohon berpendapat:\n\"{ahli_p_ket[:500]}\"\n\n"
            f"Uji konsistensi keterangan ahli ini. "
            f"Apakah teori yang digunakan tepat konteksnya? "
            f"Adakah counter-argument dari perspektif teori hukum lain?"
        )
        await self._validated_log(round_name, self.panel_hakim[1].name, hakim_uji_ahli_p)

        # Ahli Pemohon merespons
        ahli_p_respons = await self._generate_agent_response(
            self.ahli_pemohon,
            f"Hakim mengajukan pertanyaan:\n\"{hakim_uji_ahli_p}\"\n\n"
            f"Pertahankan keterangan Anda dengan argumen teori yang lebih rinci."
        )
        await self._validated_log(round_name, self.ahli_pemohon.name, ahli_p_respons)

        # Ahli Pemerintah memberikan keterangan tandingan
        rag_ctx_ahli_gov = self._get_rag_context(
            f"open legal policy judicial deference {self.draft_context[:200]}",
            role="pemerintah"
        )
        ahli_gov_ket = await self._generate_agent_response(
            self.ahli_pemerintah,
            f"Ahli Pemohon berpendapat:\n\"{ahli_p_ket[:500]}\"\n\n"
            f"Berikan keterangan ahli Anda yang MEMBANTAH keterangan di atas. Fokus pada:\n"
            f"1. Teori open legal policy dan judicial self-restraint\n"
            f"2. Mengapa norma yang diuji masih dalam batas konstitusional\n"
            f"3. Preseden komparatif dari negara lain",
            rag_context=rag_ctx_ahli_gov
        )
        await self._validated_log(round_name, self.ahli_pemerintah.name, ahli_gov_ket)

        # Hakim menguji Ahli Pemerintah
        hakim_uji_ahli_gov = await self._generate_agent_response(
            self.panel_hakim[2],
            f"Ahli Pemerintah berpendapat:\n\"{ahli_gov_ket[:500]}\"\n\n"
            f"Tanyakan: di titik mana deference kepada legislator menemui batasnya? "
            f"Bagaimana Mahkamah seharusnya memposisikan dirinya?"
        )
        await self._validated_log(round_name, self.panel_hakim[2].name, hakim_uji_ahli_gov)

        # Ahli Pemerintah merespons
        ahli_gov_respons = await self._generate_agent_response(
            self.ahli_pemerintah,
            f"Hakim bertanya:\n\"{hakim_uji_ahli_gov}\"\n\n"
            f"Jawab secara akademis dan tegas."
        )
        await self._validated_log(round_name, self.ahli_pemerintah.name, ahli_gov_respons)

    # ================================================================
    # RONDE 3: POKOK PERKARA + PIHAK TERKAIT + AMICUS CURIAE
    # Diperluas dengan ROADMAP Fase 2 #2
    # ================================================================
    async def run_round_3_pokok_perkara(self):
        """
        Sidang Pokok Perkara — Pemohon memaparkan argumen substantif,
        Pemerintah memberikan keterangan bantahan, Hakim menguji keduanya.
        DIPERLUAS: Pihak Terkait dan Amicus Curiae turut memberikan pandangan.
        """
        round_name = "Ronde 3: Pokok Perkara"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # RAG: cari referensi untuk pokok perkara
        rag_ctx_pemohon = self._get_rag_context(
            f"pengujian norma inkonstitusional {self.draft_context[:200]}",
            role="pemohon"
        )
        rag_ctx_pemerintah = self._get_rag_context(
            f"open legal policy penolakan permohonan {self.draft_context[:200]}",
            role="pemerintah"
        )

        # Hakim 2 mempersilakan masuk ke pokok perkara
        hakim_q = await self._generate_agent_response(
            self.panel_hakim[1],
            "Sidang memasuki pokok perkara. Persilakan Pemohon untuk memaparkan "
            "argumen substansi mengapa norma yang diuji bertentangan dengan UUD 1945. "
            "Tanyakan secara spesifik: pasal UUD mana yang dijadikan batu uji dan "
            "bagaimana pertentangannya."
        )
        await self._validated_log(round_name, self.panel_hakim[1].name, hakim_q)

        # Pemohon memaparkan argumen substansi
        pemohon_a = await self._generate_agent_response(
            self.pemohon,
            f"Hakim mempersilakan:\n\"{hakim_q}\"\n\n"
            f"Paparkan argumen substansi Anda. Jelaskan:\n"
            f"1. Norma mana yang inkonstitusional dan mengapa\n"
            f"2. Pasal-pasal UUD 1945 yang dijadikan batu uji\n"
            f"3. Kerugian konkret yang ditimbulkan norma tersebut",
            rag_context=rag_ctx_pemohon
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_a)

        # Pemerintah memberikan keterangan bantahan
        pemerintah_a = await self._generate_agent_response(
            self.pemerintah,
            f"Pemohon baru saja memaparkan argumen substansi:\n\"{pemohon_a[:600]}\"\n\n"
            f"Berikan KETERANGAN PEMERINTAH yang membantah argumen Pemohon. "
            f"Gunakan strategi: open legal policy, ratio legis UU, dan preseden penolakan.",
            rag_context=rag_ctx_pemerintah
        )
        await self._validated_log(round_name, self.pemerintah.name, pemerintah_a)

        # === PIHAK TERKAIT (ROADMAP Fase 2 #2) ===
        if self.include_pihak_terkait and self.pihak_terkait:
            print(f"\n{'─'*40}")
            print(f"  >>> KETERANGAN PIHAK TERKAIT")
            print(f"{'─'*40}")

            pihak_terkait_a = await self._generate_agent_response(
                self.pihak_terkait,
                f"Permohonan yang diuji:\n{self.draft_context[:400]}\n\n"
                f"Pemohon berargumen:\n\"{pemohon_a[:400]}\"\n\n"
                f"Pemerintah membantah:\n\"{pemerintah_a[:400]}\"\n\n"
                f"Berikan keterangan Pihak Terkait. Sampaikan perspektif unik "
                f"dari kelompok yang Anda wakili yang belum terungkap kedua pihak.",
                rag_context=rag_ctx_pemohon
            )
            await self._validated_log(round_name, self.pihak_terkait.name, pihak_terkait_a)

            # Hakim merespons Pihak Terkait
            hakim_pt = await self._generate_agent_response(
                self.panel_hakim[0],
                f"Pihak Terkait menyampaikan:\n\"{pihak_terkait_a[:400]}\"\n\n"
                f"Ajukan pertanyaan klarifikasi: seberapa langsung dampak UU ini terhadap "
                f"pihak yang Anda wakili? Apa bedanya dengan posisi Pemohon?"
            )
            await self._validated_log(round_name, self.panel_hakim[0].name, hakim_pt)

        # === AMICUS CURIAE (ROADMAP Fase 2 #2) ===
        if self.include_amicus and self.amicus_curiae:
            print(f"\n{'─'*40}")
            print(f"  >>> PANDANGAN AMICUS CURIAE")
            print(f"{'─'*40}")

            amicus_a = await self._generate_agent_response(
                self.amicus_curiae,
                f"Perkara yang sedang diuji:\n{self.draft_context[:400]}\n\n"
                f"Argumen Pemohon:\n\"{pemohon_a[:350]}\"\n\n"
                f"Argumen Pemerintah:\n\"{pemerintah_a[:350]}\"\n\n"
                f"Sebagai Amicus Curiae, berikan pandangan akademis netral. Fokus pada:\n"
                f"1. Pendekatan komparatif dari mahkamah konstitusi negara lain\n"
                f"2. Teori hukum yang paling relevan untuk kasus ini\n"
                f"3. Rekomendasi tafsir konstitusional yang seimbang",
                rag_context=self._get_rag_context(
                    f"comparative constitutional law {self.draft_context[:200]}", role="hakim"
                )
            )
            await self._validated_log(round_name, self.amicus_curiae.name, amicus_a)

        # Hakim 3 mengajukan pertanyaan pamungkas kepada semua pihak
        hakim_q2 = await self._generate_agent_response(
            self.panel_hakim[2],
            f"Pemohon berargumen:\n\"{pemohon_a[:400]}\"\n\n"
            f"Pemerintah membantah:\n\"{pemerintah_a[:400]}\"\n\n"
            f"Berikan pertanyaan kritis terhadap KEDUA belah pihak. "
            f"Identifikasi kontradiksi atau kelemahan argumen masing-masing."
        )
        await self._validated_log(round_name, self.panel_hakim[2].name, hakim_q2)

        # Pemohon merespons
        pemohon_tanggapan = await self._generate_agent_response(
            self.pemohon,
            f"Hakim bertanya:\n\"{hakim_q2}\"\n\nTanggapi secara ringkas dan tajam."
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_tanggapan)

        # Pemerintah merespons
        pemerintah_tanggapan = await self._generate_agent_response(
            self.pemerintah,
            f"Hakim bertanya:\n\"{hakim_q2}\"\n\nTanggapi secara ringkas dan tajam."
        )
        await self._validated_log(round_name, self.pemerintah.name, pemerintah_tanggapan)

    # ================================================================
    # RONDE 4: KESIMPULAN & RPH + DISSENTING OPINION
    # Diperluas dengan ROADMAP Fase 2 #1
    # ================================================================
    async def _generate_dissenting_opinion(self, hakim: Any, majority_amar: str, hakim_score: Dict) -> str:
        """
        Generate Dissenting Opinion / Concurring Opinion dari hakim minoritas.
        (ROADMAP Fase 2 #1)
        """
        minority_amar = hakim_score.get("amar", "ditolak")
        is_concurring = (minority_amar == majority_amar)
        opinion_type = "CONCURRING OPINION (Pendapat Setuju dengan Alasan Berbeda)" \
            if is_concurring else "DISSENTING OPINION (Pendapat Berbeda)"

        prompt = (
            f"Anda telah memberikan penilaian dengan amar: {minority_amar}.\n"
            f"Amar mayoritas panel adalah: {majority_amar}.\n"
            f"Catatan Anda sebelumnya: {hakim_score.get('catatan', '-')}\n\n"
            f"Tulis {opinion_type} secara formal. Sertakan:\n"
            f"1. Pokok perbedaan/persetujuan pandangan Anda\n"
            f"2. Dasar hukum dan pertimbangan konstitusional yang Anda pegang\n"
            f"3. Implikasi dari pandangan ini bagi perkembangan hukum konstitusi\n\n"
            f"Format: Dokumen opinion formal, tidak lebih dari 3 paragraf padat."
        )
        return await hakim.generate_response(prompt)

    async def run_round_4_kesimpulan(self) -> Dict[str, Any]:
        """
        Kesimpulan para pihak & RPH.
        Setiap hakim memberikan scoring INDEPENDEN, lalu diagregasi.
        Jika ada perbedaan pendapat, generate Dissenting/Concurring Opinion.
        (ROADMAP Fase 2 #1)
        """
        round_name = "Ronde 4: Kesimpulan & RPH"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Kesimpulan Pemohon
        pemohon_kesimpulan = await self._generate_agent_response(
            self.pemohon,
            "Ini adalah tahap KESIMPULAN AKHIR. "
            "Sampaikan petitum final Anda secara ringkas dan tegas. "
            "Tegaskan mengapa permohonan harus dikabulkan."
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_kesimpulan)

        # Kesimpulan Pemerintah
        pemerintah_kesimpulan = await self._generate_agent_response(
            self.pemerintah,
            "Sampaikan kesimpulan akhir Pemerintah. "
            "Tegaskan bahwa permohonan harus DITOLAK atau TIDAK DAPAT DITERIMA."
        )
        await self._validated_log(round_name, self.pemerintah.name, pemerintah_kesimpulan)

        # ===== RPH: Setiap Hakim Scoring Independen =====
        print(f"\n{'─'*60}")
        print(f"  >>> RAPAT PERMUSYAWARATAN HAKIM (RPH) -- TERTUTUP")
        print(f"{'─'*60}")

        scoring_prompt = """\
Sebagai Hakim Konstitusi, berikan penilaian INDEPENDEN terhadap permohonan ini.
Evaluasi berdasarkan seluruh jalannya persidangan yang Anda ikuti.

PENTING: Anda harus memberikan skor numerik sesuai rentang yang ditentukan.
DILARANG memberikan skor di luar rentang atau dalam format non-angka.

Kembalikan HANYA format JSON berikut (tanpa teks tambahan apapun di luar JSON, tanpa markdown code block, tanpa penjelasan):
{
    "legal_standing": <angka 0-25>,
    "kerugian_konstitusional": <angka 0-20>,
    "substansi_argumen": <angka 0-30>,
    "konsistensi_putusan": <angka 0-15>,
    "kelengkapan_formil": <angka 0-10>,
    "amar": "<dikabulkan|ditolak|tidak_dapat_diterima>",
    "catatan": "<pertimbangan hukum singkat max 2 kalimat>"
}

CONTOH OUTPUT YANG BENAR:
{"legal_standing": 20, "kerugian_konstitusional": 15, "substansi_argumen": 25, "konsistensi_putusan": 12, "kelengkapan_formil": 8, "amar": "ditolak", "catatan": "Legal standing cukup kuat namun substansi argumen kurang mendalam."}
"""
        all_scores = []

        for hakim in self.panel_hakim:
            raw_score = await self._generate_agent_response(hakim, scoring_prompt)
            self._log_interaction(round_name, f"RPH - {hakim.name}", raw_score)
            score_data = self._parse_json_score(raw_score, hakim.name)
            all_scores.append(score_data)

        # Agregasi scoring
        aggregated = self._aggregate_scores(all_scores)
        self._log_interaction(round_name, "PUTUSAN AKHIR", json.dumps(aggregated, indent=2, ensure_ascii=False))

        # ===== DISSENTING / CONCURRING OPINION (ROADMAP Fase 2 #1) =====
        majority_amar = aggregated.get("amar", "ditolak")
        voting_detail = aggregated.get("voting_detail", {})

        # Jika tidak unanimous (ada perbedaan suara)
        if len(voting_detail) > 1:
            print(f"\n{'─'*60}")
            print(f"  >>> DISSENTING / CONCURRING OPINIONS")
            print(f"{'─'*60}")

            for hakim, score_data in zip(self.panel_hakim, all_scores):
                hakim_amar = score_data.get("amar", majority_amar)
                # Generate opinion untuk setiap hakim yang berbeda ATAU yang setuju tapi ingin concur
                if hakim_amar != majority_amar:
                    opinion = await self._generate_dissenting_opinion(hakim, majority_amar, score_data)
                    opinion_type = "Dissenting Opinion"
                    self._log_interaction(
                        round_name,
                        f"{opinion_type} — {hakim.name}",
                        opinion
                    )
                    self.dissenting_opinions.append({
                        "hakim": hakim.name,
                        "type": opinion_type,
                        "amar_hakim": hakim_amar,
                        "amar_mayoritas": majority_amar,
                        "opinion": opinion
                    })
        else:
            print(f"\n  ✅ Voting bulat — tidak ada Dissenting Opinion.")

        return {
            "simulation_id": self.simulation_id,
            "transcript": self.transcript,
            "individual_scores": all_scores,
            "scores": aggregated,
            "dissenting_opinions": self.dissenting_opinions
        }


    # ================================================================
    # RONDE 5: UMPAN BALIK HAKIM (ROADMAP Fase 4 #8) — BARU
    # ================================================================
    async def run_round_5_feedback(self) -> Dict[str, Any]:
        """
        Generate structured feedback for Pemohon after RPH.
        Setiap hakim memberikan umpan balik terstruktur.
        """
        round_name = "Umpan Balik Hakim"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        feedback_prompt = """\
Berdasarkan seluruh persidangan, berikan UMPAN BALIK TERSTRUKTUR untuk membantu \
Pemohon memperbaiki kualitas permohonan ke depan.

Kembalikan HANYA format JSON berikut (tanpa teks lain):
{
    "skor_potensial_perbaikan": <angka 0-30 — estimasi peningkatan skor jika saran diikuti>,
    "kelemahan_utama": [
        "<kelemahan spesifik 1>",
        "<kelemahan spesifik 2>"
    ],
    "rekomendasi": [
        {
            "aspek": "<Legal Standing|Substansi Argumen|Batu Uji|Kelengkapan Formil>",
            "masalah": "<deskripsi masalah spesifik>",
            "saran_konkret": "<tindakan konkret yang harus diambil>"
        }
    ],
    "rekomendasi_petitum": "<saran revisi petitum yang lebih tepat>",
    "prioritas_perbaikan": "<aspek yang paling kritis untuk diperbaiki>"
}
"""
        all_feedback = []
        for hakim in self.panel_hakim:
            raw = await self._generate_agent_response(hakim, feedback_prompt)
            self._log_interaction(round_name, f"Feedback - {hakim.name}", raw)
            try:
                start = raw.find('{')
                end = raw.rfind('}') + 1
                if start != -1 and end > 0:
                    all_feedback.append(json.loads(raw[start:end]))
            except Exception as e:
                logger.error(f"Gagal parse feedback dari {hakim.name}: {e}")

        aggregated = self._aggregate_feedback(all_feedback)
        self._log_interaction(round_name, "RINGKASAN UMPAN BALIK", json.dumps(aggregated, indent=2, ensure_ascii=False))
        return aggregated

    def _aggregate_feedback(self, feedbacks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Agregasi feedback dari semua hakim."""
        if not feedbacks:
            return {"error": "Tidak ada feedback valid"}

        avg_potential = round(
            sum(f.get("skor_potensial_perbaikan", 0) for f in feedbacks) / len(feedbacks), 1
        )
        all_kelemahan = []
        for f in feedbacks:
            all_kelemahan.extend(f.get("kelemahan_utama", []))
        all_rekomendasi = []
        for f in feedbacks:
            all_rekomendasi.extend(f.get("rekomendasi", []))

        prioritas_list = [f.get("prioritas_perbaikan", "") for f in feedbacks if f.get("prioritas_perbaikan")]
        from collections import Counter
        prioritas = Counter(prioritas_list).most_common(1)[0][0] if prioritas_list else "Substansi Argumen"
        petitum_recs = [f.get("rekomendasi_petitum", "") for f in feedbacks if f.get("rekomendasi_petitum")]

        return {
            "skor_potensial_perbaikan": avg_potential,
            "kelemahan_utama": list(dict.fromkeys(all_kelemahan))[:5],
            "rekomendasi": all_rekomendasi[:6],
            "rekomendasi_petitum": petitum_recs[0] if petitum_recs else "",
            "prioritas_perbaikan": prioritas
        }

    def _parse_json_score(self, raw: str, hakim_name: str) -> Dict[str, Any]:
        """Coba ekstrak JSON dari output hakim dengan multiple fallback strategies."""
        if not raw or not raw.strip():
            logger.error(f"Output dari {hakim_name} kosong.")
            return {"error": "Output kosong", "raw": ""}

        cleaned = raw.strip()

        # Strategy 1: Hapus markdown code block ```json ... ```
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if code_block_match:
            cleaned = code_block_match.group(1)

        # Strategy 2: Cari JSON object paling luar (dari { pertama sampai } terakhir yang seimbang)
        start_idx = cleaned.find('{')
        if start_idx == -1:
            logger.error(f"Tidak ditemukan {{ di output {hakim_name}: {cleaned[:200]}")
            return {"error": "Tidak ada JSON object", "raw": cleaned[:300]}

        # Cari } yang seimbang
        brace_count = 0
        end_idx = start_idx
        for i, ch in enumerate(cleaned[start_idx:]):
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = start_idx + i + 1
                    break

        json_str = cleaned[start_idx:end_idx]

        try:
            parsed = json.loads(json_str)
            # Validasi bahwa parsed memiliki setidaknya salah satu key scoring
            scoring_keys = {"legal_standing", "kerugian_konstitusional", "substansi_argumen",
                            "konsistensi_putusan", "kelengkapan_formil", "amar"}
            if not scoring_keys.intersection(parsed.keys()):
                logger.warning(f"JSON dari {hakim_name} tidak mengandung key scoring: {json_str[:200]}")
                return {"error": "JSON tidak mengandung key scoring", "raw": cleaned[:300]}
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Gagal parsing JSON dari {hakim_name}: {e} | JSON string: {json_str[:300]}")

        # Strategy 3: Fallback regex extraction per key-value
        fallback = {}
        for key in ["legal_standing", "kerugian_konstitusional", "substansi_argumen",
                    "konsistensi_putusan", "kelengkapan_formil"]:
            pattern = rf'"{key}"\s*:\s*([0-9]+(?:\.[0-9]+)?)'
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                fallback[key] = float(match.group(1))

        amar_match = re.search(r'"amar"\s*:\s*"([^"]+)"', cleaned, re.IGNORECASE)
        if amar_match:
            fallback["amar"] = amar_match.group(1).strip().lower()

        catatan_match = re.search(r'"catatan"\s*:\s*"([^"]*)"', cleaned, re.IGNORECASE)
        if catatan_match:
            fallback["catatan"] = catatan_match.group(1).strip()

        if fallback:
            logger.warning(f"Menggunakan fallback regex parsing untuk {hakim_name}")
            return fallback

        return {"error": "Format JSON gagal diparsing", "raw": cleaned[:300]}

    def _aggregate_scores(self, scores: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Agregasi skor dari semua hakim (rata-rata + voting amar)."""
        dimensions = [
            "legal_standing", "kerugian_konstitusional",
            "substansi_argumen", "konsistensi_putusan", "kelengkapan_formil"
        ]

        valid_scores = [s for s in scores if "error" not in s]
        if not valid_scores:
            return {"error": "Tidak ada scoring valid"}

        # Rata-rata per dimensi
        avg = {}
        for dim in dimensions:
            vals = []
            for s in valid_scores:
                val = s.get(dim)
                if val is not None:
                    try:
                        # Konversi ke float untuk menangani string numerik seperti "20.5"
                        vals.append(float(val))
                    except (ValueError, TypeError):
                        logger.warning(f"Nilai tidak valid untuk {dim}: {val}")
            
            avg[dim] = round(sum(vals) / len(vals), 1) if vals else 0

        # Total score
        avg["total"] = round(sum(avg[d] for d in dimensions), 1)

        # Voting amar
        amar_votes = [s.get("amar", "ditolak") for s in valid_scores]
        from collections import Counter
        amar_count = Counter(amar_votes)
        avg["amar"] = amar_count.most_common(1)[0][0]
        avg["voting_detail"] = dict(amar_count)

        # Kumpulkan catatan hakim
        avg["catatan_hakim"] = [
            f"{scores.index(s)+1}. {s.get('catatan', '-')}"
            for s in valid_scores if s.get("catatan")
        ]

        return avg

    # ================================================================
    # MAIN: Full Simulation
    # ================================================================
    async def run_full_simulation(self, draft_input: str) -> Dict[str, Any]:
        """
        Menjalankan siklus sidang penuh.
        Alur:
          Ronde 1  → Pemeriksaan Pendahuluan
          Ronde 2  → Perbaikan Permohonan
          Ronde 2B → Pemeriksaan Ahli (jika include_ahli=True)
          Ronde 3  → Pokok Perkara + Pihak Terkait + Amicus Curiae
          Ronde 4  → Kesimpulan + RPH + Dissenting Opinion
        """
        print(f"\n\n{'>'*15} MULAI SIMULASI {self.simulation_id} {'<'*15}")

        await self.run_round_1_pendahuluan(draft_input)
        await self.run_round_2_perbaikan()
        await self.run_round_2b_ahli()          # ROADMAP Fase 3 #4
        await self.run_round_3_pokok_perkara()  # ROADMAP Fase 2 #2
        result = await self.run_round_4_kesimpulan()  # ROADMAP Fase 2 #1
        feedback = await self.run_round_5_feedback()   # ROADMAP Fase 4 #8
        result["feedback"] = feedback

        print(f"{'>'*15} SIMULASI {self.simulation_id} SELESAI {'<'*15}\n")
        return result
```

### 5.4 Agents — core/agents.py

Mendefinisikan semua agen AI dalam simulasi sidang MK. Setiap agen memiliki system prompt spesifik, integrasi RAG, sliding window memory, dan word limiter.

**Agen yang didefinisikan:**
1. `PemohonAgent` — Kuasa Hukum Pemohon
2. `PemerintahAgent` — Kuasa Hukum Presiden/DPR
3. `HakimAgent` — Hakim Konstitusi (panel, bisa 3/5/7/9)
4. `PihakTerkaitAgent` — Pihak ketiga yang terdampak
5. `AmicusCuriaeAgent` — Sahabat pengadilan (netral, akademis)
6. `AhliPemohonAgent` — Ahli konstitusi pro-Pemohon
7. `AhliPemerintahAgent` — Ahli tata negara pro-Pemerintah
8. `ValidatorAgent` — Anti-hallucination citation checker

**Fitur teknis:**
- UUD 1945 injection ke system prompt (anti-halusinasi batu uji)
- Real-time streaming filter untuk reasoning models (DeepSeek, Qwen)
- Multi-provider LLM support (Local LM Studio/Ollama + Claude API)
- Word limiter per role (Pemohon: 1200, Hakim: 800, dll)

```python
"""
Agent Module — Simulasi Sidang MK
==================================
Agen AI yang merepresentasikan para pihak dalam sidang Mahkamah Konstitusi.
Dilengkapi dengan:
- System prompt berbasis hukum acara MK
- Integrasi RAG (referensi putusan & risalah)
- Sliding window memory management
- Token/Word Limiter dengan mekanisme interupsi Hakim (ROADMAP Fase 3 #5)
- Agen baru: Pihak Terkait, Amicus Curiae, Ahli Pemohon, Ahli Pemerintah, Validator (ROADMAP Fase 2 #2, #3)
"""

import asyncio
import logging
import os
import json
import re
from typing import List, Dict, Any, Optional
import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load .env jika ada
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)

# === Konfigurasi LLM ===
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://192.168.1.102:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed-for-local")
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "local-model")

client = AsyncOpenAI(
    base_url=LLM_BASE_URL, 
    api_key=LLM_API_KEY,
    timeout=httpx.Timeout(600.0)  # Toleransi timeout hingga 10 menit untuk model besar
)

# === Default Memory Config ===
DEFAULT_MAX_HISTORY = 20  # Sliding window: simpan N pesan terakhir

# === Token/Word Limiter Config (ROADMAP Fase 3 #5) ===
# Batas kata per respons — Hakim akan menginterupsi jika melebihi batas
WORD_LIMITS = {
    "pemohon": 1200,      # Dinaikkan dari 600
    "pemerintah": 1200,   # Dinaikkan dari 600
    "hakim": 800,         # Dinaikkan dari 400
    "ahli": 1000,         # Dinaikkan dari 500
    "pihak_terkait": 1000, # Dinaikkan dari 500
    "amicus": 800,        # Dinaikkan dari 400
    "validator": None,    # Tidak dibatasi
}
INTERRUPTION_NOTICE = (
    "\n\n[...DIPOTONG — Ketua Majelis: "
    "'Saudara, waktu Anda telah habis. Harap simpulkan poin Anda secara singkat.']"
)

# === Load UUD 1945 Context ===
UUD_PATH = os.path.join(os.path.dirname(__file__), '..', 'rag', 'uud_1945.json')
UUD_TEXT = ""
if os.path.exists(UUD_PATH):
    try:
        with open(UUD_PATH, 'r', encoding='utf-8') as f:
            uud_data = json.load(f)
            UUD_TEXT = uud_data.get('content', '')
    except Exception as e:
        logger.error(f"Gagal memuat UUD 1945: {e}")

UUD_PROMPT_ADDITION = f"""
============================================================
REFERENSI ABSOLUT: UUD NRI 1945 (BATU UJI)
============================================================
Anda wajib menggunakan teks UUD 1945 di bawah ini secara persis ketika merujuk pada pasal/ayat. 
DILARANG KERAS mengarang, mengubah, atau menghalusinasi isi pasal UUD 1945!

<UUD_1945_FULL_TEXT>
{UUD_TEXT}
</UUD_1945_FULL_TEXT>
""" if UUD_TEXT else ""



# ============================================================
# SYSTEM PROMPTS — Berbasis Hukum Acara MK
# ============================================================

SYSTEM_PROMPT_PEMOHON = """\
Anda adalah Kuasa Hukum Pemohon dalam sidang pengujian undang-undang (Judicial Review / PUU) \
di Mahkamah Konstitusi Republik Indonesia.

## Tugas Utama
- Membuktikan bahwa norma yang diuji bertentangan dengan UUD NRI 1945.
- Mempertahankan legal standing Pemohon dari pertanyaan kritis Majelis Hakim.

## Keahlian Hukum Anda
1. **Legal Standing (Pasal 51 ayat (1) UU MK):** Anda harus membuktikan 5 syarat:
   a) Pemohon adalah WNI, badan hukum, lembaga negara, atau kesatuan masyarakat adat
   b) Memiliki hak konstitusional yang dijamin UUD 1945
   c) Hak tersebut dirugikan oleh berlakunya undang-undang
   d) Kerugian bersifat spesifik (aktual atau potensial)
   e) Ada hubungan kausal antara kerugian dan berlakunya UU
2. **Batu Uji:** Selalu sebutkan pasal UUD 1945 yang menjadi batu uji (misal Pasal 28D, 28E, 28G, dll).
3. **Preseden:** Kutip putusan MK sebelumnya yang MENGABULKAN permohonan serupa sebagai yurisprudensi.
4. **Petitum:** Akhiri dengan petitum yang jelas (menyatakan pasal/ayat bertentangan dengan UUD & tidak mempunyai kekuatan hukum mengikat).

- DILARANG KERAS menyertakan proses berpikir, analisis internal, atau catatan di luar teks pidato/percakapan sidang.
- LANGSUNG mulai respons Anda dengan sapaan atau argumen sidang. JANGAN awali dengan perencanaan seperti "Analyze the request" atau "Output plan".
"""

SYSTEM_PROMPT_PEMERINTAH = """\
Anda adalah Kuasa Hukum Presiden/DPR (Pemerintah) dalam sidang pengujian undang-undang (PUU) \
di Mahkamah Konstitusi Republik Indonesia.

## Tugas Utama
- Mempertahankan konstitusionalitas undang-undang yang diuji.
- Membantah argumen Pemohon secara substansial.

## Strategi Pembelaan Anda
1. **Open Legal Policy:** Tegaskan bahwa norma tersebut merupakan kebijakan hukum terbuka (open legal policy) \
yang menjadi ranah legislator, bukan ranah MK untuk menguji.
2. **Tidak Bertentangan dengan UUD:** Buktikan bahwa norma yang diuji justru MELINDUNGI hak konstitusional \
warga negara secara kolektif, bukan melanggarnya.
3. **Preseden Penolakan:** Kutip putusan MK sebelumnya yang MENOLAK atau menyatakan TIDAK DAPAT DITERIMA \
permohonan serupa.
4. **Ratio Legis:** Jelaskan latar belakang dan tujuan pembentukan norma tersebut dari risalah pembahasan DPR.
5. **Original Intent:** Gunakan risalah pembahasan UU untuk menjelaskan kehendak pembentuk UU.

- DILARANG KERAS menyertakan proses berpikir, analisis internal, atau catatan di luar teks pidato/percakapan sidang.
- LANGSUNG mulai respons Anda dengan sapaan atau bantahan sidang. JANGAN awali dengan perencanaan seperti "Analyze the request" atau "Output plan".
"""

SYSTEM_PROMPT_HAKIM = """\
Anda adalah Hakim Konstitusi pada Mahkamah Konstitusi Republik Indonesia, \
anggota Majelis Hakim dalam sidang pengujian undang-undang (PUU).

## Tugas Utama
- Menggali kebenaran materiil melalui pertanyaan kritis kepada para pihak.
- Menguji argumen Pemohon dan Pemerintah secara objektif dan imparsial.

## Kompetensi Anda
1. **Pengujian Legal Standing:** Pastikan Pemohon memenuhi 5 syarat Pasal 51 ayat (1) UU MK:
   - Kualifikasi pemohon
   - Hak konstitusional yang dilindungi UUD
   - Kerugian aktual atau potensial
   - Hubungan kausal kerugian dengan UU
   - Kemungkinan pemulihan hak jika permohonan dikabulkan
2. **Pengujian Substansi:** Nilai apakah norma benar-benar bertentangan dengan UUD 1945 \
atau merupakan open legal policy.
3. **Konsistensi Putusan:** Perhatikan apakah ada putusan MK sebelumnya (ne bis in idem) \
atau pergeseran pendirian MK yang relevan.
4. **Prinsip Konstitusional:** Terapkan prinsip proporsionalitas, kepastian hukum, \
dan keadilan dalam pertimbangan Anda.

## Gaya Komunikasi
- Tajam, kritis, dan langsung ke inti permasalahan.
- Gunakan pertanyaan Socratic untuk menguji konsistensi argumen.
- Jangan berpihak — uji kelemahan KEDUA belah pihak secara setara.
- Singkat dan padat. Hakim bertanya, bukan berceramah.
- DILARANG KERAS menyertakan proses berpikir, analisis internal, atau catatan di luar teks pidato/percakapan sidang.
- LANGSUNG mulai respons Anda dengan sapaan atau pertanyaan sidang (Misal: "Saudara Pemohon...", "Hadirin Sidang..."). JANGAN awali dengan perencanaan seperti "Analyze the request" atau "Output plan".
"""


# ============================================================
# SYSTEM PROMPTS BARU — ROADMAP Fase 2 & 3
# ============================================================

SYSTEM_PROMPT_PIHAK_TERKAIT = """\
Anda adalah Kuasa Hukum Pihak Terkait dalam sidang pengujian undang-undang (PUU) \
di Mahkamah Konstitusi Republik Indonesia.

## Identitas & Posisi
Anda mewakili pihak ketiga yang kepentingannya LANGSUNG TERPENGARUH oleh undang-undang \
yang diuji, namun berbeda perspektif dari Pemohon (misalnya: asosiasi profesi, LSM, \
kelompok masyarakat sipil, atau korban langsung).

## Tugas Utama
- Memberikan perspektif unik dari sudut pandang kepentingan hak privat/sipil pihak ketiga.
- BUKAN sekadar mendukung atau menolak Pemohon, melainkan memberikan dimensi baru.

## Strategi Argumen
1. **Kepentingan Langsung:** Jelaskan bagaimana UU yang diuji berdampak spesifik pada pihak yang Anda wakili.
2. **Dimensi Hak Sipil:** Soroti aspek perlindungan hak sipil dan HAM yang mungkin terlewat kedua pihak.
3. **Keseimbangan:** Jika relevan, ungkapkan sisi positif UU yang perlu dipertahankan sambil menunjukkan bagian inkonstitusionalnya.
4. **Data Lapangan:** Sertakan fakta lapangan dari perspektif pihak terkait.

- DILARANG KERAS menyertakan proses berpikir atau analisis internal.
- LANGSUNG mulai dengan identifikasi diri: "Sebagai Pihak Terkait mewakili [kelompok], kami..."
"""

SYSTEM_PROMPT_AMICUS_CURIAE = """\
Anda adalah Amicus Curiae (Sahabat Pengadilan) dalam sidang pengujian undang-undang (PUU) \
di Mahkamah Konstitusi Republik Indonesia.

## Peran & Netralitas
Anda adalah ahli hukum konstitusi independen. TIDAK BERPIHAK pada Pemohon maupun Pemerintah. \
Peran Anda murni akademis dan komparatif.

## Tugas Utama
- Memberikan analisis hukum komparatif berdasarkan praktik konstitusional internasional.
- Menyajikan perspektif teori hukum dari literatur akademis.

## Format Analisis
1. **Perspektif Komparatif:** Bandingkan dengan putusan pengadilan konstitusi negara lain \
   (Mahkamah Eropa, SCOTUS AS, BVerfG Jerman, Mahkamah Konstitusi Korea Selatan, dll).
2. **Teori Hukum:** Terapkan teori konstitusi relevan (proporsionalitas, necessity test, \
   strict scrutiny, margin of appreciation, dll).
3. **Doktrin Akademis:** Rujuk doktrin dari pakar (Hans Kelsen, Ronald Dworkin, \
   Jimly Asshiddiqie, Sri Soemantri, dll).
4. **Rekomendasi Netral:** Rekomendasikan tafsir yang paling sesuai prinsip konstitusionalisme.

- TIDAK BERPIHAK. Gunakan bahasa akademis namun tetap accessible.
- LANGSUNG mulai dengan "Sebagai Amicus Curiae, kami memberikan pandangan akademis..."
"""

SYSTEM_PROMPT_AHLI_PEMOHON = """\
Anda adalah Ahli Hukum Konstitusi yang dihadirkan oleh Pemohon dalam sidang \
pengujian undang-undang (PUU) di Mahkamah Konstitusi Republik Indonesia.

## Peran
Memberikan keterangan ahli yang MENDUKUNG DALIL PEMOHON. \
Anda adalah akademisi/pakar yang mampu menjembatani teori hukum dengan konteks perkara konkret.

## ATURAN PENTING — Hindari Kelemahan Umum Ahli:
1. **JANGAN "NAME-DROPPING" DOKTRIN ASING TANPA KONTEKSTUALISASI.** \
   Hindari menyebut Kelsen, Schmitt, OECD, GAAR, ICCPR, ECHR, atau doktrin asing lain \
   kecuali Anda LANGSUNG menjelaskan RELEVANSINYA dengan sistem hukum Indonesia dan \
   norma yang diuji dalam perkara ini.
2. **FOKUS PADA KONTEKS INDONESIA.** Mahkamah Konstitusi Indonesia tidak pernah \
   secara buta menerima transplantasi doktrin asing. Setiap rujukan komparatif harus \
   disertai penjelasan mengapa doktrin tersebut cocok diterapkan dalam konteks \
   UUD 1945, nilai Pancasila, dan realitas sosial-ekonomi Indonesia.
3. **HUBUNGKAN LANGSUNG DENGAN NORMA YANG DIUJI.** Jangan berbicara teori umum. \
   Setiap argumen teori harus langsung diarahkan ke: \
   (a) pasal UUD 1945 yang dijadikan batu uji, \
   (b) frasa spesifik dalam norma yang diuji yang dinilai inkonstitusional, dan \
   (c) dampak konkret pada Pemohon.
4. **JANGAN MEMBERI RUANG SERANGAN KE LAWAN.** Jika Anda mengutip doktrin asing, \
   antisipasi langsung keberatan Pemerintah soal "relevansi di Indonesia" dan \
   bantah dengan argumen kontekstual.
5. **PRAKTIS, BUKAN ABSTRAK.** Hakim menguji keterangan ahli untuk menguatkan \
   pertimbangan hukumnya, bukan untuk seminar akademis. Berikan analisis yang \
   bisa langsung digunakan dalam ratio decidendi putusan MK.

## Strategi Argumentasi yang Efektif:
1. **Uji Proporsionalitas Kontekstual:** Jelaskan mengapa norma yang diuji \
   tidak proporsional dalam konteks kebutuhan pengaturan di Indonesia. \
   Bandingkan dengan UU sektoral lain yang sudah diuji MK dan dinyatakan inkonstitusional.
2. **Relevansi Putusan MK Sendiri:** Prioritaskan mengutip PUTUSAN MK sendiri \
   (bukan mahkamah konstitusi negara lain) sebagai preseden. Jika harus komparatif, \
   pilih yurisprudensi dari negara berkembang dengan sistem hukum serupa.
3. **Analisis Teks Norma:** Fokus pada redaksi spesifik norma yang diuji. \
   Jelaskan mengapa redaksi tersebut bersifat multi-tafsir, diskriminatif, atau \
   tidak proporsional dalam konteks UUD 1945.
4. **Koreksi Pemerintah:** Jika Pemerintah membela norma dengan argumen \
   "open legal policy" atau "judicial self-restraint", jelaskan batas-batas \
   deference tersebut dalam konteks sistem hukum Indonesia.

- Gunakan bahasa yang terukur dan fokus. Jangan berlebihan dalam rujukan teori.
- Setiap kali menyebut doktrin/teori, SERTAKAN penjelasan relevansinya dengan perkara.
- LANGSUNG mulai dengan