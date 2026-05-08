# Simu JR

Simu JR adalah aplikasi simulasi sidang Judicial Review Mahkamah Konstitusi berbasis AI. Project ini menggabungkan backend FastAPI, frontend React/Vite, engine simulasi multi-agent, RAG berbasis ChromaDB, serta pipeline data untuk putusan, risalah, dan permohonan PUU.

## Quick Start

Cara paling cepat di Windows:

```powershell
cd "E:\Simu JR\simulasi"
.\MULAI_SIMULASI.bat
```

Script tersebut akan membuka `http://localhost:8080` dan menjalankan `python server.py`.

Cara manual:

```powershell
cd "E:\Simu JR\simulasi"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python server.py
```

Frontend development:

```powershell
cd "E:\Simu JR\simulasi\frontend"
npm install
npm run dev
```

Backend produksi/lokal utama tetap berjalan di `http://localhost:8080`. Vite development server biasanya berjalan di `http://localhost:5173`.

## Struktur Project

```text
E:\Simu JR
|-- README.md                         # Dokumentasi utama repo
|-- ANALISI_PROGRAM.md                 # Analisis historis project
|-- download_*.py                      # Downloader sumber MK
|-- extract_pdf_links.py               # Ekstraksi link PDF dari HTML sumber
|-- permohonan_pdf/                    # Dataset PDF permohonan
|-- putusan_pdf/                       # Dataset PDF putusan
|-- risalah_pdf/                       # Dataset PDF risalah
|-- source_link_puu/                   # HTML sumber putusan PUU
|-- source_link_risalah_puu/           # HTML sumber risalah PUU
|-- results/                           # Output root-level dari script awal
|-- simulasi/                          # Aplikasi utama
|   |-- server.py                      # FastAPI backend dan API utama
|   |-- main.py                        # CLI simulasi
|   |-- config.yaml                    # Konfigurasi engine/RAG/scoring
|   |-- .env.example                   # Template environment
|   |-- requirements.txt               # Dependency Python
|   |-- Dockerfile                     # Container backend
|   |-- core/                          # Engine simulasi dan storage
|   |-- rag/                           # Retriever, ChromaDB, pipeline RAG
|   |-- frontend/                      # React + TypeScript + Vite
|   |-- static/                        # Build/static fallback yang dilayani backend
|   |-- tests/                         # Test pytest
|   |-- results/                       # Data runtime: project, simulasi, draft, logs
|   `-- docs/                          # Dokumentasi teknis
`-- packages/                          # Area paket tambahan/eksperimen
```

## Komponen Utama

| Komponen | Lokasi | Tanggung jawab |
|---|---|---|
| Backend API | `simulasi/server.py` | Menyajikan UI, API project, streaming simulasi, upload file, health check, export PDF/DOCX, dan endpoint RAG/LLM |
| CLI | `simulasi/main.py` | Menjalankan simulasi dari terminal, self-correcting loop, listing hasil simulasi |
| Core engine | `simulasi/core/` | Agent, orchestrator, prompt, scoring, generator PDF, storage project/simulasi |
| RAG | `simulasi/rag/` | Ekstraksi chunk, vector DB, retriever, intelligence banks, Pasal API |
| Frontend | `simulasi/frontend/` | UI React untuk dashboard, project, simulasi, draft permohonan, settings |
| Static build | `simulasi/frontend/dist` dan `simulasi/static` | Asset yang dilayani FastAPI |
| Tests | `simulasi/tests/` | Unit tests untuk agent, profile sidang, corpus, draft |

## Cara Kerja Singkat

1. User membuka UI di `http://localhost:8080`.
2. FastAPI di `simulasi/server.py` menyajikan React build dari `frontend/dist`.
3. Frontend memanggil endpoint `/api/*`, sebagian memakai Server-Sent Events untuk streaming output LLM.
4. `server.py` mengorkestrasi agent melalui `core/orchestrator.py`.
5. Agent memakai LLM client dari `core/llm_client.py` dan konteks RAG dari `rag/retriever.py`.
6. Hasil simulasi, project, file upload, riset, audit, dan draft disimpan sebagai JSON/file di `simulasi/results/`.

## Konfigurasi

Konfigurasi terbagi dua:

| File | Isi |
|---|---|
| `simulasi/.env` | Provider LLM, API key, base URL, path ChromaDB, CORS, port server |
| `simulasi/config.yaml` | Default jumlah hakim, mode simulasi, RAG, scoring, intelligence pipeline, self-correcting loop |

Template `.env` ada di `simulasi/.env.example`.

Provider LLM yang didukung oleh konfigurasi saat ini:

| Provider | Contoh base URL |
|---|---|
| Local OpenAI-compatible | `http://127.0.0.1:1234/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Xiaomi MiMo | `https://token-plan-sgp.xiaomimimo.com/v1` |
| DeepSeek | `https://api.deepseek.com` |

## Perintah Penting

Backend:

```powershell
cd "E:\Simu JR\simulasi"
python server.py
```

CLI simulasi:

```powershell
cd "E:\Simu JR\simulasi"
python main.py --n 1 --draft "Isi ringkas permohonan..."
python main.py --n 3 --parallel
python main.py --list-sims
python main.py --show-sim <simulation_id>
```

Test backend:

```powershell
cd "E:\Simu JR\simulasi"
python -m pytest tests -v
```

Frontend:

```powershell
cd "E:\Simu JR\simulasi\frontend"
npm run dev
npm run build
npm run lint
```

RAG:

```powershell
cd "E:\Simu JR\simulasi\rag"
python rebuild_all.py --stats
python rebuild_all.py --db-only
python rebuild_all.py --pipelines
python rebuild_all.py
```

## Dokumentasi Lanjutan

- [Dokumentasi Simulasi](E:\Simu JR\simulasi\docs\README.md)
- [Arsitektur](E:\Simu JR\simulasi\docs\ARCHITECTURE.md)
- [API Reference](E:\Simu JR\simulasi\docs\API_REFERENCE.md)
- [Maintenance Guide](E:\Simu JR\simulasi\docs\MAINTENANCE.md)
- [Data dan RAG Pipeline](E:\Simu JR\simulasi\docs\DATA_PIPELINES.md)
- [Finetuning Plan](E:\Simu JR\simulasi\docs\FINETUNING-PLAN.md)
- [Roadmap](E:\Simu JR\simulasi\ROADMAP.md)

## Aturan Maintenance Singkat

- Jangan commit `.env`, log runtime, `__pycache__`, dataset besar, atau build artifact kecuali memang dibutuhkan.
- Perubahan endpoint backend sebaiknya diikuti update `simulasi/frontend/src/hooks/useApi.ts`, `simulasi/frontend/src/types.ts`, dan `simulasi/docs/API_REFERENCE.md`.
- Perubahan alur simulasi sebaiknya dites minimal dengan `python -m pytest tests -v`.
- Perubahan RAG atau ChromaDB sebaiknya diverifikasi dengan `python rag/rebuild_all.py --stats` dan endpoint `/api/health`.
- Untuk UI, jalankan `npm run build` sebelum mengandalkan hasil di `frontend/dist`.

