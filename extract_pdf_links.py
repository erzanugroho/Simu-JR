import re
import os

def extract_links():
    source_folder = r"E:\Simu JR\source_link_puu"
    output_file = r"e:\Simu JR\pdf_links_putusan_puu.txt"

    # Broad pattern to catch all mkri PDF links regardless of URL format
    pdf_pattern = re.compile(r'https?://s\.mkri\.id[^\s<>"\']+\.pdf')

    all_links = set()

    # Extract from all source HTML files
    for filename in sorted(os.listdir(source_folder)):
        if filename.endswith(".html"):
            file_path = os.path.join(source_folder, filename)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    found = set(pdf_pattern.findall(content))
                    all_links.update(found)
                print(f"Processed {filename[:60]:60s} -> {len(found):4d} links (total unique: {len(all_links)})")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    # Sort and save
    sorted_links = sorted(list(all_links))
    with open(output_file, 'w', encoding='utf-8') as f:
        for link in sorted_links:
            f.write(link + '\n')

    print(f"\n{'='*60}")
    print(f"Total unique PDF links saved: {len(sorted_links)}")
    print(f"Output file: {output_file}")

if __name__ == "__main__":
    extract_links()
