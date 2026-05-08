"""
RAG Data Manifest utilities.

Manifest ini dipakai untuk membedakan update aplikasi dari update data RAG.
Lokasi default manifest berada di folder induk ChromaDB:

  <rag_dir>/rag_data_manifest.json
  <rag_dir>/chroma_db/
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


MANIFEST_FILENAME = "rag_data_manifest.json"


def resolve_chroma_db_path(base_dir: Optional[Path] = None) -> Path:
    """Resolve path ChromaDB dari env atau default project."""
    base = base_dir or Path(__file__).resolve().parents[1]
    raw = os.getenv("CHROMA_DB_PATH") or str(base / "rag" / "chroma_db")
    path = Path(raw)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_manifest_path(chroma_db_path: Optional[Path] = None) -> Path:
    """Resolve manifest path dari env atau folder induk ChromaDB."""
    explicit = os.getenv("RAG_DATA_MANIFEST_PATH")
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    chroma_path = chroma_db_path or resolve_chroma_db_path()
    return (Path(chroma_path).resolve().parent / MANIFEST_FILENAME).resolve()


def load_rag_manifest(chroma_db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load manifest RAG. Tidak raise agar health endpoint tetap aman."""
    manifest_path = resolve_manifest_path(chroma_db_path)
    if not manifest_path.exists():
        return {
            "status": "missing",
            "manifest_path": str(manifest_path),
            "data_version": None,
            "built_at": None,
        }

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "invalid",
            "manifest_path": str(manifest_path),
            "error": str(exc),
            "data_version": None,
            "built_at": None,
        }

    data.setdefault("status", "ready")
    data.setdefault("manifest_path", str(manifest_path))
    data.setdefault("data_version", None)
    data.setdefault("built_at", None)
    return data


def build_rag_manifest(
    *,
    data_version: str,
    source_label: str,
    chroma_db_path: Optional[Path] = None,
    collection_counts: Optional[Dict[str, int]] = None,
    files: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create normalized manifest payload."""
    chroma_path = chroma_db_path or resolve_chroma_db_path()
    return {
        "schema_version": 1,
        "data_version": data_version,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source_label": source_label,
        "chroma_db_path": str(chroma_path),
        "collection_counts": collection_counts or {},
        "files": files or {},
    }


def save_rag_manifest(manifest: Dict[str, Any], manifest_path: Optional[Path] = None) -> Path:
    """Write manifest JSON and return path."""
    path = manifest_path or resolve_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

