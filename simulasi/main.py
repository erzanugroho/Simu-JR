"""
Simulasi Sidang Mahkamah Konstitusi (MK) — Entry Point
========================================================
Menjalankan N simulasi sidang pengujian undang-undang (Judicial Review)
dengan agen AI yang berperan sebagai Pemohon, Pemerintah, dan Panel Hakim.
Setiap agen didukung oleh RAG dari 1.1M+ chunks putusan & risalah MK.
"""

import asyncio
import argparse
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any

from core.orchestrator import SimulationOrchestrator
from core.runtime_paths import runtime_dir

# Import simulation store
from core.simulation_store import save_simulation, list_simulations, load_simulation

# Import self-correcting loop
try:
    from core.self_correcting_loop import SelfCorrectingLoop
    SELF_CORRECTING_AVAILABLE = True
except Exception:
    SELF_CORRECTING_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

PROGRESS_FILE = str(runtime_dir("progress") / "progress_history.json")


def load_progress_history():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_progress_entry(scores, draft_excerpt):
    history = load_progress_history()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "draft_excerpt": draft_excerpt[:100],
        "total": scores.get("total", 0),
        "amar": scores.get("amar", "ditolak"),
        "dimensions": {k: scores.get(k, 0) for k in [
            "legal_standing", "kerugian_konstitusional",
            "substansi_argumen", "konsistensi_putusan", "kelengkapan_formil"
        ]}
    }
    history.append(entry)
    history = history[-20:]
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    return history


def print_progress_tracker(history):
    if len(history) < 2:
        return
    prev = history[-2]
    curr = history[-1]
    print(f"\n{'='*60}")
    print("  PROGRESS TRACKER")
    print(f"{'='*60}")
    delta = curr.get("total", 0) - prev.get("total", 0)
    arrow = "+" if delta >= 0 else ""
    print(f"  Skor: {curr.get('total', 0):.1f}/100  ({arrow}{delta:.1f} vs sebelumnya)")
    print(f"  Amar: {curr.get('amar')} | Sebelumnya: {prev.get('amar')}")
    dim_labels = {
        "legal_standing": "Legal Standing",
        "kerugian_konstitusional": "Kerugian Konstitusional",
        "substansi_argumen": "Substansi Argumen",
        "konsistensi_putusan": "Konsistensi Putusan",
        "kelengkapan_formil": "Kelengkapan Formil"
    }
    for key, label in dim_labels.items():
        c = curr.get("dimensions", {}).get(key, 0)
        p = prev.get("dimensions", {}).get(key, 0)
        d = c - p
        arrow2 = "+" if d >= 0 else ""
        icon = "^" if d > 0 else ("v" if d < 0 else "-")
        print(f"  {icon} {label.ljust(28)}: {c:.1f}  ({arrow2}{d:.1f})")

    if len(history) >= 3:
        print(f"\n  Tren (terakhir {min(len(history), 5)} simulasi):")
        for h in history[-5:]:
            t = h.get("total", 0)
            bar = "#" * int(t / 5)
            print(f"    {bar} {t:.0f}")
    print(f"{'='*60}")


async def cli_human_input_callback(prompt: str, rag_context: str, agent_name: str) -> str:
    print(f"\n{'='*60}")
    print("  [GILIRAN ANDA SEBAGAI PEMOHON]")
    print(f"{'='*60}")
    # Tampilkan konteks pertanyaan (600 karakter pertama)
    print(f"Konteks:\n{prompt[:600]}")
    print(f"\nMasukkan argumen Anda (ketik argumen, lalu tekan Enter):")
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, input, "> ")
    return response


