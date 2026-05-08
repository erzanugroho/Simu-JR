import re
import os
import urllib.request
import urllib.parse
import time
import ssl

# HTML source files
html_files = [
    r'C:\Users\Erza Nugroho\Downloads\view-source_https___www.mkri.id_perkara_perkara-registrasi_jenis=ALL&perPage=100&page=1.html',
    r'C:\Users\Erza Nugroho\Downloads\view-source_https___www.mkri.id_perkara_perkara-registrasi_jenis=ALL&perPage=100&page=2.html'
]

# Output directory
output_dir = r'E:\Simu JR\permohonan_pdf'
os.makedirs(output_dir, exist_ok=True)

# Step 1: Extract all PDF links
print("=" * 60)
print("STEP 1: Extracting PDF links from HTML files...")
print("=" * 60)

all_links = []
for f in html_files:
    print(f"Reading: {os.path.basename(f)}")
    with open(f, 'r', encoding='utf-8') as fh:
        content = fh.read()
    # Find all PDF links with href pattern
    links = re.findall(r'href="(https://s\.mkri\.id/public/filepermohonan/[^"]+\.pdf)"', content)
    all_links.extend(links)
    print(f"  Found {len(links)} PDF links")

# Deduplicate while preserving order
seen = set()
unique = []
for link in all_links:
    if link not in seen:
        seen.add(link)
        unique.append(link)

print(f"\nTotal unique PDF links: {len(unique)}")

# Save links to file
with open(r'e:\Simu JR\permohonan_links.txt', 'w') as f:
    for link in unique:
        f.write(link + '\n')
print("Links saved to permohonan_links.txt")

# Step 2: Download all PDFs
print("\n" + "=" * 60)
print("STEP 2: Downloading PDFs...")
print("=" * 60)

# Create SSL context that doesn't verify (for potential cert issues)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

success = 0
failed = 0
failed_links = []

for i, url in enumerate(unique, 1):
    # Extract filename from URL
    filename = url.split('/')[-1]
    # Decode URL-encoded filename
    filename = urllib.parse.unquote(filename)
    # Clean filename
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    filepath = os.path.join(output_dir, filename)
    
    # Skip if already downloaded
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        print(f"[{i}/{len(unique)}] SKIP (exists): {filename}")
        success += 1
        continue
    
    print(f"[{i}/{len(unique)}] Downloading: {filename}")
    
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            with urllib.request.urlopen(req, context=ctx, timeout=60) as response:
                data = response.read()
                with open(filepath, 'wb') as f:
                    f.write(data)
            print(f"  -> OK ({len(data):,} bytes)")
            success += 1
            break
        except Exception as e:
            if attempt < 2:
                print(f"  -> Retry {attempt+1}: {e}")
                time.sleep(2)
            else:
                print(f"  -> FAILED: {e}")
                failed += 1
                failed_links.append((url, str(e)))
    
    # Small delay between downloads
    time.sleep(0.5)

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Total links: {len(unique)}")
print(f"Success: {success}")
print(f"Failed: {failed}")

if failed_links:
    print("\nFailed downloads:")
    with open(r'E:\Simu JR\failed_permohonan.txt', 'w') as f:
        for url, err in failed_links:
            print(f"  - {url.split('/')[-1]}: {err}")
            f.write(f"{url}\t{err}\n")
    print("Failed list saved to failed_permohonan.txt")

print("\nDone!")