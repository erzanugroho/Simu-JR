import json
from pathlib import Path

from core.rag_manifest import load_rag_manifest, resolve_manifest_path, save_rag_manifest


def test_load_missing_manifest_returns_safe_status(tmp_path, monkeypatch):
    chroma = tmp_path / "chroma_db"
    monkeypatch.delenv("RAG_DATA_MANIFEST_PATH", raising=False)

    result = load_rag_manifest(chroma)

    assert result["status"] == "missing"
    assert result["data_version"] is None
    assert result["manifest_path"] == str(tmp_path / "rag_data_manifest.json")


def test_load_manifest_from_env_path(tmp_path, monkeypatch):
    manifest_path = tmp_path / "custom_manifest.json"
    manifest_path.write_text(
        json.dumps({"data_version": "2026-06", "built_at": "2026-06-01T00:00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RAG_DATA_MANIFEST_PATH", str(manifest_path))

    result = load_rag_manifest(tmp_path / "unused")

    assert result["status"] == "ready"
    assert result["data_version"] == "2026-06"
    assert result["manifest_path"] == str(manifest_path)


def test_save_manifest_creates_parent(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "rag_data_manifest.json"
    monkeypatch.setenv("RAG_DATA_MANIFEST_PATH", str(path))

    written = save_rag_manifest({"data_version": "2026-07"})

    assert written == path
    assert json.loads(path.read_text(encoding="utf-8"))["data_version"] == "2026-07"
    assert resolve_manifest_path() == path

