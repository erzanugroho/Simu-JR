"""
Script diagnosa: panggil classify_document_with_agent1 langsung dan print hasilnya.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
os.environ["ENABLE_AGENT1_CLASSIFIER"] = "true"

from rag.extract_and_chunk import classify_document_with_agent1

sample_text = """
PUTUSAN
Nomor 013/PUU-III/2005
DEMI KEADILAN BERDASARKAN KETUHANAN YANG MAHA ESA
MAHKAMAH KONSTITUSI REPUBLIK INDONESIA

Memeriksa, mengadili, dan memutus perkara konstitusi pada tingkat pertama dan terakhir,
telah menjatuhkan putusan dalam perkara permohonan Pengujian Undang-Undang Nomor 17 
Tahun 2000 tentang Perubahan Ketiga Atas Undang-Undang Nomor 7 Tahun 1983 tentang 
Pajak Penghasilan terhadap Undang-Undang Dasar Negara Republik Indonesia Tahun 1945.

Pemohon: PT Rajawali Citra Televisi Indonesia
Norma yang diuji: Pasal 4 ayat (2) UU PPh tentang pajak final
Batu uji: Pasal 28D ayat (1) UUD 1945

AMAR PUTUSAN: Menolak permohonan Pemohon untuk seluruhnya.
"""

print("Memanggil classify_document_with_agent1...")
result = classify_document_with_agent1(sample_text, "test_doc_001", "putusan")
print("\n=== HASIL ===")
print(f"Result: {result}")
print(f"flag_priority: {result.get('flag_priority', 'N/A')}")
print(f"klaster: {result.get('klaster', 'N/A')}")
