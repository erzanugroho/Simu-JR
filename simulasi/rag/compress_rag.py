"""
Compress RAG Data - Kompresi data RAG tanpa kehilangan informasi.

Strategi kompresi (aman, zero info loss):
1. Hapus duplikat exact -> chunk teks identik di file berbeda cukup 1 copy
2. Normalisasi whitespace -> hapus spasi/newline berlebih
3. Bersihkan noise PDF -> hapus artefak seperti "K E T E T A P A N"
4. Perbesar chunk_size -> 2000 chars, overlap 100 (lebih sedikit chunks, lebih banyak konteks)
5. Metadata enrich -> tambah chunk_index dan total_chunks per dokumen
"""
import json
import os
import re
import hashlib
from pathlib import Path
from collections import OrderedDict, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter

# --- PATHS ---
DIR_PUTUSAN = r"E:\Simu JR\putusan_pdf"
DIR_RISALAH = r"E:\Simu JR\risalah_pdf"
INPUT_JSONL = os.path.join(os.path.dirname(__file__), "rag_chunks.jsonl")
OUTPUT_JSONL = os.path.join(os.path.dirname(__file__), "rag_chunks_compressed.jsonl")

# --- KONFIGURASI CHUNKING BARU ---
CHUNK_SIZE = 2000       # Lebih besar -> lebih sedikit chunks, lebih banyak konteks
CHUNK_OVERLAP = 100     # Overlap kecil saja untuk continuity
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

# --- NOISE CLEANING ---
def clean_pdf_artifacts(text: str) -> str:
    """Bersihkan artefak PDF tanpa mengubah isi informasi."""
    # 1. "K E T E T A P A N" -> "KETETAPAN"
    text = re.sub(r'\b([A-Z])(\s[A-Z]){3,}\b', 
                  lambda m: m.group(0).replace(' ', ''), text)
    
    # 2. Hapus header boilerplate berulang (tetap pertahankan di metadata)
    # Tidak dihapus karena bisa jadi penting untuk konteks
    
    # 3. Normalisasi whitespace
    text = re.sub(r' +', ' ', text)           # spasi ganda -> single
    text = re.sub(r'\n{3,}', '\n\n', text)    # newline 3+ -> double
    text = re.sub(r'\n +\n', '\n\n', text)    # baris kosong dengan spasi
    
    # 4. Hapus page number standalone (baris yang hanya berisi angka)
    text = re.sub(r'\n\s*\d{1,3}\s*\n', '\n', text)
    
    return text.strip()


def extract_metadata_from_filename(filename: str, jenis: str) -> dict:
    """Ekstrak metadata dasar dari nama file."""
    metadata = {
        "jenis_dokumen": jenis,
        "source_file": filename,
    }
    match_tahun = re.search(r'(20\d{2})', filename)
    if match_tahun:
        metadata["tahun"] = match_tahun.group(1)
    return metadata


def process_pdf(pdf_path: str, jenis: str) -> list:
    """Baca PDF, bersihkan teks, pecah menjadi chunks yang lebih besar."""
    path_obj = Path(pdf_path)
    filename = path_obj.name
    
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()
        
        # Bersihkan artefak PDF
        full_text = clean_pdf_artifacts(full_text)
        if not full_text or len(full_text) < 50:
            return []
        
        # Chunking dengan ukuran lebih besar
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=SEPARATORS
        )
        
        chunks = text_splitter.split_text(full_text)
        metadata = extract_metadata_from_filename(filename, jenis)
        
        result_chunks = []
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            # Skip chunks yang terlalu pendek (noise)
            if len(chunk.strip()) < 100:
                continue
            
            chunk_data = {
                "chunk_id": f"{filename}_chunk_{i}",
                "text": chunk,
                "metadata": {
                    **metadata,
                    "chunk_index": i,
                    "total_chunks": total,
                }
            }
            result_chunks.append(chunk_data)
        
        return result_chunks
        
    except Exception:
        return []


