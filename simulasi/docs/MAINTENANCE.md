# Maintenance Guide

Panduan ini ditujukan untuk maintainer yang perlu menjalankan, memperbaiki, atau mengembangkan Simu JR tanpa membongkar seluruh codebase dari nol.

## Prasyarat

| Kebutuhan | Catatan |
|---|---|
| Python | Disarankan Python 3.11 sesuai Dockerfile dan cache test yang ada |
| Node.js/npm | Untuk frontend React/Vite |
| LLM provider | Local OpenAI-compatible, OpenRouter, MiMo, atau DeepSeek |
| ChromaDB data | Ada di `simulasi/rag/chroma_db` |
| Dataset PDF | `putusan_pdf`, `risalah_pdf`, `permohonan_pdf` |

## Setup Lokal

```powershell
cd "E:\Simu JR\simulasi"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` sesuai provider LLM. Untuk local LM Studio/Ollama compatible, pastikan server model sudah hidup dan base URL benar.

## Menjalankan Aplikasi

Windows launcher:

```powershell
cd "E:\Simu JR\simulasi"
.\MULAI_SIMULASI.bat
```

Manual:

```powershell
cd "E:\Simu JR\simulasi"
python server.py
```

Alternatif uvicorn:

```powershell
cd "E:\Simu JR\simulasi"
python -m uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

Frontend dev:

```powershell
cd "E:\Simu JR\simulasi\frontend"
npm install
npm run dev
```

Build frontend untuk dilayani backend:

```powershell
cd "E:\Simu JR\simulasi\frontend"
npm run build
```

Backend akan memprioritaskan `frontend/dist`. Folder `static/` adalah fallback.

## Testing

Backend:

```powershell
cd "E:\Simu JR\simulasi"
python -m pytest tests -v
```

Frontend:

```powershell
cd "E:\Simu JR\simulasi\frontend"
npm run lint
npm run build
```

RAG health:

```powershell
cd "E:\Simu JR\simulasi"
python rag/rebuild_all.py --stats
```

Runtime health:

```powershell
Invoke-RestMethod http://localhost:8080/api/health
```

## Lokasi Data Runtime

| Data | Lokasi | Pemilik kode |
|---|---|---|
| Project metadata | `simulasi/results/projects/_index.json` | `core/project_store.py` |
| Project detail | `simulasi/results/projects/<project_id>/metadata.json` | `core/project_store.py` |
| Upload project | `simulasi/results/projects/<project_id>/files/` | `core/project_store.py` |
| Research project | `simulasi/results/projects/<project_id>/research/` | `core/project_store.py` |
| Audit project | `simulasi/results/projects/<project_id>/audit/` | `core/project_store.py` |
| Simulasi | `simulasi/results/simulations/` | `core/simulation_store.py` |
| Draft permohonan | `simulasi/results/permohonan_drafts/` atau path terkait helper | `core/permohonan_drafts.py` |
| Self-correcting logs | `simulasi/results/self_correcting_logs/` | `core/self_correcting_loop.py` |
| ChromaDB | `simulasi/rag/chroma_db/` | `rag/rebuild_all.py`, `rag/retriever.py` |

## Konfigurasi yang Sering Diubah

### `.env`

Gunakan untuk hal yang spesifik environment:

```env
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL_NAME=local-model
LLM_MAX_TOKENS=2000
LLM_REASONING_EFFORT=none
CHROMA_DB_PATH=./rag/chroma_db
CHROMA_COLLECTION_NAME=mk_knowledge_base
CORS_ORIGINS=http://localhost:5173,http://localhost:8080
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
```

### `config.yaml`

Gunakan untuk default perilaku aplikasi:

- `simulation.jumlah_hakim`
- `simulation.jumlah_simulasi`
- `rag.n_results`
- `rag.score_threshold`
- `scoring.*`
- `intelligence_pipeline.*`
- `self_correcting.*`

## Alur Debug Cepat

### Server tidak terbuka

1. Pastikan port 8080 belum dipakai:

```powershell
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
```

2. Jalankan manual agar error terlihat:

```powershell
cd "E:\Simu JR\simulasi"
python server.py
```

3. Cek log terbaru seperti `server-*.err.log`, `codex-*.err.log`, atau output terminal.

### LLM error

1. Cek `.env` dan settings UI.
2. Buka health:

```powershell
Invoke-RestMethod "http://localhost:8080/api/health?url=http%3A%2F%2F127.0.0.1%3A1234%2Fv1"
```

3. Pastikan model provider menerima format OpenAI-compatible bila memakai local server.

### RAG kosong atau lambat

1. Cek stats:

```powershell
cd "E:\Simu JR\simulasi\rag"
python rebuild_all.py --stats
```

2. Jika collection kosong, rebuild DB:

```powershell
python rebuild_all.py --db-only
```

3. Jika intelligence bank kosong, jalankan:

```powershell
python rebuild_all.py --pipelines
```

### Upload gagal

1. Cek ekstensi file: `.pdf`, `.docx`, `.doc`, `.txt`, `.md`.
2. Cek ukuran file, default sekitar 20 MB.
3. Cek path `temp_uploads` dan permission folder.

### UI berubah tapi backend masih menampilkan versi lama

Jalankan build:

```powershell
cd "E:\Simu JR\simulasi\frontend"
npm run build
```

Restart backend. Backend membaca `frontend/dist`.

## Checklist Perubahan

### Mengubah agent/prompt

- Edit `core/agents.py` atau `core/system_prompts.py`.
- Jika prompt pipeline RAG, edit `rag/prompts/*.txt`.
- Jalankan test agent:

```powershell
python -m pytest tests/test_agents.py -v
```

### Mengubah orchestrator sidang

- Edit `core/orchestrator.py`.
- Perhatikan fungsi `run_hearing_profile`, `run_full_training_simulation`, dan `run_full_simulation`.
- Jalankan:

```powershell
python -m pytest tests/test_hearing_profiles.py tests/test_agents.py -v
```

### Mengubah storage

- Edit `core/project_store.py`, `core/simulation_store.py`, atau `core/permohonan_drafts.py`.
- Backup `simulasi/results/` sebelum migrasi data.
- Pastikan index JSON tetap sinkron dengan file detail.

### Mengubah API

- Edit `server.py`.
- Update `frontend/src/hooks/useApi.ts`.
- Update `frontend/src/types.ts`.
- Update `docs/API_REFERENCE.md`.
- Jalankan pytest dan frontend build.

### Mengubah UI

- Edit `frontend/src/`.
- Jalankan `npm run lint` dan `npm run build`.
- Pastikan route tetap bekerja lewat FastAPI fallback di `server.py`.

### Mengubah RAG

- Edit `rag/retriever.py`, `rag/pipeline_utils.py`, atau pipeline terkait.
- Cek `rag/rebuild_all.py --stats`.
- Rebuild collection yang diperlukan.
- Cek `/api/health`.

## Backup dan Restore

Minimal backup sebelum perubahan besar:

```powershell
cd "E:\Simu JR\simulasi"
Compress-Archive -Path results, rag\chroma_db, .env, config.yaml -DestinationPath "..\backup-simulasi-$(Get-Date -Format yyyyMMdd-HHmmss).zip"
```

Restore manual:

1. Matikan server.
2. Extract backup ke lokasi semula.
3. Jalankan `/api/health`.
4. Buka daftar project dan simulasi di UI.

## File yang Sebaiknya Tidak Diedit Manual

- `frontend/dist/*`, kecuali memahami bahwa ini hasil build.
- `rag/chroma_db/*`, kecuali rebuild/restore database.
- `results/**/_index.json`, kecuali sedang memperbaiki index dengan backup.
- `__pycache__`, `.pytest_cache`, log `*.log`.
- Dataset besar JSONL/PDF tanpa alasan jelas.

## Catatan Keamanan

- `.env` bisa berisi API key, jangan dipublikasikan.
- Upload file sudah disanitasi, tetapi tetap batasi akses server jika dipakai di jaringan bersama.
- Set `API_KEY` bila endpoint perlu diproteksi.
- Batasi `CORS_ORIGINS` di environment selain lokal.

