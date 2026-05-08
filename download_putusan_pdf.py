"""
Script untuk mendownload semua file PDF dari daftar link di pdf_links_putusan_puu.txt
Fitur:
  - Download paralel (5 thread default)
  - Progress bar per file & keseluruhan
  - Skip file yang sudah ada (resume-friendly)
  - Retry otomatis 3x jika gagal
  - Log hasil download
"""

import os
import sys
import io
import time
import requests

# Fix encoding untuk Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from urllib.parse import unquote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Konfigurasi ────────────────────────────────────────────────
LINK_FILE = "pdf_links_putusan_puu.txt"          # File berisi daftar URL
OUTPUT_DIR = "putusan_pdf"                        # Folder output
MAX_WORKERS = 5                                   # Jumlah thread paralel
MAX_RETRIES = 3                                   # Retry per file
TIMEOUT = 60                                      # Timeout per request (detik)
CHUNK_SIZE = 8192                                 # Ukuran chunk download
# ────────────────────────────────────────────────────────────────


def read_links(filepath: str) -> list[str]:
    """Baca file link dan kembalikan list URL unik yang valid."""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    links = []
    seen = set()
    for line in lines:
        url = line.strip()
        if url and url.startswith("http") and url not in seen:
            seen.add(url)
            links.append(url)

    return links


def get_filename_from_url(url: str) -> str:
    """Ekstrak nama file dari URL."""
    parsed = urlparse(url)
    filename = unquote(os.path.basename(parsed.path))
    return filename if filename else f"file_{hash(url)}.pdf"


def format_size(size_bytes: int) -> str:
    """Format ukuran file ke human-readable."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def download_file(url: str, output_dir: str, index: int, total: int) -> dict:
    """
    Download satu file PDF.
    Return dict berisi status download.
    """
    filename = get_filename_from_url(url)
    filepath = os.path.join(output_dir, filename)
    result = {
        "index": index,
        "url": url,
        "filename": filename,
        "status": "unknown",
        "size": 0,
        "error": None,
    }

    # Skip jika file sudah ada dan ukuran > 0
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        existing_size = os.path.getsize(filepath)
        result["status"] = "skipped"
        result["size"] = existing_size
        print(f"  [{index}/{total}] ⏭  SKIP (sudah ada): {filename} ({format_size(existing_size)})")
        return result

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            }

            response = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            with open(filepath, "wb") as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            file_size = os.path.getsize(filepath)
            result["status"] = "success"
            result["size"] = file_size
            print(f"  [{index}/{total}] ✅ OK: {filename} ({format_size(file_size)})")
            return result

        except requests.exceptions.HTTPError as e:
            result["error"] = f"HTTP {e.response.status_code}"
        except requests.exceptions.ConnectionError:
            result["error"] = "Connection error"
        except requests.exceptions.Timeout:
            result["error"] = "Timeout"
        except Exception as e:
            result["error"] = str(e)

        if attempt < MAX_RETRIES:
            wait = attempt * 2
            print(f"  [{index}/{total}] ⚠️  Retry {attempt}/{MAX_RETRIES} untuk {filename} "
                  f"({result['error']}), tunggu {wait}s...")
            time.sleep(wait)

    # Semua retry gagal
    result["status"] = "failed"
    print(f"  [{index}/{total}] ❌ GAGAL: {filename} — {result['error']}")

    # Hapus file yang tidak lengkap
    if os.path.exists(filepath):
        os.remove(filepath)

    return result


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    link_file = os.path.join(script_dir, LINK_FILE)
    output_dir = os.path.join(script_dir, OUTPUT_DIR)

    # Baca links
    if not os.path.exists(link_file):
        print(f"❌ File tidak ditemukan: {link_file}")
        sys.exit(1)

    links = read_links(link_file)
    total = len(links)

    if total == 0:
        print("❌ Tidak ada link valid ditemukan.")
        sys.exit(1)

    # Buat folder output
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(f"📥 PDF Downloader — Putusan MK")
    print(f"=" * 60)
    print(f"  Total link  : {total}")
    print(f"  Output      : {output_dir}")
    print(f"  Thread      : {MAX_WORKERS}")
    print(f"  Retry       : {MAX_RETRIES}x")
    print("=" * 60)
    print()

    start_time = time.time()
    results = []

    # Download paralel
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(download_file, url, output_dir, i + 1, total): url
            for i, url in enumerate(links)
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    elapsed = time.time() - start_time

    # ─── Ringkasan ──────────────────────────────────────────────
    success = [r for r in results if r["status"] == "success"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed = [r for r in results if r["status"] == "failed"]
    total_size = sum(r["size"] for r in results if r["status"] in ("success", "skipped"))

    print()
    print("=" * 60)
    print(f"📊 RINGKASAN")
    print(f"=" * 60)
    print(f"  ✅ Berhasil didownload : {len(success)}")
    print(f"  ⏭  Sudah ada (skip)   : {len(skipped)}")
    print(f"  ❌ Gagal               : {len(failed)}")
    print(f"  📁 Total ukuran       : {format_size(total_size)}")
    print(f"  ⏱  Waktu              : {elapsed:.1f} detik")
    print(f"  📂 Folder output      : {output_dir}")
    print("=" * 60)

    if failed:
        print()
        print("❌ Daftar file yang gagal:")
        for r in failed:
            print(f"   - {r['filename']} ({r['error']})")
            print(f"     {r['url']}")

        # Simpan log gagal
        log_file = os.path.join(script_dir, "failed_downloads.txt")
        with open(log_file, "w", encoding="utf-8") as f:
            for r in failed:
                f.write(f"{r['url']}\n")
        print(f"\n📝 Link yang gagal disimpan ke: {log_file}")


if __name__ == "__main__":
    main()
