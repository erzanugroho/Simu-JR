"""
Survive Pipeline - Agent 5
==========================
Ekstraksi jawaban Pemohon yang survive dari putusan dan risalah ke mk_survive_bank.
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


def run_survive_pipeline(jsonl_path: str = None, priority_only: bool = True, workers: int = 1):
    """
    Jalankan Agent 5: Ekstrak jawaban Pemohon yang survive.
    Memproses per FILE UNIK (bukan per chunk) untuk efisiensi.
    """
    logger.info(" Memulai Survive Pipeline (Agent 5)...")

    system_prompt = load_prompt("agent5_survive_extractor")
    if not system_prompt:
        logger.error("FAILED Prompt Agent 5 tidak ditemukan.")
        return

    all_chunks = (
        list_documents_by_type("putusan", jsonl_path, priority_only=priority_only) +
        list_documents_by_type("risalah", jsonl_path, priority_only=priority_only)
    )
    logger.info(f" Total chunks dimuat: {len(all_chunks)}")

    # -- Group chunks by source_file ---------------------------------
    file_chunks: dict[str, list] = defaultdict(list)
    for chunk in all_chunks:
        source = chunk.get("metadata", {}).get("source_file", "unknown")
        file_chunks[source].append(chunk)

    # -- Cek file yang sudah ada di database (untuk fitur Resume/Skip) --
    import chromadb
    from pathlib import Path as _Path
    db_path = str(_Path(__file__).parent / "chroma_db")
    chroma_client = chromadb.PersistentClient(path=db_path)
    try:
        # Coba ambil metadata source_file yang sudah ada
        coll = chroma_client.get_collection(name="mk_survive_bank")
        existing_res = coll.get(include=["metadatas"])
        existing_files = {m.get("source_file") for m in existing_res["metadatas"] if m}
        logger.info(f" Ditemukan {len(existing_files)} file yang sudah diproses sebelumnya. Akan di-skip.")
    except:
        existing_files = set()

    files_to_process = {s: c for s, c in file_chunks.items() if s not in existing_files}
    logger.info(f" File unik yang akan diproses: {len(files_to_process)} (Total: {len(file_chunks)}) | workers: {workers}")

    def _process(item):
        source, chunks = item
        total_chunks = len(chunks)
        # Logic sampling tetap sama...
        if total_chunks <= 12:
            selected = chunks
        else:
            q3 = int(total_chunks * 0.75)
            mid = total_chunks // 2
            selected = (
                [chunks[0]] + 
                chunks[mid-1:mid+1] + 
                chunks[q3-3:q3+2] + 
                [chunks[-1]]
            )
            
        combined_text = "\n\n".join(
            c.get("text", "") for c in selected if c.get("text")
        )[:12000]
        
        user_prompt = f"Ekstrak jawaban survive dari dokumen berikut (sampel teks):\n\n{combined_text}"
        raw = call_llm_sync(system_prompt, user_prompt, temperature=0.0)
        result = extract_json_from_text(raw)
        return source, chunks, result

    items = list(files_to_process.items())
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_process, item): item for item in items}
        for idx, future in enumerate(as_completed(futures), 1):
            source, chunks, result = future.result()
            
            doc_text = ""
            metas = []
            ids = []
            
            if result is None:
                logger.warning(f"  [{idx}/{len(items)}] [FAILED] {source}")
                continue
                
            survive_list = result.get("survive_answers", [])
            if survive_list:
                logger.info(f"  [{idx}/{len(items)}] [OK] {source} ({len(survive_list)} answers)")
                for j, ans in enumerate(survive_list):
                    t = (
                        f"Aspek: {ans.get('aspek', '')}\n"
                        f"Pihak: {ans.get('dari_pihak', '')}\n"
                        f"JAWABAN: {ans.get('jawaban_survive', '')}"
                    )
                    save_to_collection("mk_survive_bank", [t], [{
                        "source_file": source,
                        "aspek": ans.get("aspek", ""),
                        "dari_pihak": ans.get("dari_pihak", ""),
                        "diterima_mk": str(ans.get("apakah_diterima_mk", False)).lower()
                    }], [f"survive_{source}_{j}"])
            else:
                logger.info(f"  [{idx}/{len(items)}] [EMPTY] {source}")
                # Simpan metadata kosong agar di-skip nanti
                save_to_collection("mk_survive_bank", 
                    [f"No survive answers for {source}"], 
                    [{"source_file": source, "status": "empty"}], 
                    [f"survive_{source}_empty"]
                )

    logger.info("OK Survive pipeline selesai.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_survive_pipeline()

