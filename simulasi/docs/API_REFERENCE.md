# API Reference

Backend utama ada di `simulasi/server.py` dan berjalan default di `http://localhost:8080`. Frontend memakai relative API base (`''`), jadi request diarahkan ke origin yang sama dengan UI.

Sebagian endpoint mengembalikan JSON biasa, sebagian lain memakai Server-Sent Events (SSE) untuk streaming token/status.

## Konvensi

| Item | Nilai |
|---|---|
| Base URL lokal | `http://localhost:8080` |
| Content type JSON | `application/json` |
| Upload file | `multipart/form-data` |
| Streaming | `text/event-stream` |
| Auth opsional | `API_KEY` di `.env`, jika diaktifkan endpoint tertentu harus mengirim header yang sesuai implementasi |

## Health dan Model

### `GET /api/health`

Memeriksa status backend, RAG, intelligence banks, dan koneksi LLM.

Query opsional:

| Nama | Tipe | Deskripsi |
|---|---|---|
| `url` | string | Override URL LLM untuk health check |

Response ringkas:

```json
{
  "status": "ok",
  "rag": "ready",
  "rag_vectors": 12345,
  "intelligence_banks": {
    "mk_ratio_bank": 100
  },
  "llm": "ok",
  "llm_url": "http://127.0.0.1:1234/v1"
}
```

### `GET /api/mimo/models`
### `GET /api/deepseek/models`
### `GET /api/openrouter/models`

Mengambil daftar model dari provider eksternal. Dipakai oleh halaman settings.

## Simulasi

### `POST /api/simulate`

Menjalankan simulasi sidang dan mengirim progress/transcript melalui SSE.

Body utama:

```json
{
  "draft": "Teks draft permohonan",
  "jumlah_hakim": 3,
  "mode": "ai",
  "hearing_mode": "pemeriksaan_pendahuluan",
  "project_id": "optional-project-id",
  "llm_config": {
    "provider": "local",
    "api_key": "not-needed-for-local",
    "base_url": "http://127.0.0.1:1234/v1",
    "model_name": "local-model"
  }
}
```

Event SSE umum:

| Event/data type | Deskripsi |
|---|---|
| `progress` | Tahap simulasi dan pesan status |
| `transcript` | Potongan transcript sidang |
| `scores` | Hasil scoring akhir |
| `done` | Simulasi selesai |
| `error` | Error runtime |

### `POST /api/stop/{simulation_id}`

Menghentikan simulasi aktif berdasarkan ID.

### `POST /api/stop`

Menghentikan simulasi aktif kompatibilitas lama.

### `GET /api/simulations/active`

Melihat simulasi yang sedang berjalan.

### `GET /api/simulations/{simulation_id}/transcript`

Mengambil transcript simulasi aktif/tercache.

### `GET /api/progress`
### `POST /api/progress`

Endpoint progress kompatibilitas lama untuk UI/flow terdahulu.

### `POST /api/human_input`

Mengirim input manusia saat mode simulasi membutuhkan giliran user.

## Draft dan Permohonan

### `POST /api/extract-text`

Upload file dan ekstrak teks. Ekstensi yang diterima: `.pdf`, `.docx`, `.doc`, `.txt`, `.md`. Batas default sekitar 20 MB.

Form data:

| Nama | Tipe | Deskripsi |
|---|---|---|
| `file` | file | Dokumen yang ingin diekstrak |

Response:

```json
{
  "text": "Isi dokumen..."
}
```

### `POST /api/chat-revision`

Revisi draft berbasis chat.

### `POST /api/improve-draft`
### `POST /api/petition-blueprint`

Endpoint non-streaming untuk peningkatan draft dan blueprint permohonan.

### `POST /api/improve-draft-stream`

Streaming revisi draft dengan SSE.

Body:

```json
{
  "draft": "Draft awal",
  "notes": "Catatan revisi",
  "llm_config": {
    "provider": "local",
    "api_key": "not-needed-for-local",
    "base_url": "http://127.0.0.1:1234/v1",
    "model_name": "local-model"
  }
}
```

Event SSE:

| Event/data type | Deskripsi |
|---|---|
| `draft_chunk` | Potongan teks draft |
| `draft_final` | Draft final |
| `error` | Error |

### `POST /api/hearing-playbook`

Membuat strategi sidang/playbook berbasis draft dan RAG.

### `POST /api/self-correcting`

