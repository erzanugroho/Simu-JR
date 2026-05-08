import os
import fitz  # PyMuPDF
import json
import re
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Direktori sumber PDF
DIR_PUTUSAN = r"E:\Simu JR\putusan_pdf"
DIR_RISALAH = r"E:\Simu JR\risalah_pdf"
# Output file
OUTPUT_JSONL = r"E:\Simu JR\simulasi\rag\rag_chunks.jsonl"

# Konfigurasi LLM untuk Agent 1 Classifier (bisa pakai local atau API)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://192.168.1.102:1234/v1")
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "local-model")
ENABLE_CLASSIFIER = os.getenv("ENABLE_AGENT1_CLASSIFIER", "false").lower() == "true"

# Load prompt Agent 1
PROMPT_DIR = Path(__file__).parent / "prompts"
AGENT1_PROMPT_PATH = PROMPT_DIR / "agent1_classifier.txt"
AGENT1_CLASSIFIER_PROMPT = ""
if AGENT1_PROMPT_PATH.exists():
    AGENT1_CLASSIFIER_PROMPT = AGENT1_PROMPT_PATH.read_text(encoding="utf-8")

def clean_text(text: str) -> str:
    """Membersihkan teks dari karakter yang tidak perlu."""
    # Hapus spasi dan newline berlebih
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def extract_metadata_from_filename(filename: str, jenis: str) -> dict:
    """Ekstrak metadata dasar dari nama file."""
    # Contoh sederhana, bisa dipercanggih nanti dengan regex ke isi teks
    metadata = {
        "jenis_dokumen": jenis,
        "source_file": filename,
    }
    
    # Coba ekstrak tahun dari nama file (jika ada format 20xx)
    match_tahun = re.search(r'(20\d{2})', filename)
    if match_tahun:
        metadata["tahun"] = match_tahun.group(1)
        
    return metadata


def classify_document_with_agent1(text: str, doc_id: str, doc_type: str) -> dict:
    """
    Klasifikasikan dokumen menggunakan LLM (Agent 1 Classifier).
    Mengembalikan metadata tambahan: norma_diuji, batu_uji, amar, klaster, flag_priority.
    Jika classifier tidak aktif atau gagal, kembalikan dict kosong.
    """
    if not ENABLE_CLASSIFIER or not AGENT1_CLASSIFIER_PROMPT:
        return {}

    try:
        import httpx
        from openai import OpenAI

        client = OpenAI(base_url=LLM_BASE_URL, api_key="not-needed-for-local")
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.0,
            messages=[
                {"role": "system", "content": AGENT1_CLASSIFIER_PROMPT},
                {"role": "user", "content": f"Klasifikasikan dokumen berikut:\n\n{text[:4000]}"}
            ]
        )
        raw = response.choices[0].message.content.strip()
        
        # === ROBUST JSON EXTRACTION ===
        # 1. Hapus blok <think>...</think> jika ada
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
        
        # 2. Ekstrak semua JSON object menggunakan bracket-matching
        #    (regex sederhana tidak bisa handle nested array/object)
        def extract_all_json_objects(text):
            """Ekstrak semua JSON object dari teks menggunakan bracket matching."""
            objects = []
            i = 0
            while i < len(text):
                if text[i] == '{':
                    depth = 0
                    start = i
                    while i < len(text):
                        if text[i] == '{':
                            depth += 1
                        elif text[i] == '}':
                            depth -= 1
                            if depth == 0:
                                candidate = text[start:i+1]
                                objects.append(candidate)
                                break
                        i += 1
                i += 1
            return objects
        
        all_candidates = extract_all_json_objects(raw)
        
        result = None
        # Coba dari yang TERAKHIR (jawaban aktual setelah penjelasan panjang)
        for candidate_str in reversed(all_candidates):
            try:
                candidate = json.loads(candidate_str)
                # Validasi: harus punya field kunci klasifikasi
                if any(k in candidate for k in ('tahun', 'flag_priority', 'amar', 'klaster')):
                    result = candidate
                    break
            except json.JSONDecodeError:
                continue
        
        if result:
            # Pastikan field array adalah string untuk metadata ChromaDB
            if isinstance(result.get("batu_uji"), list):
                result["batu_uji"] = json.dumps(result["batu_uji"], ensure_ascii=False)
            klaster_raw = result.get("klaster", [])
            if isinstance(klaster_raw, list):
                result["klaster"] = json.dumps(klaster_raw, ensure_ascii=False)
            else:
                klaster_raw = result.get("klaster", "")
            
            # Auto-override flag_priority: paksa true jika ada klaster strategis
            PRIORITY_CLUSTERS = {"[TAX]", "[ANTI_AVOIDANCE]", "[OPENpolicy]", "[CONDITIONAL]", "[PROPORSIONALITAS]"}
            klaster_str = result.get("klaster", "")
            if any(c in klaster_str for c in PRIORITY_CLUSTERS):
                result["flag_priority"] = "true"
            elif isinstance(result.get("flag_priority"), bool):
                result["flag_priority"] = str(result["flag_priority"]).lower()
            elif not isinstance(result.get("flag_priority"), str):
                result["flag_priority"] = "false"
            return result
        
        print(f"[Agent1] WARNING: Tidak dapat mengekstrak JSON valid dari respons untuk {doc_id}")
        return {}
        
    except Exception as e:
        import traceback
        print(f"[Agent1] ERROR pada {doc_id}: {e}")
        traceback.print_exc()
        return {}

