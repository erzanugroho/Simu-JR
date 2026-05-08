import os
import sys
import logging
import json
from tabulate import tabulate

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    import chromadb
    from rag.retriever import RAGRetriever
except ImportError:
    print("Error: Pastikan dependencies (chromadb, tabulate) terinstall.")
    sys.exit(1)

def view_banks():
    print("="*60)
    print("🔍 LITIGATION INTELLIGENCE BANK VIEWER")
    print("="*60)
    
    try:
        retriever = RAGRetriever()
        client = retriever.client
        stats = retriever.get_stats()
        
        banks = [
            ("mk_ratio_bank", "Ratio Decidendi (Logika Menang)"),
            ("mk_attack_bank", "Attack Bank (Argumen Pemerintah)"),
            ("mk_concern_bank", "Concern Bank (Fokus Hakim)"),
            ("mk_survive_bank", "Survive Bank (Jawaban Sukses)")
        ]
        
        table_data = []
        for id, name in banks:
            count = stats.get(f"{id}_count", 0)
            table_data.append([name, id, f"{count:,} vectors"])
            
        print("\n[📊] Statistik Bank:")
        print(tabulate(table_data, headers=["Nama Bank", "Collection ID", "Jumlah Data"], tablefmt="grid"))
        
        while True:
            print("\nOpsi:")
            print("1-4. Lihat 5 data terakhir dari bank tersebut")
            print("5.   Cari data di semua bank")
            print("0.   Keluar")
            
            choice = input("\nPilih (0-5): ")
            
            if choice == "0":
                break
            
            if choice in ["1", "2", "3", "4"]:
                idx = int(choice) - 1
                bank_id = banks[idx][0]
                coll = client.get_collection(name=bank_id, embedding_function=retriever.embedding_fn)
                
                # Get last 5
                results = coll.get(limit=5, include=["documents", "metadatas"])
                
                print(f"\n--- 5 Data Terakhir di {bank_id} ---")
                if not results["documents"]:
                    print("(Bank masih kosong)")
                else:
                    for i, (doc, meta) in enumerate(zip(results["documents"], results["metadatas"])):
                        print(f"\n[{i+1}] Sumber: {meta.get('source_file', 'unknown')}")
                        print(f"Isi: {doc[:500]}...")
                        print("-" * 30)
            
            elif choice == "5":
                q = input("Masukkan kata kunci pencarian: ")
                print(f"\n🔍 Mencari '{q}' di semua bank...")
                
                for id, name in banks:
                    res = retriever._query_collection(id, q, n_results=2)
                    if res["context_text"]:
                        print(f"\n[✨] Hasil dari {name}:")
                        print(res["context_text"])
                    else:
                        print(f"\n[ ] {name}: Tidak ditemukan hasil relevan.")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    view_banks()
