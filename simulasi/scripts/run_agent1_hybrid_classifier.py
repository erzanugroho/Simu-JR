"""
run_agent1_hybrid_classifier.py  —  MEGA-OPTIMIZED
====================================================
Arsitektur 3 Fase:
  Fase A – Bulk Scan  : 1 pass baca seluruh ChromaDB (120 page query, bukan 11.365)
  Fase B – Parallel   : Regex / LLM sepenuhnya in-memory (tidak ada DB access)
  Fase C – Bulk Write : Tulis semua update sekaligus (batch 2000, bukan 1 per chunk)

Estimasi waktu: ~7–12 menit untuk 11.365 file (vs 18 jam sebelumnya)

Penggunaan:
    python run_agent1_hybrid_classifier.py [--workers N] [--llm-fallback] [--dry-run]
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Suppress HuggingFace noise
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
CHROMA_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rag", "chroma_db")
LLM_BASE_URL  = "http://192.168.1.102:1234/v1"
LLM_API_KEY   = "lm-studio"
PROMPT_PATH   = r"e:\Simu JR\simulasi\rag\prompts\agent1_classifier.txt"
LOG_FILE      = r"e:\Simu JR\simulasi\agent1_hybrid_classifier.log"

PRIORITY_LABELS  = {"[TAX]", "[ANTI_AVOIDANCE]", "[OPENpolicy]"}
PAGE_SIZE        = 10_000   # records per bulk scan page
WRITE_BATCH_SIZE = 2_000    # records per bulk write batch
MAX_TEXT_CHUNKS  = 8        # maks chunk per file yang disimpan untuk regex

# ---------------------------------------------------------------------------
# Keyword map
# ---------------------------------------------------------------------------
KEYWORD_MAP = {
    "[TAX]":              ["pajak", "bphtb", "pph", "ppn", "fiskal", "bea perolehan",
                           "bea materai", "cukai", "retribusi pajak", "wajib pajak", "surat setoran"],
    "[ANTI_AVOIDANCE]":   ["penghindaran pajak", "anti avoidance", "tax avoidance",
                           "penyalahgunaan", "skema pajak"],
    "[OPENpolicy]":       ["kebijakan hukum terbuka", "open legal policy", "legal policy",
                           "diskresi pembentuk undang-undang"],
    "[STANDING]":         ["legal standing", "kedudukan hukum pemohon",
                           "kualifikasi pemohon", "kerugian konstitusional"],
    "[CAUSAL]":           ["causal verband", "hubungan sebab akibat",
                           "kerugian yang bersifat spesifik", "akibat hukum", "dampak konstitusional"],
    "[IMPLEMENTASI]":     ["implementasi", "pelaksanaan undang-undang",
                           "peraturan pelaksana", "peraturan pemerintah"],
    "[KEPASTIAN_HUKUM]":  ["kepastian hukum", "rechtzekerheid", "rechtssicherheit", "norma yang jelas"],
    "[PROPORSIONALITAS]": ["proporsionalitas", "proporsional", "keseimbangan", "pembatasan hak"],
    "[CONDITIONAL]":      ["konstitusional bersyarat", "inkonstitusional bersyarat",
                           "conditionally constitutional"],
    "[28D1]":             ["pasal 28d ayat (1)", "persamaan kedudukan", "perlakuan yang sama"],
    "[28D2]":             ["pasal 28d ayat (2)", "bekerja", "imbalan yang adil"],
    "[28E]":              ["pasal 28e", "kebebasan beragama", "menyatakan pikiran"],
    "[28G]":              ["pasal 28g", "perlindungan diri", "rasa aman"],
    "[28H]":              ["pasal 28h", "hidup sejahtera", "pelayanan kesehatan", "jaminan sosial"],
    "[28I]":              ["pasal 28i", "hak untuk hidup", "tidak disiksa", "identitas budaya"],
    "[14]":               ["pasal 14", "grasi", "amnesti", "abolisi", "rehabilitasi"],
    "[FORUM]":            ["forum privilegiatum", "pengadilan khusus", "hak untuk diadili"],
    "[REVENUE]":          ["penerimaan negara", "keuangan negara", "anggaran", "apbn"],
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

def extract_tahun(text: str, filename: str) -> str:
    m = re.search(r"_(\d{4})\.pdf", filename)
    if m: return m.group(1)
    m = re.search(r"PUU[/-][IVXLC]+[/-](\d{4})", text)
    if m: return m.group(1)
    return "kosong"

def extract_amar(text: str) -> str:
    t = text.lower()
    if "mengabulkan" in t or "dikabulkan" in t: return "dikabulkan"
    if "menolak" in t or "ditolak" in t:         return "ditolak"
    if "tidak dapat diterima" in t or "niet ontvankelijk" in t: return "tidak_dapat_diterima"
    return "kosong"

def extract_norma_diuji(text: str) -> str:
    for pat in [
        r"(?:Pasal|pasal)\s+\d+[\w\s()\[\],]*(?:Undang[-\s]Undang|UU)\s+(?:Nomor\s+)?\d+",
        r"(?:UU|Undang-Undang)\s+(?:No\.|Nomor)\s+\d+\s+Tahun\s+\d{4}",
    ]:
        m = re.search(pat, text)
        if m: return m.group(0)[:150]
    return "kosong"

def extract_batu_uji(text: str) -> list:
    found = []
    for m in re.finditer(
        r"(?:Pasal|pasal)\s+\d+[A-Z]?\s*(?:ayat\s*\(\d+\))?\s*"
        r"(?:UUD|Undang-Undang Dasar)\s*(?:Negara\s+Republik\s+Indonesia\s+)?(?:Tahun\s+)?1945",
        text,
    ):
        val = m.group(0)[:100]
        if val not in found: found.append(val)
    return found[:5]

def extract_klaster(text: str) -> list:
    t = text.lower()
    found = []
    for label, keywords in KEYWORD_MAP.items():
        if any(kw in t for kw in keywords):
            if label not in found: found.append(label)
    return found

def calc_priority(klaster: list, amar: str) -> bool:
    if any(lbl in PRIORITY_LABELS for lbl in klaster): return True
    if amar == "dikabulkan" and len(klaster) >= 2:      return True
    return False


# ---------------------------------------------------------------------------
# LLM Fallback
# ---------------------------------------------------------------------------

def load_llm_prompt() -> str:
    return Path(PROMPT_PATH).read_text(encoding="utf-8")

def _repair_json(raw: str) -> str:
    """Perbaiki masalah JSON umum dari LLM output."""
    # Hapus trailing comma sebelum } atau ]
    raw = re.sub(r",\s*([\]}])", r"\1", raw)
    # Ganti true/false JavaScript-style yang mungkin salah kapitalisasi
    raw = re.sub(r"\bTrue\b", "true", raw)
    raw = re.sub(r"\bFalse\b", "false", raw)
    return raw


# Prompt langsung di-hardcode, tanpa contoh format yang bisa di-echo model
_LLM_SYSTEM_PROMPT = """Anda adalah Agent Klasifikasi Hukum Konstitusi.
Ekstrak metadata dari dokumen MK di bawah ini. JAWAB HANYA JSON, TANPA PENJELASAN.

