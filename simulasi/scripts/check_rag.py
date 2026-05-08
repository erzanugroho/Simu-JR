import sys
import os
import logging

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# Prevent encoding issues on Windows
if sys.platform == "win32":
    import functools
    print = functools.partial(print, flush=True)

logging.basicConfig(level=logging.INFO)

try:
    from rag.retriever import RAGRetriever
    # Disable re-ranker for quick check if needed, but here we want to test it
    r = RAGRetriever(use_reranker=True)
    
    stats = r.get_stats()
    print(f"\n[OK] RAG CONNECTED")
    print(f"Collection: {stats['collection_name']}")
    print(f"Total Vectors: {stats['total_vectors']:,}")
    
    # Test Query with Decision Number
    query = "Apa isi pertimbangan dalam Putusan Nomor 013-022/PUU-IV/2006?"
    print(f"\n[TEST] HYBRID SEARCH & RE-RANKING")
    print(f"Query: {query}")
    print("-" * 50)
    
    result = r.query(query, n_results=3)
    
    if result["context_text"]:
        print(f"Hasil Teratas (Re-ranked):")
        # Remove any non-ascii for console safety
        safe_text = result["context_text"][:1000].encode('ascii', 'ignore').decode('ascii')
        print(safe_text + "...")
        print("\n[SOURCES] Sumber & Skor:")
        for s in result["sources"]:
            print(f"- {s['source_file']} (Tahun {s['tahun']}) | Score: {s['relevance_score']}")
    else:
        print("[!] Tidak ada hasil yang relevan ditemukan.")

except Exception as e:
    print(f"[!] FAILURE: RAG is not available. Error: {str(e).encode('ascii', 'ignore').decode('ascii')}")
