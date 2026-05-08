"""
Extract Risalah Dialogs - Fine-Tuning Dataset Builder
=====================================================
Parse risalah sidang chunks dari rag_chunks.jsonl menjadi
multi-turn conversation pairs untuk fine-tuning Qwen.

Format risalah:
    NOMOR. PERAN: NAMA [TIMESTAMP]
    Isi dialog...

Contoh:
    1. KETUA: SUHARTOYO [00:00]
    Kita buka persidangan. Persidangan Perkara Nomor 19...
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

# Tambahkan parent ke path
sys.path.insert(0, str(Path(__file__).parent.parent))
from finetuning.config import RAG_CHUNKS_PATH, ensure_dirs, MIN_WORDS


# === Regex Pattern untuk Parsing Dialog ===
# Format: "NOMOR. PERAN: NAMA [TIMESTAMP]"
# Contoh: "1. KETUA: SUHARTOYO [00:00]"
# Contoh: "122. PEMOHON: TERENCE CAMERON [01:22:38]"
# Contoh: "6. KUASA HUKUM PEMOHON PERKARA NOMOR 19/PUU-XXII/2024: MOHAMMAD AHMADI [00:45]"
SPEAKER_PATTERN = re.compile(
    r'(\d+)\.\s+'                           # Nomor urut
    r'((?:KETUA|HAKIM\s+(?:ANGGOTA|KONSTITUSI)|'  # Hakim
    r'PEMOHON|KUASA\s+HUKUM\s+PEMOHON|'     # Pemohon
    r'PEMERINTAH|KUASA\s+HUKUM\s+P(?:RESIDEN|EMERINTAH)|'  # Pemerintah
    r'PIHAK\s+TERKAIT|KUASA\s+HUKUM\s+PIHAK\s+TERKAIT|'   # Pihak Terkait
    r'AMICUS\s+CURIAE|'                     # Amicus Curiae
    r'AHLI|SAKSI|Saksi|'                     # Ahli/Saksi
    r'PANITERA(?:\s+PENGGANTI)?|'          # Panitera
    r'NOTA|KESIMPULAN|'                     # Lain-lain
    r'[A-Z\s]+?))'                          # Generic uppercase role
    r'(?:PERKARA\s+NOMOR\s+[\d/]+(?:PUU)?[\w./-]*)?:?\s*'  # Optional perkara reference
    r'([A-Z][A-Z\s.]+?)\s*'                # Nama (uppercase)
    r'\[(\d{1,2}:\d{2}(?::\d{2})?)\]'      # Timestamp [HH:MM] atau [HH:MM:SS]
)

# Pattern untuk judul/sampul (bukan dialog)
HEADER_PATTERN = re.compile(
    r'(?:MAHKAMAH\s+KONSTITUSI|RISALAH\s+SIDANG|PERKARA\s+NOMOR|'
    r'PERIHAL|ACARA|JAKARTA|SENIN|SELASA|RABU|KAMIS|JUMAT|'
    r'SUSUNAN\s+PERSIDANGAN|MAJELIS\s+HAKIM|PANITERA\s+PENGGANTI|'
    r'Pihak\s+yang\s+Hadir|SIDANG\s+DIBUKA|SIDANG\s+DITUTUP|KETUK\s+PALU)'
)

# Pattern untuk metadata perkara
CASE_PATTERN = re.compile(
    r'PERKARA\s+NOMOR\s+([\d/]+(?:PUU)[\w./-]*)',
    re.IGNORECASE
)

NORMA_PATTERN = re.compile(
    r'(?:PENGUJIAN\s+(?:MATERIL|FORMIL)?\s*(?:UNDANG-UNDANG|UU)\s*(?:NOMOR)?\s*(\d+)\s*TAHUN\s*(\d+))',
    re.IGNORECASE
)


def classify_role(raw_role: str) -> str:
    """Klasifikasi role pembicara ke kategori standar."""
    role = raw_role.upper().strip()
    
    if 'KETUA' in role:
        return 'KETUA'
    elif 'HAKIM' in role:
        return 'HAKIM_ANGGOTA'
    elif 'KUASA HUKUM PEMOHON' in role or role.startswith('PEMOHON'):
        if 'KUASA' in role:
            return 'KUASA_HUKUM_PEMOHON'
        return 'PEMOHON'
    elif 'KUASA HUKUM P' in role and 'EMERINTAH' in role:
        return 'KUASA_HUKUM_PEMERINTAH'
    elif 'PEMERINTAH' in role:
        return 'PEMERINTAH'
    elif 'PIHAK TERKAIT' in role:
        return 'PIHAK_TERKAIT'
    elif 'AMICUS' in role:
        return 'AMICUS_CURIAE'
    elif 'AHLI' in role:
        return 'AHLI'
    elif 'SAKSI' in role or 'Saksi' in raw_role:
        return 'SAKSI'
    elif 'PANITERA' in role:
        return 'PANITERA'
    else:
        return 'LAINNYA'


def role_to_persona(role: str) -> str:
    """Map role ke system prompt persona."""
    mapping = {
        'KETUA': 'hakim',
        'HAKIM_ANGGOTA': 'hakim',
        'PEMOHON': 'pemohon',
        'KUASA_HUKUM_PEMOHON': 'pemohon',
        'PEMERINTAH': 'pemerintah',
        'KUASA_HUKUM_PEMERINTAH': 'pemerintah',
        'PIHAK_TERKAIT': 'pihak_terkait',
        'AMICUS_CURIAE': 'amicus',
        'AHLI': 'ahli',
    }
    return mapping.get(role, 'general')


def parse_speakers_from_text(text: str) -> List[Dict]:
    """
    Parse teks risalah untuk mengekstrak dialog per pembicara.
    Returns list of {speaker, role, name, timestamp, content}.
    """
    lines = text.split('\n')
    dialogs = []
    current_speaker = None
    current_content = []
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
            
        # Skip header/metadata lines
        if HEADER_PATTERN.search(line_stripped):
            continue
            
        # Cek apakah ini baris pembicara baru
        match = SPEAKER_PATTERN.match(line_stripped)
        if match:
            # Simpan dialog sebelumnya
            if current_speaker and current_content:
                content = '\n'.join(current_content).strip()
                if len(content.split()) >= 5:  # Minimal 5 kata
                    current_speaker['content'] = content
                    dialogs.append(current_speaker)
            
            # Mulai pembicara baru
            nomor = match.group(1)
            raw_role = match.group(2)
            name = match.group(3).strip()
            timestamp = match.group(4)
            
            role = classify_role(raw_role)
            
            current_speaker = {
                'nomor': int(nomor),
                'role': role,
                'raw_role': raw_role.strip(),
                'name': name,
                'timestamp': timestamp,
                'content': ''
            }
            current_content = []
        elif current_speaker:
            # Lanjutan dialog dari pembicara sebelumnya
            current_content.append(line_stripped)
    
    # Simpan dialog terakhir
    if current_speaker and current_content:
        content = '\n'.join(current_content).strip()
        if len(content.split()) >= 5:
            current_speaker['content'] = content
            dialogs.append(current_speaker)
    
    return dialogs


def group_chunks_by_session(chunks: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Group risalah chunks berdasarkan sesi sidang (sumber file).
    Key: source_file, Value: list of chunks sorted by chunk_id.
    """
    sessions = defaultdict(list)
    for chunk in chunks:
        source = chunk['metadata'].get('source_file', 'unknown')
        sessions[source].append(chunk)
    
    # Sort per session by chunk_id
    for source in sessions:
        sessions[source].sort(key=lambda c: c['chunk_id'])
    
    return dict(sessions)


