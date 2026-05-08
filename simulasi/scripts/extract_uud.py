import fitz  # PyMuPDF
import json
import re

PDF_PATH = r"e:\Simu JR\UUD45_SatuNaskah.pdf"
OUTPUT_PATH = r"e:\Simu JR\simulasi\rag\uud_1945.json"

def extract_uud():
    print(f"Mengekstrak: {PDF_PATH}")
    doc = fitz.open(PDF_PATH)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    doc.close()
    
    # Cleaning dasar
    full_text = re.sub(r'\n+', '\n', full_text)
    full_text = re.sub(r' +', ' ', full_text)
    
    # Karena kita ingin memastikan teksnya bisa dipakai utuh sebagai rujukan,
    # kita bisa menyimpannya secara keseluruhan sebagai text string.
    # Atau kita potong per Bab/Pasal jika memungkinkan.
    # Untuk menghindari salah potong regex yang rumit, menyimpan clean text adalah cara paling aman
    # untuk dijadikan rujukan absolute (System Prompt Context).
    
    data = {
        "title": "Undang-Undang Dasar Negara Republik Indonesia Tahun 1945",
        "description": "Naskah Komprehensif / Satu Naskah",
        "content": full_text
    }
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Berhasil diekstrak ke: {OUTPUT_PATH}")

if __name__ == "__main__":
    extract_uud()
