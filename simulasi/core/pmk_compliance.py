"""
PMK 2/2021 Compliance Layer
===========================
Structured drafting checklist for Peraturan Mahkamah Konstitusi Nomor 2
Tahun 2021 tentang Tata Beracara dalam Perkara Pengujian Undang-Undang.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import fitz
except Exception:  # pragma: no cover - PyMuPDF is available in the app runtime.
    fitz = None

from .runtime_paths import runtime_dir

SIMULASI_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = runtime_dir("permohonan_corpus")
PMK_COMPLIANCE_FILENAME = "pmk_2_2021_compliance.json"
DEFAULT_PMK_SOURCE_PDF = Path(
    os.getenv(
        "PERMOHONAN_PMK_2021_PDF",
        str(Path.home() / "Downloads" / "PMK 2 Tahun 2021.pdf"),
    )
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten(item) for item in value)
    return str(value or "")


def _normalize_source_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip().upper()


def _source_pdf_info(source_pdf: Optional[Path | str]) -> Dict[str, Any]:
    path = Path(source_pdf or DEFAULT_PMK_SOURCE_PDF)
    info: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "validated": False,
        "page_count": 0,
        "sha256": "",
        "title_excerpt": "",
        "warning": "",
    }
    if not path.exists():
        info["warning"] = "PDF sumber PMK MK 2/2021 tidak ditemukan; memakai checklist statis."
        return info

    try:
        info["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception as exc:
        info["warning"] = f"Gagal membaca hash PDF sumber: {exc}"

    if fitz is None:
        info["warning"] = "PyMuPDF tidak tersedia; validasi judul PDF dilewati."
        return info

    try:
        doc = fitz.open(path)
        info["page_count"] = doc.page_count
        title_text = "\n".join(doc.load_page(i).get_text("text") for i in range(min(4, doc.page_count)))
        normalized = _normalize_source_text(title_text)
        info["title_excerpt"] = re.sub(r"\s+", " ", title_text).strip()[:800]
        info["validated"] = all(
            token in normalized
            for token in [
                "PERATURAN MAHKAMAH KONSTITUSI",
                "NOMOR 2 TAHUN 2021",
                "PENGUJIAN UNDANG-UNDANG",
            ]
        )
        if not info["validated"]:
            info["warning"] = (
                "PDF sumber tidak terdeteksi sebagai Peraturan Mahkamah Konstitusi "
                "Nomor 2 Tahun 2021 tentang PUU; checklist statis tetap dipakai."
            )
        doc.close()
    except Exception as exc:
        info["warning"] = f"Gagal mengekstrak judul PDF sumber: {exc}"
    return info


def build_pmk_2_2021_compliance(source_pdf: Optional[Path | str] = None) -> Dict[str, Any]:
    """Build a compact, prompt-ready compliance layer for petition drafting."""
    source_info = _source_pdf_info(source_pdf)
    return {
        "artifact": "pmk_2_2021_compliance",
        "generated_at": _now_iso(),
        "regulation": {
            "name": "Peraturan Mahkamah Konstitusi Nomor 2 Tahun 2021",
            "title": "Tata Beracara dalam Perkara Pengujian Undang-Undang",
            "scope": "Permohonan pengujian undang-undang atau Perppu terhadap UUD 1945.",
        },
        "source_pdf": source_info,
        "agent_policy": {
            "priority": "mandatory_compliance_check",
            "use": [
                "Gunakan layer ini sebelum menyusun dan sebelum finalisasi draft.",
                "Jangan mengarang data administratif, bukti, tanggal, identitas, atau dokumen lampiran.",
                "Jika data PMK belum diberikan, tulis sebagai kekurangan pada CATATAN DRAFTER, bukan fakta baru.",
                "Pastikan petitum tidak melampaui posita dan dipilih sesuai jenis pengujian.",
            ],
            "final_output_requirement": (
                "CATATAN DRAFTER wajib memuat subbagian Checklist PMK 2/2021 "
                "berisi status terpenuhi/perlu data untuk syarat utama."
            ),
        },
        "core_petition_structure": [
            {
                "id": "identity",
                "basis": ["Pasal 10 ayat (2) huruf a"],
                "requirement": (
                    "Nama Pemohon dan/atau kuasa hukum, pekerjaan, kewarganegaraan, "
                    "alamat rumah/kantor, dan alamat surat elektronik."
                ),
                "draft_instruction": "Identitas harus ditulis eksplisit; data yang belum ada dicatat sebagai kekurangan.",
            },
            {
                "id": "authority",
                "basis": ["Pasal 10 ayat (2) huruf b angka 1"],
                "requirement": "Uraian jelas tentang kewenangan Mahkamah mengadili perkara PUU.",
                "draft_instruction": "Hubungkan kewenangan MK dengan objek pengujian UU/Perppu terhadap UUD 1945.",
            },
            {
                "id": "legal_standing",
                "basis": ["Pasal 10 ayat (2) huruf b angka 2", "Pasal 4"],
                "requirement": "Kedudukan hukum Pemohon dan kerugian hak/kewenangan konstitusional.",
                "draft_instruction": "Uji lima unsur kerugian konstitusional Pasal 4 ayat (2).",
            },
            {
                "id": "reasons",
                "basis": ["Pasal 10 ayat (2) huruf b angka 3"],
                "requirement": (
                    "Alasan permohonan untuk pengujian formil dan/atau materiil, "
                    "termasuk hubungan norma yang diuji dengan UUD 1945."
                ),
                "draft_instruction": "Pisahkan argumentasi formil dan materiil jika jenis pengujian campuran.",
            },
            {
                "id": "petitum",
                "basis": ["Pasal 10 ayat (2) huruf c", "Pasal 10 ayat (2) huruf d"],
                "requirement": "Petitum sesuai jenis pengujian dan konsisten dengan posita.",
                "draft_instruction": "Pilih model petitum formil atau materiil; jangan memperluas objek dari posita.",
            },
        ],
        "legal_standing_tests": [
            {
                "id": "constitutional_right",
                "basis": ["Pasal 4 ayat (2) huruf a"],
                "question": "Hak/kewenangan konstitusional apa yang diberikan UUD 1945 kepada Pemohon?",
            },
            {
                "id": "impaired_by_norm",
                "basis": ["Pasal 4 ayat (2) huruf b"],
                "question": "Bagaimana hak/kewenangan itu dirugikan oleh UU/Perppu yang diuji?",
            },
            {
                "id": "specific_actual_or_potential",
                "basis": ["Pasal 4 ayat (2) huruf c"],
                "question": "Apakah kerugian spesifik, aktual, atau setidaknya potensial menurut penalaran wajar?",
            },
            {
                "id": "causal_link",
                "basis": ["Pasal 4 ayat (2) huruf d"],
                "question": "Apa hubungan sebab-akibat antara norma yang diuji dan kerugian Pemohon?",
            },
            {
                "id": "redressability",
                "basis": ["Pasal 4 ayat (2) huruf e"],
                "question": "Apakah kerugian tidak lagi atau tidak akan terjadi jika permohonan dikabulkan?",
            },
        ],
        "applicant_categories": [
            {
                "id": "individual_or_group",
                "basis": ["Pasal 4 ayat (1) huruf a"],
                "label": "Perorangan WNI atau kelompok orang yang mempunyai kepentingan sama.",
                "draft_instruction": "Untuk beberapa Pemohon, tulis sebagai Para Pemohon dan jelaskan kerugian masing-masing atau kepentingan yang sama.",
            },
            {
                "id": "customary_community",
                "basis": ["Pasal 4 ayat (1) huruf b"],
                "label": "Kesatuan masyarakat hukum adat.",
                "draft_instruction": "Uraikan keberadaan, keberlanjutan, dan dasar pengakuan masyarakat hukum adat bila dipakai.",
            },
            {
                "id": "legal_entity",
                "basis": ["Pasal 4 ayat (1) huruf c"],
                "label": "Badan hukum publik atau badan hukum privat.",
                "draft_instruction": "Untuk serikat pekerja/serikat buruh, posisikan sesuai legalitas organisasinya dan catat kebutuhan AD/ART atau dokumen pengesahan.",
            },
            {
                "id": "state_institution",
                "basis": ["Pasal 4 ayat (1) huruf d"],
                "label": "Lembaga negara.",
                "draft_instruction": "Jelaskan kewenangan konstitusional yang dirugikan.",
            },
        ],
        "petitum_models": {
            "formil": {
                "basis": ["Pasal 10 ayat (2) huruf c"],
                "must_address": [
                    "Mengabulkan permohonan Pemohon.",
                    "Menyatakan pembentukan UU/Perppu tidak memenuhi ketentuan pembentukan berdasarkan UUD 1945.",
                    "Menyatakan UU/Perppu a quo tidak mempunyai kekuatan hukum mengikat.",
                    "Memerintahkan pemuatan putusan dalam Berita Negara Republik Indonesia.",
                    "Alternatif ex aequo et bono bila diperlukan.",
                ],
                "extra_check": "Untuk pengujian formil, ingatkan batas 45 hari sejak pengundangan.",
            },
            "materiil": {
                "basis": ["Pasal 10 ayat (2) huruf d"],
                "must_address": [
                    "Mengabulkan permohonan Pemohon.",
                    "Menyatakan materi muatan ayat, pasal, dan/atau bagian yang diuji bertentangan dengan UUD 1945.",
                    "Menyatakan norma tidak mempunyai kekuatan hukum mengikat, atau konstitusional bersyarat bila diminta dan didukung posita.",
                    "Memerintahkan pemuatan putusan dalam Berita Negara Republik Indonesia.",
                    "Alternatif ex aequo et bono bila diperlukan.",
                ],
                "extra_check": "Rumusan petitum harus mengikuti objek norma yang persis diberikan user.",
            },
        },
        "filing_and_evidence_checklist": [
            {
                "id": "initial_bundle",
                "basis": ["Pasal 10 ayat (1)"],
                "items": [
                    "Permohonan.",
                    "Fotokopi identitas Pemohon.",
                    "Fotokopi identitas kuasa hukum dan surat kuasa jika memakai kuasa.",
                    "AD/ART jika relevan untuk badan hukum/organisasi.",
                ],
            },
            {
                "id": "without_lawyer",
                "basis": ["Pasal 11"],
                "items": [
                    "Permohonan tertulis dalam bahasa Indonesia dan ditandatangani Pemohon.",
                    "Daftar alat bukti dan alat bukti pendukung.",
                    "Bukti surat/tulisan 1 eksemplar asli bermeterai jika ada.",
                    "Salinan UU/Perppu yang diuji, minimal bagian/bab terkait, halaman depan, dan halaman pengundangan.",
                    "Salinan UUD 1945.",
                    "Setiap alat bukti diberi label sesuai urutan daftar bukti.",
                ],
            },
            {
                "id": "with_lawyer",
                "basis": ["Pasal 12"],
                "items": [
                    "Jika dikuasakan kepada kuasa hukum, permohonan wajib diajukan secara daring.",
                    "Permohonan tertulis dalam bahasa Indonesia dan ditandatangani Pemohon atau kuasa hukum.",
                    "Daftar alat bukti dan alat bukti pendukung dengan ketentuan minimum sebagaimana Pasal 12.",
                ],
            },
            {
                "id": "soft_copy",
                "basis": ["Pasal 13"],
                "items": [
                    "Permohonan dan daftar alat bukti disertai salinan digital Word (.doc) dan PDF.",
                    "Salinan digital dapat disimpan dalam flash disk atau dikirim secara daring/media elektronik.",
                    "PDF permohonan dan daftar alat bukti ditandatangani Pemohon atau kuasa hukum.",
                ],
            },
            {
                "id": "revision_deadline",
                "basis": ["Pasal 17", "Pasal 18"],
                "items": [
                    "Jika ada APKBP, perbaikan/kelengkapan paling lama 7 hari kerja sejak dikirimnya APKBP.",
                    "Perbaikan disertai daftar alat bukti, bukti pendukung, dan/atau dokumen lain.",
                    "Perbaikan digital diserahkan dalam Word (.doc) dan PDF; PDF ditandatangani Pemohon atau kuasa hukum.",
                ],
            },
        ],
        "frontend_field_map": {
            "jenis_pengujian": "Menentukan model petitum formil/materiil/campuran.",
            "nama_pemohon": "Bagian identitas Pasal 10 ayat (2) huruf a.",
            "kategori_pemohon": "Satu atau lebih kualifikasi Pemohon Pasal 4 ayat (1), termasuk Para Pemohon atau serikat pekerja bila relevan.",
            "identitas_lengkap": "Pekerjaan, kewarganegaraan, alamat rumah/kantor, dan email.",
            "kuasa_hukum": "Kuasa hukum dan kebutuhan surat kuasa khusus bila ada.",
            "uu_diuji": "Objek permohonan UU/Perppu.",
            "pasal_diuji": "Materi muatan ayat/pasal/bagian yang diuji.",
            "batu_uji_uud": "Hak/kewenangan konstitusional dan batu uji UUD 1945.",
            "kerugian_konstitusional": "Dasar lima unsur legal standing Pasal 4 ayat (2).",
            "target_petitum": "Rumusan akhir petitum sesuai Pasal 10 ayat (2) huruf c/d.",
        },
    }


def evaluate_pmk_input_gaps(
    mode: str,
    user_input: Optional[Dict[str, Any]] = None,
    uploaded_draft: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return non-blocking PMK data gaps for the drafter note section."""
    user_input = user_input or {}
    uploaded_draft = uploaded_draft or {}
    text_pool = " ".join([_flatten(user_input), _flatten(uploaded_draft)]).lower()

    gaps = []
    required_fields = {
        "jenis_pengujian": "Jenis pengujian untuk menentukan petitum Pasal 10.",
        "nama_pemohon": "Nama Pemohon untuk identitas Pasal 10 ayat (2) huruf a.",
        "kategori_pemohon": "Kualifikasi Pemohon Pasal 4 ayat (1).",
        "uu_diuji": "Objek UU/Perppu yang diuji.",
        "pasal_diuji": "Pasal/ayat/bagian yang diuji.",
        "batu_uji_uud": "Batu uji UUD 1945.",
        "kerugian_konstitusional": "Uraian lima unsur kerugian konstitusional Pasal 4 ayat (2).",
    }
    if mode == "new_draft":
        for field, reason in required_fields.items():
            if not _flatten(user_input.get(field)).strip():
                gaps.append({"field": field, "basis": "PMK 2/2021", "reason": reason, "severity": "required"})

    identity_text = _flatten(user_input.get("identitas_lengkap"))
    for keyword, label in [
        ("pekerjaan", "pekerjaan Pemohon"),
        ("warga", "kewarganegaraan Pemohon"),
        ("alamat", "alamat rumah/kantor"),
        ("email", "alamat surat elektronik"),
    ]:
        if keyword not in identity_text.lower() and label.lower() not in identity_text.lower():
            gaps.append({
                "field": "identitas_lengkap",
                "basis": "Pasal 10 ayat (2) huruf a",
                "reason": f"Belum terdeteksi {label}.",
                "severity": "recommended",
            })

    if "formil" in _flatten(user_input.get("jenis_pengujian")).lower() and "45" not in text_pool:
        gaps.append({
            "field": "tanggal_pengundangan",
            "basis": "Pasal 9 ayat (2)",
            "reason": "Untuk pengujian formil, perlu cek tenggang waktu 45 hari sejak pengundangan.",
            "severity": "recommended",
        })

    for evidence_label in [
        "fotokopi identitas Pemohon",
        "salinan UU/Perppu yang diuji",
        "salinan UUD 1945",
        "daftar alat bukti",
    ]:
        if evidence_label.lower() not in text_pool:
            gaps.append({
                "field": "alat_bukti",
                "basis": "Pasal 10, Pasal 11, Pasal 12",
                "reason": f"Belum ada konfirmasi {evidence_label}.",
                "severity": "checklist",
            })

    if _flatten(user_input.get("kuasa_hukum")).strip() and "surat kuasa" not in text_pool:
        gaps.append({
            "field": "kuasa_hukum",
            "basis": "Pasal 7, Pasal 10 ayat (1), Pasal 12",
            "reason": "Kuasa hukum terisi, tetapi surat kuasa khusus/identitas kuasa belum terkonfirmasi.",
            "severity": "recommended",
        })

    return {
        "mode": mode,
        "summary": {
            "required": sum(1 for item in gaps if item["severity"] == "required"),
            "recommended": sum(1 for item in gaps if item["severity"] == "recommended"),
            "checklist": sum(1 for item in gaps if item["severity"] == "checklist"),
        },
        "gaps": gaps,
    }


def write_pmk_compliance_artifact(
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    source_pdf: Optional[Path | str] = None,
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    data = build_pmk_2_2021_compliance(source_pdf)
    target = output_path / PMK_COMPLIANCE_FILENAME
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return data


def load_pmk_compliance(output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> Dict[str, Any]:
    target = Path(output_dir) / PMK_COMPLIANCE_FILENAME
    if target.exists():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            pass
    return build_pmk_2_2021_compliance()