def process_pdf(pdf_path: str, jenis: str) -> list:
    """
    Membaca PDF, mengekstrak teks, dan memecahnya menjadi chunks.
    Mengembalikan list of dictionaries (chunks).
    """
    path_obj = Path(pdf_path)
    filename = path_obj.name
    
    try:
        # Buka dokumen PDF
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()
        
        full_text = clean_text(full_text)
        if not full_text:
            return []

        # Atur strategi pemotongan teks (Chunking)
        # 2000 karakter per chunk dengan overlap 100 — lebih sedikit chunks,
        # lebih banyak konteks per chunk, overlap minimal untuk continuity
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=100,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        chunks = text_splitter.split_text(full_text)
        metadata = extract_metadata_from_filename(filename, jenis)

        # Agent 1: Klasifikasi dokumen (gunakan teks awal dokumen)
        agent1_result = classify_document_with_agent1(full_text, filename, jenis)
        if agent1_result:
            metadata["norma_diuji"] = agent1_result.get("norma_diuji", "")
            metadata["batu_uji"] = agent1_result.get("batu_uji", "")
            metadata["amar"] = agent1_result.get("amar", "")
            metadata["klaster"] = agent1_result.get("klaster", "")
            metadata["flag_priority"] = str(agent1_result.get("flag_priority", False)).lower()
        
        # Susun data hasil akhir
        result_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_data = {
                "chunk_id": f"{filename}_chunk_{i}",
                "text": chunk,
                "metadata": metadata.copy()
            }
            result_chunks.append(chunk_data)
            
        return result_chunks
        
    except Exception as e:
        # Jika PDF corrupt, skip dan log diam-diam
        return []

def main():
    print("Mencari file PDF...")
    putusan_files = [os.path.join(DIR_PUTUSAN, f) for f in os.listdir(DIR_PUTUSAN) if f.lower().endswith('.pdf')]
    risalah_files = [os.path.join(DIR_RISALAH, f) for f in os.listdir(DIR_RISALAH) if f.lower().endswith('.pdf')]
    
    all_tasks = [(f, "putusan") for f in putusan_files] + [(f, "risalah") for f in risalah_files]
    
    # Agar tidak meledakkan memori dan terlalu lama waktu testing, 
    # kita bisa batasi dulu (misal: jalankan 100 file pertama untuk memastikan jalan)
    # Jika ingin jalankan semua, hapus limitasi di bawah.
    # all_tasks = all_tasks[:100] 
    
    print(f"Total PDF yang akan diproses: {len(all_tasks)}")
    print(f"Menulis hasil ke: {OUTPUT_JSONL}")
    
    os.makedirs(os.path.dirname(OUTPUT_JSONL), exist_ok=True)
    
    # Buka file dalam mode append ('a') jika ingin resume, atau write ('w') untuk mulai baru
    with open(OUTPUT_JSONL, 'w', encoding='utf-8') as f_out:
        # Gunakan multiprocessing agar 11.000 file PDF diproses super cepat via CPU Cores
        with ProcessPoolExecutor() as executor:
            # Submit semua task ke CPU
            futures = {executor.submit(process_pdf, path, jenis): (path, jenis) for path, jenis in all_tasks}
            
            # Kumpulkan hasil selagi berjalan menggunakan progress bar
            for future in tqdm(as_completed(futures), total=len(futures), desc="Memproses PDF"):
                chunks = future.result()
                if chunks:
                    for chunk in chunks:
                        # Tulis baris per baris (JSONL)
                        f_out.write(json.dumps(chunk, ensure_ascii=False) + '\n')

    print("\n✅ Proses Ekstraksi dan Chunking Selesai!")
    print(f"File database mentah tersimpan di: {OUTPUT_JSONL}")
    
    # Opsional: Cek ukuran file
    size_mb = os.path.getsize(OUTPUT_JSONL) / (1024 * 1024)
    print(f"Ukuran database JSONL: {size_mb:.2f} MB")

if __name__ == "__main__":
    main()
