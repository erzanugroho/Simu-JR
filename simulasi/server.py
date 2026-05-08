"""
Web Server - Simulasi Sidang MK
=================================
FastAPI backend yang menyajikan UI dan streaming transcript sidang secara real-time.
"""

import asyncio
import io
import json
import logging
import os
import sys
import time
import httpx
import uuid
from typing import Dict, Any, List

import re as _re
from fastapi import FastAPI, Request, UploadFile, File, Header
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Setup path agar bisa import modul lokal
sys.path.insert(0, os.path.dirname(__file__))

from core.agents import (
    PemohonAgent, PemerintahAgent, HakimAgent, JudicialReviewDraftAgent,
    RisetHukumAgent, PermohonanDrafterAgent,
)
from core.orchestrator import SimulationOrchestrator
from core.utils import extract_text_from_file
from core.templates import get_all_templates, get_template_by_id
from core.pdf_generator import generate_putusan_pdf
from core.permohonan_corpus import (
    build_drafter_handoff,
    compact_for_prompt,
    get_corpus_progress,
    get_corpus_status,
    index_permohonan_corpus,
    load_analysis_artifacts,
)
from core.permohonan_drafts import (
    get_permohonan_draft_docx_path,
    list_permohonan_drafts,
    save_permohonan_draft,
)
from core.simulation_store import (
    save_simulation, load_simulation, list_simulations,
    delete_simulation, get_simulation_stats,
    list_simulations_by_project,
)
from core.project_store import (
    create_project, get_project, list_projects, update_project, delete_project,
    add_file_to_project, list_project_files, delete_project_file,
    save_research, list_research, save_audit, list_audits,
    migrate_legacy_simulations,
    ALLOWED_EXTENSIONS as PROJECT_ALLOWED_EXTENSIONS,
    PROJECTS_DIR,
)
from core.rag_manifest import load_rag_manifest, resolve_chroma_db_path
from core.runtime_paths import runtime_dir, temp_uploads_dir

# Import retriever untuk endpoint perbaiki draft & playbook
try:
    from rag.retriever import RAGRetriever
    RAG_AVAILABLE = True
except Exception:
    RAG_AVAILABLE = False

# Import PasalAPI dari canonical source (rag/pasal_api.py)
from rag.pasal_api import pasal_api as PasalAPI

# Import self-correcting loop
try:
    from core.self_correcting_loop import SelfCorrectingLoop
    SELF_CORRECTING_AVAILABLE = True
except Exception as _e:
    SELF_CORRECTING_AVAILABLE = False

# Load prompts untuk Agent 6 & 7
PROMPT_DIR = Path(__file__).parent / "rag" / "prompts"

def _load_prompt(filename: str) -> str:
    path = PROMPT_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

AGENT6_BLUEPRINT_PROMPT = _load_prompt("agent6_petition_blueprint.txt")
AGENT7_PLAYBOOK_PROMPT = _load_prompt("agent7_hearing_playbook.txt")

IMPROVE_DRAFT_PROMPT = """\
Anda adalah Reviser Senior Permohonan Pengujian Undang-Undang (PUU) Mahkamah Konstitusi.

Tugas Anda: memperbaiki draft permohonan yang diberikan user menjadi NASKAH PERMOHONAN RESMI
yang siap dipakai untuk judicial review. Jangan membuat blueprint, template, playbook, catatan
sidang, atau metadata revisi. Hasil utama harus berupa teks permohonan penuh.

Gunakan empat intelligence bank berikut secara taktis:
1. SURVIVE BANK: pola jawaban/argumen Pemohon yang terbukti survive.
2. JUDGE CONCERN BANK: concern dan pertanyaan berulang Hakim yang harus diantisipasi.
3. GOVERNMENT ATTACK BANK: pola serangan Pemerintah/DPR yang harus dibentengi.
4. RATIO BANK: ratio decidendi terstruktur untuk memperkuat dalil dan konsistensi putusan.

Output WAJIB:
- HANYA teks naskah permohonan resmi.
- DILARANG mengeluarkan JSON.
- DILARANG menulis "ringkasan_perubahan", "alasan_perubahan", "aspek_diperbaiki", atau "bank_data_digunakan".
- DILARANG menulis kalimat playbook seperti "Majelis Hakim mungkin menanyakan..." atau "Pemohon menjawab...".

Struktur minimal:
JUDUL PERMOHONAN
I. IDENTITAS DAN KEDUDUKAN HUKUM PEMOHON
II. KEWENANGAN MAHKAMAH KONSTITUSI
III. NORMA YANG DIUJI DAN BATU UJI
IV. ALASAN-ALASAN PERMOHONAN / POSITA
V. PETITUM
VI. DAFTAR BUKTI
PENUTUP

Aturan revisi:
- Pertahankan norma yang diuji, identitas Pemohon, dan batu uji jika sudah disebutkan.
- WAJIB gunakan objek norma, nomor UU, tahun UU, dan pasal yang ada dalam draft awal. Jangan menggantinya dengan placeholder seperti "Pasal ...", "UU No. ...", atau "huruf ...".
- Perjelas 5 syarat legal standing: kualifikasi, hak konstitusional, kerugian, kausalitas, dan pemulihan.
- Bedakan kerugian norma dari masalah implementasi administratif.
- Tambahkan antisipasi atas open legal policy, norma vs implementasi, kausalitas, dan petitum kabur bila relevan.
- Petitum harus spesifik, konsisten dengan posita, dan dapat dieksekusi.
- Jangan mengarang nomor putusan. Jika bank tidak memberikan nomor yang jelas, gunakan formulasi umum tanpa nomor.
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# === CORS Middleware ===
_cors_origins = os.getenv("CORS_ORIGINS", "").strip()
_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()] if _cors_origins else ["*"]
# === Lifespan Event Handlers ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Jalankan migrasi simulasi legacy ke project default
    try:
        result = await asyncio.to_thread(migrate_legacy_simulations)
        if result:
            logger.info(f"Migrasi legacy simulations -> Proyek Default ({result})")
    except Exception as e:
        logger.warning(f"Gagal migrasi legacy simulations: {e}")
    yield
    # Shutdown: Clean up resources if any

app = FastAPI(title="Simulasi Sidang MK", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Input Size Limits ===
MAX_DRAFT_LENGTH = 100_000  # 100KB text limit for drafts
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB file upload limit
MAX_UPLOAD_CONTENT_LENGTH = MAX_FILE_SIZE + (1024 * 1024)  # Multipart overhead allowance
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}


@app.middleware("http")
async def _reject_large_uploads(request: Request, call_next):
    """Reject oversized uploads before Starlette parses multipart data."""
    if request.url.path == "/api/extract-text":
        content_length = request.headers.get("content-length")
        try:
            if content_length and int(content_length) > MAX_UPLOAD_CONTENT_LENGTH:
                return JSONResponse(
                    {"error": f"File terlalu besar. Maksimal {MAX_FILE_SIZE // (1024 * 1024)}MB"},
                    status_code=413,
                )
        except ValueError:
            pass
    return await call_next(request)

def _sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filename to prevent path traversal."""
    if not filename:
        return "upload"
    # Remove path separators and null bytes
    name = os.path.basename(filename)
    name = name.replace("\x00", "")
    # Only allow safe characters
    name = _re.sub(r'[^\w\s\-.]', '_', name)
    # Limit length
    name = name[:200]
    return name or "upload"


INTELLIGENCE_BANK_COLLECTIONS = ["mk_ratio_bank", "mk_attack_bank", "mk_concern_bank", "mk_survive_bank"]


def _get_chroma_stats_lightweight() -> Dict[str, Any]:
    """Read ChromaDB collection counts without importing Chroma or embedding models."""
    import sqlite3

    db_path = str(resolve_chroma_db_path(Path(__file__).parent))
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "mk_knowledge_base")
    sqlite_path = (Path(db_path) / "chroma.sqlite3").resolve()
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Chroma SQLite tidak ditemukan: {sqlite_path}")

    uri = f"file:{sqlite_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2.0) as conn:
        rows = conn.execute(
            """
            SELECT c.name, COUNT(e.id)
            FROM collections c
            JOIN segments s ON s.collection = c.id AND s.scope = 'METADATA'
            LEFT JOIN embeddings e ON e.segment_id = s.id
            GROUP BY c.name
            """
        ).fetchall()

    counts = {name: count for name, count in rows}
    intelligence_status = {bank: counts.get(bank, 0) for bank in INTELLIGENCE_BANK_COLLECTIONS}

    return {
        "rag": "connected",
        "rag_vectors": counts.get(collection_name, 0),
        "intelligence_banks": intelligence_status,
        "rag_data": load_rag_manifest(Path(db_path)),
    }

active_simulations: Dict[str, asyncio.Task] = {}
active_orchestrators: Dict[str, Any] = {} # {sim_id: StreamingOrchestrator}
simulation_queues: Dict[str, List[asyncio.Queue]] = {} # {sim_id: [q1, q2]}
simulation_transcripts: Dict[str, List[Dict[str, Any]]] = {} # {sim_id: [events]}
simulation_results: Dict[str, Dict[str, Any]] = {} # {sim_id: canonical result + flattened score fields}
simulation_configs: Dict[str, Dict[str, Any]] = {} # {sim_id: {draft, config, project_id, etc}}
MAX_PARALLEL_SIMULATIONS = int(os.getenv("MAX_PARALLEL_SIMULATIONS", "4"))
health_cache: Dict[str, Any] = {"rag_timestamp": 0, "rag_data": None, "llm": {}}
permohonan_index_task: asyncio.Task | None = None
permohonan_index_error: str | None = None
permohonan_index_started_at: str | None = None


def _public_llm_metadata(llm_config: Dict[str, Any]) -> Dict[str, Any]:
    """Metadata LLM yang aman disimpan/ditampilkan ulang, tanpa API key."""
    llm_config = llm_config or {}
    return {
        "llm_provider": llm_config.get("provider", "local"),
        "llm_model": llm_config.get("model_name", ""),
        "llm_base_url": llm_config.get("base_url", ""),
    }