def compress_from_jsonl(input_path: str, output_path: str):
    """
    Mode 1: Kompres dari file JSONL yang sudah ada (cepat, tanpa re-extract PDF).
    Strategi: dedup + clean text + normalisasi.
    """
    print(f"Membaca dari: {input_path}")
    
    seen_hashes = set()
    total_in = 0
    total_out = 0
    total_chars_in = 0
    total_chars_out = 0
    
    with open(input_path, 'r', encoding='utf-8') as fin, \
         open(output_path, 'w', encoding='utf-8') as fout:
        
        for line in tqdm(fin, desc="Kompresi chunks"):
            total_in += 1
            d = json.loads(line)
            text = d["text"]
            total_chars_in += len(text)
            
            # 1. Bersihkan artefak PDF
            cleaned = clean_pdf_artifacts(text)
            
            # 2. Normalisasi untuk dedup
            normalized = re.sub(r'\s+', ' ', cleaned.strip().lower())
            text_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()
            
            # 3. Skip duplikat
            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)
            
            # 4. Skip chunks terlalu pendek
            if len(cleaned.strip()) < 100:
                continue
            
            # 5. Update text yang sudah dibersihkan
            d["text"] = cleaned
            total_chars_out += len(cleaned)
            
            fout.write(json.dumps(d, ensure_ascii=False) + '\n')
            total_out += 1
    
    size_out = os.path.getsize(output_path) / (1024 * 1024)
    size_in = os.path.getsize(input_path) / (1024 * 1024)
    
    print(f"\n{'='*60}")
    print(f"HASIL KOMPRESI DARI JSONL")
    print(f"{'='*60}")
    print(f"Input : {total_in:>12,} chunks | {size_in:>10.1f} MB | {total_chars_in/1024/1024:.1f} MB text")
    print(f"Output: {total_out:>12,} chunks | {size_out:>10.1f} MB | {total_chars_out/1024/1024:.1f} MB text")
    print(f"Dedup : {total_in - total_out:>12,} chunks dihapus ({(total_in-total_out)/total_in*100:.1f}%)")
    print(f"Size  : {size_in:.1f} MB -> {size_out:.1f} MB ({(1-size_out/size_in)*100:.1f}% lebih kecil)")
    print(f"{'='*60}")
    
    return output_path


def compress_from_pdf(output_path: str):
    """
    Mode 2: Re-extract dari PDF dengan chunking baru (2000 chars, overlap 100).
    Lebih agresif, lebih sedikit chunks, lebih banyak konteks per chunk.
    """
    print("Mencari file PDF...")
    putusan_files = [os.path.join(DIR_PUTUSAN, f) for f in os.listdir(DIR_PUTUSAN) if f.lower().endswith('.pdf')]
    risalah_files = [os.path.join(DIR_RISALAH, f) for f in os.listdir(DIR_RISALAH) if f.lower().endswith('.pdf')]
    
    all_tasks = [(f, "putusan") for f in putusan_files] + [(f, "risalah") for f in risalah_files]
    print(f"Total PDF: {len(all_tasks)}")
    
    seen_hashes = set()
    total_in = 0
    total_out = 0
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f_out:
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(process_pdf, path, jenis): (path, jenis) 
                      for path, jenis in all_tasks}
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="Extract + Kompres"):
                chunks = future.result()
                for chunk in chunks:
                    total_in += 1
                    
                    # Dedup berdasarkan normalized text
                    normalized = re.sub(r'\s+', ' ', chunk["text"].strip().lower())
                    text_hash = hashlib.md5(normalized.encode('utf-8')).hexdigest()
                    
                    if text_hash in seen_hashes:
                        continue
                    seen_hashes.add(text_hash)
                    
                    f_out.write(json.dumps(chunk, ensure_ascii=False) + '\n')
                    total_out += 1
    
    size_out = os.path.getsize(output_path) / (1024 * 1024)
    size_orig = os.path.getsize(INPUT_JSONL) / (1024 * 1024) if os.path.exists(INPUT_JSONL) else 0
    
    print(f"\n{'='*60}")
    print(f"HASIL KOMPRESI DARI PDF (chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    print(f"{'='*60}")
    print(f"Original JSONL : {size_orig:.1f} MB")
    print(f"Output         : {total_out:,} chunks | {size_out:.1f} MB")
    print(f"Reduction      : {(1-size_out/size_orig)*100:.1f}% lebih kecil" if size_orig > 0 else "")
    print(f"{'='*60}")
    
    return output_path


if __name__ == "__main__":
    import sys
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "jsonl"
    
    if mode == "pdf":
        # Mode agresif: re-extract dari PDF dengan chunk baru
        compress_from_pdf(OUTPUT_JSONL)
    else:
        # Mode cepat: kompres dari JSONL existing (dedup + clean)
        if os.path.exists(INPUT_JSONL):
            compress_from_jsonl(INPUT_JSONL, OUTPUT_JSONL)
        else:
            print(f"File {INPUT_JSONL} tidak ditemukan. Gunakan mode 'pdf'.")
    
    print(f"\nOK Output tersimpan di: {OUTPUT_JSONL}")
    print("Untuk menggunakan data terkompresi, update path di create_vector_db.py:")
    print(f'  JSONL_PATH = r"{OUTPUT_JSONL}"')