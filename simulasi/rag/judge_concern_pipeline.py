"""
Judge Concern Pipeline — Agent 4
================================
Ekstraksi pertanyaan/concern hakim dari risalah sidang ke mk_concern_bank.
"""

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
from .pipeline_utils import (
    load_prompt, call_llm_sync, extract_json_from_text,
    save_to_collection, list_documents_by_type
)

logger = logging.getLogger(__name__)


def run_judge_concern_pipeline(jsonl_path: str = None, priority_only: bool = True, workers: int = 1):
    """
    Jalankan Agent 4: Ekstrak concern dan pertanyaan hakim dari risalah.
    Memproses per FILE UNIK dengan ThreadPoolExecutor.
    """
    logger.info("🚀 Memulai Judge Concern Pipeline (Agent 4)...")

    system_prompt = load_prompt("agent4_judge_concern")
    if not system_prompt:
        logger.error("❌ Prompt Agent 4 tidak ditemukan.")
        return

    risalah_docs = list_documents_by_type("risalah", jsonl_path, priority_only=priority_only)
    logger.info(f"📄 Ditemukan {len(risalah_docs)} risalah chunks (priority={priority_only}).")

    # Group by source_file
    file_chunks: dict[str, list] = defaultdict(list)
    for chunk in risalah_docs:
        source = chunk.get("metadata", {}).get("source_file", "unknown")
        file_chunks[source].append(chunk)

    # ── Cek file yang sudah ada di database (Resume Feature) ──
    import chromadb
    from pathlib import Path as _Path
    db_path = str(_Path(__file__).parent / "chroma_db")
    chroma_client = chromadb.PersistentClient(path=db_path)
    try:
        coll = chroma_client.get_collection(name="mk_concern_bank")
        existing_res = coll.get(include=["metadatas"])
        existing_files = {m.get("source_file") for m in existing_res["metadatas"] if m}
        logger.info(f"🔍 Ditemukan {len(existing_files)} concern yang sudah ada. Akan di-skip.")
    except:
        existing_files = set()

    files_to_process = {s: c for s, c in file_chunks.items() if s not in existing_files}
    logger.info(f"📁 File unik untuk diproses: {len(files_to_process)} (Total: {len(file_chunks)}) | workers: {workers}")

    def _process(item):
        source, chunks = item
        total_chunks = len(chunks)
        if total_chunks <= 12:
            selected = chunks
        else:
            mid = total_chunks // 2
            q3 = int(total_chunks * 0.75)
            selected = [chunks[0]] + chunks[mid-1:mid+1] + chunks[q3-3:q3+2] + [chunks[-1]]
            
        combined_text = "\n\n".join(
            c.get("text", "") for c in selected if c.get("text")
        )[:12000]
        
        user_prompt = f"Ekstrak concern hakim dari dokumen berikut (sampel teks):\n\n{combined_text}"
        raw = call_llm_sync(system_prompt, user_prompt, temperature=0.0)
        result = extract_json_from_text(raw)
        return source, chunks, result

    items = list(files_to_process.items())
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_process, item): item for item in items}
        for idx, future in enumerate(as_completed(futures), 1):
            source, chunks, result = future.result()

            if result is None:
                logger.warning(f"  [{idx}/{len(items)}] [FAILED] {source}")
                continue

            concerns = result.get("concerns", [])
            if concerns:
                logger.info(f"  [{idx}/{len(items)}] [OK] {source} ({len(concerns)} concerns)")
                for j, concern in enumerate(concerns):
                    doc_text = (
                        f"Hakim: {concern.get('hakim', '')}\n"
                        f"Target: {concern.get('target_pihak', '')}\n"
                        f"PERTANYAAN: {concern.get('pertanyaan', '')}"
                    )
                    save_to_collection("mk_concern_bank", [doc_text], [{
                        "source_file": source,
                        "hakim": concern.get("hakim", ""),
                        "target_pihak": concern.get("target_pihak", ""),
                        "tipe_concern": concern.get("tipe", "")
                    }], [f"concern_{source}_{j}"])
            else:
                logger.info(f"  [{idx}/{len(items)}] [EMPTY] {source}")
                save_to_collection("mk_concern_bank", 
                    [f"No concerns for {source}"], 
                    [{"source_file": source, "status": "empty"}], 
                    [f"concern_{source}_empty"]
                )

    logger.info("✅ Judge concern pipeline selesai.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_judge_concern_pipeline()
