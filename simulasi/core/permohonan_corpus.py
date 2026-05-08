"""
Permohonan Corpus Analyzer
==========================
Index and summarize local MK petition PDFs for the draft-permohonan feature.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import fitz

from .runtime_paths import runtime_dir
from .pmk_compliance import (
    PMK_COMPLIANCE_FILENAME,
    evaluate_pmk_input_gaps,
    load_pmk_compliance,
    write_pmk_compliance_artifact,
)


SIMULASI_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = SIMULASI_DIR.parent
DEFAULT_CORPUS_DIR = Path(os.getenv("PERMOHONAN_CORPUS_DIR", str(WORKSPACE_DIR / "permohonan_pdf")))
DEFAULT_OUTPUT_DIR = runtime_dir("permohonan_corpus")
DEFAULT_OCR_CACHE_DIR = DEFAULT_OUTPUT_DIR / "ocr_text"
DEFAULT_TESSDATA_DIR = SIMULASI_DIR / "ocr_tessdata"

ARTIFACT_FILENAMES = {
    "corpus_index": "corpus_index.json",
    "document_metadata": "document_metadata.jsonl",
    "revision_pairs": "revision_pairs.json",
    "format_patterns": "format_patterns.json",
    "golden_template": "golden_template.json",
    "common_improvements": "common_improvements.json",
    "drafting_guidelines": "drafting_guidelines.json",
    "pmk_compliance": PMK_COMPLIANCE_FILENAME,
}
PROGRESS_FILENAME = "corpus_index_progress.json"

SECTION_PATTERNS: Dict[str, List[str]] = {
    "judul": [
        r"permohonan\s+pengujian",
        r"perihal\s*:\s*permohonan",
    ],
    "identitas_pemohon": [
        r"identitas\s+pemohon",
        r"para\s+pemohon",
        r"pemohon\s+(?:adalah|dengan\s+ini)",
    ],
    "kuasa_hukum": [
        r"kuasa\s+hukum",
        r"berdasarkan\s+surat\s+kuasa",
    ],
    "kewenangan_mahkamah": [
        r"kewenangan\s+mahkamah",
        r"kewenangan\s+mahkamah\s+konstitusi",
    ],
    "kedudukan_hukum": [
        r"kedudukan\s+hukum",
        r"legal\s+standing",
    ],
    "objek_pengujian": [
        r"objek\s+pengujian",
        r"norma\s+yang\s+diuji",
        r"pasal\s+yang\s+diuji",
    ],
    "batu_uji": [
        r"batu\s+uji",
        r"dasar\s+pengujian",
        r"u[uú]d\s+1945",
        r"undang-undang\s+dasar\s+1945",
    ],
    "kerugian_konstitusional": [
        r"kerugian\s+konstitusional",
        r"hak\s+konstitusional",
        r"constitutional\s+injury",
    ],
    "posita": [
        r"alasan[-\s]alasan\s+permohonan",
        r"alasan\s+permohonan",
        r"posita",
        r"pokok\s+permohonan",
    ],
    "petitum": [
        r"petitum",
        r"dalam\s+provisi",
        r"mengadili",
    ],
    "daftar_bukti": [
        r"daftar\s+bukti",
        r"alat\s+bukti",
        r"bukti\s+p-",
    ],
}

STRUCTURE_ORDER = [
    "Judul Permohonan",
    "Kepada Yth. Mahkamah Konstitusi",
    "Identitas Pemohon dan/atau Kuasa Hukum",
    "Kewenangan Mahkamah Konstitusi",
    "Kedudukan Hukum Pemohon",
    "Objek Pengujian dan Batu Uji",
    "Alasan-Alasan Permohonan / Posita",
    "Petitum",
    "Daftar Bukti",
    "Penutup",
]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return value


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    tmp.replace(path)


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=_json_default))
            fh.write("\n")
    tmp.replace(path)


def normalize_text(text: str) -> str:
    """Normalize extraction artifacts while preserving legal text shape."""
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = text.replace("\u2028", "\n").replace("\u2029", "\n").replace("\x85", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?m)^\s*\d+\s*$", "", text)
    return text.strip()


def extract_case_key(filename: str) -> Optional[str]:
    """Extract stable MK family id from filenames like *_4334_8439_*.pdf."""
    name = Path(filename).stem
    match = re.search(r"(\d{3,6})[_\s-]+(\d{3,6})", name)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{2,4})\b", name)
    if match:
        return match.group(1)
    return None


def classify_document(filename: str, text: str = "", relative_path: str = "") -> str:
    """Classify petition document from path/name first, then content signals."""
    haystack = f"{relative_path} {filename} {text[:4000]}".lower()
    if "permohonan_lainnya" in haystack:
        return "tidak_pasti"
    if "perbaikan_permohonan" in haystack:
        return "perbaikan"
    if any(token in haystack for token in ["gabungan", "combined", "permohonan dan perbaikan"]):
        return "gabungan"
    if "perbaikan" in haystack or "revisi permohonan" in haystack:
        return "perbaikan"
    if "diregistrasi" in haystack or "di registrasi" in haystack:
        return "permohonan_awal"
    if "permohonan" in haystack and any(token in haystack for token in ["pengujian", "mahkamah konstitusi"]):
        return "permohonan_awal"
    return "tidak_pasti"


def detect_sections(text: str) -> Dict[str, Dict[str, Any]]:
    lowered = text.lower()
    result: Dict[str, Dict[str, Any]] = {}
    for section, patterns in SECTION_PATTERNS.items():
        hits: List[str] = []
        first_pos: Optional[int] = None
        for pattern in patterns:
            match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if match:
                hits.append(match.group(0)[:120])
                if first_pos is None or match.start() < first_pos:
                    first_pos = match.start()
        result[section] = {
            "present": bool(hits),
            "first_position": first_pos,
            "variants": hits[:5],
        }
    return result


def score_document(sections: Dict[str, Dict[str, Any]], text: str) -> Dict[str, int]:
    lowered = text.lower()
    section_count = sum(1 for info in sections.values() if info.get("present"))
    structure_score = round(section_count / max(1, len(SECTION_PATTERNS)) * 100)

    legal_standing_terms = [
        "hak konstitusional",
        "kerugian konstitusional",
        "hubungan sebab akibat",
        "kausal",
        "kedudukan hukum",
        "legal standing",
    ]
    legal_standing = min(100, sum(18 for term in legal_standing_terms if term in lowered))

    norm_chain_terms = ["pasal", "uud 1945", "bertentangan", "kerugian", "petitum"]
    norm_chain = min(100, sum(20 for term in norm_chain_terms if term in lowered))

    petitum_terms = ["mengabulkan", "menyatakan", "bertentangan", "tidak mempunyai kekuatan hukum mengikat"]
    petitum = 0
    if sections.get("petitum", {}).get("present"):
        petitum = 35 + min(65, sum(16 for term in petitum_terms if term in lowered))

    legal_language_terms = ["dengan hormat", "berdasarkan", "bahwa", "oleh karena itu", "mahkamah"]
    language = min(100, sum(18 for term in legal_language_terms if term in lowered))

    return {
        "struktur": structure_score,
        "legal_standing": legal_standing,
        "norma_kerugian_petitum": norm_chain,
        "petitum": min(100, petitum),
        "kebahasaan_hukum": language,
    }


def _find_tesseract() -> Optional[str]:
    configured = os.getenv("TESSERACT_CMD", "").strip()
    candidates = [
        configured,
        shutil.which("tesseract") or "",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _tessdata_dir() -> Optional[Path]:
    configured = os.getenv("PERMOHONAN_TESSDATA_DIR", "").strip()
    candidates = [
        Path(configured) if configured else None,
        DEFAULT_TESSDATA_DIR,
        Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tessdata"),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None


def _available_ocr_langs(tessdata_dir: Optional[Path]) -> List[str]:
    desired = os.getenv("PERMOHONAN_OCR_LANG", "ind+eng").split("+")
    if not tessdata_dir:
        return ["eng"]
    available = {path.stem for path in tessdata_dir.glob("*.traineddata")}
    selected = [lang for lang in desired if lang in available]
    if selected:
        return selected
    if "eng" in available:
        return ["eng"]
    return sorted(available)[:1] or ["eng"]


def _ocr_pdf_pages(path: Path, cache_path: Path) -> Tuple[str, Dict[str, Any]]:
    tesseract = _find_tesseract()
    if not tesseract:
        return "", {"status": "unavailable", "error": "tesseract executable not found", "chars": 0, "pages": 0}

    if cache_path.exists():
        cached = normalize_text(cache_path.read_text(encoding="utf-8", errors="ignore"))
        return cached, {"status": "cached", "chars": len(cached), "pages": None}

    tessdata_dir = _tessdata_dir()
    lang_arg = "+".join(_available_ocr_langs(tessdata_dir))
    dpi = int(os.getenv("PERMOHONAN_OCR_DPI", "180"))
    max_pages = int(os.getenv("PERMOHONAN_OCR_MAX_PAGES", "0") or "0")
    timeout_seconds = int(os.getenv("PERMOHONAN_OCR_PAGE_TIMEOUT", "120"))

    ocr_parts: List[str] = []
    processed_pages = 0
    errors: List[str] = []

    try:
        with fitz.open(path) as doc:
            page_limit = min(doc.page_count, max_pages) if max_pages > 0 else doc.page_count
            with tempfile.TemporaryDirectory(prefix="permohonan_ocr_") as tmp_dir:
                tmp_path = Path(tmp_dir)
                for page_index in range(page_limit):
                    page = doc.load_page(page_index)
                    pix = page.get_pixmap(dpi=dpi, alpha=False)
                    image_path = tmp_path / f"page_{page_index + 1}.png"
                    pix.save(image_path)

                    command = [
                        tesseract,
                        str(image_path),
                        "stdout",
                        "-l",
                        lang_arg,
                        "--psm",
                        os.getenv("PERMOHONAN_OCR_PSM", "6"),
                    ]
                    if tessdata_dir:
                        command.extend(["--tessdata-dir", str(tessdata_dir)])

                    try:
                        proc = subprocess.run(
                            command,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=timeout_seconds,
                        )
                        if proc.returncode == 0:
                            ocr_parts.append(proc.stdout)
                            processed_pages += 1
                        else:
                            errors.append(proc.stderr.strip()[:300] or f"page {page_index + 1} failed")
                    except subprocess.TimeoutExpired:
                        errors.append(f"page {page_index + 1} timeout")
    except Exception as exc:
        return "", {"status": "failed", "error": str(exc), "chars": 0, "pages": processed_pages}

    text = normalize_text("\n\n".join(ocr_parts))
    if text:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")

    return text, {
        "status": "success" if text else "failed",
        "chars": len(text),
        "pages": processed_pages,
        "languages": lang_arg,
        "errors": errors[:5],
    }


def _extract_pdf_text(path: Path) -> Tuple[str, int, Optional[str]]:
    try:
        text_parts: List[str] = []
        with fitz.open(path) as doc:
            page_count = doc.page_count
            for page in doc:
                text_parts.append(page.get_text("text") or "")
        return normalize_text("\n".join(text_parts)), page_count, None
    except Exception as exc:
        return "", 0, str(exc)


def _doc_id(path: Path) -> str:
    digest = hashlib.sha1(str(path).lower().encode("utf-8", errors="ignore")).hexdigest()
    return digest[:12]


def analyze_document(
    path: Path,
    corpus_dir: Path,
    use_ocr: bool = False,
    ocr_cache_dir: Path = DEFAULT_OCR_CACHE_DIR,
) -> Dict[str, Any]:
    relative = str(path.relative_to(corpus_dir)).replace("\\", "/")
    text, page_count, error = _extract_pdf_text(path)
    stat = path.stat()
    initial_needs_ocr = bool(not error and (len(text) < 400 or (page_count > 0 and len(text) / page_count < 80)))
    ocr_info: Dict[str, Any] = {"status": "not_attempted", "chars": 0, "pages": 0}
    if use_ocr and initial_needs_ocr:
        ocr_text, ocr_info = _ocr_pdf_pages(path, ocr_cache_dir / f"{_doc_id(path)}.txt")
        if len(ocr_text) > len(text):
            text = ocr_text

    needs_ocr = bool(not error and (len(text) < 400 or (page_count > 0 and len(text) / page_count < 80)))
    sections = detect_sections(text)
    classification = classify_document(path.name, text, relative)
    case_key = extract_case_key(path.name)

    return {
        "id": _doc_id(path),
        "filename": path.name,
        "relative_path": relative,
        "absolute_path": str(path),
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "case_key": case_key,
        "classification": classification,
        "extraction": {
            "status": "failed" if error else "extracted",
            "chars": len(text),
            "pages": page_count,
            "needs_ocr": needs_ocr,
            "initial_needs_ocr": initial_needs_ocr,
            "error": error,
        },
        "ocr": ocr_info,
        "sections": sections,
        "quality_scores": score_document(sections, text),
        "text_sample": text[:2000],
    }


def build_revision_pairs(metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in metadata:
        if item.get("case_key"):
            grouped[item["case_key"]].append(item)

    pairs: List[Dict[str, Any]] = []
    for case_key, docs in sorted(grouped.items()):
        initials = [d for d in docs if d.get("classification") == "permohonan_awal"]
        revisions = [d for d in docs if d.get("classification") == "perbaikan"]
        if not initials or not revisions:
            continue
        initial = sorted(initials, key=lambda d: d.get("modified_at", ""))[0]
        revision = sorted(revisions, key=lambda d: d.get("modified_at", ""))[-1]
        pairs.append({
            "case_key": case_key,
            "initial_document_id": initial["id"],
            "revision_document_id": revision["id"],
            "initial_file": initial["relative_path"],
            "revision_file": revision["relative_path"],
            "improvement_signals": _compare_scores(initial.get("quality_scores", {}), revision.get("quality_scores", {})),
        })
    return pairs


def _compare_scores(initial_scores: Dict[str, int], revision_scores: Dict[str, int]) -> List[Dict[str, Any]]:
    signals = []
    for key in ["struktur", "legal_standing", "norma_kerugian_petitum", "petitum", "kebahasaan_hukum"]:
        before = int(initial_scores.get(key, 0) or 0)
        after = int(revision_scores.get(key, 0) or 0)
        if after != before:
            signals.append({"area": key, "before": before, "after": after, "delta": after - before})
    return signals


def build_format_patterns(metadata: List[Dict[str, Any]], pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    classification_counts = Counter(item.get("classification", "tidak_pasti") for item in metadata)
    section_counts = Counter()
    heading_variants: Dict[str, Counter] = {key: Counter() for key in SECTION_PATTERNS}
    pages: List[int] = []
    chars: List[int] = []

    for item in metadata:
        extraction = item.get("extraction", {})
        if extraction.get("status") == "extracted":
            pages.append(int(extraction.get("pages") or 0))
            chars.append(int(extraction.get("chars") or 0))
        for section, info in item.get("sections", {}).items():
            if info.get("present"):
                section_counts[section] += 1
                for variant in info.get("variants", []):
                    heading_variants.setdefault(section, Counter())[variant.lower()] += 1

    total = max(1, len(metadata))
    return {
        "generated_at": _now_iso(),
        "classification_counts": dict(classification_counts),
        "section_presence": {
            section: {
                "count": count,
                "percentage": round((count / total) * 100, 1),
            }
            for section, count in section_counts.items()
        },
        "heading_variants": {
            section: [{"text": text, "count": count} for text, count in counter.most_common(8)]
            for section, counter in heading_variants.items()
        },
        "revision_pairs_count": len(pairs),
        "average_pages": round(sum(pages) / len(pages), 1) if pages else 0,
        "average_chars": round(sum(chars) / len(chars), 1) if chars else 0,
    }


def build_golden_template(format_patterns: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "source": "Synthesis from local permohonan corpus plus PMK-style petition structure",
        "heading_order": STRUCTURE_ORDER,
        "dominant_heading_variants": format_patterns.get("heading_variants", {}),
        "required_sections": [
            "identitas_pemohon",
            "kewenangan_mahkamah",
            "kedudukan_hukum",
            "objek_pengujian",
            "batu_uji",
            "kerugian_konstitusional",
            "posita",
            "petitum",
        ],
        "opening_pattern": (
            "Permohonan Pengujian Undang-Undang terhadap Undang-Undang Dasar Negara "
            "Republik Indonesia Tahun 1945 diajukan kepada Mahkamah Konstitusi dengan "
            "identitas Pemohon, objek norma, batu uji, dan kerugian konstitusional yang eksplisit."
        ),
        "legal_standing_pattern": [
            "Kualifikasi Pemohon",
            "Hak konstitusional yang diberikan UUD 1945",
            "Kerugian aktual atau potensial yang spesifik",
            "Hubungan kausal antara norma diuji dan kerugian",
            "Kemungkinan pemulihan jika permohonan dikabulkan",
        ],
        "petitum_pattern": [
            "Mengabulkan permohonan untuk seluruhnya atau sebagian",
            "Menyatakan norma yang diuji bertentangan dengan UUD 1945",
            "Menyatakan norma tidak mempunyai kekuatan hukum mengikat, atau konstitusional bersyarat bila diminta",
            "Memerintahkan pemuatan putusan dalam Berita Negara",
        ],
    }


def build_common_improvements(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "revision_pairs_count": len(pairs),
        "items": [
            "Legal standing dibuat lebih konkret dan mengikuti lima syarat kerugian konstitusional.",
            "Objek norma dan batu uji dipisahkan lebih tegas agar tidak bercampur dengan isu implementasi.",
            "Causal verband antara norma, hak konstitusional, kerugian, dan petitum dijelaskan dalam rantai logis.",
            "Petitum diselaraskan dengan posita dan dibuat lebih dapat dieksekusi.",
            "Dalil open legal policy, norma versus implementasi, dan petitum kabur diantisipasi sejak posita.",
            "Redaksi dipadatkan menjadi bahasa hukum formal dengan nomor butir yang konsisten.",
        ],
        "observed_score_changes": [
            signal
            for pair in pairs[:50]
            for signal in pair.get("improvement_signals", [])
            if signal.get("delta", 0) > 0
        ],
    }


def build_drafting_guidelines(format_patterns: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "must_have": [
            "Identitas Pemohon dan kuasa hukum bila ada",
            "Kewenangan Mahkamah Konstitusi",
            "Kedudukan hukum Pemohon",
            "Objek pengujian dan batu uji UUD 1945",
            "Kerugian konstitusional yang spesifik",
            "Posita yang menghubungkan norma, batu uji, kerugian, dan petitum",
            "Petitum yang spesifik dan konsisten",
        ],
        "optional_but_helpful": [
            "Kronologi singkat",
            "Daftar bukti awal",
            "Strategi khusus dan referensi perkara",
            "Argumentasi konstitusional bersyarat bila diminta",
        ],
        "avoid": [
            "Mengarang bunyi pasal, nomor putusan, atau fakta Pemohon",
            "Membuat petitum lebih luas dari posita",
            "Mencampur masalah implementasi administratif sebagai masalah norma tanpa jembatan argumentasi",
            "Memakai placeholder jika user sudah memberi objek norma",
        ],
        "frontend_form_schema": {
            "new_draft_required": [
                "jenis_pengujian",
                "nama_pemohon",
                "kategori_pemohon",
                "uu_diuji",
                "pasal_diuji",
                "batu_uji_uud",
                "kerugian_konstitusional",
            ],
            "improve_existing_required": ["uploaded_draft", "tujuan_perbaikan"],
        },
        "format_patterns_summary": {
            "revision_pairs_count": format_patterns.get("revision_pairs_count", 0),
            "classification_counts": format_patterns.get("classification_counts", {}),
        },
    }


def index_permohonan_corpus(
    corpus_dir: Path | str = DEFAULT_CORPUS_DIR,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    use_ocr: bool = False,
) -> Dict[str, Any]:
    corpus_path = Path(corpus_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(corpus_path.rglob("*.pdf")) if corpus_path.exists() else []
    progress_path = output_path / PROGRESS_FILENAME
    progress = {
        "status": "running",
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
        "corpus_dir": str(corpus_path),
        "total_files": len(pdf_files),
        "processed_files": 0,
        "extracted_files": 0,
        "failed_files": 0,
        "needs_ocr_files": 0,
        "ocr_enabled": use_ocr,
        "ocr_attempted_files": 0,
        "ocr_success_files": 0,
        "current_file": "",
    }
    _write_json(progress_path, progress)

    metadata: List[Dict[str, Any]] = []
    for index, path in enumerate(pdf_files, start=1):
        item = analyze_document(path, corpus_path, use_ocr=use_ocr, ocr_cache_dir=output_path / "ocr_text")
        metadata.append(item)
        extraction = item.get("extraction", {})
        ocr = item.get("ocr", {})
        progress.update({
            "updated_at": _now_iso(),
            "processed_files": index,
            "extracted_files": sum(1 for row in metadata if row.get("extraction", {}).get("status") == "extracted"),
            "failed_files": sum(1 for row in metadata if row.get("extraction", {}).get("status") == "failed"),
            "needs_ocr_files": sum(1 for row in metadata if row.get("extraction", {}).get("needs_ocr")),
            "ocr_attempted_files": sum(1 for row in metadata if row.get("ocr", {}).get("status") not in {"not_attempted", None}),
            "ocr_success_files": sum(1 for row in metadata if row.get("ocr", {}).get("status") in {"success", "cached"}),
            "current_file": item.get("relative_path", str(path)),
            "last_initial_needs_ocr": extraction.get("initial_needs_ocr", False),
            "last_ocr_status": ocr.get("status", "not_attempted"),
        })
        _write_json(progress_path, progress)
    pairs = build_revision_pairs(metadata)
    format_patterns = build_format_patterns(metadata, pairs)
    golden_template = build_golden_template(format_patterns)
    common_improvements = build_common_improvements(pairs)
    drafting_guidelines = build_drafting_guidelines(format_patterns)
    pmk_compliance = write_pmk_compliance_artifact(output_path)

    classification_counts = Counter(item.get("classification", "tidak_pasti") for item in metadata)
    extracted = sum(1 for item in metadata if item.get("extraction", {}).get("status") == "extracted")
    failed = sum(1 for item in metadata if item.get("extraction", {}).get("status") == "failed")
    needs_ocr = sum(1 for item in metadata if item.get("extraction", {}).get("needs_ocr"))
    ocr_attempted = sum(1 for item in metadata if item.get("ocr", {}).get("status") not in {"not_attempted", None})
    ocr_success = sum(1 for item in metadata if item.get("ocr", {}).get("status") in {"success", "cached"})

    corpus_index = {
        "status": "ready",
        "generated_at": _now_iso(),
        "corpus_dir": str(corpus_path),
        "total_files": len(pdf_files),
        "extracted_files": extracted,
        "failed_files": failed,
        "needs_ocr_files": needs_ocr,
        "ocr_enabled": use_ocr,
        "ocr_attempted_files": ocr_attempted,
        "ocr_success_files": ocr_success,
        "classification_counts": dict(classification_counts),
        "revision_pairs_count": len(pairs),
        "artifacts": ARTIFACT_FILENAMES,
    }

    _write_json(output_path / ARTIFACT_FILENAMES["corpus_index"], corpus_index)
    _write_jsonl(output_path / ARTIFACT_FILENAMES["document_metadata"], metadata)
    _write_json(output_path / ARTIFACT_FILENAMES["revision_pairs"], {"pairs": pairs})
    _write_json(output_path / ARTIFACT_FILENAMES["format_patterns"], format_patterns)
    _write_json(output_path / ARTIFACT_FILENAMES["golden_template"], golden_template)
    _write_json(output_path / ARTIFACT_FILENAMES["common_improvements"], common_improvements)
    _write_json(output_path / ARTIFACT_FILENAMES["drafting_guidelines"], drafting_guidelines)
    _write_json(output_path / ARTIFACT_FILENAMES["pmk_compliance"], pmk_compliance)
    _write_json(output_path / PROGRESS_FILENAME, {
        **progress,
        "status": "ready",
        "updated_at": _now_iso(),
        "processed_files": len(pdf_files),
        "extracted_files": extracted,
        "failed_files": failed,
        "needs_ocr_files": needs_ocr,
        "ocr_attempted_files": ocr_attempted,
        "ocr_success_files": ocr_success,
        "current_file": "",
    })

    return corpus_index


def _load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def artifact_availability(output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> Dict[str, bool]:
    output_path = Path(output_dir)
    return {key: (output_path / filename).exists() for key, filename in ARTIFACT_FILENAMES.items()}


def get_corpus_progress(output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> Dict[str, Any]:
    return _load_json(Path(output_dir) / PROGRESS_FILENAME, {})


def get_corpus_status(
    corpus_dir: Path | str = DEFAULT_CORPUS_DIR,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> Dict[str, Any]:
    corpus_path = Path(corpus_dir)
    output_path = Path(output_dir)
    index_path = output_path / ARTIFACT_FILENAMES["corpus_index"]
    availability = artifact_availability(output_path)
    if not index_path.exists():
        file_count = len(list(corpus_path.rglob("*.pdf"))) if corpus_path.exists() else 0
        return {
            "status": "not_started",
            "corpus_dir": str(corpus_path),
            "total_files": file_count,
            "extracted_files": 0,
            "failed_files": 0,
            "needs_ocr_files": 0,
            "ocr_enabled": False,
            "ocr_attempted_files": 0,
            "ocr_success_files": 0,
            "classification_counts": {},
            "revision_pairs_count": 0,
            "last_indexed_at": None,
            "artifact_availability": availability,
        }

    data = _load_json(index_path, {})
    generated_at = data.get("generated_at")
    status = "ready"
    try:
        index_mtime = index_path.stat().st_mtime
        source_mtime = max((p.stat().st_mtime for p in corpus_path.rglob("*.pdf")), default=0)
        if source_mtime > index_mtime:
            status = "stale"
    except Exception:
        status = "ready"

    return {
        "status": status,
        "corpus_dir": data.get("corpus_dir", str(corpus_path)),
        "total_files": data.get("total_files", 0),
        "extracted_files": data.get("extracted_files", 0),
        "failed_files": data.get("failed_files", 0),
        "needs_ocr_files": data.get("needs_ocr_files", 0),
        "ocr_enabled": data.get("ocr_enabled", False),
        "ocr_attempted_files": data.get("ocr_attempted_files", 0),
        "ocr_success_files": data.get("ocr_success_files", 0),
        "classification_counts": data.get("classification_counts", {}),
        "revision_pairs_count": data.get("revision_pairs_count", 0),
        "last_indexed_at": generated_at,
        "artifact_availability": availability,
    }


def load_analysis_artifacts(output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> Dict[str, Any]:
    output_path = Path(output_dir)
    revision_pairs = _load_json(output_path / ARTIFACT_FILENAMES["revision_pairs"], {"pairs": []})
    return {
        "golden_template": _load_json(output_path / ARTIFACT_FILENAMES["golden_template"], build_golden_template({})),
        "common_improvements": _load_json(output_path / ARTIFACT_FILENAMES["common_improvements"], build_common_improvements([])),
        "drafting_guidelines": _load_json(output_path / ARTIFACT_FILENAMES["drafting_guidelines"], build_drafting_guidelines({})),
        "pmk_2_2021_compliance": _load_json(
            output_path / ARTIFACT_FILENAMES["pmk_compliance"],
            load_pmk_compliance(output_path),
        ),
        "format_patterns": _load_json(output_path / ARTIFACT_FILENAMES["format_patterns"], {}),
        "revision_pairs_summary": revision_pairs.get("pairs", [])[:20],
    }


def build_drafter_handoff(
    mode: str,
    user_input: Dict[str, Any],
    uploaded_draft: Optional[Dict[str, Any]] = None,
    analysis_artifacts: Optional[Dict[str, Any]] = None,
    references: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "mode": mode,
        "user_input": user_input or {},
        "uploaded_draft": uploaded_draft or {"filename": "", "raw_text": "", "extracted_sections": {}},
        "analysis_artifacts": analysis_artifacts or load_analysis_artifacts(),
        "pmk_compliance_review": evaluate_pmk_input_gaps(mode, user_input, uploaded_draft),
        "references": references or {
            "rag_cases": [],
            "rag_risalah": [],
            "bank_data": [],
            "pasalid_norms": [],
        },
    }


def compact_for_prompt(value: Any, max_chars: int = 24000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=_json_default)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [dipotong untuk konteks prompt]"
