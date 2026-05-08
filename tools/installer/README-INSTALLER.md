# Simu JR Installer Tooling

Folder ini berisi tooling untuk distribusi Windows:

- `build-installer.ps1`: menyiapkan payload aplikasi dan memanggil Inno Setup.
- `prepare-embedded-python.ps1`: download embedded Python dan install dependency runtime.
- `SimuJR.iss`: template Inno Setup.
- `build-rag-data-pack.ps1`: membuat manifest dan arsip RAG data bulanan.
- `update-rag-data-pack.ps1`: memasang RAG data pack ke mesin user dengan backup/restore.
- `configure-simujr.ps1`: membuat folder data dan `.env` runtime.
- `run-simujr.bat`: launcher aplikasi untuk shortcut.

## Prasyarat Builder

- Windows PowerShell.
- Node.js/npm.
- Python 3.11.
- Inno Setup 6 (`ISCC.exe`).
- 7-Zip (`7z.exe`).
- Koneksi internet saat build pertama untuk download embedded Python dan wheel dependency.

## Build Aplikasi

```powershell
cd "E:\Simu JR"
powershell -ExecutionPolicy Bypass -File tools\installer\build-installer.ps1
```

Output default:

```text
dist-installer\SimuJR-Setup-<version>.exe
```

## Build RAG Data Pack

```powershell
cd "E:\Simu JR"
powershell -ExecutionPolicy Bypass -File tools\installer\build-rag-data-pack.ps1 -DataVersion 2026-06
```

Output default:

```text
dist-installer\SimuJR-RAGData-2026-06.7z
```

Jika `-SplitVolumes` aktif, output menjadi `.7z.001`, `.7z.002`, dan seterusnya.

## Update di Mesin User

User bisa menjalankan shortcut `Update RAG Data`, atau manual:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Program Files\Simu JR\tools\installer\update-rag-data-pack.ps1" -ArchivePath "D:\SimuJR-RAGData-2026-06.7z"
```

Updater akan:

1. Extract arsip ke folder temporary.
2. Validasi `rag_data_manifest.json` dan `chroma_db\chroma.sqlite3`.
3. Backup data lama ke `%ProgramData%\SimuJR\rag_backup\<old_version>\`.
4. Replace data RAG aktif.
5. Update `.env` agar `CHROMA_DB_PATH` dan `RAG_DATA_MANIFEST_PATH` menunjuk ke `%ProgramData%\SimuJR\rag`.
