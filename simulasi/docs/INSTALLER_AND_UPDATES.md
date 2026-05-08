# Installer dan Update

Dokumen ini menjelaskan implementasi distribusi Simu JR setelah dibundel.

## Jalur Update

Simu JR memakai dua jalur update:

| Jalur | Artefact | Yang berubah | Data user |
|---|---|---|---|
| App Update | `SimuJR-Setup-<version>.exe` | Kode aplikasi, frontend, script runtime | Dipertahankan |
| RAG Data Update | `SimuJR-RAGData-YYYY-MM.7z` | ChromaDB, manifest, optional JSONL kompresi | Dipertahankan |

Data runtime installer diarahkan ke `%ProgramData%\SimuJR` melalui `SIMUJR_DATA_ROOT`.

## Status RAG Data

Backend membaca manifest dari `RAG_DATA_MANIFEST_PATH` atau default folder induk ChromaDB.

Endpoint:

```text
GET /api/rag-data/status
GET /api/health
```

`/api/health` sekarang memuat field `rag_data`, misalnya:

```json
{
  "rag_data": {
    "status": "ready",
    "data_version": "2026-06",
    "built_at": "2026-06-01T10:00:00",
    "source_label": "MK PUU corpus"
  }
}
```

Jika manifest tidak ada atau invalid, aplikasi tetap hidup dan menampilkan status `missing` atau `invalid`.

## Membuat Installer App

Prasyarat builder:

- Inno Setup 6.
- Node.js/npm.
- Python 3.11.
- Koneksi internet untuk menyiapkan embedded Python.

Perintah:

```powershell
cd "E:\Simu JR"
powershell -ExecutionPolicy Bypass -File tools\installer\build-installer.ps1 -Version 1.1.0
```

Output:

```text
dist-installer\SimuJR-Setup-1.1.0.exe
```

## Membuat RAG Data Pack Bulanan

Prasyarat:

- 7-Zip.
- `simulasi\rag\chroma_db` sudah selesai direbuild dan diverifikasi.

Perintah:

```powershell
cd "E:\Simu JR"
powershell -ExecutionPolicy Bypass -File tools\installer\build-rag-data-pack.ps1 -DataVersion 2026-06 -SplitVolumes
```

Output:

```text
dist-installer\SimuJR-RAGData-2026-06.7z.001
dist-installer\SimuJR-RAGData-2026-06.7z.002
```

Tanpa `-SplitVolumes`, output berupa satu file `.7z`.

## Update RAG di Mesin User

User dapat memilih shortcut `Update RAG Data` dari Start Menu. Script akan membuka file picker untuk memilih `.7z` atau `.001`.

Manual:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Simu JR\tools\installer\update-rag-data-pack.ps1" -ArchivePath "D:\SimuJR-RAGData-2026-06.7z"
```

Updater akan:

1. Extract ke temporary folder.
2. Validasi `rag_data_manifest.json`.
3. Validasi `chroma_db\chroma.sqlite3`.
4. Backup RAG lama ke `%ProgramData%\SimuJR\rag_backup\<old_version>-<timestamp>`.
5. Replace RAG aktif.
6. Update `.env` agar menunjuk ke data baru.
7. Restore backup jika proses gagal sebelum replace selesai.

## File Penting

| File | Fungsi |
|---|---|
| `tools/installer/build-installer.ps1` | Build payload dan installer EXE |
| `tools/installer/prepare-embedded-python.ps1` | Siapkan Python embedded |
| `tools/installer/build-rag-data-pack.ps1` | Build manifest dan arsip RAG |
| `tools/installer/update-rag-data-pack.ps1` | Install/update RAG data user |
| `tools/installer/SimuJR.iss` | Inno Setup script |
| `simulasi/core/rag_manifest.py` | Loader/penulis manifest RAG |
| `simulasi/core/runtime_paths.py` | Resolver `%ProgramData%` vs source checkout |

