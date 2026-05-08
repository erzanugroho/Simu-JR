import json

from docx import Document

from core import project_store
from core.permohonan_drafts import (
    get_permohonan_draft_docx_path,
    list_permohonan_drafts,
    save_permohonan_draft,
)


def _make_project(root, project_id="project123"):
    project_dir = root / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "metadata.json").write_text(
        json.dumps({
            "id": project_id,
            "name": "Project Uji",
            "description": "",
            "created_at": "2026-05-06T00:00:00",
            "updated_at": "2026-05-06T00:00:00",
        }),
        encoding="utf-8",
    )
    return project_id


def test_save_permohonan_draft_exports_docx(tmp_path, monkeypatch):
    project_id = _make_project(tmp_path)
    monkeypatch.setattr(project_store, "PROJECTS_DIR", str(tmp_path))

    saved = save_permohonan_draft(
        project_id=project_id,
        mode="new_draft",
        user_input={"nama_pemohon": "Pemohon Uji", "uu_diuji": "UU Uji"},
        draft_text="JUDUL PERMOHONAN\n\nI. IDENTITAS PEMOHON\nBahwa Pemohon adalah warga negara.",
        uploaded_draft=None,
        sources={"rag_used": False},
        projects_dir=str(tmp_path),
    )

    assert saved is not None
    assert saved["title"] == "Permohonan Pemohon Uji - UU Uji"

    drafts = list_permohonan_drafts(project_id, projects_dir=str(tmp_path))
    assert len(drafts) == 1
    assert drafts[0]["id"] == saved["id"]

    docx_path = get_permohonan_draft_docx_path(project_id, saved["id"], projects_dir=str(tmp_path))
    assert docx_path is not None
    assert docx_path.exists()

    document = Document(str(docx_path))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "JUDUL PERMOHONAN" in text
    assert "Bahwa Pemohon adalah warga negara." in text