def _cache_simulation_result(simulation_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Cache final result in both canonical and frontend-compatible shapes."""
    scores = result.get("scores", {}) if isinstance(result.get("scores"), dict) else {}
    cached = {
        **result,
        "scores": scores,
        "individual_scores": result.get("individual_scores", []),
        "feedback": result.get("feedback", {}),
        "dissenting_opinions": result.get("dissenting_opinions", []),
        "metadata": result.get("metadata", {}),
        # Compatibility fields consumed by /transcript sync in the frontend.
        "total": scores.get("total", 0),
        "breakdown": scores.get("breakdown", {}),
        "amar": scores.get("amar", ""),
        "voting_detail": scores.get("voting_detail", {}),
        "catatan_hakim": scores.get("catatan_hakim", []),
        "individual": result.get("individual_scores", []),
    }
    simulation_results[str(simulation_id)] = cached
    return cached


def _prune_finished_simulations() -> None:
    """Bersihkan task yang sudah selesai agar slot paralel tidak tersangkut."""
    for sim_id, task in list(active_simulations.items()):
        if task.done():
            active_simulations.pop(sim_id, None)


def _active_simulation_count() -> int:
    _prune_finished_simulations()
    return sum(1 for task in active_simulations.values() if not task.done())

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_RECOMMENDED_MODELS = [
    "moonshotai/kimi-k2.6",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-opus-4.7",
    "openai/gpt-5.5",
    "openai/gpt-oss-120b",
    "anthropic/claude-sonnet-4.5",
    "openai/gpt-5.1",
    "google/gemini-2.5-pro",
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-r1-0528",
    "qwen/qwen3-235b-a22b-thinking-2507",
    "google/gemini-2.5-flash",
    "anthropic/claude-haiku-4.5",
    "~openai/gpt-mini-latest",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "openrouter/auto",
]

OPENROUTER_MODEL_OVERRIDES = {
    "moonshotai/kimi-k2.6": {
        "name": "MoonshotAI: Kimi K2.6 (Moonshot AI)",
        "pricing": {
            "prompt_per_million": 0.95,
            "completion_per_million": 4.00,
            "raw_prompt": "0.00000095",
            "raw_completion": "0.000004",
        },
        "context_length": 262144,
        "note": "Moonshot AI provider, 262K context",
    },
    "openai/gpt-oss-120b": {
        "name": "OpenAI: GPT OSS 120B (Groq US)",
        "pricing": {
            "prompt_per_million": 0.15,
            "completion_per_million": 0.60,
            "cache_read_per_million": 0.075,
            "raw_prompt": "0.00000015",
            "raw_completion": "0.0000006",
        },
        "context_length": 131072,
        "note": "Groq US, max output 65.5K",
    }
}


def _load_self_correcting_defaults() -> Dict[str, Any]:
    """Ambil default Auto-Correct Draft dari config.yaml bila tersedia."""
    defaults = {
        "max_loops": 5,
        "acceptance_threshold": 70,
        "log_dir": str(runtime_dir("self_correcting_logs")),
    }
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        return defaults
    try:
        import yaml
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        configured = loaded.get("self_correcting", {}) or {}
        defaults.update({k: v for k, v in configured.items() if v is not None})
    except Exception as e:
        logger.warning(f"Gagal membaca default self_correcting dari config.yaml: {e}")
    return defaults


def _llm_key_error(llm_config: Dict[str, Any]) -> str:
    """Return user-facing missing key error, or an empty string if config is usable."""
    provider = (llm_config or {}).get("provider", "local")
    api_key = str((llm_config or {}).get("api_key") or "").strip()
    local_placeholder_keys = {"not-needed", "not-needed-for-local", "lm-studio"}
    if provider == "claude" and (not api_key or api_key in local_placeholder_keys):
        return "API Key Claude diperlukan untuk menggunakan provider ini"
    if provider == "openrouter" and (not api_key or api_key in local_placeholder_keys):
        return "API Key OpenRouter valid diperlukan untuk menggunakan provider ini"
    if provider == "mimo" and (not api_key or api_key in local_placeholder_keys):
        return "API Key Xiaomi MiMo diperlukan untuk menggunakan provider ini"
    if provider == "deepseek" and (not api_key or api_key in local_placeholder_keys):
        return "API Key DeepSeek diperlukan untuk menggunakan provider ini"
    return ""


def _price_per_million(raw_value: Any):
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return round(value * 1_000_000, 6)


def _format_openrouter_model(model: Dict[str, Any]) -> Dict[str, Any]:
    override = OPENROUTER_MODEL_OVERRIDES.get(model.get("id"))
    pricing = model.get("pricing") or {}
    prompt_per_m = _price_per_million(pricing.get("prompt"))
    completion_per_m = _price_per_million(pricing.get("completion"))
    formatted = {
        "id": model.get("id"),
        "name": model.get("name") or model.get("id"),
        "context_length": model.get("context_length"),
        "pricing": {
            "prompt_per_million": prompt_per_m,
            "completion_per_million": completion_per_m,
            "raw_prompt": pricing.get("prompt"),
            "raw_completion": pricing.get("completion"),
        },
    }
    if override:
        formatted["name"] = override.get("name", formatted["name"])
        formatted["context_length"] = override.get("context_length", formatted["context_length"])
        formatted["pricing"].update(override.get("pricing", {}))
        if override.get("note"):
            formatted["note"] = override["note"]
    return formatted

# Queue for human input in interactive mode
human_input_queue: asyncio.Queue = asyncio.Queue()
human_input_queues: Dict[str, asyncio.Queue] = {}


def _is_human_mode(mode: Any) -> bool:
    return str(mode or "").lower() in {"human", "interactive", "interaktif"}


def _human_queue_for(simulation_id: str) -> asyncio.Queue:
    sid = str(simulation_id)
    if sid not in human_input_queues:
        human_input_queues[sid] = asyncio.Queue()
    return human_input_queues[sid]

# Serve static files (legacy fallback only, not used for main UI)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve React build (frontend/dist) - primary UI
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="react_assets")


def _read_react_index_html() -> str:
    """Read the current Vite index so rebuilt asset names never go stale."""
    index_path = FRONTEND_DIST / "index.html"
    if FRONTEND_DIST.exists() and index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return ""


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve React SPA landing page."""
    react_index = _read_react_index_html()
    if react_index:
        return HTMLResponse(content=react_index)
    # Only fallback to legacy if React build doesn't exist
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    """Extract text from uploaded file (PDF, DOCX, TXT, MD)."""
    try:
        # Validate file extension
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return JSONResponse(
                {"error": f"Format file tidak didukung: {ext}. Format yang diizinkan: {', '.join(ALLOWED_EXTENSIONS)}"},
                status_code=400
            )

        # Sanitize filename to prevent path traversal
        original_name = _sanitize_filename(file.filename)
        safe_name = f"{uuid.uuid4().hex}_{original_name}"
        
        # Create temp directory if not exists
        temp_dir = temp_uploads_dir()
        temp_dir.mkdir(exist_ok=True)
        
        file_path = str(temp_dir / safe_name)
        logger.info(f"Menerima file untuk ekstraksi: {original_name}")

        # Check file size during upload
        size = 0
        try:
            with open(file_path, "wb") as buffer:
                while chunk := await file.read(8192):
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        return JSONResponse(
                            {"error": f"File terlalu besar. Maksimal {MAX_FILE_SIZE // (1024*1024)}MB"},
                            status_code=413
                        )
                    buffer.write(chunk)

            text = await asyncio.to_thread(extract_text_from_file, file_path, safe_name)
            logger.info(f"Hasil ekstraksi ({len(text)} karakter)")
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass
        
        if not text.strip():
            return JSONResponse({"error": "Gagal mengekstrak teks atau file kosong"}, status_code=400)
            
        return {"text": text}
    except Exception as e:
        logger.error(f"File extraction error: {e}")
        return JSONResponse({"error": f"Error: {str(e)}"}, status_code=500)

@app.post("/api/chat-revision")
async def chat_revision(request: Request):
    """Chat dengan AI untuk meminta revisi draf berdasarkan transcript."""
    body = await request.json()
    message = body.get("message", "")
    draft = body.get("draft", "")
    transcript = body.get("transcript", [])
    llm_config = body.get("llm_config", {})

    if not message:
        return JSONResponse({"error": "Pesan tidak boleh kosong"}, status_code=400)

    # Buat agent sementara untuk handle chat
    agent = PemohonAgent(llm_config=llm_config)
    
    # Format context untuk chat
    transcript_text = "\n".join([f"[{t['round']}] {t['speaker']}: {t['content'][:200]}..." for t in transcript[-10:]])
    
    prompt = f"""\
Anda adalah konsultan hukum ahli Mahkamah Konstitusi. 
Berikut adalah draf permohonan saat ini:
\"\"\"
{draft}
\"\"\"

Berikut adalah ringkasan jalannya persidangan simulasi:
\"\"\"
{transcript_text}
\"\"\"

User bertanya: "{message}"

Berikan saran perbaikan draf yang taktis dan mendalam berdasarkan kritik hakim atau bantahan pemerintah dalam sidang. 
Jika diminta merevisi teks, berikan potongan teks yang disarankan.
Jawablah dengan nada profesional dan membantu.
"""

    try:
        response = await agent.generate_response(prompt)
        return {"response": response}
    except Exception as e:
        logging.error(f"Chat error: {e}")
        return JSONResponse({"error": f"Gagal mendapatkan respon dari AI: {str(e)}"}, status_code=500)

@app.post("/api/simulate")
async def run_simulation(request: Request):
    """
    Endpoint untuk menjalankan simulasi.
    Mengembalikan SSE stream dari transcript secara real-time.
    """
    body = await request.json()
    draft = body.get("draft", "")
    jumlah_hakim = body.get("jumlah_hakim", 3)
    llm_config = body.get("llm_config", {})
    mode = body.get("mode", "ai")
    simulation_id = str(body.get("simulation_id") or uuid.uuid4().hex)
    judge_personas = body.get("judge_personas", None)
    hearing_mode = body.get("hearing_mode") or SimulationOrchestrator.DEFAULT_HEARING_MODE
    target_turn_range = body.get("target_turn_range")

    logger.info(f" Memulai simulasi dengan provider: {llm_config.get('provider')}, model: {llm_config.get('model_name')}, mode: {mode}")

    # Relax draft check for reconnections
    if simulation_id not in active_simulations and not draft.strip():
        if simulation_id in simulation_configs:
            draft = simulation_configs[simulation_id].get("draft", "")
        if not draft.strip():
            return JSONResponse({"error": "Draft permohonan tidak boleh kosong"}, status_code=400)

    # Store/update config
    if draft.strip():
        existing_config = simulation_configs.get(simulation_id, {})
        started_at = existing_config.get("started_at") or time.time()
        simulation_configs[simulation_id] = {
            "draft": draft,
            "jumlah_hakim": jumlah_hakim,
            "llm_config": llm_config,
            "mode": mode,
            "hearing_mode": hearing_mode,
            "target_turn_range": target_turn_range,
            "judge_personas": judge_personas,
            "project_id": body.get("project_id"),
            "started_at": started_at,
            "started_at_iso": existing_config.get("started_at_iso") or datetime.fromtimestamp(started_at).astimezone().isoformat(),
            **_public_llm_metadata(llm_config),
        }

    key_error = _llm_key_error(llm_config)
    if key_error:
        return JSONResponse({"error": key_error}, status_code=400)

    if simulation_id not in active_simulations and _active_simulation_count() >= MAX_PARALLEL_SIMULATIONS:
        return JSONResponse(
            {"error": f"Maksimal {MAX_PARALLEL_SIMULATIONS} simulasi berjalan bersamaan"},
            status_code=429
        )

    async def event_stream():
        """Generator SSE - kirim setiap interaksi ke client secara real-time menggunakan queue."""
        q = asyncio.Queue()
        
        # Inisialisasi list queue dan transcript untuk ID ini jika belum ada
        if simulation_id not in simulation_queues:
            simulation_queues[simulation_id] = []
        simulation_queues[simulation_id].append(q)

        if simulation_id not in simulation_transcripts:
            simulation_transcripts[simulation_id] = []

        try:
            # 1. Kirim semua event yang sudah terjadi (CATCH-UP)
            if simulation_id in simulation_transcripts:
                for event in simulation_transcripts[simulation_id]:
                    yield _sse_event(event["type"], event["data"])

            # 2. Jika simulasi belum berjalan, buat orchestrator dan task baru
            if simulation_id not in active_simulations:
                orch = StreamingOrchestrator(
                    simulation_id=simulation_id,
                    jumlah_hakim=jumlah_hakim,
                    llm_config=llm_config,
                    human_input_queue=_human_queue_for(simulation_id) if _is_human_mode(mode) else None,
                    judge_personas=judge_personas,
                    hearing_mode=hearing_mode,
                    target_turn_range=target_turn_range,
                )
                active_orchestrators[simulation_id] = orch
                
                # Kirim event "started"
                provider_name = llm_config.get("provider", "local").upper()
                config = simulation_configs.get(simulation_id, {})
                yield _sse_event("status", {
                    "message": f"Simulasi dimulai ({provider_name})...",
                    "phase": "init",
                    "simulation_id": simulation_id,
                    "started_at": config.get("started_at_iso"),
                    "hearing_mode": hearing_mode,
                    "target_turn_range": target_turn_range,
                    **_public_llm_metadata(llm_config),
                })
                
                # Jalankan task di background
                task = asyncio.create_task(orch.run_full_simulation_streaming(draft))
                active_simulations[simulation_id] = task
            else:
                yield _sse_event("status", {"message": "Menyambung kembali ke simulasi...", "phase": "reconnected", "simulation_id": simulation_id})

            # 3. Loop membaca antrian broadcast
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    if event == "DONE":
                        # Ambil hasil akhir: cek orchestrator dulu, fallback ke simulation_results
                        result = None
                        orch = active_orchestrators.get(simulation_id)
                        if orch and hasattr(orch, 'last_result'):
                            result = orch.last_result
                        if not result and simulation_id in simulation_results:
                            result = simulation_results[simulation_id]
                        
                        if result:
                            if result.get("scores"):
                                yield _sse_event("scores", result.get("scores", {}))
                            yield _sse_event("individual_scores", result.get("individual_scores", []))
                            if result.get("dissenting_opinions"):
                                yield _sse_event("dissenting_opinions", result.get("dissenting_opinions", []))
                            if result.get("feedback"):
                                yield _sse_event("feedback", result.get("feedback", {}))
                            if result.get("metadata"):
                                yield _sse_event("status", {
                                    "message": "Simulasi selesai",
                                    "phase": "done",
                                    **result.get("metadata", {}),
                                })
                        break
                    
                    yield event
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"

            yield _sse_event("status", {"message": "Simulasi selesai", "phase": "done"})
            yield _sse_event("done", {})

        except asyncio.CancelledError:
            logger.warning(f"WARNING Listener {simulation_id} terputus.")
        finally:
            # Cleanup: hapus queue listener ini
            if simulation_id in simulation_queues and q in simulation_queues[simulation_id]:
                simulation_queues[simulation_id].remove(q)
                if not simulation_queues[simulation_id]:
                    simulation_queues.pop(simulation_id, None)


    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


async def _stop_simulation_task(simulation_id: str) -> Dict[str, str]:
    task = active_simulations.get(simulation_id)
    # Beritahu listener bahwa simulasi dihentikan
    if simulation_id in simulation_queues:
        for q in simulation_queues[simulation_id]:
            try:
                q.put_nowait(_sse_event("status", {"message": "Simulasi dihentikan oleh pengguna", "phase": "stopped"}))
                q.put_nowait("DONE")
            except:
                pass
    
    if task and not task.done():
        task.cancel()
        logger.info(f"STOP Simulasi {simulation_id} dibatalkan paksa.")
        active_simulations.pop(simulation_id, None)
        active_orchestrators.pop(simulation_id, None)
        return {"status": "stopping", "simulation_id": simulation_id}
    
    return {"status": "no_active_simulation"}


@app.post("/api/stop/{simulation_id}")
async def stop_simulation_by_id(simulation_id: str):
    res = await _stop_simulation_task(simulation_id)
    # Hapus data memory saat di-stop paksa
    simulation_transcripts.pop(simulation_id, None)
    simulation_results.pop(simulation_id, None)
    return res


@app.get("/api/simulations/active")
async def list_active_simulations():
    """List semua ID simulasi yang sedang berjalan di memory."""
    _prune_finished_simulations()
    active_ids = [sim_id for sim_id, task in active_simulations.items() if not task.done()]
    return {
        "active_simulations": active_ids,
        "count": len(active_ids)
    }


@app.get("/api/simulations/{simulation_id}/transcript")
async def get_simulation_transcript(simulation_id: str):
    """Ambil transkrip simulasi yang sedang atau sudah berjalan dari memory."""
    if simulation_id not in simulation_transcripts and simulation_id not in active_simulations and simulation_id not in simulation_configs:
        return JSONResponse({"error": "Simulasi tidak ditemukan atau sudah dibersihkan"}, status_code=404)
    
    # Ensure transcript list exists
    if simulation_id not in simulation_transcripts:
        simulation_transcripts[simulation_id] = []
    
    # Cari status terakhir dari transcript jika tidak ada di active_simulations
    last_status = None
    for event in reversed(simulation_transcripts[simulation_id]):
        if event["type"] == "status":
            last_status = event["data"]
            break

    return {
        "simulation_id": simulation_id,
        "is_running": simulation_id in active_simulations and not active_simulations[simulation_id].done(),
        "transcript": simulation_transcripts.get(simulation_id, []),
        "results": simulation_results.get(simulation_id, {}),
        "status": last_status,
        "config": simulation_configs.get(simulation_id, {})
    }


@app.post("/api/stop")
async def stop_simulation(request: Request):
    """Endpoint kompatibilitas: hentikan simulasi tertentu, atau semua jika id tidak dikirim."""
    simulation_id = None
    try:
        body = await request.json()
        simulation_id = body.get("simulation_id")
    except Exception:
        simulation_id = None

    if simulation_id:
        return await _stop_simulation_task(str(simulation_id))

    stopped = []
    for sim_id, task in list(active_simulations.items()):
        if not task.done():
            task.cancel()
            stopped.append(sim_id)
    return {"status": "stopping" if stopped else "no_active_simulation", "stopped": stopped}


@app.post("/api/human_input")
async def receive_human_input(request: Request):
    """Terima input dari manusia (mode interaktif) dan masukkan ke queue."""
    body = await request.json()
    text = body.get("text", "").strip()
    simulation_id = str(body.get("simulation_id") or "").strip()
    if not text:
        return JSONResponse({"error": "Input tidak boleh kosong"}, status_code=400)

    target_queue = human_input_queues.get(simulation_id) if simulation_id else None
    if target_queue is None and simulation_id:
        orchestrator = active_orchestrators.get(simulation_id)
        target_queue = getattr(orchestrator, "human_input_queue", None) if orchestrator else None
    if target_queue is None:
        target_queue = human_input_queue

    target_queue.put_nowait(text)
    return {"status": "ok"}


@app.get("/api/progress")
async def get_progress():
    """Ambil riwayat progres simulasi dari file."""
    path = runtime_dir("progress") / "progress_history.json"
    if not path.exists():
        return {"history": []}
    try:
        return {"history": json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return {"history": []}


@app.post("/api/progress")
async def save_progress(request: Request):
    """Simpan entri progres simulasi ke file."""
    body = await request.json()
    path = runtime_dir("progress") / "progress_history.json"
    path.parent.mkdir(exist_ok=True)
    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    history.append(body)
    history = history[-20:]
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "total": len(history)}

@app.post("/api/improve-draft")
@app.post("/api/petition-blueprint")
async def improve_draft_with_intelligence_banks(request: Request):
    """
    Endpoint untuk memperbaiki draft permohonan PUU.
    Menggunakan Survive, Concern, Attack, dan Ratio Bank yang sudah dibangun.
    """
    body = await request.json()
    draft = body.get("draft") or body.get("description", "")
    improvement_notes = body.get("notes", "")
    llm_config = body.get("llm_config", {})

    if not draft.strip():
        return JSONResponse({"error": "Draft permohonan tidak boleh kosong"}, status_code=400)

    # Query intelligence banks
    survive_ctx = ""
    concern_ctx = ""
    attack_ctx = ""
    ratio_ctx = ""
    rag_ctx = ""
    if RAG_AVAILABLE:
        try:
            retriever = RAGRetriever()
            rag_ctx = retriever.query_for_agent(draft, agent_role="pemohon", n_results=7, use_intelligence_banks=False)
            survive_ctx = retriever.query_survive_bank(draft, n_results=7)
            concern_ctx = retriever.query_concern_bank(draft, n_results=7)
            attack_ctx = retriever.query_attack_bank(draft, n_results=7)
            ratio_ctx = retriever.query_ratio_bank(draft, n_results=7)
        except Exception as e:
            logger.warning(f"Gagal query intelligence bank: {e}")

    agent = JudicialReviewDraftAgent(llm_config=llm_config)
    prompt = (
        f"{IMPROVE_DRAFT_PROMPT}\n\n"
        f"=== DRAFT SAAT INI ===\n{draft}\n\n"
        f"=== CATATAN PERBAIKAN USER ===\n{improvement_notes or '(tidak ada catatan khusus)'}\n\n"
        f"=== SURVIVE BANK (jawaban Pemohon yang survive) ===\n{survive_ctx or '(tidak ada data)'}\n\n"
        f"=== JUDGE CONCERN BANK (concern/pertanyaan berulang Hakim) ===\n{concern_ctx or '(tidak ada data)'}\n\n"
        f"=== GOVERNMENT ATTACK BANK (pola serangan Pemerintah/DPR) ===\n{attack_ctx or '(tidak ada data)'}\n\n"
        f"=== RATIO BANK (ratio decidendi terstruktur) ===\n{ratio_ctx or '(tidak ada data)'}\n\n"
        f"=== RAG KNOWLEDGE BASE MK ===\n{rag_ctx or '(tidak ada data)'}\n\n"
        f"Perbaiki draft di atas menjadi naskah permohonan resmi yang lengkap. "
        f"Kembalikan HANYA teks draft resmi, tanpa JSON dan tanpa metadata revisi."
    )

    try:
        raw = await agent.generate_response(prompt)
        # Coba parse JSON dari respons
        start = raw.find('{')
        end = raw.rfind('}') + 1
        parsed = None
        if start != -1 and end > 0:
            try:
                parsed = json.loads(raw[start:end])
            except Exception:
                pass

        draft_revisi = ""
        if isinstance(parsed, dict):
            draft_revisi = parsed.get("draft_revisi", "")
        draft_revisi = _extract_draft_text(draft_revisi or raw)

        return {
            "draft_revisi": draft_revisi,
            "revision_json": parsed,
            # Backward-compatible keys for older frontend calls.
            "blueprint": draft_revisi,
            "blueprint_json": parsed,
            "sources": {
                "survive_bank_used": bool(survive_ctx),
                "concern_bank_used": bool(concern_ctx),
                "attack_bank_used": bool(attack_ctx),
                "ratio_bank_used": bool(ratio_ctx),
            }
        }
    except Exception as e:
        logger.error(f"Draft improvement error: {e}")
        return JSONResponse({"error": f"Gagal memperbaiki draft: {str(e)}"}, status_code=500)


@app.post("/api/improve-draft-stream")
async def improve_draft_stream(request: Request):
    """
    Streaming endpoint untuk memperbaiki draft permohonan PUU.
    Mengirim token draft revisi secara live agar frontend bisa menampilkan bubble chat.
    """
    body = await request.json()
    draft = body.get("draft", "")
    improvement_notes = body.get("notes", "")
    llm_config = body.get("llm_config", {})

    if not draft.strip():
        return JSONResponse({"error": "Draft permohonan tidak boleh kosong"}, status_code=400)

    async def event_stream():
        yield _sse_event("status", {"message": "Mengambil data dari intelligence banks...", "phase": "retrieving"})

        survive_ctx = ""
        concern_ctx = ""
        attack_ctx = ""
        ratio_ctx = ""
        rag_ctx = ""
        if RAG_AVAILABLE:
            try:
                retriever = RAGRetriever()
                rag_ctx = retriever.query_for_agent(draft, agent_role="pemohon", n_results=7, use_intelligence_banks=False)
                survive_ctx = retriever.query_survive_bank(draft, n_results=7)
                concern_ctx = retriever.query_concern_bank(draft, n_results=7)
                attack_ctx = retriever.query_attack_bank(draft, n_results=7)
                ratio_ctx = retriever.query_ratio_bank(draft, n_results=7)
            except Exception as e:
                logger.warning(f"Gagal query intelligence bank: {e}")
                yield _sse_event("warning", {"message": f"Gagal query intelligence bank: {str(e)[:160]}"})

        yield _sse_event("sources", {
            "survive_bank_used": bool(survive_ctx),
            "concern_bank_used": bool(concern_ctx),
            "attack_bank_used": bool(attack_ctx),
            "ratio_bank_used": bool(ratio_ctx),
        })
        yield _sse_event("status", {"message": "Menyusun draft revisi...", "phase": "generating"})

        agent = JudicialReviewDraftAgent(llm_config=llm_config)

        prompt = (
            "Anda adalah Reviser Senior Permohonan Pengujian Undang-Undang (PUU) Mahkamah Konstitusi.\n"
            "Perbaiki draft user menjadi NASKAH PERMOHONAN RESMI yang siap dipakai untuk pengujian undang-undang.\n"
            "Kembalikan HANYA TEKS DRAFT RESMI. DILARANG mengembalikan JSON, markdown code block, ringkasan_perubahan, alasan_perubahan, aspek_diperbaiki, bank_data_digunakan, atau catatan di luar naskah.\n"
            "DILARANG menulis bentuk playbook seperti 'Majelis Hakim mungkin menanyakan...' atau 'Pemohon menjawab...'. Semua antisipasi harus dilebur menjadi dalil resmi dalam posita.\n\n"
            "Struktur keluaran wajib menyerupai permohonan PUU resmi:\n"
            "JUDUL PERMOHONAN\n"
            "I. IDENTITAS DAN KEDUDUKAN HUKUM PEMOHON\n"
            "II. KEWENANGAN MAHKAMAH KONSTITUSI\n"
            "III. NORMA YANG DIUJI DAN BATU UJI\n"
            "IV. ALASAN-ALASAN PERMOHONAN / POSITA\n"
            "V. PETITUM\n"
            "VI. DAFTAR BUKTI\n\n"
            "Gunakan intelligence bank berikut secara taktis:\n"
            "- SURVIVE BANK untuk formulasi Pemohon yang terbukti kuat.\n"
            "- JUDGE CONCERN BANK untuk mengantisipasi concern hakim.\n"
            "- GOVERNMENT ATTACK BANK untuk membentengi dari serangan Pemerintah/DPR.\n"
            "- RATIO BANK untuk memperkuat ratio, dalil, dan konsistensi putusan.\n\n"
            "Aturan revisi:\n"
            "- Pertahankan norma yang diuji, identitas Pemohon, dan batu uji jika sudah disebutkan.\n"
            "- WAJIB gunakan objek norma, nomor UU, tahun UU, dan pasal yang ada dalam draft awal. Jangan pakai placeholder seperti 'Pasal ...', 'UU No. ...', 'huruf ...', atau 'ayat ...'.\n"
            "- Perjelas legal standing, kerugian konstitusional, kausalitas, norma vs implementasi, dan petitum.\n"
            "- Jangan mengarang nomor putusan. Jika bank tidak memberi nomor jelas, gunakan formulasi umum.\n\n"
            f"=== DRAFT AWAL ===\n{draft}\n\n"
            f"=== CATATAN PERBAIKAN USER ===\n{improvement_notes or '(tidak ada catatan khusus)'}\n\n"
            f"=== SURVIVE BANK ===\n{survive_ctx or '(tidak ada data)'}\n\n"
            f"=== JUDGE CONCERN BANK ===\n{concern_ctx or '(tidak ada data)'}\n\n"
            f"=== GOVERNMENT ATTACK BANK ===\n{attack_ctx or '(tidak ada data)'}\n\n"
            f"=== RATIO BANK ===\n{ratio_ctx or '(tidak ada data)'}\n\n"
            f"=== RAG KNOWLEDGE BASE MK ===\n{rag_ctx or '(tidak ada data)'}\n\n"
            "Mulai langsung dari judul permohonan resmi. Akhiri dengan penutup formal Pemohon/Kuasa Hukum."
        )

        q: asyncio.Queue = asyncio.Queue()

        async def on_chunk(chunk: str):
            q.put_nowait(chunk)

        task = asyncio.create_task(agent.generate_response(prompt, on_chunk=on_chunk))
        streamed_text = ""

        while not task.done():
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=15.0)
                streamed_text += chunk
                yield _sse_event("draft_chunk", {"chunk": chunk})
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

        try:
            final_draft = await task
            while not q.empty():
                chunk = q.get_nowait()
                streamed_text += chunk
                yield _sse_event("draft_chunk", {"chunk": chunk})
            final_clean = _extract_draft_text(final_draft or streamed_text)
            if final_clean and final_clean != streamed_text:
                # In case the provider did not stream all filtered content, sync the final text.
                yield _sse_event("draft_final", {"draft": final_clean})
            else:
                yield _sse_event("draft_final", {"draft": final_clean or streamed_text or final_draft})
            yield _sse_event("status", {"message": "Draft revisi selesai", "phase": "done"})
        except Exception as e:
            logger.error(f"Streaming draft improvement error: {e}")
            yield _sse_event("error", {"message": f"Gagal memperbaiki draft: {str(e)}"})

        yield _sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/hearing-playbook")
