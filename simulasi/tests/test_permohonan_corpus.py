import json
from pathlib import Path

import fitz

from core.permohonan_corpus import (
    build_drafter_handoff,
    classify_document,
    get_corpus_status,
    index_permohonan_corpus,
    load_analysis_artifacts,
)


def _write_pdf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_classify_document_from_filename_and_text():
    assert classify_document("Permohonan diRegistrasi_4334_8439.pdf", "") == "permohonan_awal"
    assert classify_document("Perbaikan Permohonan_4334_8439.pdf", "") == "perbaikan"
    assert classify_document("gabungan_permohonan.pdf", "") == "gabungan"
    assert classify_document("scan.pdf", "teks acak") == "tidak_pasti"


def test_index_writes_required_artifacts(tmp_path):
    corpus_dir = tmp_path / "permohonan_pdf"
    output_dir = tmp_path / "artifacts"
    base_text = """
    Permohonan Pengujian Undang-Undang
    Identitas Pemohon
    Kewenangan Mahkamah Konstitusi
    Kedudukan Hukum Pemohon
    Objek Pengujian
    Batu Uji UUD 1945
    Kerugian Konstitusional
    Alasan-Alasan Permohonan
    Petitum
    Daftar Bukti
    """
    _write_pdf(corpus_dir / "Permohonan diRegistrasi_4334_8439.pdf", base_text)
    _write_pdf(corpus_dir / "perbaikan_permohonan" / "Perbaikan Permohonan_4334_8439.pdf", base_text + " legal standing lebih jelas")

    index = index_permohonan_corpus(corpus_dir=corpus_dir, output_dir=output_dir)

    assert index["total_files"] == 2
    assert index["classification_counts"]["permohonan_awal"] == 1
    assert index["classification_counts"]["perbaikan"] == 1
    assert index["revision_pairs_count"] == 1

    for filename in index["artifacts"].values():
        assert (output_dir / filename).exists()

    metadata_lines = (output_dir / "document_metadata.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(metadata_lines) == 2
    assert json.loads(metadata_lines[0])["extraction"]["status"] == "extracted"

    status = get_corpus_status(corpus_dir=corpus_dir, output_dir=output_dir)
    assert status["status"] == "ready"
    assert status["total_files"] == 2


def test_load_artifacts_and_build_handoff(tmp_path):
    corpus_dir = tmp_path / "permohonan_pdf"
    output_dir = tmp_path / "artifacts"
    _write_pdf(
        corpus_dir / "Permohonan diRegistrasi_1111_2222.pdf",
        "Permohonan Pengujian Undang-Undang\nKewenangan Mahkamah\nKedudukan Hukum\nPetitum",
    )
    index_permohonan_corpus(corpus_dir=corpus_dir, output_dir=output_dir)

    artifacts = load_analysis_artifacts(output_dir=output_dir)
    handoff = build_drafter_handoff(
        mode="new_draft",
        user_input={"nama_pemohon": "Pemohon Uji"},
        analysis_artifacts=artifacts,
        references={"rag_cases": [], "rag_risalah": [], "bank_data": [], "pasalid_norms": []},
    )

    assert handoff["mode"] == "new_draft"
    assert handoff["user_input"]["nama_pemohon"] == "Pemohon Uji"
    assert "golden_template" in handoff["analysis_artifacts"]
    assert "common_improvements" in handoff["analysis_artifacts"]
    assert "pmk_2_2021_compliance" in handoff["analysis_artifacts"]
    assert "pmk_compliance_review" in handoff
    assert handoff["pmk_compliance_review"]["summary"]["recommended"] >= 1
