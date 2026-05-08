import os
import json
import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm

# Path Configuration
# Gunakan file compressed (dedup + cleaned) untuk performa lebih baik:
#   rag_chunks_compressed.jsonl -> 802K chunks, ~920 MB (33.8% lebih kecil, zero info loss)
# Atau file original jika ingin rebuild dari awal:
#   rag_chunks.jsonl -> 1.17M chunks, ~1390 MB
JSONL_PATH = r"E:\Simu JR\simulasi\rag\rag_chunks_compressed.jsonl"
DB_PATH = r"E:\Simu JR\simulasi\rag\chroma_db"
COLLECTION_NAME = "mk_knowledge_base"
BATCH_SIZE = 1000  # ChromaDB merekomendasikan batch size maksimal sekitar 1000-5000

# Collection baru untuk Litigation Intelligence Pipeline
INTELLIGENCE_COLLECTIONS = {
    "mk_ratio_bank": "Ratio decidendi terstruktur dari putusan prioritas",
    "mk_attack_bank": "Argumen Pemerintah/DPR yang berulang dari risalah sidang",
    "mk_concern_bank": "Pertanyaan dan concern hakim yang berulang dari risalah sidang",
    "mk_survive_bank": "Jawaban Pemohon yang terbukti survive di sidang MK"
}

def get_line_count(filepath: str) -> int:
    """Menghitung total baris file JSONL untuk keperluan progress bar."""
    print("Menghitung total chunks...")
    count = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        for _ in f:
            count += 1
    return count

def main():
    if not os.path.exists(JSONL_PATH):
        print(f"Error: File {JSONL_PATH} tidak ditemukan.")
        return

    # Hitung total untuk progress bar
    total_chunks = get_line_count(JSONL_PATH)
    print(f"Total chunks yang akan diproses: {total_chunks}")

    # Inisialisasi ChromaDB Persistent Client (akan menyimpan data secara permanen di hardisk)
    print("Inisialisasi ChromaDB...")
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # Menggunakan model embedding bawaan Chroma yang sangat ringan dan cepat 
    # (all-MiniLM-L6-v2) - Sangat cocok untuk berjalan lokal tanpa membebani GPU/CPU
    sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2", device="cuda")
    
    # Membuat atau mengambil collection
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=sentence_transformer_ef
    )
    
    print("Mulai proses embedding. Ini akan memakan waktu karena mengubah jutaan kata menjadi angka vektor...")
    
    # Membaca file JSONL dan memprosesnya secara batching
    with open(JSONL_PATH, 'r', encoding='utf-8') as f:
        batch_ids = []
        batch_documents = []
        batch_metadatas = []
        
        # Kita bungkus dengan tqdm untuk progress bar
        for line in tqdm(f, total=total_chunks, desc="Embedding Chunks"):
            try:
                data = json.loads(line)
                
                # Kita tidak butuh kolom kosong atau aneh di metadata, ChromaDB strict
                # Filter agar metadata valid
                metadata = data.get("metadata", {})
                safe_metadata = {k: v for k, v in metadata.items() if v is not None}
                
                batch_ids.append(data["chunk_id"])
                batch_documents.append(data["text"])
                batch_metadatas.append(safe_metadata)
                
                # Jika sudah mencapai BATCH_SIZE, kirim ke database
                if len(batch_ids) >= BATCH_SIZE:
                    collection.add(
                        ids=batch_ids,
                        documents=batch_documents,
                        metadatas=batch_metadatas
                    )
                    # Kosongkan list untuk batch berikutnya
                    batch_ids = []
                    batch_documents = []
                    batch_metadatas = []
                    
            except Exception as e:
                # Log jika ada baris yang corrupt
                print(f"Error parsing line: {e}")
                continue
                
        # Jangan lupa simpan sisa chunks yang tidak kelipatan BATCH_SIZE
        if len(batch_ids) > 0:
            collection.add(
                ids=batch_ids,
                documents=batch_documents,
                metadatas=batch_metadatas
            )

    print("\n Proses Pembuatan Vector Database Selesai!")
    print(f"Database tersimpan secara permanen di: {DB_PATH}")
    print(f"Total Vector yang tersimpan: {collection.count()}")

    # Buat collection intelligence (kosong, akan diisi oleh pipeline)
    print("\n Membuat collection intelligence pipeline...")
    for coll_name, coll_desc in INTELLIGENCE_COLLECTIONS.items():
        try:
            client.get_or_create_collection(
                name=coll_name,
                embedding_function=sentence_transformer_ef,
                metadata={"description": coll_desc}
            )
            print(f"  OK Collection '{coll_name}' siap.")
        except Exception as e:
            print(f"  WARNING Gagal membuat collection '{coll_name}': {e}")

if __name__ == "__main__":
    main()
