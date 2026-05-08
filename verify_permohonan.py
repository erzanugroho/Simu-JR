import os

folder = r'E:\Simu JR\permohonan_pdf'
files = os.listdir(folder)
total_size = sum(os.path.getsize(os.path.join(folder, f)) for f in files)
print(f'Total files: {len(files)}')
print(f'Total size: {total_size / (1024*1024):.1f} MB')

# Check for empty files
empty = [f for f in files if os.path.getsize(os.path.join(folder, f)) == 0]
if empty:
    print(f'\nEmpty files ({len(empty)}):')
    for f in empty:
        print(f'  - {f}')
else:
    print('\nNo empty files - all downloads valid!')