def print_final_verdict(results: List[Dict[str, Any]]):
    """Menampilkan hasil akhir agregat dari seluruh simulasi."""
    print("\n" + "═" * 60)
    print("  🏛️  HASIL VERDICT AGGREGATOR")
    print("═" * 60)

    dimensions = {
        "legal_standing": 25,
        "kerugian_konstitusional": 20,
        "substansi_argumen": 30,
        "konsistensi_putusan": 15,
        "kelengkapan_formil": 10
    }

    valid_results = [r for r in results if "error" not in r.get("scores", {})]

    if not valid_results:
        print("❌ Tidak ada data scoring valid yang bisa diagregasi.")
        return

    # Agregasi lintas simulasi
    dim_totals = {d: 0 for d in dimensions}
    total_score = 0
    all_amars = []
    all_catatan = []

    for r in valid_results:
        scores = r["scores"]
        for d in dimensions:
            dim_totals[d] += scores.get(d, 0)
        total_score += scores.get("total", 0)
        all_amars.append(scores.get("amar", "ditolak"))
        all_catatan.extend(scores.get("catatan_hakim", []))

    n = len(valid_results)
    avg_total = total_score / n

    # Voting amar lintas simulasi
    from collections import Counter
    amar_count = Counter(all_amars)
    final_amar = amar_count.most_common(1)[0][0]

    print(f"\n  📊 Simulasi valid: {n}/{len(results)}")
    print(f"  📈 Skor rata-rata: {avg_total:.1f}/100")

    # Amar
    amar_emoji = {"dikabulkan": "✅", "ditolak": "❌", "tidak_dapat_diterima": "⛔"}
    print(f"\n  ⚖️  AMAR PUTUSAN: {amar_emoji.get(final_amar, '❓')} {final_amar.upper()}")
    print(f"     Voting: {dict(amar_count)}")

    # Heatmap kelemahan
    print(f"\n  🔥 HEATMAP KELEMAHAN (Skor Rata-rata per Dimensi):")
    for dim, max_val in dimensions.items():
        avg_dim = dim_totals[dim] / n
        percent = (avg_dim / max_val) * 100
        bar_len = int(percent / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        status = "🟢" if percent >= 70 else "🟡" if percent >= 40 else "🔴"
        print(f"    {status} {dim.ljust(28)}: {avg_dim:.1f}/{max_val} ({percent:.0f}%) [{bar}]")

    # Saran hakim
    if all_catatan:
        print(f"\n  💡 CATATAN DARI PANEL HAKIM:")
        for cat in all_catatan[:10]:  # Limit 10 catatan
            print(f"    • {cat}")

    api_usage_items = [
        r.get("api_usage") or r.get("scores", {}).get("api_usage")
        for r in valid_results
        if (r.get("api_usage") or r.get("scores", {}).get("api_usage"))
    ]
    paid_api_usage = [
        u for u in api_usage_items
        if u and u.get("provider") in {"openrouter", "deepseek", "mimo"}
    ]
    if paid_api_usage:
        total_cost = sum(float(u.get("cost_usd") or 0) for u in paid_api_usage)
        total_tokens = sum(int(u.get("total_tokens") or 0) for u in paid_api_usage)
        total_calls = sum(int(u.get("calls") or 0) for u in paid_api_usage)
        cache_hit_tokens = sum(int(u.get("prompt_cache_hit_tokens") or 0) for u in paid_api_usage)
        cache_miss_tokens = sum(int(u.get("prompt_cache_miss_tokens") or 0) for u in paid_api_usage)
        print(f"\n  API COST:")
        print(f"    Total biaya: ${total_cost:.6f}")
        print(f"    Total token: {total_tokens:,} | API calls: {total_calls}")
        if cache_hit_tokens or cache_miss_tokens:
            print(f"    Cache hit/miss input: {cache_hit_tokens:,} / {cache_miss_tokens:,} token")

    # Dissenting Opinions (ROADMAP Fase 2 #1)
    all_dissenting = []
    for r in valid_results:
        all_dissenting.extend(r.get("dissenting_opinions", []))
    if all_dissenting:
        print(f"\n  ⚖️  DISSENTING / CONCURRING OPINIONS ({len(all_dissenting)} total):")
        for op in all_dissenting:
            icon = "❗" if op["type"] == "Dissenting Opinion" else "💬"
            print(f"\n  {icon} {op['type']} — {op['hakim']}")
            print(f"     Amar Hakim: {op['amar_hakim']} | Amar Mayoritas: {op['amar_mayoritas']}")
            # Tampilkan 3 baris pertama opinion
            lines = op.get("opinion", "").split("\n")[:3]
            for line in lines:
                if line.strip():
                    print(f"     {line.strip()}")

    print("\n" + "═" * 60)


async def run_self_correcting_loop(
    draft_input: str,
    max_loops: int = 5,
    acceptance_threshold: int = 70,
    jumlah_hakim: int = 3
):
    """Menjalankan close-loop self-correcting draft revision."""
    if not SELF_CORRECTING_AVAILABLE:
        print("❌ Self-correcting loop tidak tersedia.")
        return

    print(f"\n🔄 Memulai Self-Correcting Loop (max {max_loops} iterasi, threshold {acceptance_threshold})...\n")

    loop = SelfCorrectingLoop(
        draft_input=draft_input,
        max_loops=max_loops,
        acceptance_threshold=acceptance_threshold,
        jumlah_hakim=jumlah_hakim
    )

    result = await loop.run()

    # Tampilkan hasil
    print("\n" + "═" * 60)
    print("  🔄  HASIL SELF-CORRECTING LOOP")
    print("═" * 60)
    print(f"\n  ✅ Berhasil: {'YA' if result['success'] else 'TIDAK'}")
    print(f"  📊 Total Loop: {result['total_loops']} / {result['max_loops']}")
    print(f"  🏆 Loop Terbaik: #{result['best_loop']} (Skor: {result['best_score']})")

    if result['history']:
        print(f"\n  📋 Riwayat Loop:")
        for record in result['history']:
            loop_num = record['loop']
            scores = record.get('scores', {})
            total = scores.get('total', 0) if scores else 0
            amar = scores.get('amar', 'unknown') if scores else 'unknown'
            accepted = record.get('accepted', False)
            status = "✅ DITERIMA" if accepted else "❌ DITOLAK"
            print(f"    Loop #{loop_num}: {status} | Amar: {amar} | Skor: {total}/100")
            if record.get('revision'):
                changes = record['revision'].get('ringkasan_perubahan', [])
                for c in changes[:3]:
                    print(f"      ↳ {c}")

    print(f"\n  💾 Log tersimpan di: {result['log_dir']}")
    print("\n" + "═" * 60)

    # Simpan hasil akhir juga ke progress history jika ada skor terbaik
    best_record = None
    best_score = -1
    for record in result['history']:
        scores = record.get('scores', {})
        if scores and not scores.get('error'):
            total = scores.get('total', 0)
            if isinstance(total, (int, float)) and total > best_score:
                best_score = total
                best_record = scores
    if best_record:
        save_progress_entry(best_record, draft_input[:100])


async def run_simulations(
    n: int,
    draft_input: str,
    sequential: bool = True,
    mode: str = "ai",
    hearing_mode: str = SimulationOrchestrator.PEDAGOGICAL_MODE,
):
    """Menjalankan N simulasi sidang MK."""
    run_mode_label = "Sekuensial" if sequential else "Paralel"
    print(f"\n🚀 Memulai {n} simulasi ({run_mode_label}, mode={mode})...\n")

    human_callback = cli_human_input_callback if mode == "human" else None

    orchestrators = [
        SimulationOrchestrator(
            i + 1,
            mode=mode,
            human_input_callback=human_callback,
            hearing_mode=hearing_mode,
        )
        for i in range(n)
    ]
    results = []

    if sequential:
        for orch in orchestrators:
            res = await orch.run_full_simulation(draft_input)
            results.append(res)
    else:
        # PERINGATAN: Paralel bisa membebani VRAM/API
        tasks = [orch.run_full_simulation(draft_input) for orch in orchestrators]
        results = await asyncio.gather(*tasks)

    # Simpan setiap simulasi secara individual ke persistent storage
    output_dir = runtime_dir("simulations_cli")
    os.makedirs(output_dir, exist_ok=True)
    for res in results:
        if "error" not in res.get("scores", {}):
            try:
                saved = save_simulation(
                    simulation_data=res,
                    draft=draft_input,
                    config={"mode": mode, "sequential": sequential},
                )
                print(f"  💾 Simulasi {saved['id']} disimpan (skor: {saved['total_score']}, amar: {saved['amar']})")
            except Exception as e:
                logger.warning(f"Gagal menyimpan simulasi: {e}")

    # Simpan transcript lengkap (backward-compatible)
    output_path = str(output_dir / "all_simulations.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n📝 Transcript simulasi disimpan di: {output_path}")

    # Tampilkan verdict
    print_final_verdict(results)

    # Progress tracker
    valid = [r for r in results if "error" not in r.get("scores", {})]
    if valid:
        avg_scores = valid[0]["scores"]  # Gunakan hasil simulasi pertama yang valid
        history = save_progress_entry(avg_scores, draft_input[:100])
        print_progress_tracker(history)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="🏛️ Simulasi Sidang MK — Pengujian Undang-Undang (AI vs AI)"
    )
    parser.add_argument(
        "--n", type=int, default=3,
        help="Jumlah simulasi yang dijalankan (default: 3)"
    )
    parser.add_argument(
        "--parallel", action="store_true",
        help="Jalankan secara paralel (AWAS VRAM!)"
    )
    parser.add_argument(
        "--draft", type=str, default=None,
        help="Path ke file .txt berisi draft permohonan (opsional)"
    )
    parser.add_argument(
        "--mode", choices=["ai", "human"], default="ai",
        help="Mode simulasi: 'ai' (default) atau 'human' (Anda berperan sebagai Pemohon)"
    )
    parser.add_argument(
        "--hearing-mode",
        choices=[
            "pemeriksaan_pendahuluan",
            "perbaikan_permohonan",
            "keterangan_pemerintah_dpr",
            "pemeriksaan_ahli",
            "pembuktian",
            "putusan",
            "full_training_simulation",
        ],
        default=SimulationOrchestrator.PEDAGOGICAL_MODE,
        help="Profil sidang CLI (default: full_training_simulation untuk tetap menghasilkan skor)"
    )
    parser.add_argument(
        "--self-correcting", action="store_true",
        help="Aktifkan mode close-loop self-correcting draft revision"
    )
    parser.add_argument(
        "--max-loops", type=int, default=5,
        help="Batas maksimal loop self-correcting (default: 5)"
    )
    parser.add_argument(
        "--threshold", type=int, default=70,
        help="Skor minimum untuk draft diterima (default: 70)"
    )
    parser.add_argument(
        "--list-sims", action="store_true",
        help="Tampilkan daftar simulasi tersimpan"
    )
    parser.add_argument(
        "--show-sim", type=str, default=None,
        help="Tampilkan detail simulasi berdasarkan ID"
    )
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Batas jumlah simulasi yang ditampilkan (default: 20)"
    )
    args = parser.parse_args()

    # Input draft
    if args.draft and os.path.exists(args.draft):
        with open(args.draft, "r", encoding="utf-8") as f:
            draft = f.read()
        print(f"📄 Draft dimuat dari: {args.draft}")
    else:
        draft = (
            "Pemohon mengajukan pengujian Pasal 28 ayat (1) UU No. 11 Tahun 2008 "
            "tentang Informasi dan Transaksi Elektronik (UU ITE). "
            "Pemohon adalah seorang jurnalis investigasi yang merasa hak kebebasan "
            "berpendapat dan kebebasan pers yang dijamin Pasal 28E ayat (2) dan "
            "Pasal 28F UUD 1945 terancam oleh ketentuan tersebut. "
            "Kerugian aktual berupa pemanggilan oleh kepolisian karena mempublikasikan "
            "artikel kritik terhadap kebijakan pejabat daerah di media daring. "
            "Pemohon berpendapat frasa 'menyebarkan berita bohong' dalam pasal tersebut "
            "bersifat multi-tafsir (overbreadth) dan berpotensi menjadi alat kriminalisasi "
            "terhadap kebebasan berekspresi."
        )
        print("📄 Menggunakan draft contoh (UU ITE)")

    if args.self_correcting:
        asyncio.run(run_self_correcting_loop(
            draft_input=draft,
            max_loops=args.max_loops,
            acceptance_threshold=args.threshold,
            jumlah_hakim=3
        ))
    elif args.list_sims:
        # Tampilkan daftar simulasi tersimpan
        result = list_simulations(limit=args.limit)
        sims = result.get("simulations", [])
        total = result.get("total", 0)
        print(f"\n{'='*70}")
        print(f"  DAFTAR SIMULASI TERSIMPAN ({total} total)")
        print(f"{'='*70}")
        if not sims:
            print("  Belum ada simulasi tersimpan.")
        else:
            for s in sims:
                ts = s.get("timestamp", "")[:19].replace("T", " ")
                score = s.get("total_score", 0)
                amar = s.get("amar", "-")
                excerpt = s.get("draft_excerpt", "")[:60]
                n_transcript = s.get("transcript_count", 0)
                print(f"  [{s['id']}] {ts}  |  Skor: {score:5.1f}  |  Amar: {amar:20s}  |  {n_transcript} entri")
                if excerpt:
                    print(f"           Draft: {excerpt}...")
        print(f"{'='*70}")
    elif args.show_sim:
        # Tampilkan detail simulasi tersimpan
        data = load_simulation(args.show_sim)
        if not data:
            print(f"❌ Simulasi '{args.show_sim}' tidak ditemukan.")
        else:
            scores = data.get("scores", {})
            print(f"\n{'='*70}")
            print(f"  DETAIL SIMULASI: {args.show_sim}")
            print(f"{'='*70}")
            print(f"  Waktu    : {data.get('timestamp', '-')[:19]}")
            print(f"  Skor     : {scores.get('total', 0)}/100")
            print(f"  Amar     : {scores.get('amar', '-')}")
            print(f"  Voting   : {scores.get('voting_detail', {})}")
            print(f"  Transcript: {len(data.get('transcript', []))} entri")
            draft_text = data.get("draft", "")
            if draft_text:
                print(f"\n  Draft ({len(draft_text)} kar):")
                print(f"  {draft_text[:300]}...")
            catatan = scores.get("catatan_hakim", [])
            if catatan:
                print(f"\n  Pertimbangan Hakim:")
                for c in catatan:
                    print(f"    • {c}")
            dissenting = data.get("dissenting_opinions", [])
            if dissenting:
                print(f"\n  Dissenting/Concurring Opinions:")
                for op in dissenting:
                    print(f"    [{op.get('type', '')}] {op.get('hakim', '')}")
            feedback = data.get("feedback", {})
            if feedback and not feedback.get("error"):
                print(f"\n  Feedback:")
                print(f"    Skor potensial perbaikan: {feedback.get('skor_potensial_perbaikan', '-')}")
                for kelemahan in feedback.get("kelemahan_utama", []):
                    print(f"    Kelemahan: {kelemahan}")
            print(f"{'='*70}")
    else:
        asyncio.run(run_simulations(
            args.n,
            draft,
            sequential=not args.parallel,
            mode=args.mode,
            hearing_mode=args.hearing_mode,
        ))
