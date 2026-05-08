import fitz  # PyMuPDF
from docx import Document
import os
import re
import logging

logger = logging.getLogger(__name__)


def extract_text_from_file(file_path: str, filename: str) -> str:
    """Extract text from PDF, DOCX, TXT, or MD files."""
    try:
        ext = os.path.splitext(filename)[1].lower()
        
        if ext == '.pdf':
            text = ""
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
            return text
        
        elif ext in ['.docx', '.doc']:
            doc = Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        
        elif ext in ['.txt', '.md']:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
    except Exception as e:
        print(f"Extraction error for {filename}: {e}")
        return ""
    
    return ""


# ============================================================
# Consolidated CoT / Thinking Stripper
# ============================================================
# Unified implementation replaces duplicates in:
#   - agents.py        → BaseAgent._strip_thinking_process()
#   - orchestrator.py  → clean_transcript_content()
#   - pdf_generator.py → _clean_cot()
# ============================================================

# Thinking keywords used for header-based block removal
_THINKING_KEYWORDS = [
    "Analyze the Request", "Identify the Core Legal Issue", "Formulate Questions",
    "Drafting the Response", "Refining based on Constraints", "Output Plan",
    "UUD Text Verification", "Internal Analysis", "Thinking", "Plan:",
    "Step 1:", "Step 2:", "Step 3:", "Step 4:", "Step 5:",
    "1. Analyze", "2. Identify", "3. Formulate", "4. Draft", "5. Refine",
    "Proses Berpikir", "Analisis Internal", "Rencana Jawaban",
    "Check against Constraints", "Draft Construction", "Mental Refinement",
    "Identify Missing", "Self-Correction/Verification", "Survive Pattern Mapping",
]

# Formal openings used for hard cutoff (aggressive mode)
_FORMAL_OPENINGS = [
    "Hadirin", "Majelis", "Saudara", "Sidang", "Terima kasih", "Berdasarkan",
    "Yang terhormat", "Yang Terhormat", "Dengan hormat", "Sebagai", "Mohon", "Baik",
]


