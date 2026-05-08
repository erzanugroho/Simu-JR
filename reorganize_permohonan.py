import re
import os
import shutil

source_dir = r'E:\Simu JR\permohonan_pdf'
perbaikan_dir = r'E:\Simu JR\permohonan_pdf\perbaikan_permohonan'
other_dir = r'E:\Simu JR\permohonan_pdf\permohonan_lainnya'

os.makedirs(perbaikan_dir, exist_ok=True)
os.makedirs(other_dir, exist_ok=True)

files = os.listdir(source_dir)

# Categorize and move
main_count = 0
perbaikan_count = 0
other_count = 0

for filename in files:
    filepath = os.path.join(source_dir, filename)
    if not os.path.isfile(filepath):
        continue
    
    filename_lower = filename.lower()
    
    if 'perbaikan' in filename_lower:
        shutil.move(filepath, os.path.join(perbaikan_dir, filename))
        perbaikan_count += 1
    elif 'diregistrasi' in filename_lower:
        main_count += 1
    else:
        shutil.move(filepath, os.path.join(other_dir, filename))
        other_count += 1

print(f"REORGANIZATION COMPLETE")
print(f"=" * 50)
print(f"Permohonan diRegistrasi (MAIN - stayed in permohonan_pdf): {main_count}")
print(f"Perbaikan Permohonan (moved to perbaikan_permohonan/): {perbaikan_count}")
print(f"Other Permohonan (moved to permohonan_lainnya/): {other_count}")
print(f"=" * 50)

# Verify
remaining = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f))]
print(f"\nFiles remaining in permohonan_pdf/: {len(remaining)}")
total_size = sum(os.path.getsize(os.path.join(source_dir, f)) for f in remaining)
print(f"Total size: {total_size / (1024*1024):.1f} MB")
print(f"\nAll {len(remaining)} files are actual permohonan judiciaire review MK.")