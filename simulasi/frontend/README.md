# Simu JR Frontend

Frontend Simu JR adalah aplikasi React + TypeScript + Vite untuk dashboard project, simulasi sidang, draft permohonan, audit, riset, dan settings LLM.

## Quick Start

```powershell
cd "E:\Simu JR\simulasi\frontend"
npm install
npm run dev
```

Default Vite dev server biasanya tersedia di `http://localhost:5173`.

Backend FastAPI tetap perlu hidup di `http://localhost:8080` untuk API:

```powershell
cd "E:\Simu JR\simulasi"
python server.py
```

## Scripts

| Command | Fungsi |
|---|---|
| `npm run dev` | Menjalankan Vite dev server |
| `npm run build` | Type-check dan build produksi ke `dist/` |
| `npm run lint` | Menjalankan ESLint |
| `npm run preview` | Preview build Vite |

## Struktur

```text
frontend/
|-- src/
|   |-- App.tsx                       # Routing utama
|   |-- main.tsx                      # React entry point
|   |-- types.ts                      # Tipe domain/API
|   |-- hooks/useApi.ts               # Hook API dan SSE
|   |-- utils/sseParser.ts            # Parser Server-Sent Events
|   |-- context/
|   |   |-- ProjectContext.tsx         # State project aktif
|   |   `-- SimulationContext.tsx      # State simulasi
|   |-- pages/                        # Halaman aplikasi
|   |-- components/                   # Komponen UI
|   `-- avatarHakim/                  # Asset avatar hakim
|-- public/                           # Asset publik
|-- dist/                             # Hasil build, dilayani backend
|-- vite.config.ts
|-- eslint.config.js
`-- package.json
```

## API Contract

Frontend memakai `API_BASE = ''` di `src/hooks/useApi.ts`, sehingga request diarahkan ke origin yang sama. Saat backend FastAPI menyajikan build dari `frontend/dist`, semua endpoint dipanggil sebagai `/api/...`.

Endpoint penting:

- `/api/health`
- `/api/simulate`
- `/api/projects`
- `/api/projects/{project_id}/files`
- `/api/projects/{project_id}/research`
- `/api/projects/{project_id}/audit`
- `/api/projects/{project_id}/permohonan-drafts/stream`
- `/api/improve-draft-stream`

Referensi lengkap ada di `E:\Simu JR\simulasi\docs\API_REFERENCE.md`.

## Streaming

Beberapa fitur memakai Server-Sent Events:

- simulasi sidang,
- peningkatan draft,
- draft permohonan,
- riset project.

Gunakan helper `consumeSSEStream` dari `src/utils/sseParser.ts` agar parsing event konsisten.

## Build untuk Backend

FastAPI di `server.py` memprioritaskan `frontend/dist`.

Setelah mengubah UI:

```powershell
cd "E:\Simu JR\simulasi\frontend"
npm run lint
npm run build
```

Restart backend jika perlu.

## Checklist Perubahan Frontend

- Jika menambah/mengubah endpoint, update `src/hooks/useApi.ts`.
- Jika shape data berubah, update `src/types.ts`.
- Jika menambah route, cek `src/App.tsx` dan fallback route FastAPI.
- Jika fitur memakai streaming, gunakan `consumeSSEStream`.
- Jalankan `npm run build` sebelum mengandalkan UI dari `http://localhost:8080`.