Katalog klaster: [TAX], [STANDING], [CAUSAL], [OPENpolicy], [IMPLEMENTASI], [28D1], [28D2], [28E], [28G], [28H], [28I], [14], [CONDITIONAL], [FORUM], [ANTI_AVOIDANCE], [REVENUE], [PROPORSIONALITAS], [KEPASTIAN_HUKUM]

flag_priority = true jika klaster mengandung [TAX]/[ANTI_AVOIDANCE]/[OPENpolicy], atau putusan dikabulkan dengan isu kompleks.

Output keys: tahun, norma_diuji, batu_uji (array), amar (dikabulkan/ditolak/tidak_dapat_diterima/kosong), klaster (array), flag_priority (bool). Isi "kosong" jika tidak ditemukan."""


def classify_with_llm(text: str, filename: str, client_llm, prompt_template: str):
    """Kirim teks ke LLM dan parse hasil JSON-nya."""
    doc_text = text[:1500]  # Dibatasi agar tidak overflow context
    raw = ""
    try:
        response = client_llm.chat.completions.create(
            model="local-model",
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"{doc_text}\n\n/no_think",
                },
            ],
            temperature=0,
            max_tokens=10000,
            timeout=60,
            response_format={"type": "text"},
        )
        raw = (response.choices[0].message.content or "").strip()

        # Strip tag <think>...</think> jika model tetap pakai
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()

        # Bersihkan markdown code block
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()

        # Ekstrak blok JSON dari mana saja dalam response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, flags=re.DOTALL)
        if json_match:
            raw = json_match.group(0).strip()

        if not raw:
            logger.warning(f"[LLM] Tidak ada JSON ditemukan untuk '{filename}'")
            return None

        # Repair JSON umum (trailing comma, dll)
        raw = _repair_json(raw)

        result = json.loads(raw)

        # Validasi: tolak jika model mengembalikan template contoh
        if result.get("tahun") == "YYYY" or result.get("norma_diuji") == "pasal/ayat UU":
            logger.warning(f"[LLM] Template echo terdeteksi untuk '{filename}'")
            return None

        return result
    except json.JSONDecodeError as exc:
        logger.warning(f"[LLM] JSON error '{filename}': {exc} | raw={raw[:150]!r}")
        return None
    except Exception as exc:
        logger.warning(f"[LLM] Gagal '{filename}': {exc}")
        return None


# ===========================================================================
# FASE A – BULK SCAN
# ===========================================================================

def bulk_scan_chromadb(collection) -> dict:
    """
    Satu pass scan SELURUH ChromaDB (~120 page query, bukan 11.365).

    Returns:
        file_map: {
            source_file: {
                "ids"       : [semua chunk id],
                "texts"     : [maks MAX_TEXT_CHUNKS teks pertama],
                "classified": bool,          # True jika klaster sudah ada & tidak kosong
                "klaster"   : list,          # klaster existing (jika classified=True)
                "priority"  : bool,
            }
        }
    """
    file_map: dict[str, dict] = {}
    offset       = 0
    total_scanned = 0

    logger.info("═" * 60)
    logger.info("  FASE A – BULK SCAN (satu pass seluruh ChromaDB)")
    logger.info("═" * 60)

    with tqdm(desc="Scanning ChromaDB", unit="rec", unit_scale=True, ncols=90) as pbar:
        while True:
            batch = collection.get(
                limit=PAGE_SIZE,
                offset=offset,
                include=["documents", "metadatas"],
            )
            ids   = batch.get("ids", [])
            docs  = batch.get("documents", [])
            metas = batch.get("metadatas", [])

            if not ids:
                break

            for doc_id, doc, meta in zip(ids, docs, metas):
                fn = (meta or {}).get("source_file")
                if not fn:
                    continue

                if fn not in file_map:
                    file_map[fn] = {
                        "ids":        [],
                        "texts":      [],
                        "classified": False,
                        "klaster":    [],
                        "priority":   False,
                    }

                entry = file_map[fn]
                entry["ids"].append(doc_id)

                # Simpan teks hanya untuk MAX_TEXT_CHUNKS chunk pertama
                if len(entry["texts"]) < MAX_TEXT_CHUNKS and doc:
                    entry["texts"].append(doc)

                # Cek apakah sudah terklasifikasi (dari chunk pertama saja)
                if not entry["classified"] and entry["ids"].__len__() == 1:
                    raw_k = (meta or {}).get("klaster", "[]")
                    try:
                        existing = json.loads(raw_k) if raw_k else []
                    except (json.JSONDecodeError, TypeError):
                        existing = []
                    if existing:
                        entry["classified"] = True
                        entry["klaster"]    = existing
                        entry["priority"]   = (meta or {}).get("flag_priority", "false") == "true"

            total_scanned += len(ids)
            pbar.update(len(ids))
            offset += PAGE_SIZE

            if len(ids) < PAGE_SIZE:
                break

    logger.info(f"Scan selesai. Total records: {total_scanned:,} | File unik: {len(file_map):,}")
    return file_map


# ===========================================================================
# FASE B – KLASIFIKASI IN-MEMORY
# ===========================================================================

def classify_in_memory(
    fn: str,
    entry: dict,
    llm_fallback: bool,
    client_llm,
    prompt_template: str | None,
) -> dict:
    """
    Klasifikasi satu file sepenuhnya in-memory. Tidak ada DB access.
    Returns dict hasil yang akan dipakai Fase C.
    """
    if entry["classified"]:
        return {
            "filename": fn,
            "method":   "skip",
            "ids":      [],          # tidak perlu update
            "new_meta": None,
            "klaster":  entry["klaster"],
            "priority": entry["priority"],
            "error":    None,
        }

    text   = " ".join(entry["texts"])
    filename = fn

    # ── Fase 1: Regex ──────────────────────────────────────────────
    klaster = extract_klaster(text)
    tahun   = extract_tahun(text, filename)
    amar    = extract_amar(text)
    norma   = extract_norma_diuji(text)
    batu    = extract_batu_uji(text)
    prio    = calc_priority(klaster, amar)
    method  = "regex"

    # ── Fase 2: LLM Fallback (hanya jika klaster kosong) ───────────
    if not klaster and llm_fallback and client_llm and prompt_template:
        llm_result = classify_with_llm(text, filename, client_llm, prompt_template)
        if llm_result:
            klaster = llm_result.get("klaster", [])
            amar    = llm_result.get("amar",          amar)
            tahun   = llm_result.get("tahun",         tahun)
            norma   = llm_result.get("norma_diuji",   norma)
            batu    = llm_result.get("batu_uji",      batu)
            prio    = llm_result.get("flag_priority",  prio)
            method  = "llm"

    new_meta = {
        "klaster":       json.dumps(klaster),
        "flag_priority": "true" if prio else "false",
        "tahun":         str(tahun),
        "amar":          amar,
        "norma_diuji":   norma if isinstance(norma, str) else "kosong",
        "batu_uji":      json.dumps(batu),
    }

    return {
        "filename": fn,
        "method":   method,
        "ids":      entry["ids"],
        "new_meta": new_meta,
        "klaster":  klaster,
        "priority": prio,
        "error":    None,
    }


# ===========================================================================
# FASE C – BULK WRITE
# ===========================================================================

def bulk_write_updates(collection, results: list, dry_run: bool) -> int:
    """
    Tulis semua update ke ChromaDB dalam batch besar.
    Returns jumlah total records yang diupdate.
    """
    logger.info("═" * 60)
    logger.info("  FASE C – BULK WRITE")
    logger.info("═" * 60)

    # Kumpulkan semua (id, meta) yang perlu diupdate
    all_ids:   list[str]  = []
    all_metas: list[dict] = []

    for r in results:
        if r["new_meta"] is None or not r["ids"]:
            continue
        for doc_id in r["ids"]:
            all_ids.append(doc_id)
            all_metas.append(r["new_meta"])

    total_records = len(all_ids)
    if total_records == 0:
        logger.info("Tidak ada record yang perlu diupdate.")
        return 0

    if dry_run:
        logger.info(f"DRY-RUN: Akan update {total_records:,} records (tidak ditulis).")
        return total_records

    logger.info(f"Menulis {total_records:,} records dalam batch {WRITE_BATCH_SIZE}...")
    n_batches = (total_records + WRITE_BATCH_SIZE - 1) // WRITE_BATCH_SIZE

    with tqdm(total=n_batches, desc="Bulk Write", unit="batch", ncols=90) as pbar:
        for i in range(0, total_records, WRITE_BATCH_SIZE):
            batch_ids   = all_ids[i:i + WRITE_BATCH_SIZE]
            batch_metas = all_metas[i:i + WRITE_BATCH_SIZE]
            try:
                collection.update(ids=batch_ids, metadatas=batch_metas)
            except Exception as exc:
                logger.error(f"[WRITE] Error pada batch {i//WRITE_BATCH_SIZE}: {exc}")
            pbar.update(1)

    logger.info(f"✅ Bulk write selesai: {total_records:,} records diupdate.")
    return total_records


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hybrid Agent 1 Classifier – MEGA-OPTIMIZED (Bulk Scan → Parallel Regex → Bulk Write)"
    )
    parser.add_argument("--workers",      type=int, default=8,
                        help="Jumlah thread paralel untuk klasifikasi in-memory (default: 8)")
    parser.add_argument("--llm-fallback", action="store_true",
                        help="Aktifkan LLM untuk dokumen dengan klaster kosong setelah regex")
    parser.add_argument("--dry-run",      action="store_true",
                        help="Hanya print hasil, tidak update ChromaDB")
    args = parser.parse_args()

    t_total_start = time.time()

    logger.info("═" * 60)
    logger.info("  Hybrid Agent 1 Classifier — MEGA-OPTIMIZED")
    logger.info(f"  Workers      : {args.workers}")
    logger.info(f"  LLM Fallback : {args.llm_fallback}")
    logger.info(f"  Dry Run      : {args.dry_run}")
    logger.info("═" * 60)

    # ── Init ChromaDB ────────────────────────────────────────────────
    logger.info("Menghubungkan ke ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2", device="cpu"
    )
    collection = chroma_client.get_collection(
        name="mk_knowledge_base", embedding_function=emb_fn
    )
    logger.info(f"ChromaDB terhubung. Total vectors: {collection.count():,}")

    # ── Init LLM (jika perlu) ────────────────────────────────────────
    client_llm      = None
    prompt_template = None
    if args.llm_fallback:
        logger.info("Init LLM client...")
        client_llm      = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        prompt_template = load_llm_prompt()
        logger.info("LLM siap.")

    # ════════════════════════════════════════════════════════════════
    # FASE A: BULK SCAN
    # ════════════════════════════════════════════════════════════════
    t_a = time.time()
    file_map = bulk_scan_chromadb(collection)
    t_a_elapsed = time.time() - t_a

    filenames      = sorted(file_map.keys())
    total_files    = len(filenames)
    already_done   = sum(1 for e in file_map.values() if e["classified"])
    need_classify  = total_files - already_done

    logger.info(f"\n  📁 Total file unik    : {total_files:,}")
    logger.info(f"  ⏭️  Sudah terklasifikasi: {already_done:,}")
    logger.info(f"  🔄 Perlu diklasifikasi : {need_classify:,}")
    logger.info(f"  ⏱️  Fase A selesai      : {t_a_elapsed:.1f}s\n")

    # ════════════════════════════════════════════════════════════════
    # FASE B: KLASIFIKASI PARALEL IN-MEMORY
    # ════════════════════════════════════════════════════════════════
    logger.info("═" * 60)
    logger.info("  FASE B – KLASIFIKASI PARALEL IN-MEMORY")
    logger.info("═" * 60)

    t_b = time.time()
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                classify_in_memory,
                fn,
                file_map[fn],
                args.llm_fallback,
                client_llm,
                prompt_template,
            ): fn
            for fn in filenames
        }

        with tqdm(total=total_files, desc="Mengklasifikasi", unit="file", ncols=90) as pbar:
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                pbar.update(1)

    t_b_elapsed = time.time() - t_b
    logger.info(f"Fase B selesai: {t_b_elapsed:.1f}s")

    # ════════════════════════════════════════════════════════════════
    # FASE C: BULK WRITE
    # ════════════════════════════════════════════════════════════════
    t_c = time.time()
    total_written = bulk_write_updates(collection, results, args.dry_run)
    t_c_elapsed = time.time() - t_c

    # ── Statistik ────────────────────────────────────────────────────
    counts = defaultdict(int)
    for r in results:
        counts[r.get("method", "unknown")] += 1
        if r.get("priority"): counts["priority"] += 1
        if r.get("error"):    counts["error"]    += 1

    regex_count    = counts["regex"]
    llm_count      = counts["llm"]
    skip_count     = counts["skip"]
    priority_count = counts["priority"]
    processed      = regex_count + llm_count
    pct_regex = (regex_count / processed * 100) if processed else 0
    pct_llm   = (llm_count   / processed * 100) if processed else 0

    t_total = time.time() - t_total_start

    logger.info(f"""
{'═' * 60}
  STATISTIK AKHIR
{'═' * 60}
  📁 Total file unik       : {total_files:,}
  ⏭️  Di-skip (sudah ada)   : {skip_count:,}
  📋 Diproses baru         : {processed:,}
  🔤 Selesai via regex     : {regex_count:,} ({pct_regex:.0f}%)
  🤖 Dikirim ke LLM        : {llm_count:,} ({pct_llm:.0f}%)
  ⭐ Marked priority        : {priority_count:,}
  💾 Records ditulis ke DB  : {total_written:,}
{'─' * 60}
  ⏱️  Fase A (Bulk Scan)    : {t_a_elapsed:.1f}s
  ⏱️  Fase B (Klasifikasi)  : {t_b_elapsed:.1f}s
  ⏱️  Fase C (Bulk Write)   : {t_c_elapsed:.1f}s
  ⏱️  TOTAL                 : {t_total:.1f}s ({t_total/60:.1f} menit)
  💾 Dry-run               : {'YA (tidak ada yang diupdate)' if args.dry_run else 'TIDAK'}
{'═' * 60}
""")


if __name__ == "__main__":
    main()
