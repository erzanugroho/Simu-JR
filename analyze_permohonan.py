import re
import os

html_files = [
    r'C:\Users\Erza Nugroho\Downloads\view-source_https___www.mkri.id_perkara_perkara-registrasi_jenis=ALL&perPage=100&page=1.html',
    r'C:\Users\Erza Nugroho\Downloads\view-source_https___www.mkri.id_perkara_perkara-registrasi_jenis=ALL&perPage=100&page=2.html'
]

all_links = []
for f in html_files:
    with open(f, 'r', encoding='utf-8') as fh:
        content = fh.read()
    links = re.findall(r'href="(https://s\.mkri\.id/public/filepermohonan/[^"]+\.pdf)"', content)
    all_links.extend(links)

# Deduplicate while preserving order
seen = set()
unique = []
for link in all_links:
    if link not in seen:
        seen.add(link)
        unique.append(link)

print(f"Total unique PDF links: {len(unique)}")
print()

# Categorize files
permohonan_utama = []  # "Permohonan" or "Permohonan diRegistrasi" - the main application
perbaikan = []         # "Perbaikan Permohonan" - revised/amended application
permohonan_awal = []   # "Permohonan" (original, non-diRegistrasi) - could be supplementary

for link in unique:
    filename = link.split('/')[-1]
    filename_lower = filename.lower()
    
    if 'perbaikan' in filename_lower:
        perbaikan.append(link)
    elif 'diregistrasi' in filename_lower or 'diRegistrasi' in filename:
        permohonan_utama.append(link)
    else:
        # Other files like "Permohonan_4677_9220_146.pdf" or "Permohonan_4375_8567_139 redacted.pdf"
        permohonan_awal.append(link)

print(f"=== CATEGORIZATION ===")
print(f"'Permohonan diRegistrasi' (main application): {len(permohonan_utama)}")
print(f"'Perbaikan Permohonan' (revised/amended): {len(perbaikan)}")
print(f"Other 'Permohonan' files: {len(permohonan_awal)}")
print(f"Total: {len(permohonan_utama) + len(perbaikan) + len(permohonan_awal)}")
print()

print("=== 'Permohonan diRegistrasi' (main) ===")
for i, link in enumerate(permohonan_utama, 1):
    print(f"  {i}. {link.split('/')[-1]}")

print()
print("=== 'Perbaikan Permohonan' (revised) ===")
for i, link in enumerate(perbaikan, 1):
    print(f"  {i}. {link.split('/')[-1]}")

print()
print("=== Other 'Permohonan' files ===")
for i, link in enumerate(permohonan_awal, 1):
    print(f"  {i}. {link.split('/')[-1]}")

# Now let's try to match each permohonan_utama with its perbaikan
# Extract the perkara number pattern from filenames
print()
print("=== MATCHING PERMOHONAN WITH PERBAIKAN ===")

# Extract case ID from filenames (e.g., 4691_9250, 4690_9248)
def extract_case_id(filename):
    # Try to match patterns like "Permohonan diRegistrasi_4691_9250_awal.pdf"
    m = re.search(r'_(\d+_\d+)_', filename)
    if m:
        return m.group(1)
    return None

# Group by case ID
from collections import defaultdict
case_files = defaultdict(list)
for link in unique:
    filename = link.split('/')[-1]
    case_id = extract_case_id(filename)
    if case_id:
        case_files[case_id].append(link)
    else:
        print(f"  No case ID: {filename}")

print(f"\nTotal unique case IDs: {len(case_files)}")

# For each case, show what files exist
main_only = 0
main_and_perbaikan = 0
other_combos = 0

for case_id, files in sorted(case_files.items()):
    has_main = any('diregistrasi' in f.split('/')[-1].lower() or 'diRegistrasi' in f.split('/')[-1] for f in files)
    has_perbaikan = any('perbaikan' in f.split('/')[-1].lower() for f in files)
    has_other = any('diregistrasi' not in f.split('/')[-1].lower() and 'diRegistrasi' not in f.split('/')[-1] and 'perbaikan' not in f.split('/')[-1].lower() for f in files)
    
    if has_main and has_perbaikan:
        main_and_perbaikan += 1
    elif has_main:
        main_only += 1
    else:
        other_combos += 1

print(f"Cases with only 'diRegistrasi': {main_only}")
print(f"Cases with both 'diRegistrasi' + 'Perbaikan': {main_and_perbaikan}")
print(f"Other combinations: {other_combos}")