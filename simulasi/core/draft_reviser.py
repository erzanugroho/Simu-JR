"""
Draft Reviser Module
====================
Modul untuk merevisi draft permohonan berdasarkan hasil simulasi sidang.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .agents import JudicialReviewDraftAgent

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).parent.parent / "rag" / "prompts"
DRAFT_REVISER_PROMPT = ""
if (PROMPT_DIR / "draft_reviser.txt").exists():
    DRAFT_REVISER_PROMPT = (PROMPT_DIR / "draft_reviser.txt").read_text(encoding="utf-8")


def _build_reviser_prompt(
    draft: str,
    transcript: List[Dict[str, str]],
    feedback: Dict[str, Any],
    scores: Dict[str, Any],
    loop_iteration: int = 1,
    external_context: str = ""
) -> str:
    """Bangun prompt lengkap untuk reviser."""

    # Ringkasan transcript (ambil 10 entry terakhir, truncate per entry untuk hemat token)
    transcript_summary = []
    for entry in transcript[-10:]:
        speaker = entry.get("speaker", "")
        content = entry.get("content", "")[:200]
        transcript_summary.append(f"[{entry.get('round', '')}] {speaker}: {content}")
    transcript_text = "\n".join(transcript_summary)

    # Scoring info
    scoring_info = json.dumps(scores, ensure_ascii=False, indent=2) if scores else "Tidak tersedia"

    # Feedback info
    feedback_info = json.dumps(feedback, ensure_ascii=False, indent=2) if feedback else "Tidak tersedia"

    return (
        f"{DRAFT_REVISER_PROMPT}\n\n"
        f"=== ITERASI REVISI KE-{loop_iteration} ===\n\n"
        f"=== DRAFT SAAT INI ===\n{draft}\n\n"
        f"=== TRANSCRIPT SIMULASI ===\n{transcript_text}\n\n"
        f"=== FEEDBACK HAKIM ===\n{feedback_info}\n\n"
        f"=== SCORING RPH ===\n{scoring_info}\n\n"
        f"=== KONTEKS RISALAH & SERANGAN PEMERINTAH/DPR TERKAIT ===\n{external_context or 'Tidak tersedia'}\n\n"
        f"Susun draft revisi berdasarkan skor terendah, amar, catatan hakim, dan rekomendasi di atas. "
        f"Gunakan risalah perkara lain yang isu/normanya mirip untuk menemukan pola pertanyaan, posisi Pemerintah/DPR/Kementerian, "
        f"dan kelemahan argumentasi negara. Balikkan/antisipasi argumen Pemerintah/DPR/Kementerian tersebut sebagai dalil Pemohon, "
        f"tanpa mengarang kutipan atau nomor perkara. Kembalikan HANYA JSON valid sesuai skema prompt. "
        f"Pastikan `draft_revisi` adalah naskah permohonan lengkap, bukan ringkasan."
    )


def _extract_balanced_json(raw: str) -> Optional[Dict[str, Any]]:
    """Ekstrak object JSON pertama secara lebih aman dari respons LLM."""
    if not raw:
        return None

    cleaned = raw.strip()
    # Hapus markdown fence jika model tetap membungkus JSON.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find('{')
    if start == -1:
        return None

    brace_count = 0
    in_string = False
    escape = False
    for i, ch in enumerate(cleaned[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                return json.loads(cleaned[start:i + 1])
    return None


async def revise_draft(
    draft: str,
    transcript: List[Dict[str, str]],
    feedback: Dict[str, Any],
    scores: Dict[str, Any],
    llm_config: Dict[str, Any] = None,
    loop_iteration: int = 1,
    external_context: str = ""
) -> Dict[str, Any]:
    """
    Revisi draft permohonan berdasarkan hasil simulasi.

    Returns:
        Dict dengan keys: draft_revisi, ringkasan_perubahan, alasan_perubahan, aspek_diperbaiki
    """
    if not DRAFT_REVISER_PROMPT:
        logger.error("Prompt reviser tidak tersedia.")
        return {"error": "Prompt reviser tidak tersedia"}

    agent = JudicialReviewDraftAgent(llm_config=llm_config or {})
    prompt = _build_reviser_prompt(draft, transcript, feedback, scores, loop_iteration, external_context)

    try:
        raw = await agent.generate_response(prompt)

        result = _extract_balanced_json(raw)
        if isinstance(result, dict):
            draft_revisi = str(result.get("draft_revisi", "")).strip()
            if not draft_revisi:
                return {
                    "error": "JSON reviser tidak berisi draft_revisi",
                    "raw": raw[:500]
                }
            result["draft_revisi"] = draft_revisi
            result.setdefault("ringkasan_perubahan", [])
            result.setdefault("alasan_perubahan", [])
            result.setdefault("aspek_diperbaiki", {})
            logger.info(f"Draft revisi berhasil dibuat (iterasi {loop_iteration})")
            return result

        logger.warning("Tidak ditemukan JSON dalam respons reviser.")
        return {
            "error": "Format JSON tidak ditemukan",
            "raw": raw[:500]
        }
    except Exception as e:
        logger.error(f"Gagal merevisi draft: {e}")
        return {"error": f"Gagal merevisi draft: {str(e)}"}


def is_draft_accepted(scores: Dict[str, Any], threshold: int = 70) -> bool:
    """
    Tentukan apakah draft diterima berdasarkan skor.

    Args:
        scores: Dict hasil scoring dari RPH
        threshold: Skor minimum total untuk dianggap diterima (default 70)

    Returns:
        True jika amar = 'dikabulkan' atau total skor >= threshold
    """
    if not scores or scores.get("error"):
        return False

    amar = str(scores.get("amar", "")).strip().lower()
    total = scores.get("total", 0)

    # Diterima jika amar dikabulkan ATAU skor total tinggi
    if amar == "dikabulkan":
        return True
    if isinstance(total, (int, float)) and total >= threshold:
        return True

    return False
