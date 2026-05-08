"""
Project Store - Persistent Storage untuk Project Management
============================================================
Menyimpan setiap project sebagai directory dengan metadata JSON,
file uploads, research history, dan audit results.

Struktur penyimpanan:
  results/projects/
    _index.json                         - index cepat untuk listing (metadata saja)
    <project_id>/
      metadata.json                     - data lengkap project
      files/                            - uploaded files (PDF, DOCX, TXT)
      research/                         - research findings
      audit/                            - audit results
"""

import json
import os
import uuid
import shutil
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from . import simulation_store
from .runtime_paths import runtime_dir

logger = logging.getLogger(__name__)

PROJECTS_DIR = str(runtime_dir('projects'))
INDEX_FILE = os.path.join(PROJECTS_DIR, '_index.json')

_index_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def _index_exists() -> bool:
    return os.path.exists(INDEX_FILE)


def _load_index() -> List[Dict[str, Any]]:
    """Load metadata index dari semua projects tersimpan."""
    if not os.path.exists(INDEX_FILE):
        return []
    try:
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Gagal membaca index project: {e}")
        return []


def _save_index(index: List[Dict[str, Any]]):
    """Simpan metadata index dengan concurrency protection."""
    _ensure_dir()
    with _index_lock:
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)


def _get_project_dir(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, project_id)


def _get_metadata_path(project_id: str) -> str:
    return os.path.join(_get_project_dir(project_id), 'metadata.json')


def _count_simulations(project_id: str) -> int:
    """Hitung simulasi yang ter-link ke project ini."""
    index = simulation_store._load_index()
    return sum(1 for entry in index if entry.get('project_id') == project_id)


def _count_files(project_id: str) -> int:
    """Hitung file yang di-upload ke project ini."""
    files_dir = os.path.join(_get_project_dir(project_id), 'files')
    if not os.path.isdir(files_dir):
        return 0
    return len([f for f in os.listdir(files_dir) if os.path.isfile(os.path.join(files_dir, f))])


def _update_index_entry(project_id: str):
    """Update single entry di _index.json berdasarkan metadata.json."""
    metadata = get_project(project_id)
    if not metadata:
        return

    index = _load_index()
    entry = {
        "id": metadata["id"],
        "name": metadata["name"],
        "description": metadata.get("description", ""),
        "created_at": metadata.get("created_at", ""),
        "updated_at": metadata.get("updated_at", ""),
        "simulation_count": _count_simulations(project_id),
        "file_count": _count_files(project_id),
    }
    index = [e for e in index if e.get("id") != project_id]
    index.append(entry)
    _save_index(index)


# --- CRUD ---------------------------------------------------------------


