"""
Rebuild All - Script terpadu untuk rebuild RAG database + intelligence banks.

Urutan rebuild:
  1. Kompresi JSONL (dedup + clean) - skip jika sudah ada compressed
  2. Rebuild mk_knowledge_base dari compressed JSONL
  3. Run intelligence pipelines (ratio_bank, attack_bank, concern_bank, survive_bank)

Penggunaan:
  python rebuild_all.py                # Full rebuild (kompress + DB + pipelines)
  python rebuild_all.py --db-only      # Hanya rebuild main DB dari compressed
  python rebuild_all.py --pipelines    # Hanya jalankan intelligence pipelines
  python rebuild_all.py --compress     # Hanya kompresi JSONL
  python rebuild_all.py --stats        # Lihat statistik database saat ini
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent
ORIGINAL_JSONL = BASE_DIR / "rag_chunks.jsonl"
COMPRESSED_JSONL = BASE_DIR / "rag_chunks_compressed.jsonl"
CHROMA_DB = BASE_DIR / "chroma_db"


def show_stats():
    """Tampilkan statistik database saat ini."""
    import chromadb
    
    print(f"\n{'='*60}")
    print(f"STATISTIK RAG DATABASE")
    print(f"{'='*60}")
    
    # JSONL files
    for name, path in [("Original JSONL", ORIGINAL_JSONL), ("Compressed JSONL", COMPRESSED_JSONL)]:
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            with open(path, 'r', encoding='utf-8') as f:
                lines = sum(1 for _ in f)
            print(f"  {name}: {lines:,} chunks | {size_mb:.1f} MB")
        else:
            print(f"  {name}: TIDAK ADA")
    
    # ChromaDB collections
    if CHROMA_DB.exists():
        client = chromadb.PersistentClient(path=str(CHROMA_DB))
        collections = client.list_collections()
        print(f"\n  ChromaDB Collections ({len(collections)}):")
        for coll in collections:
            count = coll.count()
            print(f"    - {coll.name}: {count:,} vectors")
    else:
        print(f"\n  ChromaDB: TIDAK ADA")
    
    print(f"{'='*60}\n")


def compress_jsonl():
    """Kompresi JSONL: dedup + clean. Skip jika sudah ada."""
    if COMPRESSED_JSONL.exists():
        logger.info(f"File compressed sudah ada: {COMPRESSED_JSONL}")
        size_mb = COMPRESSED_JSONL.stat().st_size / (1024 * 1024)
        logger.info(f"Ukuran: {size_mb:.1f} MB. Skip kompresi. Gunakan --force-compress untuk rebuild.")
        return
    
    if not ORIGINAL_JSONL.exists():
        logger.error(f"File original tidak ditemukan: {ORIGINAL_JSONL}")
        logger.error("Jalankan extract_and_chunk.py dulu.")
        return
    
    from compress_rag import compress_from_jsonl
    compress_from_jsonl(str(ORIGINAL_JSONL), str(COMPRESSED_JSONL))


def rebuild_main_db():
    """Rebuild mk_knowledge_base dari compressed JSONL. Support resume."""
    source = COMPRESSED_JSONL if COMPRESSED_JSONL.exists() else ORIGINAL_JSONL
    
    if not source.exists():
        logger.error(f"Tidak ada file JSONL yang tersedia.")
        return
    
    logger.info(f"Rebuild mk_knowledge_base dari: {source.name}")
    
    import chromadb
    from chromadb.utils import embedding_functions
    
    client = chromadb.PersistentClient(path=str(CHROMA_DB))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2", device="cuda"
    )
    
    # Ambil atau buat collection (jANGAN hapus agar bisa resume)
    collection = client.get_or_create_collection(
        name="mk_knowledge_base",
        embedding_function=ef
    )
    
    # Resume: ambil IDs yang sudah ada
    existing_count = collection.count()
    existing_ids = set()
    if existing_count > 0:
        logger.info(f"Ditemukan {existing_count:,} vectors existing. Resume mode...")
        # Batch get all existing IDs
        offset = 0
        batch = 5000
        while True:
            res = collection.get(limit=batch, offset=offset, include=[])
            ids = res.get("ids", [])
            if not ids:
                break
            existing_ids.update(ids)
            if len(ids) < batch:
                break
            offset += batch
        logger.info(f"Loaded {len(existing_ids):,} existing IDs untuk skip.")
    
    # Load dan embed
    from tqdm import tqdm
    
    with open(source, 'r', encoding='utf-8') as f:
        total = sum(1 for _ in f)
    
    remaining = total - len(existing_ids)
    logger.info(f"Total chunks: {total:,} | Sudah ada: {len(existing_ids):,} | Perlu diproses: {remaining:,}")
    
    batch_ids = []
    batch_docs = []
    batch_metas = []
    BATCH_SIZE = 1000
    skipped = 0
    
    with open(source, 'r', encoding='utf-8') as f:
        for line in tqdm(f, total=total, desc="Embedding"):
            data = json.loads(line)
            chunk_id = data["chunk_id"]
            
            # Skip jika sudah ada
            if chunk_id in existing_ids:
                skipped += 1
                continue
            
            meta = data.get("metadata", {})
            safe_meta = {k: v for k, v in meta.items() if v is not None}
            
            batch_ids.append(chunk_id)
            batch_docs.append(data["text"])
            batch_metas.append(safe_meta)
            
            if len(batch_ids) >= BATCH_SIZE:
                collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
                batch_ids, batch_docs, batch_metas = [], [], []
        
        if batch_ids:
            collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
    
    final_count = collection.count()
    logger.info(f"mk_knowledge_base selesai: {final_count:,} vectors (skip: {skipped:,}, baru: {final_count - existing_count:,})")


def rebuild_intelligence_banks():
    """Jalankan intelligence pipeline untuk rebuild ratio/attack/concern/survive banks."""
    # Tambah parent directory ke path untuk import
    sys.path.insert(0, str(BASE_DIR.parent))
    
    from simulasi.rag.ratio_pipeline import run_ratio_pipeline
    from simulasi.rag.attack_bank_pipeline import run_attack_bank_pipeline
    from simulasi.rag.judge_concern_pipeline import run_judge_concern_pipeline
    from simulasi.rag.survive_pipeline import run_survive_pipeline
    
    jsonl_path = str(COMPRESSED_JSONL if COMPRESSED_JSONL.exists() else ORIGINAL_JSONL)
    
    logger.info("=" * 60)
    logger.info("INTELLIGENCE PIPELINES")
    logger.info("=" * 60)
    
    # 1. Ratio Bank (Agent 2) - putusan prioritas
    logger.info("\n[1/4] Ratio Pipeline (Agent 2)...")
    try:
        run_ratio_pipeline(jsonl_path=jsonl_path, priority_only=True, workers=1)
    except Exception as e:
        logger.error(f"Ratio pipeline error: {e}")
    
    # 2. Attack Bank (Agent 3) - argumen DPR dari risalah
    logger.info("\n[2/4] Attack Bank Pipeline (Agent 3)...")
    try:
        run_attack_bank_pipeline(jsonl_path=jsonl_path, workers=1)
    except Exception as e:
        logger.error(f"Attack pipeline error: {e}")
    
    # 3. Concern Bank (Agent 4) - pertanyaan hakim dari risalah
    logger.info("\n[3/4] Judge Concern Pipeline (Agent 4)...")
    try:
        run_judge_concern_pipeline(jsonl_path=jsonl_path, workers=1)
    except Exception as e:
        logger.error(f"Concern pipeline error: {e}")
    
    # 4. Survive Bank (Agent 5) - jawaban pemohon yang survive
    logger.info("\n[4/4] Survive Pipeline (Agent 5)...")
    try:
        run_survive_pipeline(jsonl_path=jsonl_path, workers=1)
    except Exception as e:
        logger.error(f"Survive pipeline error: {e}")
    
    logger.info("\nSemua intelligence pipelines selesai!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild RAG Database")
    parser.add_argument("--stats", action="store_true", help="Lihat statistik database")
    parser.add_argument("--compress", action="store_true", help="Hanya kompresi JSONL")
    parser.add_argument("--db-only", action="store_true", help="Hanya rebuild main DB")
    parser.add_argument("--pipelines", action="store_true", help="Hanya jalankan intelligence pipelines")
    parser.add_argument("--force-compress", action="store_true", help="Paksa kompresi ulang meski sudah ada")
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
    elif args.compress:
        if args.force_compress and COMPRESSED_JSONL.exists():
            COMPRESSED_JSONL.unlink()
        compress_jsonl()
    elif args.db_only:
        rebuild_main_db()
    elif args.pipelines:
        rebuild_intelligence_banks()
    else:
        # Full rebuild
        logger.info("FULL REBUILD: Kompresi + DB + Intelligence Pipelines")
        compress_jsonl()
        rebuild_main_db()
        rebuild_intelligence_banks()
        show_stats()