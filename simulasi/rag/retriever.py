"""
RAG Retriever Module
====================
Query interface ke ChromaDB untuk menyediakan konteks hukum kepada agents.
Mendukung filtered search (by jenis_dokumen, tahun) dan re-ranking sederhana.
"""

import os
import logging
import sqlite3
from typing import List, Dict, Any, Optional

import re

# Deferred import to avoid DLL conflict with onnxruntime (chromadb) on Windows.
# CrossEncoder is only loaded when reranker is actually used.
CrossEncoder = None

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    Retriever yang menghubungkan agents dengan knowledge base ChromaDB
    berisi 1.1M+ chunks dari putusan dan risalah MK.
    """

    def __init__(
        self,
        db_path: str = None,
        collection_name: str = "mk_knowledge_base",
        embedding_model: str = "all-MiniLM-L6-v2",
        rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        n_results: int = 3,
        device: str = "cuda",
        use_reranker: bool = False,
        backend: str = None,
    ):
        # Resolve path
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "chroma_db")

        logger.info(f"Menginisialisasi RAGRetriever dari: {db_path}")

        self.db_path = db_path
        self.sqlite_path = os.path.join(db_path, "chroma.sqlite3")
        self.collection_name = collection_name
        self.n_results = n_results
        self.backend = (backend or os.getenv("RAG_RETRIEVER_BACKEND", "semantic")).lower()
        self.use_reranker = use_reranker
        self.reranker_model = rerank_model
        self.reranker_device = device
        self.client = None
        self.collection = None
        self.embedding_fn = None
        self.semantic_model = None
        self.semantic_tokenizer = None
        self.embedding_device = device
        self._torch = None
        self.reranker = None
        self._query_cache: Dict[str, str] = {}

        if self.backend in {"sqlite", "keyword", "fts"}:
            if not os.path.exists(self.sqlite_path):
                raise FileNotFoundError(f"Chroma SQLite tidak ditemukan: {self.sqlite_path}")
            stats = self.get_stats()
            logger.info(
                f"OK Collection '{collection_name}' terhubung via SQLite keyword backend. "
                f"Total vectors: {stats['total_vectors']:,}"
            )
            return

        logger.info("Menyiapkan semantic embedding stack (torch/transformers)...")
        import torch
        from transformers import AutoModel, AutoTokenizer

        # Hindari sentence_transformers dan Chroma SentenceTransformerEmbeddingFunction
        # di server Windows ini. Keduanya menarik stack pandas/pyarrow/datasets yang
        # terbukti memicu native crash. Semantic search tetap dipakai dengan pooling
        # MiniLM manual yang kompatibel dengan index Chroma.
        model_id = embedding_model if "/" in embedding_model else f"sentence-transformers/{embedding_model}"
        local_only = os.getenv("RAG_EMBEDDING_LOCAL_ONLY", "1").lower() not in {"0", "false", "no"}
        self.embedding_device = device if device != "cuda" or torch.cuda.is_available() else "cpu"
        self._torch = torch
        logger.info(
            f"Loading semantic embedding model: {model_id} "
            f"({self.embedding_device}, local_only={local_only})..."
        )
        self.semantic_tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=local_only)
        self.semantic_model = AutoModel.from_pretrained(model_id, local_files_only=local_only)
        self.semantic_model.to(self.embedding_device)
        self.semantic_model.eval()

        import chromadb

        # Inisialisasi ChromaDB client setelah embedding stack dimuat.
        # Urutan ini menghindari konflik DLL pyarrow/pandas pada Windows.
        self.client = chromadb.PersistentClient(path=db_path)

        # Inisialisasi Re-ranker (Cross-Encoder) - lazy import to avoid DLL conflict
        self.use_reranker = use_reranker
        self.reranker_model = rerank_model
        self.reranker_device = device
        if use_reranker:
            global CrossEncoder
            if CrossEncoder is None:
                from sentence_transformers import CrossEncoder as _CrossEncoder
                CrossEncoder = _CrossEncoder
            logger.info(f"Loading Re-ranker model: {rerank_model}...")
            self.reranker = CrossEncoder(rerank_model, device=device)
        else:
            self.reranker = None

        # Ambil collection yang sudah ada
        try:
            self.collection = self.client.get_collection(name=collection_name)
            total = self.collection.count()
            logger.info(f"OK Collection '{collection_name}' terhubung. Total vectors: {total:,}")
        except Exception as e:
            logger.error(f"FAILED Gagal mengakses collection '{collection_name}': {e}")
            raise

    def _semantic_query_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate query embeddings dengan model yang sama seperti index Chroma."""
        if self.semantic_model is None or self.semantic_tokenizer is None or self._torch is None:
            raise RuntimeError("Semantic embedding model belum diinisialisasi")
        encoded = self.semantic_tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.embedding_device) for key, value in encoded.items()}
        with self._torch.no_grad():
            output = self.semantic_model(**encoded)

        token_embeddings = output.last_hidden_state
        attention_mask = encoded["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
        summed = (token_embeddings * attention_mask).sum(dim=1)
        counts = attention_mask.sum(dim=1).clamp(min=1e-9)
        embeddings = summed / counts
        return embeddings.detach().cpu().numpy().tolist()

    def _sqlite_connect(self):
        uri = f"file:{self.sqlite_path.replace(os.sep, '/')}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=5.0)

    def _keywords(self, text: str, max_terms: int = 8) -> List[str]:
        stopwords = {
            "yang", "dan", "atau", "dengan", "untuk", "dari", "pada", "dalam", "bahwa",
            "adalah", "sebagai", "karena", "tersebut", "oleh", "serta", "akan", "tidak",
            "para", "ini", "itu", "dapat", "harus", "telah", "secara", "maka", "agar",
            "the", "and", "for", "with", "from", "this", "that",
        }
        raw_terms = re.findall(r"[a-zA-Z0-9_À-ÿ]+", text.lower())
        terms: List[str] = []
        for term in raw_terms:
            if term in stopwords:
                continue
            if len(term) < 4 and not any(ch.isdigit() for ch in term):
                continue
            if term not in terms:
                terms.append(term)
            if len(terms) >= max_terms:
                break
        return terms

    def _sqlite_query_collection(
        self,
        collection_name: str,
        question: str,
        n_results: int = 3,
        filter_jenis: Optional[str] = None,
        filter_tahun: Optional[str] = None,
    ) -> Dict[str, Any]:
        terms = self._keywords(question)
        if not terms:
            return {"context_text": "", "sources": [], "raw_results": None}

        fetch_n = max(n_results * 8, 20)
        params: List[Any] = [collection_name]
        where = ["c.name = ?"]
        fts_query = " OR ".join(terms)
        where.append("embedding_fulltext_search MATCH ?")
        params.append(fts_query)
        if filter_jenis:
            where.append("jenis.string_value = ?")
            params.append(filter_jenis)
        if filter_tahun:
            where.append("tahun.string_value = ?")
            params.append(filter_tahun)
        params.append(fetch_n)

        sql = f"""
            SELECT e.id, fts.string_value, source.string_value, docid.string_value,
                   jenis.string_value, tahun.string_value
            FROM embedding_fulltext_search fts
            JOIN embeddings e ON e.id = fts.rowid
            JOIN segments s ON s.id = e.segment_id
            JOIN collections c ON c.id = s.collection
            LEFT JOIN embedding_metadata source ON source.id = e.id AND source.key = 'source_file'
            LEFT JOIN embedding_metadata docid ON docid.id = e.id AND docid.key = 'doc_id'
            LEFT JOIN embedding_metadata jenis ON jenis.id = e.id AND jenis.key = 'jenis_dokumen'
            LEFT JOIN embedding_metadata tahun ON tahun.id = e.id AND tahun.key = 'tahun'
            WHERE {" AND ".join(where)}
            LIMIT ?
        """

        try:
            with self._sqlite_connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.warning(f"SQLite keyword query gagal untuk '{collection_name}': {e}")
            return {"context_text": "", "sources": [], "raw_results": None}

        if not rows:
            return {"context_text": "", "sources": [], "raw_results": []}

        scored_results = []
        for emb_id, doc, source_file, doc_id, jenis, tahun in rows:
            doc = doc or ""
            doc_lower = doc.lower()
            source = source_file or doc_id or "unknown"
            score = sum(doc_lower.count(term) for term in terms)
            score += sum(1 for term in terms if term in str(source).lower())
            scored_results.append({
                "id": emb_id,
                "doc": doc,
                "meta": {
                    "source_file": source,
                    "jenis_dokumen": jenis or collection_name,
                    "tahun": tahun or "?",
                },
                "score": score,
            })

        scored_results.sort(key=lambda item: item["score"], reverse=True)
        final_results = scored_results[:n_results]

        context_parts = []
        sources = []
        for i, res in enumerate(final_results):
            doc = res["doc"]
            meta = res["meta"]
            if len(doc) > 800:
                doc = doc[:800] + "..."
            context_parts.append(
                f"[{i+1}] ({str(meta.get('jenis_dokumen', 'unknown')).upper()} - "
                f"{meta.get('source_file', 'unknown')}, Tahun {meta.get('tahun', '?')})\n{doc}"
            )
            sources.append({
                "source_file": meta.get("source_file", "unknown"),
                "jenis": meta.get("jenis_dokumen", "unknown"),
                "tahun": meta.get("tahun", "?"),
                "relevance_score": round(float(res["score"]), 4),
            })

        return {
            "context_text": "\n\n---\n\n".join(context_parts),
            "sources": sources,
            "raw_results": rows,
        }

    def query(
        self,
        question: str,
        n_results: int = None,
        filter_jenis: Optional[str] = None,
        filter_tahun: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query knowledge base dan kembalikan chunks yang relevan.

        Args:
            question: Pertanyaan atau konteks yang ingin dicari
            n_results: Jumlah hasil (override default)
            filter_jenis: Filter berdasarkan jenis dokumen ('putusan' atau 'risalah')
            filter_tahun: Filter berdasarkan tahun dokumen

        Returns:
            Dict dengan keys: 'context_text', 'sources', 'raw_results'
        """
        n = n_results or self.n_results

        if self.backend in {"sqlite", "keyword", "fts"}:
            return self._sqlite_query_collection(
                self.collection_name,
                question,
                n_results=n,
                filter_jenis=filter_jenis,
                filter_tahun=filter_tahun,
            )

        # Build where filter (ChromaDB filter syntax)
        where_filter = None
        conditions = []

        if filter_jenis:
            conditions.append({"jenis_dokumen": {"$eq": filter_jenis}})
        if filter_tahun:
            conditions.append({"tahun": {"$eq": filter_tahun}})

        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        try:
            # Ambil lebih banyak kandidat jika menggunakan re-ranker
            fetch_n = n * 5 if self.use_reranker else n
            
            query_embeddings = self._semantic_query_embeddings([question])
            results = self.collection.query(
                query_embeddings=query_embeddings,
                n_results=fetch_n,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error(f"Query RAG gagal: {e}")
            return {"context_text": "", "sources": [], "raw_results": None}

        # --- RE-RANKING & KEYWORD BOOSTING LOGIC ---
        documents = results["documents"][0] if results.get("documents") else []
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(documents)
        distances = results["distances"][0] if results.get("distances") else [1.0] * len(documents)

        if not documents:
            return {"context_text": "", "sources": [], "raw_results": results}

        # 1. Ekstraksi keyword penting (nomor putusan/pasal) dari pertanyaan
        keywords = re.findall(r'(\d+[\d\-\/A-Z]*)', question)
        
        scored_results = []
        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
            # Base score dari jarak semantik (semakin kecil distance, semakin besar score)
            base_score = 1.0 - (dist / 2.0)
            
            # Keyword Boosting (sangat penting untuk nomor putusan)
            boost = 0.0
            for kw in keywords:
                if len(kw) > 2: # Hanya boost untuk keyword yang cukup panjang
                    if kw.lower() in doc.lower() or kw.lower() in meta.get("source_file", "").lower():
                        boost += 0.5
            
            scored_results.append({
                "doc": doc,
                "meta": meta,
                "score": base_score + boost
            })

        # 2. Re-ranking dengan Cross-Encoder (jika aktif)
        if self.use_reranker and self.reranker:
            pairs = [[question, r["doc"]] for r in scored_results]
            cross_scores = self.reranker.predict(pairs)
            for idx, score in enumerate(cross_scores):
                # Gabungkan cross-score dengan keyword boost
                base_score = scored_results[idx]["score"]
                scored_results[idx]["score"] = score + (base_score - (1.0 - (distances[idx]/2.0)))

        # 3. Sort berdasarkan score akhir dan ambil top N
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        final_results = scored_results[:n]

        # Format hasil
        context_parts = []
        sources = []

        for i, res in enumerate(final_results):
            doc = res["doc"]
            meta = res["meta"]
            
            source_file = meta.get("source_file", "unknown")
            jenis = meta.get("jenis_dokumen", "unknown")
            tahun = meta.get("tahun", "?")

            # Truncate chunk untuk hemat token (relevance tertinggi di awal chunk)
            if len(doc) > 800:
                doc = doc[:800] + "..."

            context_parts.append(
                f"[{i+1}] ({jenis.upper()} - {source_file}, Tahun {tahun})\n{doc}"
            )

            sources.append({
                "source_file": source_file,
                "jenis": jenis,
                "tahun": tahun,
                "relevance_score": round(res["score"], 4)
            })

        context_text = "\n\n---\n\n".join(context_parts) if context_parts else ""

        return {
            "context_text": context_text,
            "sources": sources,
            "raw_results": results
        }

    def query_for_agent(
        self,
        question: str,
        agent_role: str = "umum",
        n_results: int = None,
        use_intelligence_banks: bool = True
    ) -> str:
        """
        Query yang disesuaikan per role agent.
        Hakim mendapat konteks dari putusan + concern bank + ratio bank.
        Pemohon mendapat konteks dari putusan + survive bank + ratio bank.
        Pemerintah mendapat konteks dari putusan + attack bank.

        Returns:
            Formatted context string siap inject ke prompt agent.
        """
        # ----- CACHE CHECK -----
        key = f"{question}|{agent_role}"
        if key in self._query_cache:
            logger.debug(f"Cache hit untuk ({agent_role})")
            return self._query_cache[key]

        filter_jenis = None

        if agent_role == "hakim":
            # Hakim perlu referensi putusan untuk menilai
            filter_jenis = "putusan"
        elif agent_role == "pemohon":
            # Pemohon biasanya mencari preseden yang dikabulkan
            filter_jenis = "putusan"
        elif agent_role == "pemerintah":
            # Pemerintah biasanya mencari preseden yang ditolak atau risalah terkait
            pass  # Tidak filter agar dapat keduanya

        result = self.query(question, n_results=n_results, filter_jenis=filter_jenis)
        base = result["context_text"] if result["context_text"] else ""

        # Jika intelligence banks tidak diaktifkan, kembalikan base saja
        if not use_intelligence_banks:
            if not base:
                return ""
            wrapped = (
                "========================================\n"
                " REFERENSI HUKUM DARI DATABASE MK:\n"
                "(Gunakan informasi di bawah ini untuk memperkuat argumen Anda. "
                "Kutip nomor putusa/pasal secara akurat.)\n"
                "========================================\n\n"
                f"{base}\n\n"
                "=======================================\n"
            )
            # Cache and return
            self._query_cache[key] = wrapped
            return wrapped

        # Routing berbasis role dengan intelligence banks
        intelligence_parts = []

        if agent_role == "hakim":
            ratio = self.query_ratio_bank(question, n_results=3)
            concern = self.query_concern_bank(question, n_results=3)
            if ratio:
                intelligence_parts.append(f"=== RATIO BANK ===\n{ratio}")
            if concern:
                intelligence_parts.append(f"=== JUDGE CONCERN BANK ===\n{concern}")

        elif agent_role == "pemohon":
            survive = self.query_survive_bank(question, n_results=3)
            ratio = self.query_ratio_bank(question, n_results=3)
            if survive:
                intelligence_parts.append(f"=== SURVIVE BANK ===\n{survive}")
            if ratio:
                intelligence_parts.append(f"=== RATIO BANK ===\n{ratio}")

        elif agent_role == "pemerintah":
            attack = self.query_attack_bank(question, n_results=3)
            if attack:
                intelligence_parts.append(f"=== GOVERNMENT ATTACK BANK ===\n{attack}")

        # Gabungkan base + intelligence
        combined = base
        if intelligence_parts:
            combined += "\n\n" + "\n\n".join(intelligence_parts)

        if not combined.strip():
            wrapped = ""
        else:
            wrapped = (
                "========================================\n"
                " REFERENSI HUKUM DARI DATABASE MK:\n"
                "(Gunakan informasi di bawah ini untuk memperkuat argumen Anda. "
                "Kutip nomor putusa/pasal secara akurat.)\n"
                "========================================\n\n"
                f"{combined}\n\n"
                "=======================================\n"
            )

        # Cache and return
        self._query_cache[key] = wrapped
        return wrapped

    def _query_collection(
        self,
        collection_name: str,
        question: str,
        n_results: int = 3
    ) -> Dict[str, Any]:
        """
        Query ke collection ChromaDB tertentu dan kembalikan hasil terformat.
        """
        if self.backend in {"sqlite", "keyword", "fts"}:
            return self._sqlite_query_collection(collection_name, question, n_results)

        try:
            coll = self.client.get_collection(name=collection_name)
            query_embeddings = self._semantic_query_embeddings([question])
            results = coll.query(
                query_embeddings=query_embeddings,
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.warning(f"Query collection '{collection_name}' gagal: {e}")
            return {"context_text": "", "sources": []}

        documents = results["documents"][0] if results.get("documents") else []
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(documents)
        distances = results["distances"][0] if results.get("distances") else [1.0] * len(documents)

        if not documents:
            return {"context_text": "", "sources": []}

        context_parts = []
        sources = []
        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
            source_file = meta.get("source_file", meta.get("doc_id", "unknown"))
            # Truncate chunk untuk hemat token
            if len(doc) > 800:
                doc = doc[:800] + "..."
            context_parts.append(
                f"[{collection_name} {i+1}] (Sumber: {source_file})\n{doc}"
            )
            sources.append({
                "source": source_file,
                "collection": collection_name,
                "distance": round(dist, 4)
            })

        return {
            "context_text": "\n\n---\n\n".join(context_parts),
            "sources": sources
        }

    def query_ratio_bank(self, query: str, n_results: int = 3) -> str:
        """Query ke mk_ratio_bank - ratio decidendi terstruktur."""
        result = self._query_collection("mk_ratio_bank", query, n_results)
        return result["context_text"]

    def query_attack_bank(self, query: str, n_results: int = 3) -> str:
        """Query ke mk_attack_bank - argumen Pemerintah/DPR."""
        result = self._query_collection("mk_attack_bank", query, n_results)
        return result["context_text"]

    def query_concern_bank(self, query: str, n_results: int = 3) -> str:
        """Query ke mk_concern_bank - pertanyaan/concern hakim."""
        result = self._query_collection("mk_concern_bank", query, n_results)
        return result["context_text"]

    def query_survive_bank(self, query: str, n_results: int = 3) -> str:
        """Query ke mk_survive_bank - jawaban Pemohon yang survive."""
        result = self._query_collection("mk_survive_bank", query, n_results)
        return result["context_text"]

    def get_stats(self) -> Dict[str, Any]:
        """Mengembalikan statistik database untuk semua collection."""
        if self.backend in {"sqlite", "keyword", "fts"}:
            with self._sqlite_connect() as conn:
                rows = conn.execute(
                    """
                    SELECT c.name, COUNT(e.id)
                    FROM collections c
                    JOIN segments s ON s.collection = c.id AND s.scope = 'METADATA'
                    LEFT JOIN embeddings e ON e.segment_id = s.id
                    GROUP BY c.name
                    """
                ).fetchall()
            counts = {name: count for name, count in rows}
            stats = {
                "total_vectors": counts.get(self.collection_name, 0),
                "collection_name": self.collection_name,
                "backend": self.backend,
            }
            for coll_name in ["mk_ratio_bank", "mk_attack_bank", "mk_concern_bank", "mk_survive_bank"]:
                stats[f"{coll_name}_count"] = counts.get(coll_name, 0)
            return stats

        stats = {
            "total_vectors": self.collection.count(),
            "collection_name": self.collection.name,
            "backend": self.backend,
        }
        # Cek collection intelligence
        for coll_name in ["mk_ratio_bank", "mk_attack_bank", "mk_concern_bank", "mk_survive_bank"]:
            try:
                coll = self.client.get_collection(name=coll_name)
                stats[f"{coll_name}_count"] = coll.count()
            except Exception:
                stats[f"{coll_name}_count"] = 0
        return stats


# --- Testing ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    retriever = RAGRetriever()

    print(f"\n Stats: {retriever.get_stats()}\n")

    test_query = "legal standing pemohon dalam pengujian UU ITE"
    print(f" Query: '{test_query}'\n")

    result = retriever.query(test_query, n_results=3)
    print(result["context_text"][:2000])
    print(f"\n Sources: {result['sources']}")
