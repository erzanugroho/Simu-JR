"""
Agent 1 Retroactive Classifier
================================
Mengklasifikasi dokumen-dokumen yang sudah ada di ChromaDB.

OPTIMASI:
- Satu klasifikasi per FILE unik (bukan per chunk) → hemat 10-100x waktu
- Parallel processing dengan ThreadPoolExecutor → hemat 2-4x waktu
- Progress di-save otomatis; bisa dilanjutkan jika terputus
- Supports --all untuk proses semua file tanpa limit
"""

import os
import sys
import logging
import argparse
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Setup path SEBELUM import apapun
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# KRITIS: set env var SEBELUM import module yang membacanya saat load
os.environ["ENABLE_AGENT1_CLASSIFIER"] = "true"

from rag.retriever import RAGRetriever
from rag.extract_and_chunk import classify_document_with_agent1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent1_classifier.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Lock untuk thread-safe ChromaDB updates dan counter
_lock = threading.Lock()
_counter = {"done": 0, "priority": 0, "error": 0}


def get_unique_files_to_classify(coll, doc_type="putusan", limit=None):
    """
    Ambil SATU chunk representative per file unik yang belum diklasifikasi.
    Ini jauh lebih efisien daripada memproses semua 1.1 juta chunks.
    """
    logger.info(f"Mengambil semua chunk '{doc_type}' dari ChromaDB untuk deduplikasi...")
    
    seen_files = set()
    candidates = []   # list of (chunk_id, text, meta)
    already_done = set()

    offset = 0
    batch = 5000
    total_scanned = 0

    while True:
        try:
            res = coll.get(
                where={"jenis_dokumen": {"$eq": doc_type}},
                limit=batch,
                offset=offset,
                include=["documents", "metadatas"]
            )
        except Exception as e:
            logger.error(f"Error saat scan batch offset={offset}: {e}")
            break

        ids = res.get("ids", [])
        if not ids:
            break

        for chunk_id, doc, meta in zip(ids, res["documents"], res["metadatas"]):
            total_scanned += 1
            source = meta.get("source_file", chunk_id)

            if "flag_priority" in meta:
                # Sudah diklasifikasi — skip, catat sebagai done
                already_done.add(source)
                continue

            if source not in seen_files:
                seen_files.add(source)
                candidates.append((chunk_id, doc, meta))
                if limit and len(candidates) >= limit:
                    logger.info(f"  Limit {limit} file tercapai. Total scan: {total_scanned}")
                    return candidates, len(already_done)

        logger.info(f"  Scan progress: {total_scanned:,} chunks... ({len(candidates)} file belum klf, {len(already_done)} sudah)")

        if len(ids) < batch:
            break
        offset += batch

    return candidates, len(already_done)


def classify_one(args):
    """Fungsi untuk dijalankan di thread pool."""
    chunk_id, doc, meta, coll, index, total = args
    source = meta.get("source_file", chunk_id)

    try:
        agent1_meta = classify_document_with_agent1(doc[:4000], chunk_id, "putusan")
    except KeyboardInterrupt:
        return "interrupted", source
    except Exception as e:
        with _lock:
            _counter["error"] += 1
        logger.warning(f"  [{index}/{total}] ⚠️ Error: {source}: {e}")
        return "error", source

    if agent1_meta:
        new_meta = {**meta, **agent1_meta}
        try:
            with _lock:
                coll.update(ids=[chunk_id], metadatas=[new_meta])
                _counter["done"] += 1
                is_priority = str(new_meta.get("flag_priority", "")).lower() == "true"
                if is_priority:
                    _counter["priority"] += 1
        except Exception as e:
            logger.warning(f"  ⚠️ Gagal update ChromaDB untuk {source}: {e}")
            return "error", source

        klaster = new_meta.get("klaster", "N/A")
        flag = new_meta.get("flag_priority", "false")
        star = "⭐ PRIORITAS" if str(flag).lower() == "true" else "  -"
        logger.info(f"  [{index}/{total}] {star} {source} | {klaster}")
        return "ok", source
    else:
        logger.warning(f"  [{index}/{total}] ⚠️ Tidak ada hasil untuk: {source}")
        return "empty", source