Menjalankan loop revisi otomatis sampai threshold skor atau batas iterasi.

### `GET /api/permohonan-corpus/status`

Melihat status indexing korpus permohonan.

### `POST /api/permohonan-corpus/reindex`

Memulai re-index korpus permohonan.

### `GET /api/projects/{project_id}/permohonan-drafts`

Daftar draft permohonan yang tersimpan pada project.

### `POST /api/projects/{project_id}/permohonan-drafts/stream`

Generate draft permohonan baru atau memperbaiki draft yang diupload. Response berupa SSE.

Body:

```json
{
  "mode": "new_draft",
  "user_input": {
    "title": "Permohonan PUU ...",
    "norma": "...",
    "batu_uji": "..."
  },
  "uploaded_draft": {
    "filename": "draft.docx",
    "raw_text": "Isi draft lama"
  },
  "llm_config": {
    "provider": "local",
    "api_key": "not-needed-for-local",
    "base_url": "http://127.0.0.1:1234/v1",
    "model_name": "local-model"
  }
}
```

Event SSE:

| Event/data type | Deskripsi |
|---|---|
| `status` | Status fase generate |
| `warning` | Peringatan non-fatal |
| `sources` | Ketersediaan sumber/artifact |
| `draft_chunk` | Potongan draft |
| `draft_final` | Draft final |
| `draft_saved` | Metadata draft tersimpan |
| `error` | Error |

### `GET /api/projects/{project_id}/permohonan-drafts/{draft_id}/docx`

Download draft permohonan DOCX.

## Project Management

### `GET /api/projects`

Daftar project.

### `POST /api/projects`

Membuat project.

Body:

```json
{
  "name": "Nama Project",
  "description": "Deskripsi opsional"
}
```

### `GET /api/projects/{project_id}`
### `PUT /api/projects/{project_id}`
### `DELETE /api/projects/{project_id}`

CRUD metadata project.

### `POST /api/projects/{project_id}/files`

Upload file ke project. File disimpan di `simulasi/results/projects/<project_id>/files/`.

### `GET /api/projects/{project_id}/files`
### `GET /api/projects/{project_id}/files/{file_id}/content`
### `GET /api/projects/{project_id}/files/{file_id}/raw`
### `DELETE /api/projects/{project_id}/files/{file_id}`

Kelola file project.

### `GET /api/projects/{project_id}/simulations`

Daftar simulasi yang terkait project.

### `GET /api/projects/{project_id}/research`
### `POST /api/projects/{project_id}/research`

Menyimpan dan menjalankan riset hukum project. Endpoint POST memakai streaming untuk jawaban riset.

### `GET /api/projects/{project_id}/audit`
### `POST /api/projects/{project_id}/audit`

Daftar dan jalankan audit konsistensi draft.

## Simulasi Tersimpan

### `GET /api/saved-simulations`
### `GET /api/saved-simulations/stats`
### `GET /api/saved-simulations/{simulation_id}`
### `DELETE /api/saved-simulations/{simulation_id}`
### `POST /api/saved-simulations/save`

Endpoint kompatibilitas untuk menyimpan dan membuka simulasi dari UI.

### `GET /api/simulations`
### `GET /api/simulations/{simulation_id}`

Endpoint listing/load simulasi persisten dari `core/simulation_store.py`.

## Referensi, Template, dan Export

### `POST /api/legal-references`

Mengambil referensi hukum terkait query/draft.

### `GET /api/templates`
### `GET /api/templates/{template_id}`

Mengambil template dari `core/templates.py`.

### `POST /api/export-pdf`

Export hasil putusan/simulasi menjadi PDF melalui `core/pdf_generator.py`.

### `POST /api/analyze-arguments`

Analisis argumen.

### `POST /api/learning-tips`

Menghasilkan tips pembelajaran/perbaikan berbasis hasil simulasi.

## UI Fallback

### `GET /`

Menyajikan `frontend/dist/index.html` jika build React tersedia. Jika tidak, fallback ke `static/index.html`.

### `GET /{full_path:path}`

Fallback untuk route React dan static files.

## Checklist Saat Mengubah API

- Update endpoint di `server.py`.
- Update hook frontend di `frontend/src/hooks/useApi.ts`.
- Update tipe response/request di `frontend/src/types.ts`.
- Update dokumentasi ini.
- Jalankan `python -m pytest tests -v`.
- Untuk endpoint yang dipakai UI, jalankan `npm run build`.

