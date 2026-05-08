"""
Simulation Store - Persistent Storage untuk Simulasi Sidang MK
===============================================================
Menyimpan setiap simulasi secara individual sebagai JSON file
agar bisa di-load, di-replay, atau dianalisa ulang kapan saja.

Struktur penyimpanan:
  results/simulations/
    _index.json              - index cepat untuk listing (metadata saja)
    sim_<uuid>.json          - data lengkap satu simulasi
"""

import json
import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .runtime_paths import runtime_dir

logger = logging.getLogger(__name__)

SIMULATIONS_DIR = str(runtime_dir('simulations'))
INDEX_FILE = os.path.join(SIMULATIONS_DIR, '_index.json')


def _ensure_dir():
    os.makedirs(SIMULATIONS_DIR, exist_ok=True)


def _load_index() -> List[Dict[str, Any]]:
    """Load metadata index dari semua simulasi tersimpan."""
    if not os.path.exists(INDEX_FILE):
        return []
    try:
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Gagal membaca index simulasi: {e}")
        return []


def _save_index(index: List[Dict[str, Any]]):
    """Simpan metadata index."""
    _ensure_dir()
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def save_simulation(
    simulation_data: Dict[str, Any],
    draft: str = "",
    config: Optional[Dict[str, Any]] = None,
    sim_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simpan satu simulasi secara persisten.

    Args:
        simulation_data: Hasil lengkap dari SimulationOrchestrator.run_full_simulation()
                         (transcript, scores, individual_scores, dissenting_opinions, feedback, api_usage)
        draft: Draft permohonan yang digunakan
        config: Konfigurasi simulasi (jumlah_hakim, llm_config, mode, judge_personas)
        sim_id: ID unik (opsional, auto-generated jika tidak disediakan)

    Returns:
        Dict dengan 'id', 'file_path', dan metadata ringkas
    """
    _ensure_dir()

    sim_id = sim_id or uuid.uuid4().hex[:12]
    timestamp = datetime.now().isoformat()
    filename = f"sim_{sim_id}.json"
    file_path = os.path.join(SIMULATIONS_DIR, filename)

    # Ekstrak metadata untuk index
    scores = simulation_data.get("scores", {})
    total_score = scores.get("total", 0)
    amar = scores.get("amar", "-")
    transcript = simulation_data.get("transcript", [])
    transcript_count = len(transcript)
    dissenting = simulation_data.get("dissenting_opinions", [])
    feedback = simulation_data.get("feedback", {})
    api_usage = simulation_data.get("api_usage", {})
    metadata = simulation_data.get("metadata", {}) or {}
    llm_config = (config or {}).get("llm_config", {}) or {}
    if llm_config and not metadata.get("llm_provider"):
        metadata = {
            **metadata,
            "llm_provider": llm_config.get("provider"),
            "llm_model": llm_config.get("model_name"),
            "llm_base_url": llm_config.get("base_url"),
        }

    # Susun data lengkap untuk disimpan
    full_data = {
        "id": sim_id,
        "timestamp": timestamp,
        "draft": draft,
        "config": config or {},
        "project_id": config.get("project_id") if config else None,
        "simulation_id": simulation_data.get("simulation_id"),
        "transcript": transcript,
        "individual_scores": simulation_data.get("individual_scores", []),
        "scores": scores,
        "dissenting_opinions": dissenting,
        "feedback": feedback,
        "api_usage": api_usage,
        "metadata": metadata,
    }

    # Tulis file simulasi
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Simulasi {sim_id} disimpan: {file_path}")
    except Exception as e:
        logger.error(f"Gagal menyimpan simulasi {sim_id}: {e}")
        raise

    # Update index
    index_entry = {
        "id": sim_id,
        "timestamp": timestamp,
        "draft_excerpt": draft[:150] if draft else "",
        "total_score": total_score,
        "amar": amar,
        "transcript_count": transcript_count,
        "has_dissenting": len(dissenting) > 0,
        "has_feedback": bool(feedback and not feedback.get("error")),
        "project_id": config.get("project_id") if config else None,
        "duration_seconds": metadata.get("duration_seconds"),
        "llm_provider": metadata.get("llm_provider"),
        "llm_model": metadata.get("llm_model"),
        "file": filename,
    }

    index = _load_index()
    # Hindari duplikasi
    index = [e for e in index if e.get("id") != sim_id]
    index.append(index_entry)
    _save_index(index)

    return index_entry


def load_simulation(sim_id: str) -> Optional[Dict[str, Any]]:
    """
    Load data lengkap simulasi berdasarkan ID.

    Returns:
        Dict data lengkap atau None jika tidak ditemukan
    """
    file_path = os.path.join(SIMULATIONS_DIR, f"sim_{sim_id}.json")
    if not os.path.exists(file_path):
        # Coba cari di index
        index = _load_index()
        entry = next((e for e in index if e["id"] == sim_id), None)
        if entry:
            file_path = os.path.join(SIMULATIONS_DIR, entry.get("file", ""))
        if not os.path.exists(file_path):
            return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Gagal memuat simulasi {sim_id}: {e}")
        return None


def list_simulations(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """
    Daftar simulasi tersimpan (metadata saja, tanpa transcript penuh).

    Returns:
        Dict dengan 'simulations' (list) dan 'total' (int)
    """
    index = _load_index()
    # Sort by timestamp descending
    index.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    total = len(index)
    return {
        "simulations": index[offset:offset + limit],
        "total": total,
    }


def delete_simulation(sim_id: str) -> bool:
    """Hapus simulasi berdasarkan ID."""
    file_path = os.path.join(SIMULATIONS_DIR, f"sim_{sim_id}.json")
    deleted = False

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            deleted = True
        except Exception as e:
            logger.error(f"Gagal menghapus file simulasi {sim_id}: {e}")

    # Hapus dari index
    index = _load_index()
    new_index = [e for e in index if e.get("id") != sim_id]
    if len(new_index) < len(index):
        _save_index(new_index)
        deleted = True

    return deleted


def get_simulation_stats() -> Dict[str, Any]:
    """Statistik ringkas tentang simulasi tersimpan."""
    index = _load_index()
    if not index:
        return {"total": 0, "avg_score": 0, "best_score": 0, "amar_distribution": {}}

    scores = [e.get("total_score", 0) for e in index if isinstance(e.get("total_score"), (int, float))]
    amars = [e.get("amar", "unknown") for e in index]

    from collections import Counter
    amar_dist = Counter(amars)

    return {
        "total": len(index),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "best_score": round(max(scores), 1) if scores else 0,
        "amar_distribution": dict(amar_dist),
    }


def list_simulations_by_project(project_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """Daftar simulasi yang ter-link ke project tertentu."""
    index = _load_index()
    project_sims = [e for e in index if e.get("project_id") == project_id]
    project_sims.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    total = len(project_sims)
    return {
        "simulations": project_sims[offset:offset + limit],
        "total": total,
    }
