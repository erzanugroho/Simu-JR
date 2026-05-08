"""Verifikasi bahwa compressed data tetap memiliki semua informasi."""
import json, os, sys

sys.stdout.reconfigure(encoding='utf-8')

orig = os.path.join(os.path.dirname(__file__), 'rag_chunks.jsonl')
comp = os.path.join(os.path.dirname(__file__), 'rag_chunks_compressed.jsonl')

# Check sample from compressed
with open(comp, 'r', encoding='utf-8') as f:
    sample = json.loads(next(f))

print('=== SAMPLE COMPRESSED CHUNK ===')
print(f'chunk_id: {sample["chunk_id"]}')
print(f'text len: {len(sample["text"])}')
print(f'metadata: {sample["metadata"]}')
print(f'text preview: {sample["text"][:200]}')
print()

# Verify all source files are represented
comp_files = set()
with open(comp, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        comp_files.add(d['metadata']['source_file'])

orig_files = set()
with open(orig, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        orig_files.add(d['metadata']['source_file'])

print(f'=== FILE COVERAGE ===')
print(f'Original files: {len(orig_files)}')
print(f'Compressed files: {len(comp_files)}')
missing = orig_files - comp_files
print(f'Files lost in compression: {len(missing)}')
if missing:
    for mf in list(missing)[:5]:
        print(f'  - {mf}')
print(f'All files preserved: {orig_files == comp_files}')

# Verify doc types
comp_types = {}
with open(comp, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        t = d['metadata'].get('jenis_dokumen', '?')
        comp_types[t] = comp_types.get(t, 0) + 1

print(f'\n=== DOCUMENT TYPES IN COMPRESSED ===')
for t, c in sorted(comp_types.items()):
    print(f'  {t}: {c:,} chunks')