def create_project(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Buat project baru.

    Args:
        data: Dict dengan 'name' (required), 'description' (optional)

    Returns:
        Dict metadata project yang baru dibuat
    """
    _ensure_dir()

    project_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now().isoformat()

    project_dir = _get_project_dir(project_id)
    os.makedirs(os.path.join(project_dir, 'files'), exist_ok=True)
    os.makedirs(os.path.join(project_dir, 'research'), exist_ok=True)
    os.makedirs(os.path.join(project_dir, 'audit'), exist_ok=True)

    metadata = {
        "id": project_id,
        "name": data.get("name", "Untitled Project"),
        "description": data.get("description", ""),
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    metadata_path = _get_metadata_path(project_id)
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # Update index
    _update_index_entry(project_id)

    logger.info(f"Project {project_id} dibuat: {metadata['name']}")
    return metadata


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Load metadata project berdasarkan ID.

    Returns:
        Dict metadata atau None jika tidak ditemukan
    """
    metadata_path = _get_metadata_path(project_id)
    if not os.path.exists(metadata_path):
        return None

    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Gagal memuat project {project_id}: {e}")
        return None


def list_projects(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """
    Daftar semua projects (metadata saja).

    Returns:
        Dict dengan 'projects' (list) dan 'total' (int)
    """
    index = _load_index()
    index.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    total = len(index)
    return {
        "projects": index[offset:offset + limit],
        "total": total,
    }


def update_project(project_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Update metadata project.

    Args:
        project_id: ID project
        data: Dict dengan field yang ingin di-update ('name', 'description')

    Returns:
        Dict metadata yang sudah di-update, atau None jika tidak ditemukan
    """
    metadata = get_project(project_id)
    if not metadata:
        return None

    if "name" in data:
        metadata["name"] = data["name"]
    if "description" in data:
        metadata["description"] = data["description"]
    metadata["updated_at"] = datetime.now().isoformat()

    metadata_path = _get_metadata_path(project_id)
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    _update_index_entry(project_id)

    logger.info(f"Project {project_id} di-update")
    return metadata


def delete_project(project_id: str) -> bool:
    """
    Hapus project dan semua file/metadata terkait.
    Unlink simulasi dari project (hapus project_id dari index simulasi).

    Returns:
        True jika berhasil dihapus, False jika tidak ditemukan
    """
    project_dir = _get_project_dir(project_id)
    if not os.path.isdir(project_dir):
        return False

    try:
        shutil.rmtree(project_dir)
        logger.info(f"Project directory {project_dir} dihapus")
    except Exception as e:
        logger.error(f"Gagal menghapus project directory {project_id}: {e}")
        return False

    # Unlink simulations
    sim_index = simulation_store._load_index()
    changed = False
    for entry in sim_index:
        if entry.get('project_id') == project_id:
            del entry['project_id']
            changed = True
    if changed:
        simulation_store._save_index(sim_index)

    # Remove from project index
    index = _load_index()
    new_index = [e for e in index if e.get("id") != project_id]
    if len(new_index) < len(index):
        _save_index(new_index)

    return True


# --- Files --------------------------------------------------------------

ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt'}


def add_file_to_project(
    project_id: str,
    filename: str,
    file_content: bytes,
    mime_type: str = '',
) -> Optional[Dict[str, Any]]:
    """
    Upload file ke project.

    Args:
        project_id: ID project
        filename: Nama file asli
        file_content: Isi file dalam bytes
        mime_type: MIME type file

    Returns:
        Dict file metadata atau None jika gagal
    """
    project = get_project(project_id)
    if not project:
        return None

    # Validate extension
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"File type {ext} tidak diizinkan")
        return None

    file_id = uuid.uuid4().hex[:8]
    safe_filename = f"{file_id}_{filename}"
    files_dir = os.path.join(_get_project_dir(project_id), 'files')
    os.makedirs(files_dir, exist_ok=True)
    file_path = os.path.join(files_dir, safe_filename)

    try:
        with open(file_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        logger.error(f"Gagal menyimpan file {filename}: {e}")
        return None

    file_meta = {
        "id": file_id,
        "filename": filename,
        "stored_filename": safe_filename,
        "size": len(file_content),
        "mime_type": mime_type,
        "uploaded_at": datetime.now().isoformat(),
    }

    # Save file metadata
    meta_path = os.path.join(files_dir, f"{file_id}.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(file_meta, f, ensure_ascii=False, indent=2)

    _update_index_entry(project_id)

    logger.info(f"File {filename} di-upload ke project {project_id}")
    return file_meta


def list_project_files(project_id: str) -> List[Dict[str, Any]]:
    """List semua file di project."""
    files_dir = os.path.join(_get_project_dir(project_id), 'files')
    if not os.path.isdir(files_dir):
        return []

    files = []
    for f in os.listdir(files_dir):
        if f.endswith('.json'):
            meta_path = os.path.join(files_dir, f)
            try:
                with open(meta_path, 'r', encoding='utf-8') as fh:
                    files.append(json.load(fh))
            except Exception:
                continue

    files.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
    return files


def delete_project_file(project_id: str, file_id: str) -> bool:
    """Hapus file dari project."""
    files_dir = os.path.join(_get_project_dir(project_id), 'files')
    if not os.path.isdir(files_dir):
        return False

    meta_path = os.path.join(files_dir, f"{file_id}.json")
    if not os.path.exists(meta_path):
        return False

    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            file_meta = json.load(f)
    except Exception:
        return False

    stored_path = os.path.join(files_dir, file_meta.get("stored_filename", ""))
    if os.path.exists(stored_path):
        os.remove(stored_path)
    os.remove(meta_path)

    _update_index_entry(project_id)
    return True


# --- Research -----------------------------------------------------------


def save_research(project_id: str, query: str, answer: str, sources: List[str] = None) -> Optional[Dict[str, Any]]:
    """Simpan hasil research ke project."""
    project = get_project(project_id)
    if not project:
        return None

    research_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().isoformat()

    research_data = {
        "id": research_id,
        "query": query,
        "answer": answer,
        "sources": sources or [],
        "timestamp": timestamp,
    }

    research_dir = os.path.join(_get_project_dir(project_id), 'research')
    os.makedirs(research_dir, exist_ok=True)
    research_path = os.path.join(research_dir, f"research_{research_id}.json")

    try:
        with open(research_path, 'w', encoding='utf-8') as f:
            json.dump(research_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Gagal menyimpan research: {e}")
        return None

    logger.info(f"Research {research_id} disimpan ke project {project_id}")
    return research_data


def list_research(project_id: str) -> List[Dict[str, Any]]:
    """List semua research findings di project."""
    research_dir = os.path.join(_get_project_dir(project_id), 'research')
    if not os.path.isdir(research_dir):
        return []

    findings = []
    for f in os.listdir(research_dir):
        if f.endswith('.json'):
            path = os.path.join(research_dir, f)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    findings.append(json.load(fh))
            except Exception:
                continue

    findings.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return findings


# --- Audit --------------------------------------------------------------


def save_audit(project_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Simpan hasil audit ke project."""
    project = get_project(project_id)
    if not project:
        return None

    audit_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().isoformat()

    audit_data = {
        "id": audit_id,
        "consistent": result.get("consistent", False),
        "issues": result.get("issues", []),
        "summary": result.get("summary", ""),
        "timestamp": timestamp,
    }

    audit_dir = os.path.join(_get_project_dir(project_id), 'audit')
    os.makedirs(audit_dir, exist_ok=True)
    audit_path = os.path.join(audit_dir, f"audit_{audit_id}.json")

    try:
        with open(audit_path, 'w', encoding='utf-8') as f:
            json.dump(audit_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Gagal menyimpan audit: {e}")
        return None

    logger.info(f"Audit {audit_id} disimpan ke project {project_id}")
    return audit_data


def list_audits(project_id: str) -> List[Dict[str, Any]]:
    """List semua audit results di project."""
    audit_dir = os.path.join(_get_project_dir(project_id), 'audit')
    if not os.path.isdir(audit_dir):
        return []

    audits = []
    for f in os.listdir(audit_dir):
        if f.endswith('.json'):
            path = os.path.join(audit_dir, f)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    audits.append(json.load(fh))
            except Exception:
                continue

    audits.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return audits


# --- Migration ----------------------------------------------------------


def migrate_legacy_simulations() -> Optional[str]:
    """
    Migrasi simulasi existing ke 'Proyek Default'.
    Hanya berjalan sekali (saat _index.json project belum ada).

    Returns:
        Project ID dari 'Proyek Default' atau None jika tidak perlu migrasi
    """
    if _index_exists():
        # Sudah ada projects, skip migrasi
        existing = _load_index()
        if existing:
            return None

    orphan_sims = simulation_store.list_simulations()
    if not orphan_sims or orphan_sims.get("total", 0) == 0:
        return None

    # Backup index simulasi sebelum migrasi
    sim_index = simulation_store._load_index()
    backup_path = os.path.join(simulation_store.SIMULATIONS_DIR, '_index_backup.json')
    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(sim_index, f, ensure_ascii=False, indent=2)
        logger.info(f"Backup index simulasi disimpan: {backup_path}")
    except Exception as e:
        logger.warning(f"Gagal backup index simulasi: {e}")

    default_project = create_project({
        "name": "Proyek Default",
        "description": "Simulasi yang di-migrate dari sistem sebelumnya"
    })

    project_id = default_project["id"]

    # Link semua simulasi ke default project
    updated_index = simulation_store._load_index()
    for entry in updated_index:
        if not entry.get('project_id'):
            entry['project_id'] = project_id
    simulation_store._save_index(updated_index)

    _update_index_entry(project_id)

    logger.info(f"Migrasi selesai: {orphan_sims['total']} simulasi linked ke Proyek Default ({project_id})")
    return project_id
