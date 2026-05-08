import os
import sys
from pathlib import Path

# Tambahkan path agar bisa import dari folder rag
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.pipeline_utils import call_llm_sync, extract_json_from_text

def test():
    print("=== DIAGNOSTIK LLM ===")
    system_prompt = "Anda adalah asisten hukum. Jawab dalam JSON."
    user_prompt = "Ekstrak nama pemohon dari kalimat ini: 'Pemohon adalah Erza Nugroho yang mengajukan uji materi UU ITE.'"
    
    print(f"\n1. Memanggil LLM...")
    raw = call_llm_sync(system_prompt, user_prompt)
    
    print("\n2. Respon MENTAH dari AI:")
    print("-" * 50)
    print(raw if raw else "[KOSONG / EMPTY]")
    print("-" * 50)
    
    if raw:
        print("\n3. Mencoba Ekstraksi JSON...")
        result = extract_json_from_text(raw)
        if result:
            print("OK BERHASIL: ", result)
        else:
            print("FAILED GAGAL EKSTRAKSI JSON")
    else:
        print("\nFAILED GAGAL: AI tidak memberikan respon.")

if __name__ == "__main__":
    test()
