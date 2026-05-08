"""Analisis struktur dan ukuran data RAG chunks."""
import json
import os
import statistics

f = os.path.join(os.path.dirname(__file__), "rag_chunks.jsonl")

sizes = []
sources = set()
doc_types = {"putusan": 0, "risalah": 0}
samples = []
total_bytes = 0
metadata_keys_sample = None

with open(f, "r", encoding="utf-8") as fh:
    for i, line in enumerate(fh):
        d = json.loads(line)
        text_len = len(d["text"])
        sizes.append(text_len)
        
        # Metadata analysis
        meta = d.get("metadata", {})
        if i == 0:
            metadata_keys_sample = list(meta.keys())
        
        src = meta.get("source_file", "unknown")
        sources.add(src)
        
        jen = meta.get("jenis_dokumen", "unknown")
        if jen in doc_types:
            doc_types[jen] += 1
        
        if i < 3:
            samples.append({
                "chunk_id": d["chunk_id"],
                "text_len": text_len,
                "text_preview": d["text"][:300],
                "metadata": meta
            })

total_bytes = os.path.getsize(f)
n = len(sizes)

print(f"=== STATISTIK RAG CHUNKS ===")
print(f"Total chunks      : {n:,}")
print(f"Total unique files: {len(sources):,}")
print(f"Jenis dokumen     : {doc_types}")
print(f"File size         : {total_bytes / (1024*1024):.2f} MB")
print()
print(f"=== UKURAN CHUNK TEXT ===")
print(f"  Min    : {min(sizes)} chars")
print(f"  Max    : {max(sizes)} chars")
print(f"  Mean   : {statistics.mean(sizes):.0f} chars")
print(f"  Median : {statistics.median(sizes):.0f} chars")
print(f"  Total text: {sum(sizes) / (1024*1024):.2f} MB")
print()
print(f"Metadata keys : {metadata_keys_sample}")
print()

# Overlap analysis
print(f"=== OVERLAP ANALYSIS ===")
# chunk_size=1000, overlap=200 means ~800 new chars per chunk
# So for 1000 chars effective, 200 chars are repeated
overlap_ratio = 200 / 1000
estimated_unique = sum(sizes) * (1 - overlap_ratio * 0.5)
print(f"  Chunk config: size=1000, overlap=200")
print(f"  Estimated overlap waste: ~{overlap_ratio*100:.0f}%")
print(f"  Estimated unique content: {estimated_unique / (1024*1024):.2f} MB")
print()

# Sample chunks
print(f"=== SAMPLE CHUNKS ===")
for s in samples:
    print(f"  chunk_id: {s['chunk_id']}")
    print(f"  text_len: {s['text_len']}")
    print(f"  preview: {s['text_preview'][:150]}...")
    print(f"  metadata: {s['metadata']}")
    print("  ---")