def extract_case_info(chunks: List[Dict]) -> Dict:
    """Ekstrak informasi perkara dari chunk pertama sesi."""
    full_text = ' '.join(c['text'] for c in chunks[:3])
    
    case_numbers = CASE_PATTERN.findall(full_text)
    norma_match = NORMA_PATTERN.search(full_text)
    
    info = {
        'case_numbers': case_numbers if case_numbers else [],
        'norma_uu': '',
        'norma_tahun': '',
    }
    
    if norma_match:
        info['norma_uu'] = norma_match.group(1)
        info['norma_tahun'] = norma_match.group(2)
    
    return info


def build_conversation_pairs(
    dialogs: List[Dict],
    case_info: Dict,
    window_size: int = 5,
) -> List[Dict]:
    """
    Bangun conversation pairs dari sequence dialog.
    
    Setiap pair:
    - system: persona pembicara target
    - user: konteks (case info + N dialog sebelumnya sebagai history)
    - assistant: respons aktual dari pembicara target
    
    window_size: berapa dialog sebelumnya yang dijadikan konteks.
    """
    pairs = []
    
    # Build case context string
    case_context = ""
    if case_info['case_numbers']:
        case_context += f"Perkara Nomor {', '.join(case_info['case_numbers'])}. "
    if case_info['norma_uu']:
        case_context += f"Pengujian UU Nomor {case_info['norma_uu']} Tahun {case_info['norma_tahun']}. "
    
    for i, dialog in enumerate(dialogs):
        role = dialog['role']
        persona = role_to_persona(role)
        
        # Skip role yang tidak relevan untuk training
        if persona == 'general':
            continue
        
        # Bangun konteks dari dialog sebelumnya
        context_dialogs = dialogs[max(0, i - window_size):i]
        
        history_lines = []
        for ctx in context_dialogs:
            history_lines.append(f"[{ctx['role']}: {ctx['name']}]\n{ctx['content']}")
        
        history_text = '\n\n'.join(history_lines) if history_lines else '(Sidang baru dimulai)'
        
        # Build user message
        user_message = f"KONTEKS SIDANG MK:\n{case_context}\n\nRIWAYAT DIALOG:\n{history_text}\n\nBerdasarkan riwayat dialog di atas, berikan respons sebagai {dialog['role'].replace('_', ' ').title()} ({dialog['name']}) sesuai dengan tata bahasa sidang Mahkamah Konstitusi yang natural."
        
        # Build assistant response (ground truth dari risalah)
        assistant_response = dialog['content']
        
        # Filter: minimal 10 kata untuk respons assistant
        if len(assistant_response.split()) < 10:
            continue
        
        pairs.append({
            'persona': persona,
            'role': dialog['role'],
            'speaker_name': dialog['name'],
            'turn_number': dialog['nomor'],
            'user': user_message,
            'assistant': assistant_response,
            'case_numbers': case_info['case_numbers'],
            'word_count': len(assistant_response.split()),
        })
    
    return pairs