async def generate_hearing_playbook(request: Request):
    """
    Endpoint untuk menghasilkan hearing playbook berdasarkan draft permohonan.
    Menggunakan Attack Bank, Concern Bank, dan Survive Bank.
    """
    body = await request.json()
    draft = body.get("draft", "")
    llm_config = body.get("llm_config", {})
    simulation_feedback = body.get("simulation_feedback", {})

    if not draft.strip():
        return JSONResponse({"error": "Draft tidak boleh kosong"}, status_code=400)

    if not AGENT7_PLAYBOOK_PROMPT:
        return JSONResponse({"error": "Prompt playbook tidak tersedia"}, status_code=500)

    # Query intelligence banks
    attack_ctx = ""
    concern_ctx = ""
    survive_ctx = ""
    if RAG_AVAILABLE:
        try:
            retriever = RAGRetriever()
            attack_ctx = retriever.query_attack_bank(draft, n_results=5)
            concern_ctx = retriever.query_concern_bank(draft, n_results=5)
            survive_ctx = retriever.query_survive_bank(draft, n_results=5)
        except Exception as e:
            logger.warning(f"Gagal query intelligence bank: {e}")

    agent = PemohonAgent(llm_config=llm_config)
    prompt = (
        f"{AGENT7_PLAYBOOK_PROMPT}\n\n"
        f"=== DRAFT PERMOHONAN ===\n{draft}\n\n"
        f"=== GOVERNMENT ATTACK BANK ===\n{attack_ctx or '(tidak ada data)'}\n\n"
        f"=== JUDGE CONCERN BANK ===\n{concern_ctx or '(tidak ada data)'}\n\n"
        f"=== SURVIVE BANK ===\n{survive_ctx or '(tidak ada data)'}\n\n"
        f"=== FEEDBACK SIMULASI ===\n{json.dumps(simulation_feedback, ensure_ascii=False)}\n\n"
        f"Susun hearing playbook berdasarkan data di atas. "
        f"Kembalikan HANYA JSON sesuai format yang diminta."
    )

    try:
        playbook = await agent.generate_response(prompt)
        # Coba parse JSON dari respons
        start = playbook.find('{')
        end = playbook.rfind('}') + 1
        parsed = None
        if start != -1 and end > 0:
            try:
                parsed = json.loads(playbook[start:end])
            except Exception:
                pass
        return {
            "playbook": playbook,
            "playbook_json": parsed,
            "sources": {
                "attack_bank_used": bool(attack_ctx),
                "concern_bank_used": bool(concern_ctx),
                "survive_bank_used": bool(survive_ctx)
            }
        }
    except Exception as e:
        logger.error(f"Playbook generation error: {e}")
        return JSONResponse({"error": f"Gagal generate playbook: {str(e)}"}, status_code=500)


@app.post("/api/self-correcting")
async def run_self_correcting(request: Request):
    """
    Endpoint untuk menjalankan close-loop self-correcting draft revision.
    Mengembalikan SSE stream dengan event per loop.
    """
    if not SELF_CORRECTING_AVAILABLE:
        return JSONResponse(
            {"error": "Self-correcting loop tidak tersedia. Periksa dependensi."},
            status_code=503
        )

    body = await request.json()
    draft = body.get("draft", "")
    jumlah_hakim = body.get("jumlah_hakim", 3)
    llm_config = body.get("llm_config", {})
    defaults = _load_self_correcting_defaults()
    max_loops = int(body.get("max_loops", defaults.get("max_loops", 5)))
    acceptance_threshold = int(body.get("acceptance_threshold", defaults.get("acceptance_threshold", 70)))
    log_dir = body.get("log_dir", defaults.get("log_dir", "results/self_correcting_logs"))

    if not draft.strip():
        return JSONResponse({"error": "Draft permohonan tidak boleh kosong"}, status_code=400)

    key_error = _llm_key_error(llm_config)
    if key_error:
        return JSONResponse({"error": key_error}, status_code=400)

    async def event_stream():
        # Padding awal membantu browser/proxy segera membuka stream, tidak menunggu operasi berat.
        yield ": auto-correct stream opened\n\n"
        yield _sse_event("status", {
            "message": f"Self-correcting loop dimulai (max {max_loops} iterasi)...",
            "phase": "init"
        })

        try:
            q = asyncio.Queue()
            loop = SelfCorrectingLoop(
                draft_input=draft,
                llm_config=llm_config,
                max_loops=max_loops,
                acceptance_threshold=acceptance_threshold,
                jumlah_hakim=jumlah_hakim,
                log_dir=log_dir,
                event_queue=q,
                # Retriever dimuat lazy di loop/revisi agar stream awal tidak tertahan.
                retriever=None
            )

            task = asyncio.create_task(loop.run())
            active_simulations["current"] = task

            # Baca event dari queue selama task berjalan
            while not task.done():
                try:
                    event_type, data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield _sse_event(event_type, data)
                except asyncio.TimeoutError:
                    yield _sse_event("status", {
                        "message": "Auto-Correct masih berjalan - menunggu respons agen/RAG...",
                        "phase": "running"
                    })
                    yield ": keep-alive\n\n"

            # Ambil hasil akhir
            result = await task
            yield _sse_event("final_result", result)
            yield _sse_event("status", {"message": "Loop selesai", "phase": "done"})
        except asyncio.CancelledError:
            yield _sse_event("status", {"message": "Loop dibatalkan", "phase": "stopped"})
        except Exception as e:
            logger.exception("Self-correcting stream gagal")
            yield _sse_event("error", {"message": f"Auto-Correct gagal di server: {str(e)}"})
        finally:
            active_simulations.pop("current", None)

        yield _sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/mimo/models")
