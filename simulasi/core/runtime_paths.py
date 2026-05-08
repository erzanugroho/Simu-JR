"""
Runtime path helpers.

Source checkout default tetap memakai folder `simulasi/results`. Installer dapat
set `SIMUJR_DATA_ROOT=%ProgramData%\\SimuJR` agar data user tidak ditulis ke
folder aplikasi di Program Files.
"""

from __future__ import annotations

import os
from pathlib import Path


SIMULASI_DIR = Path(__file__).resolve().parents[1]


def data_root() -> Path:
    raw = os.getenv("SIMUJR_DATA_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (SIMULASI_DIR / "results").resolve()


def runtime_dir(name: str) -> Path:
    path = data_root() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_uploads_dir() -> Path:
    raw = os.getenv("SIMUJR_TEMP_UPLOADS_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
    else:
        path = data_root() / "temp_uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path