def main():
    parser = argparse.ArgumentParser(
        description="Agent 1 Retroactive Classifier — 1 klasifikasi per file PDF unik"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Jumlah FILE unik yang diklasifikasi (default: semua). Gunakan angka kecil untuk test."
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Jumlah thread paralel (default: 1). Naikkan ke 2-4 jika LLM mendukung concurrent requests."
    )
    parser.add_argument(
        "--doc-type", type=str, default="putusan",
        choices=["putusan", "risalah"],
        help="Jenis dokumen yang diklasifikasi (default: putusan)"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  AGENT 1: RETROACTIVE CLASSIFIER (Optimized)")
    logger.info(f"  Mode: {'SEMUA file' if not args.limit else f'{args.limit} file'}")
    logger.info(f"  Workers: {args.workers} thread paralel")
    logger.info(f"  Doc type: {args.doc_type}")
    logger.info("=" * 60)

    try:
        retriever = RAGRetriever()
        coll = retriever.collection
    except Exception as e:
        logger.error(f"Gagal koneksi ke ChromaDB: {e}")
        return

    # Ambil kandidat (1 per file unik)
    candidates, already_done_count = get_unique_files_to_classify(
        coll,
        doc_type=args.doc_type,
        limit=args.limit
    )

    logger.info(f"\n{'='*60}")
    logger.info(f"  ✅ Sudah diklasifikasi sebelumnya : {already_done_count:,} file")
    logger.info(f"  🔄 Akan diklasifikasi sekarang   : {len(candidates):,} file")
    logger.info(f"  ⏱️  Estimasi waktu (@30s/file, {args.workers} worker): "
                f"{len(candidates)*30//args.workers//60} menit")
    logger.info(f"{'='*60}\n")

    if not candidates:
        logger.info("🎉 Semua file sudah diklasifikasi!")
        return

    total = len(candidates)
    start_time = time.time()

    # Buat task list
    tasks = [
        (chunk_id, doc, meta, coll, i + 1, total)
        for i, (chunk_id, doc, meta) in enumerate(candidates)
    ]

    try:
        if args.workers == 1:
            # Single-threaded (lebih stabil untuk LM Studio)
            for task in tasks:
                result, source = classify_one(task)
                if result == "interrupted":
                    logger.info("\n⚠️ Dihentikan. Progress tersimpan otomatis.")
                    break
                # Progress report setiap 10 file
                done = _counter["done"] + _counter["error"]
                if done % 10 == 0 and done > 0:
                    elapsed = time.time() - start_time
                    rate = done / elapsed if elapsed > 0 else 0
                    remaining = (total - done) / rate if rate > 0 else 0
                    logger.info(
                        f"  📊 Progress: {done}/{total} | "
                        f"⭐ {_counter['priority']} prioritas | "
                        f"⏱️ Sisa ~{remaining/60:.0f} menit"
                    )
        else:
            # Multi-threaded
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = {executor.submit(classify_one, task): task for task in tasks}
                try:
                    for future in as_completed(futures):
                        result, source = future.result()
                        if result == "interrupted":
                            logger.info("\n⚠️ Dihentikan. Progress tersimpan otomatis.")
                            executor.shutdown(wait=False)
                            break
                        done = _counter["done"] + _counter["error"]
                        if done % 20 == 0 and done > 0:
                            elapsed = time.time() - start_time
                            rate = done / elapsed if elapsed > 0 else 0
                            remaining = (total - done) / rate if rate > 0 else 0
                            logger.info(
                                f"  📊 Progress: {done}/{total} | "
                                f"⭐ {_counter['priority']} prioritas | "
                                f"⏱️ Sisa ~{remaining/60:.0f} menit"
                            )
                except KeyboardInterrupt:
                    logger.info("\n⚠️ Dihentikan. Progress tersimpan otomatis.")
                    executor.shutdown(wait=False)

    except KeyboardInterrupt:
        logger.info("\n⚠️ Dihentikan. Progress tersimpan otomatis.")

    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 60)
    logger.info(f"  SELESAI")
    logger.info(f"  ✅ Berhasil diklasifikasi : {_counter['done']:,} file")
    logger.info(f"  ⭐ Ditandai prioritas     : {_counter['priority']:,} file")
    logger.info(f"  ❌ Error                  : {_counter['error']:,} file")
    logger.info(f"  ⏱️  Total waktu           : {elapsed/60:.1f} menit")
    logger.info("=" * 60)
    logger.info("\n👉 Sekarang jalankan: python run_pipeline.py --stage all --priority-only")


if __name__ == "__main__":
    main()