async def get_mimo_models():
    """
    Ambil daftar model Xiaomi MiMo yang tersedia.
    Harga belum tersedia publik, jadi pricing bersifat informatif.
    """
    from core.llm_client import MIMO_MODELS, MIMO_BASE_URL, MIMO_DEFAULT_MODEL
    return {
        "models": MIMO_MODELS,
        "default_model": MIMO_DEFAULT_MODEL,
        "base_url": MIMO_BASE_URL,
        "source": "https://platform.xiaomimimo.com/docs/en-US/api/chat/openai-api",
    }


@app.get("/api/deepseek/models")
async def get_deepseek_models():
    """
    Ambil daftar model DeepSeek native beserta harga resmi per 1 juta token.
    Context caching DeepSeek aktif default; biaya cache hit/miss dipisah.
    """
    from core.llm_client import DEEPSEEK_MODELS, DEEPSEEK_BASE_URL, DEEPSEEK_DEFAULT_MODEL
    return {
        "models": DEEPSEEK_MODELS,
        "default_model": DEEPSEEK_DEFAULT_MODEL,
        "base_url": DEEPSEEK_BASE_URL,
        "source": "https://api-docs.deepseek.com/quick_start/pricing",
    }


@app.get("/api/openrouter/models")
async def get_openrouter_models():
    """
    Ambil daftar model OpenRouter yang direkomendasikan beserta harga live.
    Harga dari OpenRouter API berupa USD per token; endpoint ini mengubahnya
    menjadi USD per 1 juta token agar mudah dibaca di UI.
    """
    now = time.time()
    cached = health_cache.get("openrouter_models")
    if cached and now - cached.get("timestamp", 0) < 3600:
        return cached["data"]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(OPENROUTER_MODELS_URL)
            resp.raise_for_status()
            raw_models = resp.json().get("data", [])
    except Exception as e:
        logger.warning(f"Gagal mengambil daftar model OpenRouter: {e}")
        return JSONResponse(
            {"error": f"Gagal mengambil daftar model OpenRouter: {str(e)}"},
            status_code=502,
        )

    by_id = {m.get("id"): m for m in raw_models if m.get("id")}
    recommended = []
    for model_id in OPENROUTER_RECOMMENDED_MODELS:
        model = by_id.get(model_id)
        if model:
            recommended.append(_format_openrouter_model(model))

    free_models = [
        _format_openrouter_model(m)
        for m in raw_models
        if str((m.get("pricing") or {}).get("prompt")) == "0"
        and str((m.get("pricing") or {}).get("completion")) == "0"
    ][:5]

    payload = {
        "models": recommended,
        "free_models": free_models,
        "source": OPENROUTER_MODELS_URL,
        "retrieved_at": now,
    }
    health_cache["openrouter_models"] = {"timestamp": now, "data": payload}
    return payload


@app.get("/api/health")
async def health(url: str = None):
    """Health check & RAG/LLM status."""
    now = time.time()
    check_url = url or os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    base = check_url.rstrip("/")

    rag_status = "unavailable"
    rag_vectors = 0
    rag_data_manifest = load_rag_manifest()
    # Hindari init RAG berat pada polling UI; health hanya perlu statistik ChromaDB.
    if health_cache.get("rag_data") and now - health_cache.get("rag_timestamp", 0) < 120:
        rag_cached = health_cache["rag_data"]
        rag_status = rag_cached.get("rag", "unavailable")
        rag_vectors = rag_cached.get("rag_vectors", 0)
        intelligence_status = dict(rag_cached.get("intelligence_banks", {}))
        rag_data_manifest = rag_cached.get("rag_data", rag_data_manifest)
    else:
        try:
            rag_cached = await asyncio.to_thread(_get_chroma_stats_lightweight)
            rag_status = rag_cached.get("rag", "unavailable")
            rag_vectors = rag_cached.get("rag_vectors", 0)
            intelligence_status = dict(rag_cached.get("intelligence_banks", {}))
            rag_data_manifest = rag_cached.get("rag_data", rag_data_manifest)
        except Exception as e:
            rag_status = f"error: {str(e)[:100]}"
            intelligence_status = {}
        health_cache["rag_timestamp"] = now
        health_cache["rag_data"] = {
            "rag": rag_status,
            "rag_vectors": rag_vectors,
            "intelligence_banks": intelligence_status,
            "rag_data": rag_data_manifest,
        }

    # LLM connectivity check
    llm_status = "unknown"
    llm_cache = health_cache.setdefault("llm", {})
    llm_cached = llm_cache.get(base)
    if llm_cached and now - llm_cached.get("timestamp", 0) < 10:
        llm_status = llm_cached.get("llm", "unknown")
    else:
        try:
            # Coba panggil models endpoint (standard OpenAI spec)
            async with httpx.AsyncClient() as client:
                # Pastikan URL berakhir dengan /v1 jika tidak ada
                test_url = f"{base}/models" if "/v1" in base else f"{base}/v1/models"

                resp = await client.get(test_url, timeout=5.0)
                if resp.status_code == 200:
                    llm_status = "connected"
                else:
                    llm_status = f"status: {resp.status_code}"
        except httpx.ConnectError:
            llm_status = "connection_refused"
        except httpx.TimeoutException:
            llm_status = "timeout"
        except Exception as e:
            llm_status = f"error: {str(e)[:50]}"
        llm_cache[base] = {"timestamp": now, "llm": llm_status}

    data = {
        "status": "ok",
        "rag": rag_status,
        "rag_vectors": rag_vectors,
        "intelligence_banks": intelligence_status,
        "rag_data": rag_data_manifest,
        "llm": llm_status,
        "llm_url": check_url
    }
    return data


@app.get("/api/rag-data/status")
async def rag_data_status():
    """Return installed RAG data manifest without probing ChromaDB."""
    return load_rag_manifest()


def _sse_event(event_type: str, data: Any) -> str:
    """Format SSE event string."""
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


def _extract_draft_text(raw: str) -> str:
    """Ambil hanya naskah draft dari output reviser, walau model mengembalikan JSON."""
    if not raw:
        return ""

    text = raw.strip()

    # Case 1: valid JSON object with draft_revisi.
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start:end])
            if isinstance(parsed, dict) and parsed.get("draft_revisi"):
                return str(parsed["draft_revisi"]).strip()
        except Exception:
            pass

    # Case 2: leaked JSON tail after draft text.
    markers = [
        '\n  "ringkasan_perubahan"',
        '\n"ringkasan_perubahan"',
        '", "ringkasan_perubahan"',
        '",\n  "ringkasan_perubahan"',
        '\n  "alasan_perubahan"',
        '\n"alasan_perubahan"',
    ]
    cut_at = -1
    for marker in markers:
        idx = text.find(marker)
        if idx != -1:
            cut_at = idx if cut_at == -1 else min(cut_at, idx)
    if cut_at != -1:
        text = text[:cut_at]

    # Case 3: starts like a JSON field but JSON parsing failed.
    prefixes = ['{"draft_revisi":', '"draft_revisi":']
    for prefix in prefixes:
        if text.lstrip().startswith(prefix):
            text = text[text.find(":") + 1:].strip()
            break

    return text.strip().strip(",").strip().strip('"').replace("\\n", "\n")


def _looks_like_incomplete_permohonan(text: str, mode: str = "") -> str:
    """Return a reason when a generated petition is clearly only a tail/note fragment."""
    normalized = _re.sub(r"\s+", " ", text or "").strip().lower()
    if not normalized:
        return "output kosong"
    main_text = normalized.split("catatan drafter", 1)[0]
    has_core_section = any(
        marker in main_text
        for marker in [
            "kewenangan mahkamah",
            "kedudukan hukum",
            "alasan permohonan",
            "posita",
            "objek pengujian",
            "petitum",
        ]
    )
    starts_like_tail = normalized.startswith((
        "majelis hakim mahkamah konstitusi agar berkenan",
        "hormat kami",
        "jakarta,",
        "[ditandatangani]",
        "catatan drafter",
    ))
    if starts_like_tail and not has_core_section:
        return "output hanya berisi penutup/catatan drafter, badan permohonan tidak ada"
    if mode == "improve_existing_draft" and "catatan drafter" in normalized and len(main_text) < 1800:
        return "badan permohonan terlalu pendek sebelum CATATAN DRAFTER"
    if mode == "improve_existing_draft" and not has_core_section:
        return "bagian inti permohonan tidak terdeteksi"
    return ""


def _permohonan_status_with_runtime() -> Dict[str, Any]:
    status = get_corpus_status()
    if permohonan_index_task and not permohonan_index_task.done():
        progress = get_corpus_progress()
        if progress:
            status.update(progress)
        status["status"] = "running"
        status["started_at"] = status.get("started_at") or permohonan_index_started_at
    if permohonan_index_error:
        status["last_error"] = permohonan_index_error
        if status.get("status") in {"not_started", "stale"}:
            status["status"] = "failed"
    return status


async def _run_permohonan_reindex_job() -> None:
    global permohonan_index_error
    try:
        await asyncio.to_thread(index_permohonan_corpus, use_ocr=True)
        permohonan_index_error = None
    except Exception as exc:
        permohonan_index_error = str(exc)
        logger.error(f"Permohonan corpus indexing failed: {exc}")


