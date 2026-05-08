"""
Self-Correcting Loop — Close Loop Draft Revision
=================================================
Modul untuk menjalankan simulasi sidang berulang kali dengan revisi draft
otomatis sampai draft diterima atau mencapai batas maksimal loop.

Alur:
  1. User input draft
  2. Jalankan simulasi sidang
  3. Evaluasi hasil (amar + skor)
  4. Jika ditolak → revisi draft berdasarkan transcript & feedback
  5. Ulangi dari langkah 2 dengan draft revisi
  6. Simpan log setiap iterasi
"""

import asyncio
import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .orchestrator import SimulationOrchestrator
from .draft_reviser import revise_draft, is_draft_accepted
from .runtime_paths import runtime_dir

logger = logging.getLogger(__name__)

LOG_DIR = runtime_dir("self_correcting_logs")


class SelfCorrectingLoop:
    """
    Orchestrator untuk close-loop self-correcting draft revision.
    """

    def __init__(
        self,
        draft_input: str,
        llm_config: Dict[str, Any] = None,
        max_loops: int = 5,
        acceptance_threshold: int = 70,
        jumlah_hakim: int = 3,
        log_dir: str = None,
        event_queue: Optional[asyncio.Queue] = None,
        retriever: Optional[Any] = None
    ):
        self.original_draft = draft_input
        self.current_draft = draft_input
        self.llm_config = llm_config or {}
        self.max_loops = max_loops
        self.acceptance_threshold = acceptance_threshold
        self.jumlah_hakim = jumlah_hakim
        self.log_dir = Path(log_dir) if log_dir else LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.event_queue = event_queue
        self.retriever = retriever

        self.loop_history: List[Dict[str, Any]] = []
        self.current_loop = 0

    def _emit(self, event_type: str, data: Dict[str, Any]):
        """Kirim event ke queue jika tersedia (untuk SSE streaming)."""
        if self.event_queue is not None:
            try:
                self.event_queue.put_nowait((event_type, data))
            except Exception:
                pass

    def _build_external_revision_context(
        self,
        scores: Dict[str, Any],
        feedback: Dict[str, Any],
        transcript: List[Dict[str, Any]]
    ) -> str:
        """
        Ambil konteks tambahan untuk agent revisi:
        - risalah perkara lain yang masalah/normanya mirip,
        - pola serangan Pemerintah/DPR/Kementerian,
        - concern hakim dan jawaban Pemohon yang pernah survive.
        """
        if not self.retriever:
            try:
                from rag.retriever import RAGRetriever
                logger.info("📚 Memuat RAG retriever lazy untuk konteks revisi draft...")
                self.retriever = RAGRetriever()
            except Exception as e:
                logger.warning(f"Konteks risalah/attack bank tidak tersedia untuk revisi: {e}")
                return ""

        weakness_parts = []
        for key in ["legal_standing", "kerugian_konstitusional", "substansi_argumen", "konsistensi_putusan", "kelengkapan_formil"]:
            if key in scores:
                weakness_parts.append(f"{key}: {scores.get(key)}")
        if feedback:
            weakness_parts.append(json.dumps(feedback, ensure_ascii=False)[:1200])

        gov_transcript = []
        for entry in transcript:
            speaker = str(entry.get("speaker", "")).lower()
            if any(x in speaker for x in ["pemerintah", "dpr", "presiden", "menteri", "kementerian"]):
                gov_transcript.append(str(entry.get("content", ""))[:500])

        query = (
            f"{self.current_draft[:1200]}\n\n"
            f"Kelemahan/skor: {'; '.join(weakness_parts)}\n\n"
            f"Argumen negara dalam simulasi ini: {' '.join(gov_transcript[-4:])}"
        )

        parts = []
        try:
            risalah = self.retriever.query(query, n_results=5, filter_jenis="risalah").get("context_text", "")
            if risalah:
                parts.append("=== RISALAH PERKARA MIRIP (isu/norma terkait) ===\n" + risalah)
        except Exception as e:
            logger.warning(f"Gagal mengambil konteks risalah untuk revisi: {e}")

        for title, method_name in [
            ("GOVERNMENT/DPR ATTACK BANK", "query_attack_bank"),
            ("JUDGE CONCERN BANK", "query_concern_bank"),
            ("SURVIVE BANK", "query_survive_bank"),
            ("RATIO BANK", "query_ratio_bank"),
        ]:
            try:
                method = getattr(self.retriever, method_name, None)
                if method:
                    ctx = method(query, n_results=4)
                    if ctx:
                        parts.append(f"=== {title} ===\n{ctx}")
            except Exception as e:
                logger.warning(f"Gagal mengambil {title} untuk revisi: {e}")

        return "\n\n".join(parts)[:6000]

    async def run(self) -> Dict[str, Any]:
        """
        Jalankan close-loop self-correcting sampai draft diterima atau max loop tercapai.

        Returns:
            Dict hasil akhir dengan seluruh history loop.
        """
        logger.info("=" * 70)
        logger.info("  SELF-CORRECTING DRAFT REVISION LOOP")
        logger.info("=" * 70)
        logger.info(f"  Max loops: {self.max_loops}")
        logger.info(f"  Acceptance threshold: {self.acceptance_threshold}")
        logger.info(f"  Draft awal: {self.original_draft[:80]}...")

        while self.current_loop < self.max_loops:
            self.current_loop += 1
            logger.info(f"\n{'─' * 60}")
            logger.info(f"  LOOP #{self.current_loop} / {self.max_loops}")
            logger.info(f"{'─' * 60}")

            self._emit("loop_started", {
                "loop": self.current_loop,
                "max_loops": self.max_loops,
                "draft_excerpt": self.current_draft[:200]
            })

            # 1. Jalankan simulasi dengan draft saat ini
            logger.info(f"📄 Draft: {self.current_draft[:80]}...")
            
            async def chunk_callback(role, chunk):
                self._emit("transcript_chunk", {
                    "loop": self.current_loop,
                    "role": role,
                    "content": chunk
                })

            orch = SimulationOrchestrator(
                simulation_id=self.current_loop,
                jumlah_hakim=self.jumlah_hakim,
                llm_config=self.llm_config,
                retriever=self.retriever,
                on_chunk_callback=chunk_callback,
                hearing_mode=SimulationOrchestrator.PEDAGOGICAL_MODE,
            )
            result = await orch.run_full_simulation(self.current_draft)

            scores = result.get("scores", {})
            feedback = result.get("feedback", {})
            transcript = result.get("transcript", [])

            # 2. Evaluasi hasil
            accepted = is_draft_accepted(scores, self.acceptance_threshold)
            loop_record = {
                "loop": self.current_loop,
                "timestamp": datetime.now().isoformat(),
                "draft": self.current_draft,
                "scores": scores,
                "feedback": feedback,
                "accepted": accepted,
                "transcript_count": len(transcript)
            }
            self.loop_history.append(loop_record)

            logger.info(f"\n  📊 Hasil Loop #{self.current_loop}:")
            if scores and not scores.get("error"):
                logger.info(f"     Total Skor: {scores.get('total', 0)}/100")
                logger.info(f"     Amar: {scores.get('amar', 'unknown')}")
            logger.info(f"     Diterima: {'YA' if accepted else 'TIDAK'}")

            self._emit("loop_result", {
                "loop": self.current_loop,
                "accepted": accepted,
                "scores": scores,
                "feedback": feedback
            })

            # 3. Jika diterima, selesai
            if accepted:
                self._save_loop_log(loop_record)
                logger.info(f"\n{'=' * 60}")
                logger.info(f"  LOOP BERHASIL — Draft diterima pada iterasi #{self.current_loop}")
                logger.info(f"{'=' * 60}")
                self._emit("loop_accepted", {
                    "loop": self.current_loop,
                    "scores": scores
                })
                return self._build_final_result(success=True)

            # 4. Jika masih ditolak dan belum max loop → revisi draft
            if self.current_loop < self.max_loops:
                logger.info(f"\n  🔄 Draft ditolak. Memulai revisi otomatis...")
                self._emit("revision_started", {
                    "loop": self.current_loop,
                    "next_loop": self.current_loop + 1,
                    "scores": scores,
                    "feedback": feedback
                })
                revision = await revise_draft(
                    draft=self.current_draft,
                    transcript=transcript,
                    feedback=feedback,
                    scores=scores,
                    llm_config=self.llm_config,
                    loop_iteration=self.current_loop,
                    external_context=self._build_external_revision_context(scores, feedback, transcript)
                )

                if "error" in revision:
                    logger.error(f"  ❌ Gagal merevisi draft: {revision['error']}")
                    # Lanjutkan dengan draft yang sama jika revisi gagal
                    loop_record["revision_error"] = revision["error"]
                    self._emit("revision_error", {"loop": self.current_loop, "error": revision["error"]})
                else:
                    new_draft = revision.get("draft_revisi", self.current_draft)
                    changes = revision.get("ringkasan_perubahan", [])
                    reasons = revision.get("alasan_perubahan", [])
                    old_hash = hashlib.sha256(self.current_draft.strip().encode("utf-8")).hexdigest()
                    new_hash = hashlib.sha256(str(new_draft).strip().encode("utf-8")).hexdigest()

                    logger.info(f"  ✅ Draft revisi berhasil dibuat.")
                    if changes:
                        logger.info(f"  📝 Perubahan:")
                        for c in changes:
                            logger.info(f"     • {c}")

                    loop_record["revision"] = {
                        "ringkasan_perubahan": changes,
                        "alasan_perubahan": reasons,
                        "aspek_diperbaiki": revision.get("aspek_diperbaiki", {}),
                        "draft_revisi": new_draft,
                        "changed": old_hash != new_hash
                    }
                    self.current_draft = new_draft
                    self._emit("revision_done", {
                        "loop": self.current_loop,
                        "next_loop": self.current_loop + 1,
                        "changes": changes,
                        "reasons": reasons,
                        "draft_excerpt": str(new_draft)[:200],
                        "draft_revisi": new_draft,
                        "changed": old_hash != new_hash
                    })

                # Simpan setelah revisi agar log iterasi memuat draft revisi dan metadata perubahan.
                self._save_loop_log(loop_record)
            else:
                self._save_loop_log(loop_record)
                logger.info(f"\n  ⛔ Max loop ({self.max_loops}) tercapai.")
                self._emit("max_loop_reached", {
                    "loop": self.current_loop,
                    "max_loops": self.max_loops
                })

        # Max loop tercapai tanpa diterima
        logger.info(f"\n{'=' * 60}")
        logger.info(f"  LOOP SELESAI — Draft belum diterima setelah {self.max_loops} iterasi")
        logger.info(f"{'=' * 60}")
        return self._build_final_result(success=False)

    def _save_loop_log(self, loop_record: Dict[str, Any]):
        """Simpan log satu loop ke file JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"loop_{loop_record['loop']:02d}_{timestamp}.json"
        filepath = self.log_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(loop_record, f, ensure_ascii=False, indent=2)

        logger.info(f"  💾 Log disimpan: {filepath}")

    def _build_final_result(self, success: bool) -> Dict[str, Any]:
        """Bangun hasil akhir dari seluruh loop."""
        best_loop = None
        best_score = -1

        for record in self.loop_history:
            scores = record.get("scores", {})
            if scores and not scores.get("error"):
                total = scores.get("total", 0)
                if isinstance(total, (int, float)) and total > best_score:
                    best_score = total
                    best_loop = record

        result = {
            "success": success,
            "total_loops": self.current_loop,
            "max_loops": self.max_loops,
            "threshold": self.acceptance_threshold,
            "original_draft": self.original_draft,
            "final_draft": self.current_draft,
            "best_loop": best_loop["loop"] if best_loop else None,
            "best_score": best_score if best_score >= 0 else None,
            "history": self.loop_history,
            "log_dir": str(self.log_dir)
        }

        # Simpan hasil akhir
        summary_path = self.log_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"  📋 Ringkasan disimpan: {summary_path}")

        return result
