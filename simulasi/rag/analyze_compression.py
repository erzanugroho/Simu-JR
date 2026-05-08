"""Analisis mendalam peluang kompresi RAG chunks tanpa kehilangan informasi."""
import json
import os
import re
from collections import Counter, defaultdict

f = os.path.join(os.path.dirname(__file__), "rag_chunks.jsonl")

# === ANALISIS 1: Noise / PDF Artifacts ===
noise_patterns = {
    "spaced_letters": r'^[A-Z](\s[A-Z]){3,}',  # K E T E T A P A N
    "page_numbers": r'^\s*\d+\s*$',              # halaman kosong
    "excessive_newlines": r'\n{3,}',             # newline berlebih
    "pdf_headers": r'MAHKAMAH KONSTITUSI REPUBLIK INDONESIA',
    "repeated_whitespace": r' {3,}',             # spasi berlebih
}

# === ANALISIS 2: Duplicate detection (within same file) ===
file_chunks = defaultdict(list)  # source_file -> list of (idx, text)

# === ANALISIS 3: Boilerplate detection ===
first_chunks = []   # Chunk pertama dari setiap file (biasanya boilerplate)
last_chunks = []    # Chunk terakhir dari setiap file

noise_chars = 0
total_chars = 0
total_chunks = 0
chunk_sizes = []
unique_files = set()

# Sample untuk duplicate check
print("Menganalisis chunks...")
with open(f, "r", encoding="utf-8") as fh:
    for i, line in enumerate(fh):
        d = json.loads(line)
        text = d["text"]
        total_chars += len(text)
        total_chunks += 1
        chunk_sizes.append(len(text))
        
        source = d["metadata"].get("source_file", "")
        unique_files.add(source)
        
        # Track per-file chunks for duplicate analysis
        file_chunks[source].append((i, text))
        
        # Noise analysis
        for pat_name, pat in noise_patterns.items():
            matches = re.findall(pat, text, re.MULTILINE)
            for m in matches:
                noise_chars += len(m) if isinstance(m, str) else len(str(m))
        
        # Check if text is mostly whitespace
        non_ws = len(text.strip())
        if non_ws < len(text) * 0.3:  # More than 70% whitespace
            noise_chars += len(text) - non_ws

print(f"\n=== ANALISIS 1: NOISE & PDF ARTIFACTS ===")
print(f"Total chars across all chunks: {total_chars:,} ({total_chars/(1024*1024):.1f} MB)")
print(f"Noise chars detected: {noise_chars:,} ({noise_chars/(1024*1024):.1f} MB)")
print(f"Noise ratio: {noise_chars/total_chars*100:.1f}%")

# === ANALISIS 2: Exact duplicates ===
print(f"\n=== ANALISIS 2: EXACT TEXT DUPLICATES ===")
text_counter = Counter()
with open(f, "r", encoding="utf-8") as fh:
    for line in fh:
        d = json.loads(line)
        # Normalize for comparison
        normalized = re.sub(r'\s+', ' ', d["text"].strip().lower())
        text_counter[normalized] += 1

dup_count = sum(c - 1 for c in text_counter.values() if c > 1)
dup_chars = sum(len(t) * (c - 1) for t, c in text_counter.items() if c > 1)
print(f"Unique chunk texts: {len(text_counter):,}")
print(f"Duplicate chunks: {dup_count:,}")
print(f"Duplicate chars (wasted): {dup_chars:,} ({dup_chars/(1024*1024):.1f} MB)")

# === ANALISIS 3: Boilerplate (first/last chunk per file) ===
print(f"\n=== ANALISIS 3: BOILERPLATE CHUNKS (first/last per file) ===")
boilerplate_chars = 0
boilerplate_patterns = [
    'DEMI KEADILAN BERDASARKAN KETUHANAN YANG MAHA ESA',
    'MAHKAMAH KONSTITUSI REPUBLIK INDONESIA',
    'K E T E T A P A N',
    'R I S A L A H',
    'RAPAT PERMUSYAWARATAN HAKIM',
    'Nomor 023/PUU',
    'DEMI KEADILAN',
]

for source, chunks_list in file_chunks.items():
    if len(chunks_list) > 0:
        first_text = chunks_list[0][1]
        # Check if first chunk is mostly boilerplate header
        is_boilerplate = any(bp in first_text for bp in boilerplate_patterns)
        if is_boilerplate and len(first_text) > 500:
            # Only count the boilerplate portion, not the actual content
            boilerplate_chars += min(300, len(first_text))  # ~300 chars of boilerplate

print(f"Files with boilerplate first chunk: est. {boilerplate_chars:,} chars recoverable")
print(f"Boilerplate savings: {boilerplate_chars/(1024*1024):.2f} MB")

# === ANALISIS 4: Chunk size distribution per file ===
print(f"\n=== ANALISIS 4: CHUNKS PER FILE ===")
chunks_per_file = {src: len(chunks) for src, chunks in file_chunks.items()}
cpf_values = list(chunks_per_file.values())
import statistics
print(f"Total files: {len(cpf_values):,}")
print(f"Mean chunks/file: {statistics.mean(cpf_values):.0f}")
print(f"Median chunks/file: {statistics.median(cpf_values):.0f}")
print(f"Max chunks/file: {max(cpf_values)}")
print(f"Min chunks/file: {min(cpf_values)}")

# Estimate savings with bigger chunks
print(f"\n=== ESTIMASI DENGAN CHUNK SIZE LEBIH BESAR ===")
# Current: 1000 chars, 200 overlap → ~800 new chars per chunk
# Option A: 1500 chars, 150 overlap → ~1350 new chars per chunk → 1.69x fewer chunks
# Option B: 2000 chars, 200 overlap → ~1800 new chars per chunk → 2.25x fewer chunks
# Option C: 2000 chars, 100 overlap → ~1900 new chars per chunk → 2.375x fewer chunks

current_eff = 1000 - 200  # 800 new chars per chunk
for new_size, new_overlap in [(1500, 150), (2000, 200), (2000, 100), (2000, 0)]:
    new_eff = new_size - new_overlap
    ratio = current_eff / new_eff
    est_chunks = int(total_chunks * ratio)
    est_size = est_chunks * (new_size * 0.95)  # ~0.95 avg fill
    print(f"  chunk_size={new_size}, overlap={new_overlap}: ~{est_chunks:,} chunks ({ratio*100:.0f}%), ~{est_size/(1024*1024):.0f} MB")

# === SUMMARY ===
print(f"\n=== RINGKASAN PELUANG KOMPRESI ===")
print(f"Current: {total_chunks:,} chunks, {total_chars/(1024*1024):.1f} MB text")
print()
print(f"1. Noise removal (PDF artifacts): ~{noise_chars/(1024*1024):.1f} MB savings")
print(f"2. Deduplicate exact duplicates:  ~{dup_chars/(1024*1024):.1f} MB savings ({dup_count:,} chunks)")
print(f"3. Increase chunk size (2000/100): ~60% fewer chunks")
print(f"4. Text normalization (whitespace): ~5-10% additional savings")
print()
total_savings_pct = (noise_chars + dup_chars) / total_chars * 100
print(f"Conservative total savings (strategies 1+2): {total_savings_pct:.1f}%")
print(f"Aggressive savings (all strategies): ~65-75%")