def _flatten_for_query(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_for_query(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_for_query(v) for v in value)
    return str(value or "")


def _build_permohonan_query(user_input: Dict[str, Any], uploaded_draft: Dict[str, Any]) -> str:
    parts = [
        user_input.get("uu_diuji"),
        user_input.get("pasal_diuji"),
        user_input.get("batu_uji_uud"),
        user_input.get("kerugian_konstitusional"),
        user_input.get("alasan_permohonan"),
        user_input.get("catatan_strategi"),
        user_input.get("instruksi_tambahan"),
        (uploaded_draft or {}).get("raw_text", "")[:2000],
    ]
    query = " ".join(_flatten_for_query(part) for part in parts).strip()
    return query[:6000] or "permohonan pengujian undang-undang Mahkamah Konstitusi"


def _extract_norm_reference_query(text: str) -> str:
    """Build a short Pasal.id query from legal norm references in a long draft."""
    if not text:
        return ""
    compact = _re.sub(r"\s+", " ", text)

    pph_match = _re.search(
        r"Pasal\s+4\s+ayat\s+\(1\)\s+huruf\s+a",
        compact,
        flags=_re.IGNORECASE,
    )
    if pph_match and _re.search(r"Pajak\s+Penghasilan|UU\s+PPh", compact, flags=_re.IGNORECASE):
        phrase = ""
        phrase_match = _re.search(r"frasa\s+\"([^\"]+)\"", compact, flags=_re.IGNORECASE)
        if phrase_match:
            phrase = f" {phrase_match.group(1)}"
        return f"UU Pajak Penghasilan Pasal 4 ayat (1) huruf a{phrase}".strip()

    candidates: List[str] = []

    for pattern in [
        r"frasa\s+\"[^\"]+\"\s+dalam\s+Pasal\s+[^.]{0,160}",
        r"Pasal\s+\d+[A-Za-z]?(?:\s+ayat\s+\([^)]+\))?(?:\s+huruf\s+[a-z])?[^.]{0,180}",
        r"Undang-Undang\s+Nomor\s+\d+\s+Tahun\s+\d{4}[^.]{0,120}",
        r"UU\s+Nomor\s+\d+\s+Tahun\s+\d{4}[^.]{0,120}",
        r"UU\s+PPh[^.]{0,120}",
        r"Pajak\s+Penghasilan[^.]{0,140}",
    ]:
        for match in _re.finditer(pattern, compact, flags=_re.IGNORECASE):
            value = match.group(0).strip(" .;")
            if value and value.lower() not in [item.lower() for item in candidates]:
                candidates.append(value)
            if len(candidates) >= 5:
                break
        if len(candidates) >= 5:
            break

    query = " ".join(candidates)
    return query[:260].strip()


_REFERENCE_TOPIC_GROUPS: List[Dict[str, Any]] = [
    {
        "id": "pph",
        "label": "Pajak Penghasilan",
        "patterns": [
            r"\bpajak\s+penghasilan\b",
            r"\bUU\s+PPh\b",
            r"\bPPh\b",
            r"nomor\s+7\s+tahun\s+1983",
            r"nomor\s+36\s+tahun\s+2008",
        ],
        "queries": [
            "UU Pajak Penghasilan",
            "Pajak Penghasilan Pasal 4 ayat (1)",
            "Undang-Undang Nomor 36 Tahun 2008 Pajak Penghasilan",
            "Undang-Undang Nomor 7 Tahun 1983 Pajak Penghasilan",
        ],
    },
    {
        "id": "uud1945",
        "label": "Undang-Undang Dasar 1945",
        "patterns": [
            r"\bUUD\s*(?:NRI\s*)?1945\b",
            r"Undang-Undang\s+Dasar\s+Negara\s+Republik\s+Indonesia\s+Tahun\s+1945",
            r"Undang-Undang\s+Dasar\s+1945",
            r"\bPasal\s+28D\b",
            r"\bPasal\s+23A\b",
        ],
        "queries": [
            "Undang-Undang Dasar 1945",
        ],
    },
    {
        "id": "mk",
        "label": "Mahkamah Konstitusi",
        "patterns": [
            r"\bUU\s+MK\b",
            r"Mahkamah\s+Konstitusi",
            r"nomor\s+24\s+tahun\s+2003",
            r"\bPasal\s+51\b",
        ],
        "queries": [
            "UU Mahkamah Konstitusi Pasal 51 ayat (1)",
            "Undang-Undang Nomor 24 Tahun 2003 Mahkamah Konstitusi",
        ],
    },
]


def _flatten_transcript_for_references(transcript: Any, limit: int = 8) -> str:
    """Keep only the latest hearing discussion for reference search context."""
    if isinstance(transcript, str):
        return _re.sub(r"\s+", " ", transcript)[-5000:]
    if not isinstance(transcript, list):
        return ""

    parts: List[str] = []
    for entry in transcript[-limit:]:
        if isinstance(entry, dict):
            speaker = str(entry.get("speaker") or entry.get("role") or "")
            content = str(entry.get("content") or "")
            if content.strip():
                parts.append(f"{speaker}: {content}")
        elif entry:
            parts.append(str(entry))
    return _re.sub(r"\s+", " ", " ".join(parts)).strip()[-5000:]


def _reference_topic_groups(text: str) -> List[Dict[str, Any]]:
    compact = _re.sub(r"\s+", " ", text or "")
    groups: List[Dict[str, Any]] = []
    for group in _REFERENCE_TOPIC_GROUPS:
        patterns = group.get("patterns", [])
        if any(_re.search(str(pattern), compact, flags=_re.IGNORECASE) for pattern in patterns):
            groups.append(group)
    return groups


def _reference_matches_topic(text: str, groups: List[Dict[str, Any]]) -> bool:
    if not groups:
        return True
    compact = _re.sub(r"\s+", " ", text or "")
    for group in groups:
        patterns = group.get("patterns", [])
        if any(_re.search(str(pattern), compact, flags=_re.IGNORECASE) for pattern in patterns):
            return True
        label = str(group.get("label") or "")
        if label and label.lower() in compact.lower():
            return True
    return False


def _build_simulation_reference_queries(draft: str, transcript: Any = None, limit: int = 5) -> List[str]:
    """Extract compact Pasal.id searches from the active hearing context."""
    discussion = _flatten_transcript_for_references(transcript)
    compact = _re.sub(r"\s+", " ", f"{discussion} {draft or ''}").strip()
    if not compact:
        return []

    queries: List[str] = []

    def add_query(value: str) -> None:
        clean = _re.sub(r"\s+", " ", value or "").strip(" .;,:")
        clean = _re.sub(r"^(?:bahwa|dan|atau)\s+", "", clean, flags=_re.IGNORECASE).strip()
        clean = _re.sub(r"\s+terhadap\s+Pasal\s+.*$", "", clean, flags=_re.IGNORECASE).strip()
        if len(clean) < 6:
            return
        if clean.lower() not in [item.lower() for item in queries]:
            queries.append(clean[:180])

    targeted_patterns = [
        r"Pasal\s+\d+[A-Za-z]?(?:\s+ayat\s+\([^)]+\))?(?:\s+huruf\s+[a-z])?(?:\s+angka\s+\d+)?[^.;]{0,120}(?:Undang-Undang|UU)\s+(?:Nomor\s+\d+\s+Tahun\s+\d{4}|No\.?\s*\d+\s+Tahun\s+\d{4}|[A-Z][^.;]{2,80})",
        r"(?:Undang-Undang|UU)\s+(?:Nomor\s+\d+\s+Tahun\s+\d{4}|No\.?\s*\d+\s+Tahun\s+\d{4})[^.;]{0,120}",
        r"(?:UU|Undang-Undang)\s+[A-Z][A-Za-z0-9\s.\-/]{2,70}",
        r"Pasal\s+\d+[A-Za-z]?(?:\s+ayat\s+\([^)]+\))?(?:\s+huruf\s+[a-z])?[^.;]{0,80}",
    ]

    for pattern in targeted_patterns:
        for match in _re.finditer(pattern, compact, flags=_re.IGNORECASE):
            add_query(match.group(0))
            if len(queries) >= limit:
                return queries

    for match in _re.finditer(
        r"Pasal\s+(28D|23A)(?:\s+ayat\s+\([^)]+\))?",
        compact,
        flags=_re.IGNORECASE,
    ):
        add_query(f"{match.group(0)} UUD 1945")
        if len(queries) >= limit:
            return queries

    topic_groups = _reference_topic_groups(compact)
    for group in topic_groups:
        for query in group.get("queries", []):
            add_query(str(query))
            if len(queries) >= limit:
                return queries

    topical_fallbacks = [
        ("Pajak Penghasilan", "UU Pajak Penghasilan"),
        ("Cipta Kerja", "UU Cipta Kerja"),
        ("Pemilu", "UU Pemilu"),
        ("Ketenagakerjaan", "UU Ketenagakerjaan"),
        ("KPK", "UU Komisi Pemberantasan Korupsi"),
        ("ITE", "UU Informasi dan Transaksi Elektronik"),
        ("Minerba", "UU Mineral dan Batubara"),
    ]
    lowered = compact.lower()
    for marker, query in topical_fallbacks:
        if marker.lower() in lowered:
            add_query(query)
            if len(queries) >= limit:
                return queries

    fallback = _extract_norm_reference_query(compact)
    if fallback:
        add_query(fallback)

    return queries[:limit]


def _reference_topic_keywords(draft: str) -> List[str]:
    compact = _re.sub(r"\s+", " ", draft or "")
    keywords = [str(group.get("label")) for group in _reference_topic_groups(compact)]

    for pattern in [
        r"(?:Undang-Undang|UU)\s+Nomor\s+\d+\s+Tahun\s+\d{4}",
        r"(?:Undang-Undang|UU)\s+No\.?\s*\d+\s+Tahun\s+\d{4}",
    ]:
        for match in _re.finditer(pattern, compact, flags=_re.IGNORECASE):
            keywords.append(match.group(0).replace("No.", "Nomor"))

    topical_markers = [
        "Pajak Penghasilan",
        "Cipta Kerja",
        "Pemilu",
        "Ketenagakerjaan",
        "Komisi Pemberantasan Korupsi",
        "Informasi dan Transaksi Elektronik",
        "Mineral dan Batubara",
    ]
    for marker in topical_markers:
        if marker.lower() in compact.lower():
            keywords.append(marker)

    if _re.search(r"\bUU\s+PPh\b|\bPPh\b", compact, flags=_re.IGNORECASE):
        keywords.append("Pajak Penghasilan")

    deduped: List[str] = []
    for keyword in keywords:
        if keyword.lower() not in [item.lower() for item in deduped]:
            deduped.append(keyword)
    return deduped[:4]


def _pasal_id_type_for_reference_query(query: str) -> str:
    if _re.search(r"\bUUD\b|Undang-Undang\s+Dasar|1945", query or "", flags=_re.IGNORECASE):
        return "UUD"
    if _re.search(r"\bPP\b|Peraturan\s+Pemerintah", query or "", flags=_re.IGNORECASE):
        return "PP"
    return "UU"


def _article_number_sort_key(article: Dict[str, Any]) -> tuple:
    raw = str(article.get("number") or "")
    match = _re.match(r"^(\d+)([A-Za-z]*)$", raw)
    if match:
        return (0, int(match.group(1)), match.group(2))
    return (1, int(article.get("sort_order") or 0), raw)


def _format_law_articles(articles: List[Dict[str, Any]], max_chars: int = 120_000) -> tuple[str, bool]:
    parts: List[str] = []
    total = 0
    truncated = False

    for article in sorted(articles, key=_article_number_sort_key):
        number = str(article.get("number") or "").strip()
        heading = str(article.get("heading") or "").strip()
        content = str(article.get("content") or "").strip()
        if not number and not heading and not content:
            continue

        header = f"Pasal {number}".strip() if number else "Pasal"
        section = header
        if heading:
            section += f"\n{heading}"
        if content:
            section += f"\n{content}"
        if total + len(section) > max_chars:
            truncated = True
            remaining = max_chars - total
            if remaining > 500:
                parts.append(section[:remaining].rstrip())
            break
        parts.append(section)
        total += len(section)

    return "\n\n".join(parts).strip(), truncated


def _extract_requested_article_numbers(*texts: str) -> List[str]:
    numbers: List[str] = []
    for text in texts:
        for match in _re.finditer(r"\bPasal\s+(\d+[A-Za-z]?|[IVXLC]+)\b", text or "", flags=_re.IGNORECASE):
            value = match.group(1).upper()
            if value not in numbers:
                numbers.append(value)
    return numbers


def _format_relevant_articles(articles: List[Dict[str, Any]], article_numbers: List[str]) -> str:
    if not article_numbers:
        return ""
    wanted = {number.upper() for number in article_numbers}
    selected = [
        article for article in articles
        if str(article.get("number") or "").strip().upper() in wanted
    ]
    text, _ = _format_law_articles(selected, max_chars=40_000)
    return text


async def _extract_pdf_text_for_reader(pdf_url: str, pdf_text_cache: Dict[str, str]) -> str:
    if not pdf_url:
        return ""
    if pdf_url in pdf_text_cache:
        return pdf_text_cache[pdf_url]
    try:
        import fitz

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(pdf_url, timeout=20.0)
            response.raise_for_status()
        with fitz.open(stream=response.content, filetype="pdf") as doc:
            parts = []
            total = 0
            for page in doc:
                text = page.get_text().strip()
                if not text:
                    continue
                if total + len(text) > 150_000:
                    parts.append(text[: max(0, 150_000 - total)])
                    break
                parts.append(text)
                total += len(text)
        pdf_text_cache[pdf_url] = "\n\n".join(parts).strip()
    except Exception as exc:
        logger.warning("Gagal mengambil PDF sumber Pasal.id %s: %s", pdf_url, str(exc)[:160])
        pdf_text_cache[pdf_url] = ""
    return pdf_text_cache[pdf_url]


def _query_mentions_work(query: str, work: Dict[str, Any]) -> bool:
    number = str(work.get("number") or "").strip()
    year = str(work.get("year") or "").strip()
    if number and year and _re.search(
        rf"(?:Nomor|No\.?)\s*{_re.escape(number)}\s+Tahun\s+{_re.escape(year)}",
        query or "",
        flags=_re.IGNORECASE,
    ):
        return True
    title = str(work.get("title") or "")
    return bool(title and title.lower() in (query or "").lower())


async def _enrich_pasal_reference_for_reader(
    item: Dict[str, Any],
    query: str,
    snippet: str,
    matching_pasals: str,
    law_detail_cache: Dict[str, Dict[str, Any]],
    pdf_text_cache: Dict[str, str],
) -> Dict[str, Any]:
    work = item.get("work", {}) if isinstance(item.get("work"), dict) else {}
    frbr_uri = str(work.get("frbr_uri") or item.get("frbr_uri") or "").strip()
    if not frbr_uri:
        return {
            "content": snippet,
            "full_content": "",
            "relevant_content": "",
            "source_url": work.get("source_url") or "",
            "source_pdf_url": work.get("source_pdf_url") or "",
            "content_source": "search_snippet",
            "content_truncated": False,
        }

    if frbr_uri not in law_detail_cache:
        law_detail_cache[frbr_uri] = await PasalAPI.get_law(frbr_uri)
    detail = law_detail_cache[frbr_uri]
    if detail.get("error"):
        return {
            "content": snippet,
            "full_content": "",
            "relevant_content": "",
            "source_url": work.get("source_url") or "",
            "source_pdf_url": work.get("source_pdf_url") or "",
            "content_source": "search_snippet",
            "content_error": detail.get("error"),
            "content_truncated": False,
        }

    detail_work = detail.get("work", {}) if isinstance(detail.get("work"), dict) else {}
    merged_work = {**work, **detail_work}
    articles = detail.get("articles") if isinstance(detail.get("articles"), list) else []
    full_content, truncated = _format_law_articles([a for a in articles if isinstance(a, dict)])
    requested_numbers = _extract_requested_article_numbers(matching_pasals, query, snippet)
    relevant_content = _format_relevant_articles(
        [a for a in articles if isinstance(a, dict)],
        requested_numbers,
    )
    source_pdf_url = detail_work.get("source_pdf_url") or work.get("source_pdf_url") or ""
    content_source = "law_detail" if full_content else "search_snippet"

    if source_pdf_url and len(full_content) < 5000 and _query_mentions_work(query, merged_work):
        pdf_content = await _extract_pdf_text_for_reader(source_pdf_url, pdf_text_cache)
        if pdf_content:
            full_content = pdf_content
            content_source = "source_pdf"

    return {
        "content": full_content or relevant_content or snippet,
        "full_content": full_content,
        "relevant_content": relevant_content,
        "source_url": detail_work.get("source_url") or work.get("source_url") or "",
        "source_pdf_url": source_pdf_url,
        "content_source": content_source,
        "content_truncated": truncated,
        "articles_count": len(articles),
    }


def _build_pasalid_query(user_input: Dict[str, Any], uploaded_draft: Dict[str, Any]) -> str:
    explicit_parts = [
        user_input.get("uu_diuji"),
        user_input.get("pasal_diuji"),
        user_input.get("batu_uji_uud"),
    ]
    explicit = " ".join(_flatten_for_query(part) for part in explicit_parts).strip()
    if explicit:
        return explicit[:700]
    extracted = _extract_norm_reference_query((uploaded_draft or {}).get("raw_text", ""))
    return extracted or "pengujian undang-undang Mahkamah Konstitusi"


def _validate_permohonan_payload(mode: str, user_input: Dict[str, Any], uploaded_draft: Dict[str, Any]) -> str:
    if mode == "new_draft":
        required = [
            "jenis_pengujian",
            "nama_pemohon",
            "kategori_pemohon",
            "uu_diuji",
            "pasal_diuji",
            "batu_uji_uud",
            "kerugian_konstitusional",
        ]
        missing = [field for field in required if not _flatten_for_query(user_input.get(field)).strip()]
        if missing:
            return f"Field wajib belum lengkap: {', '.join(missing)}"
    elif mode == "improve_existing_draft":
        if not (uploaded_draft or {}).get("raw_text", "").strip():
            return "Draft lama wajib diunggah atau diekstrak terlebih dahulu"
        if not _flatten_for_query(user_input.get("tujuan_perbaikan")).strip():
            return "Tujuan perbaikan wajib diisi"
    else:
        return "Mode tidak dikenal"
    return ""


async def _collect_permohonan_references(query: str, pasal_query: str = "") -> tuple[Dict[str, Any], Dict[str, bool], List[str]]:
    references: Dict[str, Any] = {
        "rag_cases": [],
        "rag_risalah": [],
        "bank_data": [],
        "pasalid_norms": [],
    }
    sources = {
        "rag_used": False,
        "survive_bank_used": False,
        "concern_bank_used": False,
        "attack_bank_used": False,
        "ratio_bank_used": False,
        "pasal_id_used": False,
    }
    warnings: List[str] = []

    if RAG_AVAILABLE:
        try:
            retriever = RAGRetriever()
            rag_ctx = retriever.query_for_agent(query, agent_role="pemohon", n_results=8, use_intelligence_banks=False)
            survive_ctx = retriever.query_survive_bank(query, n_results=5)
            concern_ctx = retriever.query_concern_bank(query, n_results=5)
            attack_ctx = retriever.query_attack_bank(query, n_results=5)
            ratio_ctx = retriever.query_ratio_bank(query, n_results=5)
            if rag_ctx:
                references["rag_cases"].append({"type": "rag", "content": rag_ctx})
                sources["rag_used"] = True
            for name, content in [
                ("survive_bank", survive_ctx),
                ("concern_bank", concern_ctx),
                ("attack_bank", attack_ctx),
                ("ratio_bank", ratio_ctx),
            ]:
                if content:
                    references["bank_data"].append({"name": name, "content": content})
                    sources[f"{name}_used"] = True
        except Exception as exc:
            warnings.append(f"Gagal mengambil RAG/internal banks: {str(exc)[:160]}")

    try:
        pasal_res = await PasalAPI.search(pasal_query or query[:700], limit=8)
        if pasal_res.get("error"):
            warnings.append(f"Pasal.id: {pasal_res.get('error')}")
        else:
            results = pasal_res.get("results") or pasal_res.get("data") or []
            for item in results[:8]:
                work = item.get("work", {}) if isinstance(item, dict) else {}
                references["pasalid_norms"].append({
                    "title": work.get("title") or item.get("title", "Peraturan"),
                    "snippet": item.get("snippet") or item.get("content", ""),
                    "matching_pasals": item.get("matching_pasals", ""),
                })
            sources["pasal_id_used"] = bool(references["pasalid_norms"])
            if not sources["pasal_id_used"]:
                warnings.append(f"Pasal.id: tidak ada hasil untuk query ringkas '{(pasal_query or query)[:120]}'")
    except Exception as exc:
        warnings.append(f"Pasal.id: {str(exc)[:160]}")

    return references, sources, warnings


@app.post("/api/legal-references")
async def api_legal_references(request: Request):
    """Return Pasal.id legal references related to the active hearing discussion."""
    body = await request.json()
    draft = str(body.get("draft") or "")
    transcript_context = body.get("transcript") or body.get("transcript_context") or []
    discussion = _flatten_transcript_for_references(transcript_context)
    reference_context = _re.sub(r"\s+", " ", f"{discussion} {draft}").strip()
    queries = _build_simulation_reference_queries(draft, transcript_context)
    if not queries:
        query = _extract_norm_reference_query(reference_context) or "pengujian undang-undang Mahkamah Konstitusi"
        queries = [query]

    references: List[Dict[str, Any]] = []
    fallback_references: List[Dict[str, Any]] = []
    warnings: List[str] = []
    seen: set[str] = set()
    topic_groups = _reference_topic_groups(reference_context)
    law_detail_cache: Dict[str, Dict[str, Any]] = {}
    pdf_text_cache: Dict[str, str] = {}

    for query in queries[:4]:
        try:
            pasal_res = await PasalAPI.search(query, law_type=_pasal_id_type_for_reference_query(query), limit=6)
        except Exception as exc:
            warnings.append(f"Pasal.id: {str(exc)[:160]}")
            continue

        if pasal_res.get("error"):
            warning = f"Pasal.id: {pasal_res.get('error')}"
            if warning not in warnings:
                warnings.append(warning)
            continue

        results = pasal_res.get("results") or pasal_res.get("data") or []
        for item in results:
            if not isinstance(item, dict):
                continue
            work = item.get("work", {}) if isinstance(item.get("work"), dict) else {}
            metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
            title = work.get("title") or item.get("title") or metadata.get("title") or "Peraturan"
            snippet = item.get("snippet") or item.get("content") or item.get("text") or ""
            matching_pasals = item.get("matching_pasals") or metadata.get("node_number") or ""
            key = f"{title}|{matching_pasals}|{snippet[:80]}".lower()
            if key in seen:
                continue
            seen.add(key)
            base_reference = {
                "title": str(title),
                "snippet": str(snippet),
                "content": str(snippet),
                "full_content": "",
                "relevant_content": "",
                "source_url": work.get("source_url") or "",
                "source_pdf_url": work.get("source_pdf_url") or "",
                "content_source": "search_snippet",
                "content_truncated": False,
                "matching_pasals": str(matching_pasals),
                "query": query,
                "source": "Pasal.id",
                "score": item.get("score"),
                "url": item.get("url") or work.get("url") or work.get("source_url") or "",
            }
            query_groups = _reference_topic_groups(query)
            required_groups = query_groups or topic_groups
            searchable = f"{title} {snippet} {matching_pasals}"
            if required_groups and not _reference_matches_topic(searchable, required_groups):
                fallback_references.append(base_reference)
                continue
            reader_content = await _enrich_pasal_reference_for_reader(
                item=item,
                query=query,
                snippet=str(snippet),
                matching_pasals=str(matching_pasals),
                law_detail_cache=law_detail_cache,
                pdf_text_cache=pdf_text_cache,
            )
            reference = {
                **base_reference,
                **reader_content,
                "url": item.get("url") or work.get("url") or reader_content.get("source_url") or base_reference.get("url") or "",
            }
            references.append(reference)
            if len(references) >= 8:
                break
        if len(references) >= 8:
            break

    if not references and fallback_references and not topic_groups:
        references = fallback_references[:8]
    elif not references and fallback_references:
        warnings.append("Pasal.id mengembalikan hasil umum, tetapi disembunyikan karena tidak cocok dengan topik transkrip.")

    if not references and not warnings:
        warnings.append("Pasal.id: tidak ada peraturan terkait yang ditemukan.")

    return {
        "queries": queries,
        "references": references,
        "warnings": warnings,
        "pasal_id_used": bool(references),
        "context": "transcript" if discussion else "draft",
    }


@app.get("/api/permohonan-corpus/status")
async def api_permohonan_corpus_status():
    """Return global permohonan corpus indexing status."""
    return _permohonan_status_with_runtime()


@app.post("/api/permohonan-corpus/reindex")
async def api_permohonan_corpus_reindex():
    """Start background indexing of local permohonan corpus."""
    global permohonan_index_task, permohonan_index_error, permohonan_index_started_at
    if permohonan_index_task and not permohonan_index_task.done():
        return _permohonan_status_with_runtime()

    permohonan_index_error = None
    permohonan_index_started_at = datetime.now().isoformat(timespec="seconds")
    permohonan_index_task = asyncio.create_task(_run_permohonan_reindex_job())
    return _permohonan_status_with_runtime()


@app.get("/api/projects/{project_id}/permohonan-drafts")
async def api_list_permohonan_drafts(project_id: str):
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)
    return {"drafts": list_permohonan_drafts(project_id)}


