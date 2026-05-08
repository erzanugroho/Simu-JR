"""
Pipeline Risalah Sidang PUU - Menggunakan Selenium dengan view-source: prefix
Step 1: Download 99 halaman source HTML via browser (view-source:)
Step 2: Ekstrak link PDF
Step 3: Download semua PDF
"""

import os
import sys
import io
import re
import time
import requests
from urllib.parse import unquote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── Konfigurasi ────────────────────────────────────────────────
BASE_DIR = r"E:\Simu JR"
SOURCE_DIR = os.path.join(BASE_DIR, "source_link_risalah_puu")
LINKS_FILE = os.path.join(BASE_DIR, "pdf_links_risalah_puu.txt")
OUTPUT_DIR = os.path.join(BASE_DIR, "risalah_pdf")

BASE_URL = "https://www.mkri.id/perkara/persidangan/risalah"
TOTAL_PAGES = 99
PER_PAGE = 100

MAX_WORKERS = 5
MAX_RETRIES = 3
TIMEOUT = 60
CHUNK_SIZE = 8192

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}
# ────────────────────────────────────────────────────────────────


def step1_download_source_pages():
    """Download semua halaman source HTML menggunakan view-source: di Selenium."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    print("=" * 60)
    print("📄 STEP 1: Download Source HTML Pages (view-source:)")
    print("=" * 60)

    os.makedirs(SOURCE_DIR, exist_ok=True)

    # Cek halaman yang sudah ada
    existing = set()
    for f in os.listdir(SOURCE_DIR):
        if f.endswith(".html") and os.path.getsize(os.path.join(SOURCE_DIR, f)) > 1024:
            m = re.search(r'page_(\d+)', f)
            if m:
                existing.add(int(m.group(1)))

    pages_to_download = [p for p in range(1, TOTAL_PAGES + 1) if p not in existing]

    if not pages_to_download:
        print(f"  ✅ Semua {TOTAL_PAGES} halaman sudah ada. Skip Step 1.")
        print()
        return True

    print(f"  Sudah ada     : {len(existing)} halaman")
    print(f"  Perlu download: {len(pages_to_download)} halaman")
    print()

    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")

    print("  🌐 Membuka browser...")
    driver = webdriver.Chrome(options=chrome_options)

    try:
        downloaded = 0
        failed = 0

        for idx, page in enumerate(pages_to_download):
            filename = f"risalah_puu_page_{page}.html"
            filepath = os.path.join(SOURCE_DIR, filename)

            # Gunakan view-source: prefix!
            url = f"view-source:https://www.mkri.id/perkara/persidangan/risalah?jenis=PUU&perPage={PER_PAGE}&page={page}"

            try:
                driver.get(url)
                time.sleep(3)

                # Ambil text content dari halaman view-source
                # view-source menampilkan source dalam elemen <pre> atau body
                page_source = driver.find_element("tag name", "body").text

                # Jika body kosong, coba page_source
                if not page_source or len(page_source) < 500:
                    page_source = driver.page_source

                if len(page_source) > 1000 and ".pdf" in page_source:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(page_source)
                    size_kb = len(page_source) / 1024
                    downloaded += 1
                    print(f"  [{page}/{TOTAL_PAGES}] ✅ OK: {filename} ({size_kb:.1f} KB)")
                else:
                    failed += 1
                    print(f"  [{page}/{TOTAL_PAGES}] ❌ GAGAL: Konten tidak valid (size={len(page_source)})")

                # Jeda antar halaman
                time.sleep(1)

            except Exception as e:
                failed += 1
                print(f"  [{page}/{TOTAL_PAGES}] ❌ GAGAL: {e}")

        print(f"\n  Ringkasan Step 1: Downloaded={downloaded}, Skipped={len(existing)}, Failed={failed}")

    finally:
        driver.quit()
        print("  🌐 Browser ditutup.\n")

    return True


def step2_extract_pdf_links():
    """Ekstrak semua link PDF dari file source HTML."""
    print("=" * 60)
    print("🔗 STEP 2: Ekstrak Link PDF dari Source HTML")
    print("=" * 60)

    pdf_pattern = re.compile(r'https?://s\.mkri\.id[^<>"\']+\.pdf')

    all_links = set()

    for filename in sorted(os.listdir(SOURCE_DIR)):
        if filename.endswith(".html"):
            filepath = os.path.join(SOURCE_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                found = set(pdf_pattern.findall(content))
                all_links.update(found)
                print(f"  {filename}: {len(found)} links (total unique: {len(all_links)})")
            except Exception as e:
                print(f"  ❌ Error: {filename}: {e}")

    sorted_links = sorted(list(all_links))
    with open(LINKS_FILE, 'w', encoding='utf-8') as f:
        for link in sorted_links:
            f.write(link + '\n')

    print(f"\n  Total unique PDF links: {len(sorted_links)}")
    print(f"  Saved to: {LINKS_FILE}")
    print()
    return sorted_links


def format_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def download_one_pdf(url, output_dir, index, total):
    parsed = urlparse(url)
    filename = unquote(os.path.basename(parsed.path))
    if not filename:
        filename = f"file_{hash(url)}.pdf"

    filepath = os.path.join(output_dir, filename)
    result = {"index": index, "url": url, "filename": filename, "status": "unknown", "size": 0, "error": None}

    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        existing_size = os.path.getsize(filepath)
        result["status"] = "skipped"
        result["size"] = existing_size
        print(f"  [{index}/{total}] ⏭  SKIP: {filename} ({format_size(existing_size)})")
        return result

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
            response.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
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
            print(f"  [{index}/{total}] ⚠️  Retry {attempt}/{MAX_RETRIES}: {filename} ({result['error']}), tunggu {wait}s...")
            time.sleep(wait)

    result["status"] = "failed"
    print(f"  [{index}/{total}] ❌ GAGAL: {filename} — {result['error']}")
    if os.path.exists(filepath):
        os.remove(filepath)
    return result


def step3_download_pdfs(links):
    print("=" * 60)
    print("📥 STEP 3: Download PDF Risalah Sidang")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    total = len(links)
    print(f"  Total link  : {total}")
    print(f"  Output      : {OUTPUT_DIR}")
    print(f"  Thread      : {MAX_WORKERS}")
    print()

    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(download_one_pdf, url, OUTPUT_DIR, i + 1, total): url
            for i, url in enumerate(links)
        }
        for future in as_completed(futures):
            results.append(future.result())

    elapsed = time.time() - start_time
    success = [r for r in results if r["status"] == "success"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed_list = [r for r in results if r["status"] == "failed"]
    total_size = sum(r["size"] for r in results if r["status"] in ("success", "skipped"))

    print()
    print("=" * 60)
    print("📊 RINGKASAN DOWNLOAD RISALAH")
    print("=" * 60)
    print(f"  ✅ Berhasil didownload : {len(success)}")
    print(f"  ⏭  Sudah ada (skip)   : {len(skipped)}")
    print(f"  ❌ Gagal               : {len(failed_list)}")
    print(f"  📁 Total ukuran       : {format_size(total_size)}")
    print(f"  ⏱  Waktu              : {elapsed:.1f} detik")
    print(f"  📂 Folder output      : {OUTPUT_DIR}")
    print("=" * 60)

    if failed_list:
        print("\n❌ Daftar file yang gagal:")
        for r in failed_list:
            print(f"   - {r['filename']} ({r['error']})")
        log_file = os.path.join(BASE_DIR, "failed_risalah_downloads.txt")
        with open(log_file, "w", encoding="utf-8") as f:
            for r in failed_list:
                f.write(f"{r['url']}\n")
        print(f"\n📝 Link gagal disimpan ke: {log_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline Download Risalah Sidang PUU")
    parser.add_argument("--step", type=int, choices=[1, 2, 3],
                        help="Jalankan step tertentu (1=download source, 2=extract links, 3=download PDFs)")
    parser.add_argument("--skip-source", action="store_true",
                        help="Skip Step 1 (jika source HTML sudah ada)")
    args = parser.parse_args()

    print()
    print("🏛️  Pipeline Download Risalah Sidang PUU — Mahkamah Konstitusi")
    print("=" * 60)
    print()

    if args.step:
        if args.step == 1:
            step1_download_source_pages()
        elif args.step == 2:
            step2_extract_pdf_links()
        elif args.step == 3:
            with open(LINKS_FILE, 'r') as f:
                links = [l.strip() for l in f if l.strip()]
            step3_download_pdfs(links)
    else:
        if not args.skip_source:
            step1_download_source_pages()
        links = step2_extract_pdf_links()
        if links:
            step3_download_pdfs(links)
        else:
            print("❌ Tidak ada link PDF ditemukan.")


if __name__ == "__main__":
    main()
