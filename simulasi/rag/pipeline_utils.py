"""
Pipeline Utilities — Litigation Intelligence Pipeline
=====================================================
Helper functions untuk menjalankan pipeline 7 agent.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://192.168.1.102:1234/v1")
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "local-model")


def load_prompt(prompt_name: str) -> str:
    """Load prompt dari folder prompts/."""
    prompt_dir = Path(__file__).parent / "prompts"
    prompt_path = prompt_dir / f"{prompt_name}.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning(f"Prompt file tidak ditemukan: {prompt_path}")
    return ""

def call_llm_sync(system_prompt: str, user_prompt: str, temperature: float = 0.0) -> str:
    """Panggil LLM dengan timeout panjang dan pembersihan respon agresif."""
    from openai import OpenAI
    import re as _re
    import time as _time
    
    # Timeout ditingkatkan ke 600 detik (10 menit) karena file Risalah sangat berat
    # dan mungkin antre lama di GPU (4 slots).
    client = OpenAI(base_url=LLM_BASE_URL, api_key="not-needed-for-local", timeout=600.0)
    
    for attempt in range(2):
        try:
            logger.debug(f"Calling LLM (Attempt {attempt+1})")
            response = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=temperature,
                max_tokens=10000,
                messages=[
                    {"role": "system", "content": system_prompt + "\n\nIMPORTANT: Output ONLY valid JSON starting with '{' and ending with '}'. No extra text."},
                    {"role": "user", "content": user_prompt}
                ]
            )
            raw = (response.choices[0].message.content or "").strip()
            if raw: return raw
            
            _time.sleep(1)
        except Exception as e:
            if "timed out" in str(e).lower():
                logger.error(f"LLM Timeout (Attempt {attempt+1}): LM Studio mungkin sedang overload atau GPU hang. Coba kurangi --workers.")
            else:
                logger.error(f"LLM Error (Attempt {attempt+1}): {e}")
            _time.sleep(5) # Beri jeda lebih lama jika error
            
    return ""


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Ekstrak JSON secara robust dengan mencoba semua blok kurung kurawal."""
    if not text: return None
    import json as _json
    import re as _re
    
    # 1. Bersihkan thinking tags
    text = _re.sub(r"<(?:think|thinking)>.*?</(?:think|thinking)>", "", text, flags=_re.DOTALL | _re.IGNORECASE).strip()
    
    # 2. Cari semua blok yang tampak seperti JSON object {...} secara berpasangan (balanced braces)
    matches = []
    for m in _re.finditer(r'\{', text):
        start = m.start()
        balance = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                balance += 1
            elif text[i] == '}':
                balance -= 1
                if balance == 0:
                    matches.append(text[start:i+1])
                    break
    
    if not matches:
        return None
        
    # Coba mem-parse setiap match, mulai dari yang paling panjang/lengkap
    # Prioritaskan hasil yang ada di bagian paling akhir teks (biasanya final output)
    for candidate in sorted(matches, key=lambda x: (len(x), text.find(x)), reverse=True):
        try:
            # Bersihkan karakter perusak umum
            s = candidate.strip()
            # Hapus trailing commas sebelum penutup
            s = _re.sub(r",\s*([\]}])", r"\1", s)
            parsed = _json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except:
            continue
            
    return None



def save_to_collection(
    collection_name: str,
    documents: List[str],
    metadatas: List[Dict[str, Any]],
    ids: List[str],
    db_path: str = None
):
    """Simpan dokumen ke collection ChromaDB."""
    import chromadb
    from chromadb.utils import embedding_functions

    if db_path is None:
        db_path = Path(__file__).parent / "chroma_db"

    client = chromadb.PersistentClient(path=str(db_path))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2",
        device="cuda"
    )

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef
    )

    # Batch add
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i:i+batch_size]
        batch_meta = metadatas[i:i+batch_size]
        batch_ids = ids[i:i+batch_size]
        collection.add(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_meta
        )
        logger.info(f"  [+] Added batch {i//batch_size + 1} to {collection_name}")

    logger.info(f"[OK] Total {len(documents)} items saved to '{collection_name}'")


def list_documents_by_type(doc_type: str, jsonl_path: str = None, priority_only: bool = False) -> List[Dict[str, Any]]:
    """List semua dokumen dari ChromaDB berdasarkan jenis_dokumen.

    Membaca dari ChromaDB (bukan JSONL) karena flag_priority tersimpan di ChromaDB.
    Mengembalikan data dalam format yang kompatibel dengan pipeline:
    {"chunk_id": ..., "text": ..., "metadata": {...}}

    Args:
        priority_only: Jika True, filter flag_priority=true langsung di DB query
                       (jauh lebih efisien daripada load semua lalu filter).
    """
    import chromadb
    from chromadb.utils import embedding_functions
    from pathlib import Path as _Path

    db_path = str(_Path(__file__).parent / "chroma_db")
    chroma_client = chromadb.PersistentClient(path=db_path)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    try:
        coll = chroma_client.get_collection(name="mk_knowledge_base", embedding_function=ef)
    except Exception as e:
        logger.warning(f"Tidak bisa koneksi ke mk_knowledge_base: {e}. Fallback ke JSONL.")
        if jsonl_path is None:
            # Prioritaskan compressed file, fallback ke original
            compressed = _Path(__file__).parent / "rag_chunks_compressed.jsonl"
            if compressed.exists():
                jsonl_path = compressed
            else:
                jsonl_path = _Path(__file__).parent / "rag_chunks.jsonl"
        results = []
        if not _Path(jsonl_path).exists():
            return results
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    meta = data.get("metadata", {})
                    if meta.get("jenis_dokumen") == doc_type:
                        if not priority_only or str(meta.get("flag_priority", "")).lower() == "true":
                            results.append(data)
                except Exception:
                    continue
        return results

    # Bangun where clause — filter di level DB
    if priority_only:
        where = {"$and": [
            {"jenis_dokumen":  {"$eq": doc_type}},
            {"flag_priority":  {"$eq": "true"}},
        ]}
    else:
        where = {"jenis_dokumen": {"$eq": doc_type}}

    results = []
    offset  = 0
    batch   = 5000
    while True:
        try:
            res = coll.get(
                where=where,
                limit=batch,
                offset=offset,
                include=["documents", "metadatas"],
            )
        except Exception as e:
            logger.warning(f"Error saat get batch offset={offset}: {e}")
            break

        ids = res.get("ids", [])
        if not ids:
            break

        for chunk_id, text, meta in zip(ids, res["documents"], res["metadatas"]):
            results.append({
                "chunk_id": chunk_id,
                "text":     text,
                "metadata": meta,
            })

        if len(ids) < batch:
            break
        offset += batch

    label = f"priority {doc_type}" if priority_only else doc_type
    logger.info(f"list_documents_by_type('{label}'): {len(results)} dokumen dari ChromaDB")
    return results