@app.get("/api/projects/{project_id}/permohonan-drafts/{draft_id}/docx")
async def api_get_permohonan_draft_docx(project_id: str, draft_id: str):
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": "Project tidak ditemukan"}, status_code=404)

    docx_path = get_permohonan_draft_docx_path(project_id, draft_id)
    if not docx_path:
        return JSONResponse({"error": "Draft DOCX tidak ditemukan"}, status_code=404)
    return FileResponse(
        str(docx_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=docx_path.name,
    )


@app.post("/api/projects/{project_id}/permohonan-drafts/stream")
async def api_generate_permohonan_draft_stream(project_id: str, request: Request):
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)

    body = await request.json()
    mode = str(body.get("mode") or "new_draft")
    user_input = body.get("user_input") if isinstance(body.get("user_input"), dict) else {}
    uploaded_draft = body.get("uploaded_draft") if isinstance(body.get("uploaded_draft"), dict) else {}
    llm_config = body.get("llm_config") if isinstance(body.get("llm_config"), dict) else {}

    validation_error = _validate_permohonan_payload(mode, user_input, uploaded_draft)
    if validation_error:
        return JSONResponse({"error": validation_error}, status_code=400)

    async def event_stream():
        yield _sse_event("status", {"message": "Memuat hasil analisis korpus permohonan...", "phase": "corpus"})
        corpus_status = _permohonan_status_with_runtime()
        if corpus_status.get("status") in {"not_started", "failed"}:
            yield _sse_event("warning", {
                "message": "Korpus belum terindeks penuh. Drafter memakai template dasar dan referensi yang tersedia."
            })
        elif corpus_status.get("status") == "stale":
            yield _sse_event("warning", {
                "message": "Korpus berubah sejak indexing terakhir. Hasil tetap dibuat memakai cache terbaru yang tersedia."
            })

        analysis_artifacts = load_analysis_artifacts()
        query = _build_permohonan_query(user_input, uploaded_draft)
        pasal_query = _build_pasalid_query(user_input, uploaded_draft)

        yield _sse_event("status", {"message": "Mengambil referensi RAG, internal banks, dan Pasal.id...", "phase": "references"})
        references, sources, warnings = await _collect_permohonan_references(query, pasal_query=pasal_query)
        pmk_layer = analysis_artifacts.get("pmk_2_2021_compliance", {})
        pmk_source = pmk_layer.get("source_pdf", {}) if isinstance(pmk_layer, dict) else {}
        sources["pmk_2_2021_compliance_used"] = bool(pmk_layer)
        if pmk_layer and not pmk_source.get("validated", False):
            warning = pmk_source.get("warning") or "PMK 2/2021 compliance layer memakai fallback statis."
            yield _sse_event("warning", {"message": warning})
        for warning in warnings:
            yield _sse_event("warning", {"message": warning})
        yield _sse_event("sources", sources)

        uploaded_for_prompt = dict(uploaded_draft)
        raw_upload_text = str(uploaded_for_prompt.get("raw_text") or "")
        if len(raw_upload_text) > 24000:
            uploaded_for_prompt["raw_text"] = raw_upload_text[:24000] + "\n... [draft user dipotong untuk konteks prompt]"

        handoff = build_drafter_handoff(
            mode=mode,
            user_input=user_input,
            uploaded_draft=uploaded_for_prompt,
            analysis_artifacts=analysis_artifacts,
            references=references,
        )

        prompt = (
            "Gunakan payload handoff berikut untuk menyusun output. "
            "Jangan mengarang fakta yang tidak ada di user_input, uploaded_draft, analysis_artifacts, references, atau Pasal.id.\n\n"
            "WAJIB gunakan analysis_artifacts.pmk_2_2021_compliance sebagai compliance layer PMK 2/2021. "
            "Sebelum finalisasi, audit struktur, legal standing, model petitum, lampiran, tanda tangan, "
            "format dokumen, dan tenggang waktu formil terhadap pmk_compliance_review. "
            "Data yang belum tersedia jangan dikarang; letakkan sebagai kebutuhan data pada CATATAN DRAFTER.\n\n"
            "Untuk mode new_draft, mulai dengan naskah permohonan resmi lengkap. Setelah PENUTUP, tambahkan bagian CATATAN DRAFTER "
            "berisi checklist data kurang, daftar bukti yang perlu disiapkan, catatan kecocokan petitum, dan Checklist PMK 2/2021.\n"
            "Untuk mode improve_existing_draft, mulai dengan versi draft yang telah diperbaiki. Setelah PENUTUP, tambahkan bagian CATATAN DRAFTER "
            "berisi ringkasan perbaikan, bagian yang masih lemah, saran bukti/data tambahan, dan Checklist PMK 2/2021.\n\n"
            f"=== PAYLOAD HANDOFF ===\n{compact_for_prompt(handoff, max_chars=52000)}\n\n"
            "Keluarkan hanya dokumen dan catatan drafter, tanpa JSON, tanpa markdown code block."
        )

        yield _sse_event("status", {"message": "Drafter Permohonan MK menyusun dokumen...", "phase": "generating"})
        agent = PermohonanDrafterAgent(llm_config=llm_config)
        q: asyncio.Queue = asyncio.Queue()

        async def on_chunk(chunk: str):
            q.put_nowait(chunk)

        task = asyncio.create_task(agent.generate_response(prompt, on_chunk=on_chunk))
        streamed_text = ""

        while not task.done():
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=15.0)
                streamed_text += chunk
                yield _sse_event("draft_chunk", {"chunk": chunk})
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

        try:
            final = await task
            while not q.empty():
                chunk = q.get_nowait()
                streamed_text += chunk
                yield _sse_event("draft_chunk", {"chunk": chunk})

            final_draft = _extract_draft_text(final or streamed_text)
            if final_draft and final_draft != streamed_text:
                yield _sse_event("draft_final", {"draft": final_draft})
            else:
                final_draft = final_draft or streamed_text
                yield _sse_event("draft_final", {"draft": final_draft})

            incomplete_reason = _looks_like_incomplete_permohonan(final_draft, mode)
            if incomplete_reason:
                yield _sse_event("error", {
                    "message": (
                        "Output drafter tampak tidak lengkap: "
                        f"{incomplete_reason}. Draft tidak disimpan; jalankan ulang dengan model/konteks yang lebih kuat."
                    )
                })
                yield _sse_event("done", {})
                return

            saved = save_permohonan_draft(
                project_id=project_id,
                mode=mode,
                user_input=user_input,
                draft_text=final_draft,
                uploaded_draft=uploaded_draft,
                sources={
                    **sources,
                    "corpus_status": corpus_status.get("status"),
                    "corpus_last_indexed_at": corpus_status.get("last_indexed_at"),
                },
            )
            if saved:
                yield _sse_event("draft_saved", saved)
            else:
                yield _sse_event("warning", {"message": "Draft dibuat, tetapi gagal disimpan ke project."})
            yield _sse_event("status", {"message": "Dokumen permohonan selesai", "phase": "done"})
        except Exception as exc:
            logger.error(f"Permohonan draft streaming error: {exc}")
            yield _sse_event("error", {"message": f"Gagal membuat dokumen permohonan: {str(exc)}"})

        yield _sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class StreamingOrchestrator(SimulationOrchestrator):
    """
    Extends orchestrator untuk mengumpulkan SSE events
    dan memasukannya ke Queue agar bisa langsung di-stream ke browser.
    Mendukung multiple listeners (broadcast).
    """

    def __init__(self, *args, human_input_queue=None, judge_personas=None, **kwargs):
        # Tambahkan callback untuk handle chunks dari agent
        kwargs["on_chunk_callback"] = self._on_agent_chunk
        # Jika human_input_queue disediakan, aktifkan mode manusia
        if human_input_queue is not None:
            kwargs["mode"] = "human"
            kwargs["human_input_callback"] = self._human_input_handler
        # Pass judge_personas ke parent
        if judge_personas:
            kwargs["judge_personas"] = judge_personas
        super().__init__(*args, **kwargs)
        self.human_input_queue = human_input_queue

    def _broadcast(self, event_type, data):
        """Kirim event ke semua listener yang terdaftar dan simpan ke transcript memory."""
        event = _sse_event(event_type, data)
        
        # Simpan ke memory untuk resume (hanya event permanen, bukan chunk)
        if event_type not in ["transcript_chunk", "status"]:
            if self.simulation_id not in simulation_transcripts:
                simulation_transcripts[self.simulation_id] = []
            simulation_transcripts[self.simulation_id].append({"type": event_type, "data": data})

        # Kirim ke semua queue listener
        sid = str(self.simulation_id)
        if sid in simulation_queues:
            for q in simulation_queues[sid]:
                try:
                    q.put_nowait(event)
                except:
                    pass

    async def _on_agent_chunk(self, speaker: str, chunk: str):
        """Kirim potongan teks (chunk) ke frontend via SSE."""
        self._broadcast("transcript_chunk", {
            "speaker": speaker,
            "content": chunk
        })

    def _fallback_human_suggestions(self) -> List[str]:
        return [
            "Izin, Yang Mulia. Kerugian Pemohon bersifat aktual karena norma a quo langsung menjadi dasar penerapan terhadap hak konstitusional Pemohon, sehingga hubungan sebab akibatnya bukan dugaan melainkan konsekuensi dari berlakunya frasa yang diuji.",
            "Baik, Yang Mulia. Pemohon menegaskan yang diuji adalah ketidakpastian makna norma a quo, karena frasa tersebut membuka ruang penerapan yang melampaui batas konstitusional dan langsung mempengaruhi posisi hukum Pemohon.",
            "Terima kasih, Yang Mulia. Jawaban Pemohon kami batasi pada norma yang diuji: rumusan pasal a quo tidak memberi ukuran yang pasti, sehingga menimbulkan kerugian konkret dan perlu dinilai terhadap UUD 1945.",
        ]

    async def _build_human_suggestions(self, prompt: str, rag_context: str) -> List[str]:
        """Buat tiga opsi jawaban instan dari perspektif Kuasa Pemohon."""
        focuses = [
            "jawaban langsung yang menjawab inti pertanyaan hakim",
            "jawaban yang menegaskan hubungan sebab akibat dan kerugian konkret",
            "jawaban yang fokus pada batu uji konstitusional dan kepastian hukum",
        ]

        async def make_suggestion(focus: str) -> str:
            agent = PemohonAgent(llm_config=self.llm_config)
            if hasattr(self.pemohon, "memory"):
                agent.memory = [dict(message) for message in self.pemohon.memory]
            suggestion_prompt = (
                f"{prompt}\n\n"
                "Tulis SATU opsi jawaban instan untuk pengguna yang sedang berperan sebagai Kuasa Hukum Pemohon. "
                f"Fokus opsi: {focus}. "
                "Maksimal 2 kalimat pendek, siap dibacakan langsung di sidang. "
                "Jangan menulis label opsi, markdown, analisis, atau alternatif lain."
            )
            answer = await agent.generate_response(suggestion_prompt, rag_context=rag_context)
            answer = str(answer or "").strip().strip('"')
            answer = _re.sub(r"^\s*(?:opsi|alternatif|jawaban)\s*\d*\s*[:.\-]\s*", "", answer, flags=_re.IGNORECASE)
            return answer.strip()

        fallback = self._fallback_human_suggestions()
        try:
            suggestions = await asyncio.wait_for(
                asyncio.gather(*(make_suggestion(focus) for focus in focuses)),
                timeout=90.0,
            )
        except Exception as exc:
            logger.warning(f"Gagal membuat opsi jawaban interaktif: {exc}")
            return fallback

        cleaned: List[str] = []
        for suggestion in suggestions:
            if not suggestion or suggestion.startswith("["):
                continue
            if suggestion not in cleaned:
                cleaned.append(suggestion)

        for suggestion in fallback:
            if len(cleaned) >= 3:
                break
            cleaned.append(suggestion)

        return cleaned[:3]

    async def _human_input_handler(self, prompt: str, rag_context: str, agent_name: str) -> str:
        """Handler untuk menunggu input manusia via queue."""
        while True:
            try:
                self.human_input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        turn_id = uuid.uuid4().hex
        requested_at = time.time()
        self._broadcast("waiting_for_human", {
            "prompt": prompt[:1200],
            "agent_name": agent_name,
            "suggestions": [],
            "is_generating_suggestions": True,
            "turn_id": turn_id,
            "requested_at": requested_at,
        })
        input_task = asyncio.create_task(self.human_input_queue.get())
        suggestions_task = asyncio.create_task(self._build_human_suggestions(prompt, rag_context))
        done, _ = await asyncio.wait(
            {input_task, suggestions_task},
            timeout=90.0,
            return_when=asyncio.FIRST_COMPLETED,
        )
        try:
            if input_task in done:
                suggestions_task.cancel()
                return input_task.result()

            if suggestions_task in done:
                try:
                    suggestions = suggestions_task.result()
                except Exception as exc:
                    logger.warning(f"Gagal membuat opsi jawaban interaktif: {exc}")
                    suggestions = self._fallback_human_suggestions()
            else:
                suggestions_task.cancel()
                suggestions = self._fallback_human_suggestions()

            if input_task.done():
                return input_task.result()

            self._broadcast("waiting_for_human", {
                "prompt": prompt[:1200],
                "agent_name": agent_name,
                "suggestions": suggestions,
                "is_generating_suggestions": False,
                "turn_id": turn_id,
                "requested_at": requested_at,
            })

            response = await asyncio.wait_for(input_task, timeout=510.0)
            return response
        except asyncio.TimeoutError:
            return "[Waktu habis - Pemohon tidak memberikan respons]"

        finally:
            for task in (input_task, suggestions_task):
                if not task.done():
                    task.cancel()

    def _log_interaction(self, round_name: str, speaker: str, content: str, validation_result=None):
        """Override: log + dorong SSE event ke Queue seketika."""
        super()._log_interaction(round_name, speaker, content, validation_result)
        self._broadcast("transcript", {
            "round": round_name,
            "speaker": speaker,
            "content": content,
            "timestamp": time.time()
        })

    def _finalize_streaming_result(self, sid: str, draft_input: str, result: Dict[str, Any]) -> Dict[str, Any]:
        saved_config = simulation_configs.get(sid, {})
        started_at = saved_config.get("started_at")
        ended_at = time.time()
        duration_seconds = round(ended_at - started_at) if isinstance(started_at, (int, float)) else None
        metadata = {
            **(result.get("metadata") if isinstance(result.get("metadata"), dict) else {}),
            "started_at": saved_config.get("started_at_iso"),
            "ended_at": datetime.fromtimestamp(ended_at).astimezone().isoformat(),
            "duration_seconds": duration_seconds,
            **_public_llm_metadata(self.llm_config or {}),
        }
        result["metadata"] = metadata
        if isinstance(result.get("scores"), dict) and result["scores"]:
            result["scores"]["api_usage"] = result.get("api_usage", self._collect_api_usage())
            result["scores"]["metadata"] = metadata
        if result.get("feedback"):
            self._broadcast("feedback", result["feedback"])

        self.last_result = _cache_simulation_result(sid, result)
        try:
            save_simulation(
                simulation_data=result,
                draft=draft_input,
                config={
                    "jumlah_hakim": self.jumlah_hakim,
                    "llm_config": {k: v for k, v in (self.llm_config or {}).items() if k != "api_key"},
                    "mode": self.mode,
                    "hearing_mode": self.hearing_mode,
                    "target_turn_range": list(self.target_turn_range),
                    "judge_personas": self.judge_personas,
                    "project_id": saved_config.get("project_id"),
                },
                sim_id=sid,
            )
            self._broadcast("simulation_saved", {
                "id": sid,
                "total_score": result.get("scores", {}).get("total", 0),
                "amar": result.get("scores", {}).get("amar", "TIDAK DAPAT DITERIMA"),
            })
        except Exception as save_err:
            logger.warning(f"Gagal menyimpan simulasi ke storage: {save_err}")
        return result

    async def run_full_simulation_streaming(self, draft_input: str) -> Dict[str, Any]:
        """Jalankan simulasi penuh, dorong status ke Queue seketika."""
        result = {}
        sid = str(self.simulation_id)
        try:
            if self.hearing_mode != self.PEDAGOGICAL_MODE:
                profile = self.get_hearing_profile()
                self._broadcast("status", {
                    "message": f"Sidang {profile.get('label', self.hearing_mode)}",
                    "phase": profile.get("phase", "hearing"),
                    "hearing_mode": self.hearing_mode,
                    "target_turn_range": list(self.target_turn_range),
                })
                result = await self.run_full_simulation(draft_input)
                return self._finalize_streaming_result(sid, draft_input, result)

            self._broadcast("status", {"message": "Ronde 1: Pemeriksaan Pendahuluan", "phase": "round1"})
            await self.run_round_1_pendahuluan(draft_input)

            self._broadcast("status", {"message": "Ronde 2: Perbaikan Permohonan", "phase": "round2"})
            await self.run_round_2_perbaikan()

            self._broadcast("status", {"message": "Ronde 2B: Pemeriksaan Ahli", "phase": "round2b"})
            await self.run_round_2b_ahli()

            self._broadcast("status", {"message": "Ronde 3: Pokok Perkara", "phase": "round3"})
            await self.run_round_3_pokok_perkara()

            self._broadcast("status", {"message": "Ronde 4: Kesimpulan & RPH", "phase": "round4"})
            result = await self.run_round_4_kesimpulan()

            self._broadcast("status", {"message": "Umpan Balik Hakim", "phase": "feedback"})
            feedback = await self.run_round_5_feedback()
            result["feedback"] = feedback
            result["api_usage"] = self._collect_api_usage()
            self._finalize_streaming_result(sid, draft_input, result)

        except Exception as e:
            logger.error(f"Error during simulation: {e}")
            result = {"error": str(e)}
        finally:
            # Sinyal selesai ke semua listener
            if sid in simulation_queues:
                for q in simulation_queues[sid]:
                    q.put_nowait("DONE")
            # Cleanup orchestrator
            active_orchestrators.pop(sid, None)
            active_simulations.pop(sid, None)

        return result


