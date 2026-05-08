import os
import sys
import logging
from rag.retriever import RAGRetriever

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

def check_metadata():
    try:
        retriever = RAGRetriever()
        coll = retriever.collection
        
        # Check for flag_priority
        results = coll.get(where={"flag_priority": {"$eq": True}}, limit=5)
        print(f"Priority Documents: {len(results['ids'])}")
        
        if len(results['ids']) == 0:
            print("\n[!] PERINGATAN: Tidak ada dokumen yang ditandai sebagai 'priority'.")
            print("Ini sebabnya pipeline tadi tidak mengekstrak apa-apa.")
            print("\nSolusi: Anda perlu menjalankan Agent 1 (Classifier) terlebih dahulu untuk menandai putusan-putusan penting.")
            
            # Check a few random entries to see current metadata
            print("\nContoh metadata pada 3 dokumen pertama:")
            random_docs = coll.get(limit=3, include=["metadatas"])
            for i, meta in enumerate(random_docs["metadatas"]):
                print(f"Doc {i+1}: {meta}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_metadata()