def process_all_risalah(
    chunks_path: Path = RAG_CHUNKS_PATH,
    max_sessions: int = None,
) -> List[Dict]:
    """
    Proses semua risalah chunks dan hasilkan training pairs.
    
    Returns list of conversation pairs siap untuk format_chatml.py.
    """
    print(f"Loading chunks from {chunks_path}...")
    
    # Load hanya risalah chunks
    risalah_chunks = []
    with open(chunks_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 100000 == 0:
                print(f"  Loading line {line_num:,}...")
            chunk = json.loads(line)
            if chunk['metadata'].get('jenis_dokumen') == 'risalah':
                risalah_chunks.append(chunk)
    
    print(f"Loaded {len(risalah_chunks):,} risalah chunks.")
    
    # Group by session
    sessions = group_chunks_by_session(risalah_chunks)
    print(f"Found {len(sessions)} sidang sessions.")
    
    if max_sessions:
        sessions = dict(list(sessions.items())[:max_sessions])
        print(f"Limited to {max_sessions} sessions.")
    
    # Process each session
    all_pairs = []
    sessions_processed = 0
    sessions_skipped = 0
    
    for source_file, chunks in sessions.items():
        # Gabungkan semua text dalam sesi
        full_text = '\n'.join(c['text'] for c in chunks)
        
        # Parse dialogs
        dialogs = parse_speakers_from_text(full_text)
        
        if len(dialogs) < 3:  # Terlalu sedikit dialog
            sessions_skipped += 1
            continue
        
        # Extract case info
        case_info = extract_case_info(chunks)
        
        # Build conversation pairs
        pairs = build_conversation_pairs(dialogs, case_info)
        all_pairs.extend(pairs)
        
        sessions_processed += 1
        if sessions_processed % 50 == 0:
            print(f"  Processed {sessions_processed} sessions, {len(all_pairs):,} pairs so far...")
    
    print(f"\nDone!")
    print(f"  Sessions processed: {sessions_processed}")
    print(f"  Sessions skipped: {sessions_skipped}")
    print(f"  Total training pairs: {len(all_pairs):,}")
    
    # Stats per role
    role_counts = {}
    for p in all_pairs:
        r = p['role']
        role_counts[r] = role_counts.get(r, 0) + 1
    print(f"\n  Distribution by role:")
    for role, count in sorted(role_counts.items(), key=lambda x: -x[1]):
        print(f"    {role}: {count:,}")
    
    return all_pairs


def save_pairs(pairs: List[Dict], output_path: Path):
    """Simpan pairs ke JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + '\n')
    print(f"Saved {len(pairs):,} pairs to {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract risalah dialogs into training pairs")
    parser.add_argument("--chunks-path", type=Path, default=RAG_CHUNKS_PATH,
                        help="Path to rag_chunks.jsonl")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output JSONL path (default: data/risalah_pairs.jsonl)")
    parser.add_argument("--max-sessions", type=int, default=None,
                        help="Max sessions to process (for testing)")
    args = parser.parse_args()
    
    ensure_dirs()
    
    output_path = args.output or (Path(__file__).parent / "data" / "risalah_pairs.jsonl")
    
    pairs = process_all_risalah(
        chunks_path=args.chunks_path,
        max_sessions=args.max_sessions,
    )
    
    save_pairs(pairs, output_path)