def strip_cot(text: str, *, aggressive: bool = False) -> str:
    """
    Hapus chain-of-thought, thinking tags, self-correction notes, dan JSON leak
    dari output LLM.

    Args:
        text: Teks LLM yang akan dibersihkan.
        aggressive: Jika True, aktifkan formal-opening hard cutoff
                    (untuk membersihkan respons agent sebelum masuk memory).

    Returns:
        Teks yang sudah dibersihkan.
    """
    if not text:
        return text

    original_len = len(text)

    # ── 0. Envelope pattern: [THINK]...[/THINK] ──
    text = re.sub(r'\[THINK\].*?\[/THINK\]', '', text, flags=re.DOTALL | re.IGNORECASE)
    if aggressive:
        # Aggressive: hapus [THINK] tanpa penutup sampai sapaan formal
        text = re.sub(
            r'\[THINK\][\s\S]*?(?=(?:Hadirin|Majelis|Saudara|Sidang|Terima kasih|Berdasarkan|Yang [Tt]erhormat))',
            '', text, flags=re.IGNORECASE,
        )
    else:
        # Conservative: hapus [THINK] tanpa penutup sampai akhir
        text = re.sub(r'\[THINK\][\s\S]*', '', text, flags=re.IGNORECASE)

    # ── 1. XML-style thinking tags (DeepSeek, Qwen, QwQ) ──
    text = re.sub(
        r'<\s*(?:think|thinking|thought|reasoning)\s*>'
        r'([\s\S]*?)'
        r'<\s*/\s*(?:think|thinking|thought|reasoning)\s*>',
        '', text, flags=re.IGNORECASE,
    )
    # Unclosed opening tag
    text = re.sub(
        r'[\s\S]*?<\s*/\s*(?:think|thinking|thought|reasoning)\s*>',
        '', text, flags=re.IGNORECASE,
    )

    # ── 2. Markdown code block thinking ──
    text = re.sub(r'```\s*(?:think|thinking|thought|reasoning).*?```', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'```\s*(?:think|thinking|thought|reasoning)[\s\S]*', '', text, flags=re.IGNORECASE)

    # ── 3. JSON blocks (scoring / feedback leak) — ONLY in non-aggressive (display) mode ──
    # In aggressive mode (agent response processing), we must preserve JSON
    # because it may be the actual response (e.g., RPH scoring, feedback).
    if not aggressive:
        text = re.sub(
            r'\{[^{}]*"(?:legal_standing|kerugian|substansi|amar|catatan|score)"[^{}]*\}',
            '', text, flags=re.DOTALL,
        )

    # ── 4. Generic code blocks ──
    text = re.sub(r'```[\s\S]*?```', '', text)

    # ── 5. "Here's a thinking process" patterns ──
    text = re.sub(r"(?i)here'?s\s+a?\s*(?:thinking|thought|reasoning)\s*(?:process|analysis)?:.*?\n\n", '\n\n', text, flags=re.DOTALL)
    text = re.sub(r"(?i)(?:thinking|thought|reasoning)\s*(?:process|analysis)?:.*?\n\n", '\n\n', text, flags=re.DOTALL)

    # ── 6. Header-based thinking blocks ──
    for kw in _THINKING_KEYWORDS:
        pattern = rf"(?i)\**{re.escape(kw)}.*?\n\n"
        text = re.sub(pattern, '\n\n', text, flags=re.DOTALL)

    # ── 7. Leading thinking markers ──
    text = re.sub(
        r"^(Thinking|Thought|Reasoning|Analisis|Analisa|Proses Berpikir|Planning|Rencana):.*?\n+",
        '', text, flags=re.IGNORECASE,
    )

    # ── 8. Qwen/DeepSeek reasoning format ──
    text = re.sub(
        r"(?i)^(Wait[,\.]?\s+|Let me think[\.\s]+|Hmm[,\.]?\s+|Okay[,\.]?\s+(?:so|let me|I need to)\s+).*?(?:\n\n|\Z)",
        '', text, flags=re.DOTALL,
    )

    # ── 9. Numbered checklist thinking that leaks through ──
    text = re.sub(
        r'^\d+\.\s*\*\*(?:Self-Correction|Check against|Draft|Mental Refinement|Analyze|Identify|Formulate).*?\n\n',
        '\n\n', text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r'^\*\*\d+\.\s*\*\*(?:Self-Correction|Check against).*?\n\n',
        '\n\n', text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    # Inline notes in parentheses
    text = re.sub(r'\(Note:[^)]{0,300}\)', '', text, flags=re.IGNORECASE)

    # ── 10. Trailing removal: self-correction, constraints, planning ──
    trailing_patterns = [
        r'\d+\.\s*\*\*Self-Correction.*$',
        r'\*\*Self-Correction/Verification.*$',
        r'-\s*\*\*Self-Correction.*$',
        r'Self-Correction/Verification against Constraints:.*$',
        r'\*\*Self-Correction/Verification during thought.*$',
        r'\d+\.\s*\*\*Check against Constraints.*$',
        r'\*\*Check against Constraints.*$',
        r'-\s*Check against Constraints.*$',
        r'5\.\s+\*\*Check against Constraints:.*$',
        r'\d+\.\s*\*\*Draft (?:Generation|Response|Construction).*$',
        r'\*\*Draft (?:Generation|Response|Construction).*$',
        r'\d+\.\s*\*\*Mental Refinement.*$',
        r'\*\*Mental Refinement.*$',
        r'\d+\.\s*\*\*Analyze User Input:.*$',
        r'\*\*Analyze User Input:.*$',
        r'Analyze User Input:.*$',
        r'\d+\.\s*\*\*Deconstruct.*$',
        r'\*\*Deconstruct Requirements.*$',
        r'Deconstruct (?:the |Requirements).*?$',
        r'\d+\.\s*\*\*Identify Core Legal Issues:.*$',
        r'\*\*Identify Core Legal Issues:.*$',
        r'\*\*Identify Missing.*$',
        r'\d+\.\s*\*\*(?:Internal|Verification|Forbidden).*$',
        r'\*\*(?:Internal|Verification).*$',
        r'(?:NO |FORBIDDEN (?:to )?)internal.*$',
        r'\*\*Constraints?\*\*.*$',
        r'-\s*\*\*Constraints?\*\*.*$',
        r'Proses Berpikir.*$',
    ]
    for pat in trailing_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE | re.DOTALL)

    # ── 11. Line-by-line removal: planning notes, internal reasoning ──
    line_patterns = [
        r'^\s*(?:-\s*)?(?:\*\*)?Address Q\d+.*$',
        r'^\s*(?:-\s*)?\*\*(?:Conclude|Maintain|Ensure|Start|Apply|Cite|Explain|Link|Attack|Emphasize)\b.*$',
        r'^\s*-\s*\*Point \d+:.*$',
        r'^\s*-\s*\*(?:Role|Task|5 Conditions|Pattern|No internal|Survive|UUD Citations|Precedents|Closing|Direct start|Numbered list|Specific parts|Progressive judge|Question|Mapping|Start|Expertise)\b.*$',
        r'^\s*-\s*\*Start:?\*.*$',
        r'^\s*-\s*\*Mapping:?\*.*$',
        r'^\s*.*\bI need to (?:pick|choose|decide|select|find)\b.*$',
        r"^\s*.*\b(?:Let's go with|Let's stick to|Actually,)\b.*$",
        r'^\s*.*\b(?:mk_attack_bank|survive_bank|bank \d)\b.*$',
        r'^\s*(?:NO |FORBIDDEN ).*$',
        r'^\s*-\s*\*\*Role:\*\*.*$',
        r'^\s*-\s*\*\*Task:\*\*.*$',
        r'^\s*-\s*\*\*Expertise Required:\*\*.*$',
        r'^\d+\.\s+\*\*(?:Check|Draft|Self-Correction|Mental|Analyze|Identify|Formulate)\b.*$',
        r'^\s*\(Note:.*$',
        r'^\s*\*\*Constraints?\*\*\s*$',
        r'^\s*Survive Pattern Mapping.*$',
    ]
    for pat in line_patterns:
        text = re.sub(pat, '', text, flags=re.MULTILINE)

    # ── 12. Formal opening hard cutoff (aggressive mode only) ──
    if aggressive:
        for opening in _FORMAL_OPENINGS:
            if opening in text:
                idx = text.find(opening)
                if idx > 2:
                    potential_trash = text[:idx].strip()
                    if len(potential_trash) > 100 or (len(text) > 0 and len(potential_trash) / len(text) > 0.3):
                        logger.debug(f"Hard cutoff at '{opening}': discarded {len(potential_trash)} chars ({len(potential_trash)*100//(len(text)+1)}%)")
                        text = text[idx:]
                    elif len(potential_trash) > 15:
                        text = text[idx:]
                break

    # ── 13. Whitespace cleanup ──
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'^[\s\n]+', '', text)

    if original_len != len(text):
        logger.debug(f"strip_cot(aggressive={aggressive}): {original_len} -> {len(text)} chars")

    return text.strip()