# ================================================================
# TEMPLATE KASUS ENDPOINTS
# ================================================================

@app.get("/api/templates")
async def list_templates():
    """Ambil daftar semua template kasus."""
    return {"templates": get_all_templates()}


@app.get("/api/templates/{template_id}")
async def get_template(template_id: str):
    """Ambil detail template kasus berdasarkan ID."""
    template = get_template_by_id(template_id)
    if not template:
        return JSONResponse({"error": f"Template '{template_id}' tidak ditemukan"}, status_code=404)
    return template


# ================================================================
# EXPORT PDF ENDPOINT
# ================================================================

@app.post("/api/export-pdf")
async def export_pdf(request: Request):
    """Generate dan download PDF putusan MK dari hasil simulasi."""
    body = await request.json()
    try:
        pdf_bytes = generate_putusan_pdf(body)
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=putusan_mk.pdf"}
        )
    except Exception as e:
        logger.error(f"PDF generation error: {e}", exc_info=True)
        return JSONResponse({"error": f"Gagal generate PDF: {type(e).__name__}: {str(e)}"}, status_code=500)


# ================================================================
# ARGUMENT CHAIN ANALYZER ENDPOINT
# ================================================================

@app.post("/api/analyze-arguments")
async def analyze_arguments(request: Request):
    """Analisis struktur argumen dari transcript simulasi."""
    body = await request.json()
    transcript = body.get("transcript", [])
    llm_config = body.get("llm_config", {})

    if not transcript:
        return JSONResponse({"error": "Transcript kosong"}, status_code=400)

    # Format transcript untuk analisis
    transcript_text = "\n".join([
        f"[{t.get('round', '')}] {t.get('speaker', '')}: {t.get('content', '')[:300]}"
        for t in transcript[:30]  # Batasi agar tidak terlalu panjang
    ])

    agent = PemohonAgent(llm_config=llm_config)
    prompt = f"""\
Analisis transkrip sidang MK berikut dan ekstrak STRUKTUR ARGUMEN dari setiap pihak.

TRANSCRIPT:
{transcript_text}

Kembalikan HANYA format JSON berikut (tanpa teks tambahan):
{{
    "chains": [
        {{
            "party": "Pemohon",
            "party_class": "pemohon",
            "arguments": [
                {{
                    "dalil": "Dalil utama yang disampaikan",
                    "legal_basis": "Dasar hukum (pasal/putusan)",
                    "strength": "kuat|sedang|lemah"
                }}
            ]
        }},
        {{
            "party": "Pemerintah",
            "party_class": "pemerintah",
            "arguments": [...]
        }},
        {{
            "party": "Hakim",
            "party_class": "hakim",
            "arguments": [
                {{
                    "dalil": "Pertanyaan/posisi hakim",
                    "legal_basis": "",
                    "strength": ""
                }}
            ]
        }}
    ]
}}

Hanya masukkan pihak yang benar-benar menyampaikan argumen. Analisis kekuatan berdasarkan:
- kuat: didukung teks UUD/putusan MK yang jelas
- sedang: argumen logis tapi kurang referensi
- lemah: argumen tanpa dasar hukum yang kuat
"""

    try:
        raw = await agent.generate_response(prompt)
        start = raw.find('{')
        end = raw.rfind('}') + 1
        if start != -1 and end > 0:
            parsed = json.loads(raw[start:end])
            return parsed
        return {"chains": [], "raw": raw}
    except Exception as e:
        logger.error(f"Argument analysis error: {e}")
        return JSONResponse({"error": f"Gagal menganalisis argumen: {str(e)}"}, status_code=500)


# ================================================================
# LEARNING MODE ENDPOINTS
# ================================================================

@app.post("/api/learning-tips")
async def get_learning_tips(request: Request):
    """Generate tips strategis berdasarkan draft permohonan sebelum simulasi."""
    body = await request.json()
    draft = body.get("draft", "")
    llm_config = body.get("llm_config", {})

    if not draft or len(draft) < 50:
        return {"tips": ["Draft terlalu pendek. Tulis minimal 50 karakter untuk mendapatkan tips."]}

    agent = PemohonAgent(llm_config=llm_config)
    prompt = f"""\
Anda adalah konsultan hukum ahli Mahkamah Konstitusi. Analisis draft permohonan berikut \
dan berikan TIPS STRATEGIS untuk mempersiapkan sidang.

DRAFT:
{draft[:2000]}

Berikan tips dalam format JSON:
{{
    "tips": [
        "Tips 1: [tips spesifik]",
        "Tips 2: [tips spesifik]",
        "Tips 3: [tips spesifik]"
    ],
    "weak_points": ["Kelemahan 1", "Kelemahan 2"],
    "recommended_articles": ["Pasal X UUD 1945", "Pasal Y UUD 1945"]
}}

Fokus pada:
1. Pasal UUD 1945 yang paling relevan sebagai batu uji
2. Kelemahan yang mungkin ditanyakan hakim
3. Strategi mengantisipasi argumen pemerintah
4. Preseden putusan MK yang relevan
"""

    try:
        raw = await agent.generate_response(prompt)
        start = raw.find('{')
        end = raw.rfind('}') + 1
        if start != -1 and end > 0:
            parsed = json.loads(raw[start:end])
            return parsed
        return {"tips": [raw[:500]]}
    except Exception as e:
        logger.error(f"Learning tips error: {e}")
        return {"tips": [f"Gagal generate tips: {str(e)}"]}


# ================================================================
# SAVED SIMULATIONS ENDPOINTS (untuk Replay & Analisa Ulang)
# ================================================================

@app.get("/api/saved-simulations")
async def list_saved_simulations(limit: int = 50, offset: int = 0):
    """Ambil daftar simulasi yang tersimpan (metadata saja)."""
    result = list_simulations(limit=limit, offset=offset)
    return result


@app.get("/api/saved-simulations/stats")
async def saved_simulations_stats():
    """Statistik ringkas tentang simulasi tersimpan."""
    return get_simulation_stats()


@app.get("/api/saved-simulations/{simulation_id}")
async def get_saved_simulation(simulation_id: str):
    """Ambil data lengkap simulasi tersimpan untuk replay/analisa."""
    data = load_simulation(simulation_id)
    if not data:
        return JSONResponse(
            {"error": f"Simulasi '{simulation_id}' tidak ditemukan"},
            status_code=404
        )
    return data


@app.delete("/api/saved-simulations/{simulation_id}")
async def delete_saved_simulation(simulation_id: str):
    """Hapus simulasi tersimpan."""
    deleted = delete_simulation(simulation_id)
    if not deleted:
        return JSONResponse(
            {"error": f"Simulasi '{simulation_id}' tidak ditemukan"},
            status_code=404
        )
    return {"status": "deleted", "id": simulation_id}


@app.post("/api/saved-simulations/save")
async def save_simulation_manually(request: Request):
    """Simpan simulasi secara manual dari frontend (client-side state)."""
    body = await request.json()
    simulation_data = body.get("simulation_data", {})
    draft = body.get("draft", "")
    config = body.get("config", {})
    sim_id = body.get("sim_id") or simulation_data.get("simulation_id")

    if not simulation_data.get("transcript"):
        return JSONResponse({"error": "Tidak ada data transcript untuk disimpan"}, status_code=400)

    try:
        saved_meta = save_simulation(
            simulation_data=simulation_data,
            draft=draft,
            config=config,
            sim_id=str(sim_id) if sim_id else None,
        )
        return {"status": "saved", **saved_meta}
    except Exception as e:
        logger.error(f"Gagal menyimpan simulasi manual: {e}")
        return JSONResponse({"error": f"Gagal menyimpan: {str(e)}"}, status_code=500)


@app.get("/api/simulations")
async def list_simulations_compat():
    """Ambil daftar simulasi yang tersimpan (backward-compatible)."""
    result = list_simulations(limit=50)
    return {"simulations": result["simulations"]}


@app.get("/api/simulations/{simulation_id}")
async def get_simulation_compat(simulation_id: str):
    """Ambil data simulasi tersimpan untuk replay (backward-compatible)."""
    data = load_simulation(simulation_id)
    if not data:
        return JSONResponse(
            {"error": f"Simulasi '{simulation_id}' tidak ditemukan"},
            status_code=404
        )
    return data


# ================================================================
# PROJECT MANAGEMENT ENDPOINTS
# ================================================================


@app.get("/api/projects")
async def api_list_projects(limit: int = 50, offset: int = 0):
    """List semua projects."""
    result = list_projects(limit=limit, offset=offset)
    return result


@app.post("/api/projects")
async def api_create_project(request: Request):
    """Buat project baru."""
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Nama project tidak boleh kosong"}, status_code=400)
    project = create_project({"name": name, "description": body.get("description", "")})
    return project


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
    """Ambil detail project."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)
    # Tambahkan counts
    project["simulation_count"] = list_simulations_by_project(project_id, limit=0, offset=0).get("total", 0)
    project["file_count"] = len(list_project_files(project_id))
    return project


@app.put("/api/projects/{project_id}")
async def api_update_project(project_id: str, request: Request):
    """Update metadata project."""
    body = await request.json()
    project = update_project(project_id, body)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)
    return project


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
    """Hapus project dan semua data terkait."""
    deleted = delete_project(project_id)
    if not deleted:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)
    return {"status": "deleted", "id": project_id}


@app.post("/api/projects/{project_id}/files")
async def api_upload_project_file(project_id: str, file: UploadFile = File(...)):
    """Upload file ke project."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)

    filename = _sanitize_filename(file.filename)
    size = 0
    content = bytearray()
    while chunk := await file.read(8192):
        size += len(chunk)
        if size > MAX_FILE_SIZE:
            return JSONResponse(
                {"error": f"File terlalu besar. Maksimal {MAX_FILE_SIZE // (1024*1024)}MB"},
                status_code=413,
            )
        content.extend(chunk)

    result = add_file_to_project(
        project_id=project_id,
        filename=filename,
        file_content=bytes(content),
        mime_type=file.content_type or '',
    )
    if not result:
        return JSONResponse({"error": "Gagal menyimpan file. Pastikan format file didukung (PDF, DOCX, DOC, TXT)."}, status_code=400)
    return result


@app.get("/api/projects/{project_id}/files")
async def api_list_project_files(project_id: str):
    """List file di project."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)
    return {"files": list_project_files(project_id)}


@app.get("/api/projects/{project_id}/files/{file_id}/content")
async def api_get_project_file_content(project_id: str, file_id: str):
    """Ambil isi teks dari file project."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": "Project tidak ditemukan"}, status_code=404)

    files = list_project_files(project_id)
    file_meta = next((f for f in files if f['id'] == file_id), None)
    if not file_meta:
        return JSONResponse({"error": "File tidak ditemukan"}, status_code=404)

    file_path = os.path.join(PROJECTS_DIR, project_id, 'files', file_meta['stored_filename'])
    if not os.path.exists(file_path):
        return JSONResponse({"error": "File fisik tidak ditemukan"}, status_code=404)

    try:
        text = extract_text_from_file(file_path, file_meta['filename'])
        return {"id": file_id, "filename": file_meta['filename'], "text": text}
    except Exception as e:
        logger.error(f"Gagal ekstraksi teks file {file_id}: {e}")
        return JSONResponse({"error": f"Gagal mengekstrak teks: {str(e)}"}, status_code=500)


@app.get("/api/projects/{project_id}/files/{file_id}/raw")
async def api_get_project_file_raw(project_id: str, file_id: str):
    """Tampilkan file project asli untuk preview/download."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": "Project tidak ditemukan"}, status_code=404)

    files = list_project_files(project_id)
    file_meta = next((f for f in files if f['id'] == file_id), None)
    if not file_meta:
        return JSONResponse({"error": "File tidak ditemukan"}, status_code=404)

    file_path = os.path.abspath(os.path.join(PROJECTS_DIR, project_id, 'files', file_meta['stored_filename']))
    project_files_dir = os.path.abspath(os.path.join(PROJECTS_DIR, project_id, 'files'))
    if not file_path.startswith(project_files_dir + os.sep):
        return JSONResponse({"error": "Path file tidak valid"}, status_code=400)
    if not os.path.exists(file_path):
        return JSONResponse({"error": "File fisik tidak ditemukan"}, status_code=404)

    return FileResponse(
        file_path,
        media_type=file_meta.get('mime_type') or 'application/octet-stream',
        filename=file_meta['filename'],
        headers={"Content-Disposition": f"inline; filename=\"{file_meta['filename']}\""},
    )


@app.delete("/api/projects/{project_id}/files/{file_id}")
async def api_delete_project_file(project_id: str, file_id: str):
    """Hapus file dari project."""
    deleted = delete_project_file(project_id, file_id)
    if not deleted:
        return JSONResponse({"error": "File tidak ditemukan"}, status_code=404)
    return {"status": "deleted", "file_id": file_id}


@app.get("/api/projects/{project_id}/simulations")
async def api_list_project_simulations(project_id: str, limit: int = 50, offset: int = 0):
    """List simulasi yang ter-link ke project."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)
    return list_simulations_by_project(project_id, limit=limit, offset=offset)


@app.get("/api/projects/{project_id}/research")
async def api_list_project_research(project_id: str):
    """List research findings di project."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)
    return {"research": list_research(project_id)}


@app.post("/api/projects/{project_id}/research")
async def api_run_research(project_id: str, request: Request):
    """Jalankan research query via RAG - streaming SSE agar respons tidak terpotong."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)

    body = await request.json()
    query = body.get("query", "").strip()
    if not query:
        return JSONResponse({"error": "Query tidak boleh kosong"}, status_code=400)

    if not RAG_AVAILABLE:
        return JSONResponse({"error": "RAG tidak tersedia di server ini"}, status_code=503)

    llm_config = body.get("llm_config", {})

    async def event_stream():
        yield _sse_event("status", {"message": "Mencari data dari RAG knowledge base...", "phase": "retrieving"})

        rag_ctx = ""
        survive_ctx = ""
        ratio_ctx = ""
        try:
            retriever = RAGRetriever()
            rag_ctx = retriever.query_for_agent(query, agent_role="pemohon", n_results=10, use_intelligence_banks=False)
            survive_ctx = retriever.query_survive_bank(query, n_results=5)
            ratio_ctx = retriever.query_ratio_bank(query, n_results=5)
        except Exception as e:
            logger.warning(f"Gagal query RAG: {e}")

        # --- Integrasi Pasal.id (ROADMAP Fase 5 Extension) ---
        yield _sse_event("status", {"message": "Mencari pasal terkait di pasal.id...", "phase": "pasal_id_searching"})
        pasal_ctx = ""
        pasal_error = None
        try:
            pasal_res = await PasalAPI.search(query, limit=10)
            if "error" in pasal_res:
                pasal_error = pasal_res["error"]
                logger.warning(f"Pasal.id Error: {pasal_error}")
            else:
                results = pasal_res.get("results", [])
                if results:
                    pasal_parts = []
                    for r in results:
                        work = r.get('work', {})
                        title = work.get('title') or r.get('title', 'Peraturan')
                        content = r.get('snippet') or r.get('content', '')
                        pasals = r.get('matching_pasals', '')
                        
                        header = f"--- {title} ---"
                        if pasals:
                            header += f" (Kaitan: {pasals})"
                        
                        pasal_parts.append(f"{header}\n{content}")
                    pasal_ctx = "\n\n".join(pasal_parts)
        except Exception as e:
            pasal_error = str(e)
            logger.error(f"Pasal.id Exception: {e}")

        if pasal_error:
            yield _sse_event("pasal_id_error", {"error": pasal_error})

        yield _sse_event("sources", {
            "rag_used": bool(rag_ctx),
            "survive_bank_used": bool(survive_ctx),
            "ratio_bank_used": bool(ratio_ctx),
            "pasal_id_used": bool(pasal_ctx),
        })
        yield _sse_event("status", {"message": "Menyusun jawaban riset...", "phase": "generating"})

        agent = RisetHukumAgent(llm_config=llm_config)
        prompt = (
            f"=== PERTANYAAN ===\n{query}\n\n"
            f"=== PASAL.ID (EXTERNAL LEGAL DATA) ===\n{pasal_ctx or '(tidak ada data atau query pasal.id gagal)'}\n\n"
            f"=== RAG KNOWLEDGE BASE ===\n{rag_ctx or '(tidak ada data)'}\n\n"
            f"=== SURVIVE BANK ===\n{survive_ctx or '(tidak ada data)'}\n\n"
            f"=== RATIO BANK ===\n{ratio_ctx or '(tidak ada data)'}\n\n"
            "Jawab pertanyaan riset di atas secara komprehensif dan tuntas. "
            "Gunakan data dari pasal.id sebagai referensi utama jika relevan, "
            "dan kombinasikan dengan konteks dari RAG internal. "
            "Sertakan referensi putusan MK atau pasal UUD yang relevan."
        )

        q: asyncio.Queue = asyncio.Queue()

        async def on_chunk(chunk: str):
            q.put_nowait(chunk)

        task = asyncio.create_task(agent.generate_response(prompt, on_chunk=on_chunk))
        full_answer = ""

        while not task.done():
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=15.0)
                full_answer += chunk
                yield _sse_event("research_chunk", {"chunk": chunk})
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

        try:
            final = await task
            while not q.empty():
                c = q.get_nowait()
                full_answer += c
                yield _sse_event("research_chunk", {"chunk": c})

            answer = final or full_answer

            # Simpan ke database
            try:
                saved = save_research(project_id, query, answer, sources=[])
                yield _sse_event("research_saved", saved or {"query": query, "answer": answer})
            except Exception as save_err:
                logger.warning(f"Gagal menyimpan riset: {save_err}")
                yield _sse_event("research_saved", {"query": query, "answer": answer})

            yield _sse_event("status", {"message": "Riset selesai", "phase": "done"})
        except Exception as e:
            logger.error(f"Research streaming error: {e}")
            yield _sse_event("error", {"message": f"Gagal menjalankan riset: {str(e)}"})

        yield _sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/projects/{project_id}/audit")
async def api_list_project_audits(project_id: str):
    """List audit results di project."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)
    return {"audits": list_audits(project_id)}


@app.post("/api/projects/{project_id}/audit")
async def api_run_audit(project_id: str, request: Request):
    """Analisis konsistensi Petitum vs Posita dari draft."""
    project = get_project(project_id)
    if not project:
        return JSONResponse({"error": f"Project '{project_id}' tidak ditemukan"}, status_code=404)

    body = await request.json()
    draft = body.get("draft", "").strip()
    if not draft:
        return JSONResponse({"error": "Draft tidak boleh kosong"}, status_code=400)

    agent = PemohonAgent(llm_config=body.get("llm_config", {}))
    prompt = f"""\
Anda adalah auditor hukum ahli Mahkamah Konstitusi.
Analisis draft permohonan PUU berikut dan periksa KONSISTENSI antara POSITA (alasan-alasan permohonan) dan PETITUM (permohonan/permintaan kepada MK).

DRAFT:
{draft[:8000]}

Tugas Anda:
1. Identifikasi semua dalil dalam POSITA
2. Identifikasi semua permohonan dalam PETITUM
3. Periksa apakah setiap PETITUM didukung oleh POSITA yang memadai
4. Periksa apakah ada POSITA yang tidak tercermin dalam PETITUM
5. Periksa apakah ada PETITUM yang tidak didukung POSITA

Kembalikan HANYA JSON berikut (tanpa teks tambahan):
{{
    "consistent": true/false,
    "summary": "Ringkasan singkat hasil audit",
    "issues": [
        {{
            "location": "Petitum butir X / Posita bagian Y",
            "type": "missing|mismatch|weak_argument|unsupported_claim",
            "description": "Penjelasan detail masalah",
            "suggestion": "Saran perbaikan"
        }}
    ],
    "posita_count": 5,
    "petitum_count": 3,
    "matched_count": 2
}}
"""

    try:
        raw = await agent.generate_response(prompt)
        start = raw.find('{')
        end = raw.rfind('}') + 1
        parsed = None
        if start != -1 and end > 0:
            try:
                parsed = json.loads(raw[start:end])
            except Exception:
                pass

        if not parsed:
            parsed = {
                "consistent": True,
                "summary": raw[:500],
                "issues": [],
            }

        saved = save_audit(project_id, parsed)
        if saved:
            return saved
        return parsed
    except Exception as e:
        logger.error(f"Audit error: {e}")
        return JSONResponse({"error": f"Gagal menjalankan audit: {str(e)}"}, status_code=500)


@app.get("/{full_path:path}")
async def serve_spa_fallback(full_path: str):
    """Serve React SPA fallback untuk client-side routes (registered last so API routes match first)."""
    if full_path.startswith("api/"):
        return JSONResponse({"error": "API endpoint tidak ditemukan"}, status_code=404)

    # Serve static file jika ada di frontend/dist
    react_index = _read_react_index_html()
    if react_index and FRONTEND_DIST.exists():
        file_path = FRONTEND_DIST / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return HTMLResponse(content=file_path.read_text(encoding="utf-8"))
        return HTMLResponse(content=react_index)
    # Fallback ke legacy static
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    print("\n>>> Simulasi Sidang MK -- Web Server")
    print("    Buka browser: http://localhost:8080\n")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
