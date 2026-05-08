"""
Simulation Orchestrator — Sidang MK
=====================================
Mengatur alur sidang pengujian undang-undang (PUU) sesuai hukum acara MK.
Setiap ronde meng-query RAG untuk memperkaya argumen agents dengan referensi hukum.

Alur Sidang (ROADMAP terintegrasi):
  Ronde 1  → Pemeriksaan Pendahuluan (Legal Standing)
  Ronde 2  → Perbaikan Permohonan (opsional)
  Ronde 2B → Pemeriksaan Ahli — BARU (ROADMAP Fase 3 #4)
  Ronde 3  → Pokok Perkara + Pihak Terkait + Amicus Curiae — DIPERLUAS (ROADMAP Fase 2 #2)
  Ronde 4  → Kesimpulan & RPH + Dissenting Opinion — DIPERLUAS (ROADMAP Fase 2 #1)

Fitur Baru:
  - Validator Dalil (Anti-Hallucination) sebelum pencatatan transcript (ROADMAP Fase 2 #3)
  - Word Limiter + Interupsi Hakim per respons agen (ROADMAP Fase 3 #5)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from typing import Dict, Any, List, Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def clean_transcript_content(text: str) -> str:
    """Bersihkan output LLM dari chain-of-thought, self-correction, dan JSON leak."""
    from .utils import strip_cot
    return strip_cot(text)

from .agents import (
    PemohonAgent, PemerintahAgent, HakimAgent,
    PihakTerkaitAgent, AmicusCuriaeAgent,
    AhliPemohonAgent, AhliPemerintahAgent,
    ValidatorAgent,
    extract_relevant_uud_pasals, UUD_TEXT,
)
from rag.pasal_api import pasal_api

# Import retriever — graceful fallback jika DB belum ada
try:
    if os.getenv("SIMU_DISABLE_RAG_IMPORT") == "1":
        raise ImportError("RAG import disabled by SIMU_DISABLE_RAG_IMPORT")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from rag.retriever import RAGRetriever
    RAG_AVAILABLE = True
except Exception as e:
    RAG_AVAILABLE = False
    logging.warning(f"⚠️ RAG tidak tersedia: {e}. Simulasi berjalan tanpa referensi hukum.")

logger = logging.getLogger(__name__)


class SimulationOrchestrator:
    """Orkestrator utama yang mengatur alur sidang MK."""

    PEDAGOGICAL_MODE = "full_training_simulation"
    DEFAULT_HEARING_MODE = "pemeriksaan_pendahuluan"
    HEARING_PROFILES = {
        "pemeriksaan_pendahuluan": {
            "label": "Pemeriksaan Pendahuluan",
            "phase": "hearing_pendahuluan",
            "turn_range": (5, 20),
        },
        "perbaikan_permohonan": {
            "label": "Perbaikan Permohonan",
            "phase": "hearing_perbaikan",
            "turn_range": (5, 20),
        },
        "keterangan_pemerintah_dpr": {
            "label": "Mendengarkan Keterangan Pemerintah/DPR",
            "phase": "hearing_pemerintah_dpr",
            "turn_range": (25, 60),
        },
        "pemeriksaan_ahli": {
            "label": "Pemeriksaan Ahli",
            "phase": "hearing_ahli",
            "turn_range": (25, 60),
        },
        "pembuktian": {
            "label": "Pembuktian",
            "phase": "hearing_pembuktian",
            "turn_range": (25, 60),
        },
        "putusan": {
            "label": "Pengucapan Putusan",
            "phase": "hearing_putusan",
            "turn_range": (5, 20),
        },
    }
    HEARING_MODE_ALIASES = {
        "full": PEDAGOGICAL_MODE,
        "training": PEDAGOGICAL_MODE,
        "pedagogis": PEDAGOGICAL_MODE,
        "simulasi_lengkap": PEDAGOGICAL_MODE,
        "pemerintah": "keterangan_pemerintah_dpr",
        "dpr": "keterangan_pemerintah_dpr",
        "ahli": "pemeriksaan_ahli",
        "pendahuluan": "pemeriksaan_pendahuluan",
        "perbaikan": "perbaikan_permohonan",
    }
    DEFAULT_PERSONAS = ["formalis", "progresif", "positivis"]
    SCORE_DIMENSIONS = [
        "legal_standing",
        "kerugian_konstitusional",
        "substansi_argumen",
        "konsistensi_putusan",
        "kelengkapan_formil",
    ]
    SCORE_MAX = {
        "legal_standing": 25,
        "kerugian_konstitusional": 20,
        "substansi_argumen": 30,
        "konsistensi_putusan": 15,
        "kelengkapan_formil": 10,
    }

    def __init__(
        self,
        simulation_id: int,
        jumlah_hakim: int = 3,
        llm_config: Dict[str, Any] = None,
        on_chunk_callback: Any = None,
        include_pihak_terkait: bool = True,
        include_amicus: bool = True,
        include_ahli: bool = True,
        enable_validator: bool = True,
        mode: str = "ai",
        human_input_callback: Optional[Any] = None,
        retriever: Optional[Any] = None,
        judge_personas: Optional[List[str]] = None,
        hearing_mode: str = DEFAULT_HEARING_MODE,
        target_turn_range: Optional[Any] = None,
    ):
        self.simulation_id = simulation_id
        self.jumlah_hakim = jumlah_hakim
        self.judge_personas = judge_personas or []
        self.hearing_mode = self._normalize_hearing_mode(hearing_mode)
        self.target_turn_range = self._normalize_target_turn_range(target_turn_range)
        self.stop_reason: Optional[str] = None
        self.llm_config = llm_config or {}
        self.on_chunk_callback = on_chunk_callback
        self.include_pihak_terkait = include_pihak_terkait
        self.include_amicus = include_amicus
        self.include_ahli = include_ahli
        self.enable_validator = enable_validator
        self.mode = mode
        self.human_input_callback = human_input_callback

        # === Agen Inti ===
        self.pemohon = PemohonAgent(llm_config=self.llm_config)
        self.pemerintah = PemerintahAgent(llm_config=self.llm_config)

        # === Persona Hakim ===
        if judge_personas:
            personas = judge_personas[:jumlah_hakim]
            # Pad dengan default jika kurang
            while len(personas) < jumlah_hakim:
                idx = len(personas) % len(self.DEFAULT_PERSONAS)
                personas.append(self.DEFAULT_PERSONAS[idx])
        else:
            personas = [self.DEFAULT_PERSONAS[i % len(self.DEFAULT_PERSONAS)] for i in range(jumlah_hakim)]

        self.panel_hakim = [
            HakimAgent(i + 1, llm_config=self.llm_config, persona=personas[i])
            for i in range(jumlah_hakim)
        ]

        # === Agen Baru (ROADMAP Fase 2 & 3) ===
        self.pihak_terkait = PihakTerkaitAgent(llm_config=self.llm_config) if include_pihak_terkait else None
        self.amicus_curiae = AmicusCuriaeAgent(llm_config=self.llm_config) if include_amicus else None
        self.ahli_pemohon = AhliPemohonAgent(llm_config=self.llm_config) if include_ahli else None
        self.ahli_pemerintah = AhliPemerintahAgent(llm_config=self.llm_config) if include_ahli else None
        self.validator = ValidatorAgent(llm_config=self.llm_config) if enable_validator else None

        # Inisialisasi RAG retriever (shared across rounds)
        self.retriever = retriever
        if self.retriever is None and RAG_AVAILABLE:
            try:
                self.retriever = RAGRetriever()
                stats = self.retriever.get_stats()
                logger.info(f"📚 RAG terhubung: {stats['total_vectors']:,} vectors")
            except Exception as e:
                logger.warning(f"⚠️ RAG init gagal: {e}")
                self.retriever = None
        elif self.retriever:
            logger.info("📚 Menggunakan shared RAG retriever")

        self.transcript: List[Dict[str, str]] = []
        self.draft_context: str = ""  # Disimpan setelah ronde 1
        self.dissenting_opinions: List[Dict[str, str]] = []  # ROADMAP Fase 2 #1
        self._rag_cache: Dict[str, str] = {}  # Batch RAG cache per ronde

    def _normalize_hearing_mode(self, hearing_mode: Optional[str]) -> str:
        """Normalize mode sidang baru tanpa memutus mode lama."""
        mode = str(hearing_mode or self.DEFAULT_HEARING_MODE).strip().lower()
        mode = self.HEARING_MODE_ALIASES.get(mode, mode)
        if mode == self.PEDAGOGICAL_MODE or mode in self.HEARING_PROFILES:
            return mode
        logger.warning("Mode sidang tidak dikenal: %s. Pakai default.", hearing_mode)
        return self.DEFAULT_HEARING_MODE

    def _normalize_target_turn_range(self, target_turn_range: Optional[Any]) -> Tuple[int, int]:
        if self.hearing_mode == self.PEDAGOGICAL_MODE:
            return (0, 0)

        default_range = self.HEARING_PROFILES[self.hearing_mode]["turn_range"]
        if not target_turn_range:
            return default_range

        try:
            low, high = target_turn_range
            low = max(1, int(low))
            high = max(low, int(high))
            return (low, high)
        except Exception:
            logger.warning("target_turn_range tidak valid: %r. Pakai default.", target_turn_range)
            return default_range

    def get_hearing_profile(self) -> Dict[str, Any]:
        if self.hearing_mode == self.PEDAGOGICAL_MODE:
            return {
                "label": "Simulasi Lengkap",
                "phase": "full_training_simulation",
                "turn_range": self.target_turn_range,
            }
        return {
            "mode": self.hearing_mode,
            **self.HEARING_PROFILES[self.hearing_mode],
            "turn_range": self.target_turn_range,
        }

    def _select_target_turn_count(self, draft_input: str) -> int:
        low, high = self.target_turn_range
        if high <= 0:
            return 0
        if low == high:
            return low

        seed = f"{self.simulation_id}|{self.hearing_mode}|{len(draft_input)}|{draft_input[:120]}"
        digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()
        return low + (int(digest[:8], 16) % (high - low + 1))

    def _hearing_result(self, stop_reason: str) -> Dict[str, Any]:
        self.stop_reason = stop_reason
        metadata = {
            "hearing_mode": self.hearing_mode,
            "turn_count": len(self.transcript),
            "target_turn_range": list(self.target_turn_range),
            "stop_reason": stop_reason,
        }
        return {
            "simulation_id": self.simulation_id,
            "transcript": self.transcript,
            "scores": {},
            "individual_scores": [],
            "dissenting_opinions": [],
            "feedback": {},
            "metadata": metadata,
        }

    async def _prepare_hearing_context(self, draft_input: str):
        api_context = await self._fetch_uu_context_from_api(draft_input)
        self.draft_context = draft_input + api_context

    async def _chair_closes_hearing(self, round_name: str, reason: str):
        close_text = await self._generate_agent_response(
            self.panel_hakim[0],
            f"Tutup sidang {round_name}. Alasan penutupan: {reason}. "
            "Ucapkan penutup singkat seperti risalah sidang MK dan nyatakan sidang selesai."
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, close_text)

    def _turns_left_for_pair(self, target_turn_count: int) -> bool:
        return len(self.transcript) + 2 < target_turn_count

    def _style_prompt(self, agent: Any, prompt: str) -> str:
        """Tambahkan batas gaya agar transkrip terasa seperti sidang lisan."""
        if "Kembalikan HANYA format JSON" in prompt or "OBJEK JSON" in prompt:
            return prompt

        role = getattr(agent, "role", "")
        if role == "hakim":
            speech_rule = (
                "Buat ucapan hakim seperti risalah MK modern: awali boleh dengan 'Baik,' atau 'Oke,'; "
                "1 isu saja, maksimal 2 kalimat; arahkan pihak secara prosedural, bukan kuliah hukum. "
                "Gunakan bentuk seperti 'jelaskan saja', 'di mana letak kerugiannya?', atau 'itu yang harus dijelaskan'. "
                "Hakim tidak boleh menyapa pihak dengan 'Yang Mulia'; gunakan 'Saudara Pemohon', 'Saudara Ahli', "
                "'Saudara Pemerintah', atau langsung bertanya."
            )
        elif role == "pemohon":
            speech_rule = (
                "Jawab sebagai Kuasa Pemohon seperti risalah MK modern dalam 1-2 kalimat pendek, idealnya 35-55 kata. "
                "Mulai natural dengan 'Baik, Yang Mulia,' 'Izin, Yang Mulia,' atau langsung jawab. "
                "Kalimat pertama jawab inti pertanyaan; kalimat kedua beri 1 fakta/bukti/halaman dan simpulan. "
                "Jangan membaca posita, jangan mengulang semua unsur legal standing kecuali diminta."
            )
        elif role == "ahli":
            speech_rule = (
                "Jawab sebagai ahli lisan di MK: mulai singkat dengan 'Terima kasih, Yang Mulia.' "
                "Maksimal 2-3 kalimat; jelaskan konsep lalu hubungkan langsung ke norma a quo. "
                "Jangan bergaya artikel akademik."
            )
        elif role == "pemerintah":
            speech_rule = (
                "Jawab sebagai Pemerintah dalam gaya risalah: mulai dengan 'Terima kasih, Yang Mulia.' "
                "Maksimal 3 kalimat pendek; tegaskan posisi Pemerintah, dasar kebijakan, dan penutup singkat."
            )
        elif role == "amicus":
            speech_rule = (
                "Jawab sebagai amicus lisan di MK, maksimal 2-3 kalimat pendek. "
                "Berikan satu prinsip komparatif atau akademik yang langsung relevan, lalu rekomendasi singkat. "
                "Jangan membuat heading, markdown, atau esai teori."
            )
        else:
            speech_rule = "Jawab sebagai ucapan sidang lisan, maksimal 4 kalimat pendek."

        case_context = ""
        if self.draft_context:
            case_context = (
                "\n\nKONTEKS PERKARA WAJIB DIIKUTI:\n"
                f"{self.draft_context[:1200]}\n"
                "Dilarang mengganti identitas pemohon, objek norma, atau pokok perkara. "
                "Jika detail tidak ada dalam konteks, jangan mengarang fakta baru. "
                "Jika referensi RAG bertentangan dengan konteks perkara ini, ikuti konteks perkara ini."
            )

        return (
            "ATURAN GAYA SIDANG:\n"
            f"- {speech_rule}\n"
            "- Langsung ke inti, tanpa markdown, tanpa daftar panjang, tanpa heading.\n"
            "- Jika pertanyaan hakim memuat banyak sub-isu, pilih jawaban paling menentukan dulu; detail lain cukup disebut bila perlu.\n"
            "- Gunakan bahasa sidang MK yang natural dan to the point.\n"
            "- Tiru ritme risalah asli: banyak ucapan pendek seperti 'Ya', 'Baik', 'Silakan', 'Cukup', 'Terima kasih'; bukan pidato esai.\n"
            "- Jangan menyebut label internal RAG seperti SURVIVE BANK, RATIO BANK, JUDGE CONCERN BANK, atau GOVERNMENT ATTACK BANK dalam ucapan sidang.\n"
            "- Jangan memakai placeholder seperti 'Nomor ...'; bila nomor perkara tidak tersedia, cukup sebut 'perkara ini'.\n"
            "- Hindari frasa generik panjang seperti 'Yang Terhormat Majelis' berulang-ulang; cukup gunakan 'Yang Mulia' secara natural.\n"
            "- Untuk nasihat perbaikan, maksimal 2 poin lengkap; jangan berhenti pada nomor daftar kosong seperti '2.'.\n"
            "- Hakim tidak pernah memanggil Pemohon, Ahli, Pemerintah, atau Pihak Terkait dengan 'Yang Mulia'.\n"
            "- Untuk Pemohon, bila hakim meminta legal standing, jawab siapa Pemohon, apa haknya, kerugian konkret, dan hubungan norma dalam satu tarikan singkat.\n"
            "- Untuk Hakim, bila Pemohon mulai membaca naskah, arahkan dengan gaya risalah: 'jangan dibacakan, jelaskan pokoknya saja'.\n"
            f"{case_context}\n\n"
            f"TUGAS:\n{prompt}"
        )

    def _inject_uud_context(self, prompt: str, rag_context: str) -> str:
        """Tambahkan pasal UUD 1945 yang relevan ke rag_context berdasarkan prompt + draft."""
        if not UUD_TEXT:
            return rag_context
        # Gabungkan prompt + draft_context sebagai basis pencarian
        search_text = prompt
        if hasattr(self, 'draft_context') and self.draft_context:
            search_text += "\n" + self.draft_context[:2000]
        uud_part = extract_relevant_uud_pasals(search_text, UUD_TEXT, max_chars=4000)
        if uud_part:
            if rag_context:
                return rag_context + "\n" + uud_part
            return uud_part
        return rag_context

    async def _generate_agent_response(self, agent: Any, prompt: str, rag_context: str = "") -> str:
        """Helper untuk memanggil generate_response dengan streaming callback jika tersedia."""
        prompt = self._style_prompt(agent, prompt)
        # Inject pasal UUD 1945 yang relevan (hemat ~10K token vs full text)
        rag_context = self._inject_uud_context(prompt, rag_context)

        # Mode manusia: jika pemohon dan callback tersedia, gunakan input manusia
        if (self.mode == "human"
                and hasattr(agent, "role")
                and agent.role == "pemohon"
                and self.human_input_callback):
            response = await self.human_input_callback(prompt, rag_context, agent.name)
            # Simpan ke memori agen
            if hasattr(agent, "memory"):
                agent.memory.append({"role": "assistant", "content": response})
                # Trim memori agar tidak terlalu panjang
                if len(agent.memory) > 20:
                    agent.memory = agent.memory[-20:]
            return response

        if self.on_chunk_callback:
            # Pastikan callback dibungkus untuk menyertakan info speaker
            async def chunk_handler(chunk):
                await self.on_chunk_callback(agent.name, chunk)

            response = await agent.generate_response(prompt, rag_context=rag_context, on_chunk=chunk_handler)
        else:
            response = await agent.generate_response(prompt, rag_context=rag_context)

        if not str(response or "").strip() and "Kembalikan HANYA format JSON" not in prompt:
            retry_prompt = (
                f"{prompt}\n\nJawaban sebelumnya kosong. Ulangi dengan sangat singkat, "
                "langsung berupa ucapan sidang, tanpa markdown."
            )
            response = await agent.generate_response(retry_prompt, rag_context=rag_context)

        return response

    def _log_interaction(self, round_name: str, speaker: str, content: str,
                         validation_result: Optional[Dict] = None):
        """Catat setiap interaksi ke transcript dan console."""
        # Bersihkan chain-of-thought dan JSON leak dari output LLM
        content = clean_transcript_content(content)
        if not str(content or "").strip():
            logger.info(f"[TRANSCRIPT] Lewati entri kosong: {round_name} / {speaker}")
            return
        # Tampilkan validasi jika ada peringatan (ROADMAP Fase 2 #3)
        display_content = content
        if validation_result and validation_result.get("verdict") != "LOLOS":
            verdict = validation_result.get("verdict", "")
            warnings = validation_result.get("suspicious_citations", [])
            warning_text = (
                f"\n\n⚠️  [VALIDATOR DALIL — {verdict}] "
                f"Potensi halusinasi terdeteksi:\n"
                + "\n".join(f"  • {w}" for w in warnings)
            )
            display_content = content + warning_text

        # Gunakan safe print untuk mencegah UnicodeEncodeError di Windows Console
        try:
            print(f"\n[{round_name}] {speaker}:\n{display_content}\n" + "-" * 60)
        except UnicodeEncodeError:
            safe_content = display_content.encode('ascii', 'replace').decode('ascii')
            print(f"\n[{round_name}] {speaker}:\n{safe_content}\n" + "-" * 60)

        entry: Dict[str, Any] = {
            "round": round_name,
            "speaker": speaker,
            "content": content
        }
        if validation_result and validation_result.get("verdict") != "LOLOS":
            entry["validation_warning"] = validation_result
        self.transcript.append(entry)

    async def _validated_log(self, round_name: str, speaker: str, content: str):
        """
        Wrapper: validasi kutipan terlebih dahulu, lalu catat ke transcript.
        Hanya aktif jika enable_validator=True (ROADMAP Fase 2 #3).
        """
        validation_result = None
        if self.validator and self.enable_validator:
            try:
                validation_result = await self.validator.validate(content)
                if validation_result.get("verdict") != "LOLOS":
                    logger.warning(
                        f"[VALIDATOR] {speaker} — {validation_result.get('verdict')}: "
                        f"{validation_result.get('suspicious_citations', [])}"
                    )
            except Exception as e:
                logger.warning(f"[VALIDATOR] Gagal memvalidasi: {e}")
        self._log_interaction(round_name, speaker, content, validation_result)

    def _get_rag_context(self, query: str, role: str = "umum", use_intelligence_banks: bool = True) -> str:
        """Query RAG dan kembalikan formatted context. Cek cache dulu jika batch prefetch aktif."""
        cache_key = f"{query}|{role}"
        if cache_key in self._rag_cache:
            return self._rag_cache[cache_key]
        if not self.retriever:
            return ""
        try:
            context = self.retriever.query_for_agent(
                query, agent_role=role, use_intelligence_banks=use_intelligence_banks
            )
            if context:
                logger.info(f"📎 RAG context ditemukan untuk {role} ({len(context)} chars)")
            return context
        except Exception as e:
            logger.warning(f"RAG query error: {e}")
            return ""

    def _query_intelligence_bank(self, bank_method: str, query: str, n_results: int = 3) -> str:
        """Generic intelligence bank query with caching."""
        cache_key = f"{bank_method}:{query}:{n_results}"
        if cache_key in self._rag_cache:
            return self._rag_cache[cache_key]
        if not self.retriever:
            return ""
        try:
            method = getattr(self.retriever, bank_method, None)
            if not method:
                return ""
            result = method(query, n_results=n_results)
            self._rag_cache[cache_key] = result
            return result
        except Exception as e:
            logger.warning(f"{bank_method} query error: {e}")
            return ""

    def _get_survive_context(self, query: str) -> str:
        """Query survive bank untuk mendapatkan jawaban Pemohon yang terbukti efektif."""
        return self._query_intelligence_bank("query_survive_bank", query)

    def _get_concern_context(self, query: str) -> str:
        """Query concern bank untuk mendapatkan pertanyaan/concern hakim yang berulang."""
        return self._query_intelligence_bank("query_concern_bank", query)

    def _get_attack_context(self, query: str) -> str:
        """Query attack bank untuk mendapatkan pola serangan Pemerintah/DPR."""
        return self._query_intelligence_bank("query_attack_bank", query)

    def _get_ratio_context(self, query: str) -> str:
        """Query ratio bank untuk mendapatkan ratio decidendi terstruktur."""
        return self._query_intelligence_bank("query_ratio_bank", query)

    async def _batch_fetch_rag(self, query_role_pairs: list, fetch_intel_banks: bool = True) -> None:
        """
        Prefetch RAG + intelligence banks untuk beberapa query sekaligus di awal ronde.
        Hasil di-cache di self._rag_cache agar _get_rag_context / _get_*_context
        berikutnya tidak perlu query ulang.
        """
        self._rag_cache = {}
        for query, role in query_role_pairs:
            cache_key = f"{query}|{role}"
            try:
                ctx = self.retriever.query_for_agent(
                    query, agent_role=role, use_intelligence_banks=fetch_intel_banks
                )
                self._rag_cache[cache_key] = ctx or ""
            except Exception as e:
                logger.warning(f"Batch RAG fetch error for {role}: {e}")
                self._rag_cache[cache_key] = ""
        logger.info(f"📦 Batch RAG: {len(query_role_pairs)} queries prefetched")

    async def _fetch_uu_context_from_api(self, draft: str) -> str:
        """Ekstrak nama UU/Pasal dari draft dan cari teks aslinya di pasal.id API."""
        queries = []
        # Cari pola 'Pasal X UU Y'
        pasal_matches = re.finditer(r'(Pasal\s+\d+[a-zA-Z]*(?:\s+ayat\s*\(\d+\))?.*?UU[A-Za-z0-9\s\.\-]+)', draft, re.IGNORECASE)
        for m in pasal_matches:
            queries.append(m.group(1).strip())
        
        # Fallback: cari pola 'UU No X Tahun Y'
        if not queries:
            uu_matches = re.finditer(r'(UU|Undang-Undang)\s+(?:No\.?\s*|Nomor\s*)?\d+\s+Tahun\s+\d{4}', draft, re.IGNORECASE)
            for m in uu_matches:
                queries.append(m.group(0).strip())
                
        # Deduplikasi dan batasi maks 2 query agar tidak spam
        queries = list(set(queries))[:2]
        
        if not queries:
            return ""
            
        logger.info(f"🔍 Mengambil teks pasal asli dari pasal.id untuk: {queries}")
        context_parts = []
        for q in queries:
            res = await pasal_api.search(q, limit=3)
            if res and not res.get("error") and res.get("results"):
                for item in res["results"]:
                    # Hanya ambil hasil yang relevansinya di atas threshold (0.4)
                    if item.get("score", 0) > 0.4:
                        meta = item.get("metadata", {})
                        work = item.get("work", {})
                        snippet = item.get("snippet", "")
                        context_parts.append(
                            f"[{work.get('title')} - {meta.get('node_type', 'Bagian').title()} {meta.get('node_number', '')}]\n\"{snippet}\""
                        )
                        
        if context_parts:
            return "\n\n=== REFERENSI PASAL (pasal.id API) ===\n" + "\n\n".join(context_parts)
        return ""

    # ================================================================
    # RONDE 1: PEMERIKSAAN PENDAHULUAN
    # ================================================================
    async def run_round_1_pendahuluan(self, draft_input: str):
        """
        Sidang Pendahuluan — Majelis Hakim menguji legal standing Pemohon.
        Panel 3 hakim secara bergiliran menanyakan aspek legal standing.
        """
        round_name = "Ronde 1: Pemeriksaan Pendahuluan"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Tarik data dari API Pasal (jika ditemukan referensi UU di draf)
        api_context = await self._fetch_uu_context_from_api(draft_input)
        self.draft_context = draft_input + api_context

        # Batch RAG: prefetch semua query sekaligus di awal ronde
        draft_snip = draft_input[:200]
        await self._batch_fetch_rag([
            (f"legal standing pemohon pengujian {draft_snip}", "hakim"),
            (f"legal standing dikabulkan {draft_snip}", "pemohon"),
        ])

        rag_ctx_hakim = self._get_rag_context(
            f"legal standing pemohon pengujian {draft_snip}",
            role="hakim"
        )
        if api_context:
            rag_ctx_hakim += api_context

        # Hakim Ketua membuka sidang & menanyakan legal standing
        hakim_q = await self._generate_agent_response(
            self.panel_hakim[0],
            f"Sidang dibuka. Berikut adalah ringkasan permohonan Pemohon:\n\n"
            f"\"{draft_input}\"\n\n"
            f"Sebagai Hakim Ketua, tanyakan secara kritis mengenai KEDUDUKAN HUKUM (Legal Standing) Pemohon. "
            f"Fokus pada: kualifikasi pemohon, hak konstitusional yang dirugikan, "
            f"dan hubungan kausal kerugian dengan berlakunya UU.",
            rag_context=rag_ctx_hakim
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, hakim_q)

        # RAG: cari preseden untuk pemohon
        rag_ctx_pemohon = self._get_rag_context(
            f"legal standing dikabulkan {draft_input[:200]}",
            role="pemohon"
        )
        if api_context:
            rag_ctx_pemohon += api_context

        # Pemohon menjawab legal standing
        pemohon_a = await self._generate_agent_response(
            self.pemohon,
            f"Majelis Hakim bertanya:\n\"{hakim_q}\"\n\n"
            f"Jelaskan legal standing Anda secara meyakinkan. "
            f"Buktikan 5 syarat Pasal 51 ayat (1) UU MK. "
            f"Sebutkan kerugian konstitusional yang spesifik dan aktual.",
            rag_context=rag_ctx_pemohon
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_a)

        # Hakim 2 menguji kelemahan legal standing
        hakim_q2 = await self._generate_agent_response(
            self.panel_hakim[1],
            f"Pemohon baru saja menjawab mengenai legal standing:\n\"{pemohon_a[:500]}\"\n\n"
            f"Berikan satu pertanyaan tajam yang menguji KELEMAHAN legal standing tersebut. "
            f"Apakah kerugian benar-benar spesifik? Apakah ada hubungan kausal yang jelas?",
            rag_context=rag_ctx_hakim
        )
        await self._validated_log(round_name, self.panel_hakim[1].name, hakim_q2)

        # Pemohon merespons pertanyaan lanjutan
        pemohon_a2 = await self._generate_agent_response(
            self.pemohon,
            f"Hakim bertanya lanjutan:\n\"{hakim_q2}\"\n\n"
            f"Jawab dengan bukti tambahan dan penguatan argumen legal standing Anda.",
            rag_context=rag_ctx_pemohon
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_a2)

    # ================================================================
    # RONDE 2: PERBAIKAN PERMOHONAN (opsional / advisory)
    # ================================================================
    async def run_round_2_perbaikan(self):
        """
        Sidang Perbaikan — Majelis memberikan nasihat perbaikan permohonan.
        Dalam MK asli, pemohon diberi 14 hari untuk memperbaiki.
        Di simulasi ini, hakim memberikan catatan perbaikan.
        """
        round_name = "Ronde 2: Perbaikan Permohonan"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Hakim Ketua memberikan nasihat perbaikan
        nasihat = await self._generate_agent_response(
            self.panel_hakim[0],
            f"Berdasarkan pemeriksaan pendahuluan sebelumnya, berikan NASIHAT PERBAIKAN "
            f"kepada Pemohon. Sebutkan secara spesifik bagian mana dari permohonan yang "
            f"perlu diperjelas atau dilengkapi (misal: batu uji, posita, petitum).\n"
            f"Berikan dalam format daftar bernomor yang ringkas."
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, nasihat)

        # Pemohon merespons perbaikan
        perbaikan = await self._generate_agent_response(
            self.pemohon,
            f"Majelis Hakim memberikan nasihat perbaikan:\n\"{nasihat}\"\n\n"
            f"Sampaikan perbaikan dan penajaman argumen Anda berdasarkan nasihat tersebut."
        )
        await self._validated_log(round_name, self.pemohon.name, perbaikan)

    # ================================================================
    # RONDE 2B: PEMERIKSAAN AHLI (ROADMAP Fase 3 #4) — BARU
    # ================================================================
    async def run_round_2b_ahli(self):
        """
        Sidang Pemeriksaan Ahli — Ronde tambahan setelah Perbaikan Permohonan.
        Ahli Pemohon dan Ahli Pemerintah berdebat di tataran teori konstitusi.
        Hakim menguji keduanya dengan pertanyaan akademis.
        (ROADMAP Fase 3 #4)
        """
        if not self.include_ahli or not self.ahli_pemohon or not self.ahli_pemerintah:
            logger.info("⏭️ Ronde 2B (Ahli) dilewati — agen ahli tidak aktif.")
            return

        round_name = "Ronde 2B: Pemeriksaan Ahli"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Batch RAG: prefetch untuk sesi ahli
        draft_snip = self.draft_context[:200]
        await self._batch_fetch_rag([
            (f"teori konstitusi pengujian norma {draft_snip}", "pemohon"),
            (f"open legal policy judicial deference {draft_snip}", "pemerintah"),
        ])

        # Hakim Ketua membuka sesi ahli
        hakim_pembuka = await self._generate_agent_response(
            self.panel_hakim[0],
            f"Sidang memasuki sesi Pemeriksaan Ahli. "
            f"Persilakan Ahli Pemohon untuk memberikan keterangan teori mengenai "
            f"konstitusionalitas norma yang diuji. "
            f"Konteks perkara: {self.draft_context[:300]}"
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, hakim_pembuka)

        rag_ctx_ahli = self._get_rag_context(
            f"teori konstitusi pengujian norma {draft_snip}",
            role="pemohon"
        )
        ahli_p_ket = await self._generate_agent_response(
            self.ahli_pemohon,
            f"Hakim Ketua mempersilakan Anda:\n\"{hakim_pembuka}\"\n\n"
            f"Berikan keterangan ahli Anda. Fokus pada:\n"
            f"1. Teori konstitusi yang mendukung posisi Pemohon\n"
            f"2. Doktrin hukum internasional yang relevan\n"
            f"3. Mengapa norma yang diuji tidak proporsional atau melanggar prinsip konstitusional",
            rag_context=rag_ctx_ahli
        )
        await self._validated_log(round_name, self.ahli_pemohon.name, ahli_p_ket)

        # Hakim menguji Ahli Pemohon
        hakim_uji_ahli_p = await self._generate_agent_response(
            self.panel_hakim[1],
            f"Ahli Pemohon berpendapat:\n\"{ahli_p_ket[:500]}\"\n\n"
            f"Uji konsistensi keterangan ahli ini. "
            f"Apakah teori yang digunakan tepat konteksnya? "
            f"Adakah counter-argument dari perspektif teori hukum lain?"
        )
        await self._validated_log(round_name, self.panel_hakim[1].name, hakim_uji_ahli_p)

        # Ahli Pemohon merespons
        ahli_p_respons = await self._generate_agent_response(
            self.ahli_pemohon,
            f"Hakim mengajukan pertanyaan:\n\"{hakim_uji_ahli_p}\"\n\n"
            f"Pertahankan keterangan Anda dengan argumen teori yang lebih rinci."
        )
        await self._validated_log(round_name, self.ahli_pemohon.name, ahli_p_respons)

        # Ahli Pemerintah memberikan keterangan tandingan
        rag_ctx_ahli_gov = self._get_rag_context(
            f"open legal policy judicial deference {self.draft_context[:200]}",
            role="pemerintah"
        )
        ahli_gov_ket = await self._generate_agent_response(
            self.ahli_pemerintah,
            f"Ahli Pemohon berpendapat:\n\"{ahli_p_ket[:500]}\"\n\n"
            f"Berikan keterangan ahli Anda yang MEMBANTAH keterangan di atas. Fokus pada:\n"
            f"1. Teori open legal policy dan judicial self-restraint\n"
            f"2. Mengapa norma yang diuji masih dalam batas konstitusional\n"
            f"3. Preseden komparatif dari negara lain",
            rag_context=rag_ctx_ahli_gov
        )
        await self._validated_log(round_name, self.ahli_pemerintah.name, ahli_gov_ket)

        # Hakim menguji Ahli Pemerintah
        hakim_uji_ahli_gov = await self._generate_agent_response(
            self.panel_hakim[2],
            f"Ahli Pemerintah berpendapat:\n\"{ahli_gov_ket[:500]}\"\n\n"
            f"Tanyakan: di titik mana deference kepada legislator menemui batasnya? "
            f"Bagaimana Mahkamah seharusnya memposisikan dirinya?"
        )
        await self._validated_log(round_name, self.panel_hakim[2].name, hakim_uji_ahli_gov)

        # Ahli Pemerintah merespons
        ahli_gov_respons = await self._generate_agent_response(
            self.ahli_pemerintah,
            f"Hakim bertanya:\n\"{hakim_uji_ahli_gov}\"\n\n"
            f"Jawab secara akademis dan tegas."
        )
        await self._validated_log(round_name, self.ahli_pemerintah.name, ahli_gov_respons)

    # ================================================================
    # RONDE 3: POKOK PERKARA + PIHAK TERKAIT + AMICUS CURIAE
    # Diperluas dengan ROADMAP Fase 2 #2
    # ================================================================
    async def run_round_3_pokok_perkara(self):
        """
        Sidang Pokok Perkara — Pemohon memaparkan argumen substantif,
        Pemerintah memberikan keterangan bantahan, Hakim menguji keduanya.
        DIPERLUAS: Pihak Terkait dan Amicus Curiae turut memberikan pandangan.
        """
        round_name = "Ronde 3: Pokok Perkara"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Batch RAG: prefetch semua query untuk ronde ini
        draft_snip = self.draft_context[:200]
        await self._batch_fetch_rag([
            (f"pengujian norma inkonstitusional {draft_snip}", "pemohon"),
            (f"open legal policy penolakan permohonan {draft_snip}", "pemerintah"),
            (f"comparative constitutional law {draft_snip}", "hakim"),
        ])

        rag_ctx_pemohon = self._get_rag_context(
            f"pengujian norma inkonstitusional {draft_snip}",
            role="pemohon"
        )
        rag_ctx_pemerintah = self._get_rag_context(
            f"open legal policy penolakan permohonan {draft_snip}",
            role="pemerintah"
        )

        # Hakim 2 mempersilakan masuk ke pokok perkara
        hakim_q = await self._generate_agent_response(
            self.panel_hakim[1],
            "Sidang memasuki pokok perkara. Persilakan Pemohon untuk memaparkan "
            "argumen substansi mengapa norma yang diuji bertentangan dengan UUD 1945. "
            "Tanyakan secara spesifik: pasal UUD mana yang dijadikan batu uji dan "
            "bagaimana pertentangannya."
        )
        await self._validated_log(round_name, self.panel_hakim[1].name, hakim_q)

        # Pemohon memaparkan argumen substansi
        pemohon_a = await self._generate_agent_response(
            self.pemohon,
            f"Hakim mempersilakan:\n\"{hakim_q}\"\n\n"
            f"Paparkan argumen substansi Anda. Jelaskan:\n"
            f"1. Norma mana yang inkonstitusional dan mengapa\n"
            f"2. Pasal-pasal UUD 1945 yang dijadikan batu uji\n"
            f"3. Kerugian konkret yang ditimbulkan norma tersebut",
            rag_context=rag_ctx_pemohon
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_a)

        # Pemerintah memberikan keterangan bantahan
        pemerintah_a = await self._generate_agent_response(
            self.pemerintah,
            f"Pemohon baru saja memaparkan argumen substansi:\n\"{pemohon_a[:600]}\"\n\n"
            f"Berikan KETERANGAN PEMERINTAH yang membantah argumen Pemohon. "
            f"Gunakan strategi: open legal policy, ratio legis UU, dan preseden penolakan.",
            rag_context=rag_ctx_pemerintah
        )
        await self._validated_log(round_name, self.pemerintah.name, pemerintah_a)

        # === PIHAK TERKAIT (ROADMAP Fase 2 #2) ===
        if self.include_pihak_terkait and self.pihak_terkait:
            print(f"\n{'─'*40}")
            print(f"  >>> KETERANGAN PIHAK TERKAIT")
            print(f"{'─'*40}")

            pihak_terkait_a = await self._generate_agent_response(
                self.pihak_terkait,
                f"Permohonan yang diuji:\n{self.draft_context[:400]}\n\n"
                f"Pemohon berargumen:\n\"{pemohon_a[:400]}\"\n\n"
                f"Pemerintah membantah:\n\"{pemerintah_a[:400]}\"\n\n"
                f"Berikan keterangan Pihak Terkait. Sampaikan perspektif unik "
                f"dari kelompok yang Anda wakili yang belum terungkap kedua pihak.",
                rag_context=rag_ctx_pemohon
            )
            await self._validated_log(round_name, self.pihak_terkait.name, pihak_terkait_a)

            # Hakim merespons Pihak Terkait
            hakim_pt = await self._generate_agent_response(
                self.panel_hakim[0],
                f"Pihak Terkait menyampaikan:\n\"{pihak_terkait_a[:400]}\"\n\n"
                f"Ajukan pertanyaan klarifikasi: seberapa langsung dampak UU ini terhadap "
                f"pihak yang Anda wakili? Apa bedanya dengan posisi Pemohon?"
            )
            await self._validated_log(round_name, self.panel_hakim[0].name, hakim_pt)

        # === AMICUS CURIAE (ROADMAP Fase 2 #2) ===
        if self.include_amicus and self.amicus_curiae:
            print(f"\n{'─'*40}")
            print(f"  >>> PANDANGAN AMICUS CURIAE")
            print(f"{'─'*40}")

            amicus_a = await self._generate_agent_response(
                self.amicus_curiae,
                f"Perkara yang sedang diuji:\n{self.draft_context[:400]}\n\n"
                f"Argumen Pemohon:\n\"{pemohon_a[:350]}\"\n\n"
                f"Argumen Pemerintah:\n\"{pemerintah_a[:350]}\"\n\n"
                f"Sebagai Amicus Curiae, berikan pandangan akademis netral. Fokus pada:\n"
                f"1. Pendekatan komparatif dari mahkamah konstitusi negara lain\n"
                f"2. Teori hukum yang paling relevan untuk kasus ini\n"
                f"3. Rekomendasi tafsir konstitusional yang seimbang",
                rag_context=self._get_rag_context(
                    f"comparative constitutional law {self.draft_context[:200]}", role="hakim"
                )
            )
            await self._validated_log(round_name, self.amicus_curiae.name, amicus_a)

        # Hakim 3 mengajukan pertanyaan pamungkas kepada semua pihak
        hakim_q2 = await self._generate_agent_response(
            self.panel_hakim[2],
            f"Pemohon berargumen:\n\"{pemohon_a[:400]}\"\n\n"
            f"Pemerintah membantah:\n\"{pemerintah_a[:400]}\"\n\n"
            f"Berikan pertanyaan kritis terhadap KEDUA belah pihak. "
            f"Identifikasi kontradiksi atau kelemahan argumen masing-masing."
        )
        await self._validated_log(round_name, self.panel_hakim[2].name, hakim_q2)

        # Pemohon merespons
        pemohon_tanggapan = await self._generate_agent_response(
            self.pemohon,
            f"Hakim bertanya:\n\"{hakim_q2}\"\n\nTanggapi secara ringkas dan tajam."
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_tanggapan)

        # Pemerintah merespons
        pemerintah_tanggapan = await self._generate_agent_response(
            self.pemerintah,
            f"Hakim bertanya:\n\"{hakim_q2}\"\n\nTanggapi secara ringkas dan tajam."
        )
        await self._validated_log(round_name, self.pemerintah.name, pemerintah_tanggapan)

    # ================================================================
    # RONDE 4: KESIMPULAN & RPH + DISSENTING OPINION
    # Diperluas dengan ROADMAP Fase 2 #1
    # ================================================================
    async def _generate_dissenting_opinion(self, hakim: Any, majority_amar: str, hakim_score: Dict) -> str:
        """
        Generate Dissenting Opinion / Concurring Opinion dari hakim minoritas.
        (ROADMAP Fase 2 #1)
        """
        minority_amar = hakim_score.get("amar", "ditolak")
        is_concurring = (minority_amar == majority_amar)
        opinion_type = "CONCURRING OPINION (Pendapat Setuju dengan Alasan Berbeda)" \
            if is_concurring else "DISSENTING OPINION (Pendapat Berbeda)"

        prompt = (
            f"Anda telah memberikan penilaian dengan amar: {minority_amar}.\n"
            f"Amar mayoritas panel adalah: {majority_amar}.\n"
            f"Catatan Anda sebelumnya: {hakim_score.get('catatan', '-')}\n\n"
            f"Tulis {opinion_type} secara formal. Sertakan:\n"
            f"1. Pokok perbedaan/persetujuan pandangan Anda\n"
            f"2. Dasar hukum dan pertimbangan konstitusional yang Anda pegang\n"
            f"3. Implikasi dari pandangan ini bagi perkembangan hukum konstitusi\n\n"
            f"Format: Dokumen opinion formal, tidak lebih dari 3 paragraf padat."
        )
        return await hakim.generate_response(prompt)

    async def run_round_4_kesimpulan(self) -> Dict[str, Any]:
        """
        Kesimpulan para pihak & RPH.
        Setiap hakim memberikan scoring INDEPENDEN, lalu diagregasi.
        Jika ada perbedaan pendapat, generate Dissenting/Concurring Opinion.
        (ROADMAP Fase 2 #1)
        """
        round_name = "Ronde 4: Kesimpulan & RPH"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        # Kesimpulan Pemohon
        pemohon_kesimpulan = await self._generate_agent_response(
            self.pemohon,
            "Ini adalah tahap KESIMPULAN AKHIR. "
            "Sampaikan petitum final Anda secara ringkas dan tegas. "
            "Tegaskan mengapa permohonan harus dikabulkan."
        )
        await self._validated_log(round_name, self.pemohon.name, pemohon_kesimpulan)

        # Kesimpulan Pemerintah
        pemerintah_kesimpulan = await self._generate_agent_response(
            self.pemerintah,
            "Sampaikan kesimpulan akhir Pemerintah. "
            "Tegaskan bahwa permohonan harus DITOLAK atau TIDAK DAPAT DITERIMA."
        )
        await self._validated_log(round_name, self.pemerintah.name, pemerintah_kesimpulan)

        # ===== RPH: Setiap Hakim Scoring Independen =====
        print(f"\n{'─'*60}")
        print(f"  >>> RAPAT PERMUSYAWARATAN HAKIM (RPH) -- TERTUTUP")
        print(f"{'─'*60}")

        scoring_prompt = """\
Sebagai Hakim Konstitusi, berikan penilaian INDEPENDEN terhadap permohonan ini.
Evaluasi berdasarkan seluruh jalannya persidangan yang Anda ikuti.

PENTING:
- Anda harus memberikan skor numerik sesuai rentang yang ditentukan.
- DILARANG memberikan skor di luar rentang atau dalam format non-angka.
- DILARANG KERAS menulis proses berpikir, analisis, deliberasi, atau teks apapun di luar JSON.
- Output Anda HARUS dimulai dengan karakter { dan diakhiri dengan karakter }.
- JANGAN tulis kalimat pembuka, penjelasan, atau komentar apapun.

Kembalikan HANYA format JSON berikut (tanpa teks tambahan apapun di luar JSON, tanpa markdown code block, tanpa penjelasan):
{
    "legal_standing": <angka 0-25>,
    "kerugian_konstitusional": <angka 0-20>,
    "substansi_argumen": <angka 0-30>,
    "konsistensi_putusan": <angka 0-15>,
    "kelengkapan_formil": <angka 0-10>,
    "amar": "<dikabulkan|ditolak|tidak_dapat_diterima>",
    "catatan": "<pertimbangan hukum singkat max 2 kalimat>"
}

CONTOH OUTPUT YANG BENAR:
{"legal_standing": 20, "kerugian_konstitusional": 15, "substansi_argumen": 25, "konsistensi_putusan": 12, "kelengkapan_formil": 8, "amar": "ditolak", "catatan": "Legal standing cukup kuat namun substansi argumen kurang mendalam."}
"""
        all_scores = []

        for hakim in self.panel_hakim:
            raw_score = await self._generate_agent_response(hakim, scoring_prompt)
            score_data = self._parse_json_score(raw_score, hakim.name)

            # Retry jika parsing gagal — minta hakim output JSON saja
            if "error" in score_data:
                logger.warning(f"Retry RPH untuk {hakim.name}: {score_data['error']}")
                retry_prompt = (
                    "OUTPUT ANDA SEBELUMNYA TIDAK VALID. "
                    "Jangan tulis analisis atau proses berpikir. "
                    "Langsung tulis OBJEK JSON SAJA dimulai dari karakter { dan diakhiri }. "
                    "Format: {\"legal_standing\": <0-25>, \"kerugian_konstitusional\": <0-20>, "
                    "\"substansi_argumen\": <0-30>, \"konsistensi_putusan\": <0-15>, "
                    "\"kelengkapan_formil\": <0-10>, \"amar\": \"<dikabulkan|ditolak|tidak_dapat_diterima>\", "
                    "\"catatan\": \"<singkat>\"}"
                )
                raw_retry = await self._generate_agent_response(hakim, retry_prompt)
                score_data = self._parse_json_score(raw_retry, hakim.name)

            all_scores.append(score_data)

        # Agregasi scoring
        aggregated = self._aggregate_scores(all_scores)

        # ===== DISSENTING / CONCURRING OPINION (ROADMAP Fase 2 #1) =====
        majority_amar = aggregated.get("amar", "ditolak")
        voting_detail = aggregated.get("voting_detail", {})

        # Jika tidak unanimous (ada perbedaan suara)
        if len(voting_detail) > 1:
            print(f"\n{'─'*60}")
            print(f"  >>> DISSENTING / CONCURRING OPINIONS")
            print(f"{'─'*60}")

            for hakim, score_data in zip(self.panel_hakim, all_scores):
                hakim_amar = score_data.get("amar", majority_amar)
                # Generate opinion untuk setiap hakim yang berbeda ATAU yang setuju tapi ingin concur
                if hakim_amar != majority_amar:
                    opinion = await self._generate_dissenting_opinion(hakim, majority_amar, score_data)
                    opinion_type = "Dissenting Opinion"
                    self._log_interaction(
                        round_name,
                        f"{opinion_type} — {hakim.name}",
                        opinion
                    )
                    self.dissenting_opinions.append({
                        "hakim": hakim.name,
                        "type": opinion_type,
                        "amar_hakim": hakim_amar,
                        "amar_mayoritas": majority_amar,
                        "opinion": opinion
                    })
        else:
            print(f"\n  ✅ Voting bulat — tidak ada Dissenting Opinion.")

        return {
            "simulation_id": self.simulation_id,
            "transcript": self.transcript,
            "individual_scores": all_scores,
            "scores": aggregated,
            "dissenting_opinions": self.dissenting_opinions
        }


    # ================================================================
    # RONDE 5: UMPAN BALIK HAKIM (ROADMAP Fase 4 #8) — BARU
    # ================================================================
    async def run_round_5_feedback(self) -> Dict[str, Any]:
        """
        Generate structured feedback for Pemohon after RPH.
        Setiap hakim memberikan umpan balik terstruktur.
        """
        round_name = "Umpan Balik Hakim"
        print(f"\n{'='*60}")
        print(f"  >>> {round_name.upper()}")
        print(f"{'='*60}")

        feedback_prompt = """\
Berdasarkan seluruh persidangan, berikan UMPAN BALIK TERSTRUKTUR untuk membantu \
Pemohon memperbaiki kualitas permohonan ke depan.

PENTING:
- DILARANG menulis proses berpikir, analisis, atau teks apapun di luar JSON.
- Output HARUS dimulai dengan karakter {{ dan diakhiri dengan karakter }}.
- JANGAN tulis kalimat pembuka atau penjelasan.

Kembalikan HANYA format JSON berikut (tanpa teks lain):
{
    "skor_potensial_perbaikan": <angka 0-30 — estimasi peningkatan skor jika saran diikuti>,
    "kelemahan_utama": [
        "<kelemahan spesifik 1>",
        "<kelemahan spesifik 2>"
    ],
    "rekomendasi": [
        {
            "aspek": "<Legal Standing|Substansi Argumen|Batu Uji|Kelengkapan Formil>",
            "masalah": "<deskripsi masalah spesifik>",
            "saran_konkret": "<tindakan konkret yang harus diambil>"
        }
    ],
    "rekomendasi_petitum": "<saran revisi petitum yang lebih tepat>",
    "prioritas_perbaikan": "<aspek yang paling kritis untuk diperbaiki>"
}
"""
        all_feedback = []
        for hakim in self.panel_hakim:
            raw = await self._generate_agent_response(hakim, feedback_prompt)
            parsed = None
            try:
                start = raw.find('{')
                end = raw.rfind('}') + 1
                if start != -1 and end > 0:
                    parsed = json.loads(raw[start:end])
            except Exception as e:
                logger.error(f"Gagal parse feedback dari {hakim.name}: {e}")

            # Retry jika parsing gagal
            if not parsed:
                logger.warning(f"Retry feedback untuk {hakim.name}")
                retry_prompt = (
                    "OUTPUT ANDA SEBELUMNYA TIDAK VALID. "
                    "Jangan tulis analisis atau proses berpikir. "
                    "Langsung tulis OBJEK JSON SAJA dimulai dari karakter { dan diakhiri }. "
                    'Format: {"skor_potensial_perbaikan": <0-30>, "kelemahan_utama": ["..."], '
                    '"rekomendasi": [{"aspek": "...", "masalah": "...", "saran_konkret": "..."}], '
                    '"rekomendasi_petitum": "...", "prioritas_perbaikan": "..."}'
                )
                raw_retry = await self._generate_agent_response(hakim, retry_prompt)
                try:
                    start = raw_retry.find('{')
                    end = raw_retry.rfind('}') + 1
                    if start != -1 and end > 0:
                        parsed = json.loads(raw_retry[start:end])
                except Exception as e:
                    logger.error(f"Gagal parse feedback RETRY dari {hakim.name}: {e}")

            if parsed:
                all_feedback.append(parsed)

        aggregated = self._aggregate_feedback(all_feedback)
        return aggregated

    def _aggregate_feedback(self, feedbacks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Agregasi feedback dari semua hakim."""
        if not feedbacks:
            return {"error": "Tidak ada feedback valid"}

        avg_potential = round(
            sum(f.get("skor_potensial_perbaikan", 0) for f in feedbacks) / len(feedbacks), 1
        )
        all_kelemahan = []
        for f in feedbacks:
            all_kelemahan.extend(f.get("kelemahan_utama", []))
        all_rekomendasi = []
        for f in feedbacks:
            all_rekomendasi.extend(f.get("rekomendasi", []))

        prioritas_list = [f.get("prioritas_perbaikan", "") for f in feedbacks if f.get("prioritas_perbaikan")]
        from collections import Counter
        prioritas = Counter(prioritas_list).most_common(1)[0][0] if prioritas_list else "Substansi Argumen"
        petitum_recs = [f.get("rekomendasi_petitum", "") for f in feedbacks if f.get("rekomendasi_petitum")]

        return {
            "skor_potensial_perbaikan": avg_potential,
            "kelemahan_utama": list(dict.fromkeys(all_kelemahan))[:5],
            "rekomendasi": all_rekomendasi[:6],
            "rekomendasi_petitum": petitum_recs[0] if petitum_recs else "",
            "prioritas_perbaikan": prioritas
        }

    def _parse_json_score(self, raw: str, hakim_name: str) -> Dict[str, Any]:
        """Coba ekstrak JSON dari output hakim dengan multiple fallback strategies."""
        if not raw or not raw.strip():
            logger.error(f"Output dari {hakim_name} kosong.")
            return {"error": "Output kosong", "raw": ""}

        cleaned = raw.strip()

        # Strategy 1: Hapus markdown code block ```json ... ```
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if code_block_match:
            cleaned = code_block_match.group(1)

        # Strategy 2: Cari JSON object paling luar (dari { pertama sampai } terakhir yang seimbang)
        start_idx = cleaned.find('{')
        if start_idx == -1:
            logger.error(f"Tidak ditemukan {{ di output {hakim_name}: {cleaned[:200]}")
            return {"error": "Tidak ada JSON object", "raw": cleaned[:300]}

        # Cari } yang seimbang
        brace_count = 0
        end_idx = start_idx
        for i, ch in enumerate(cleaned[start_idx:]):
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = start_idx + i + 1
                    break

        json_str = cleaned[start_idx:end_idx]

        try:
            parsed = json.loads(json_str)
            # Validasi bahwa parsed memiliki setidaknya salah satu key scoring
            scoring_keys = set(self.SCORE_DIMENSIONS) | {"amar"}
            if not scoring_keys.intersection(parsed.keys()):
                logger.warning(f"JSON dari {hakim_name} tidak mengandung key scoring: {json_str[:200]}")
                return {"error": "JSON tidak mengandung key scoring", "raw": cleaned[:300]}
            return self._normalize_score_data(parsed, hakim_name)
        except json.JSONDecodeError as e:
            logger.error(f"Gagal parsing JSON dari {hakim_name}: {e} | JSON string: {json_str[:300]}")

        # Strategy 3: Fallback regex extraction per key-value
        fallback = {}
        for key in ["legal_standing", "kerugian_konstitusional", "substansi_argumen",
                    "konsistensi_putusan", "kelengkapan_formil"]:
            pattern = rf'"{key}"\s*:\s*([0-9]+(?:\.[0-9]+)?)'
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                fallback[key] = float(match.group(1))

        amar_match = re.search(r'"amar"\s*:\s*"([^"]+)"', cleaned, re.IGNORECASE)
        if amar_match:
            fallback["amar"] = amar_match.group(1).strip().lower()

        catatan_match = re.search(r'"catatan"\s*:\s*"([^"]*)"', cleaned, re.IGNORECASE)
        if catatan_match:
            fallback["catatan"] = catatan_match.group(1).strip()

        if fallback:
            logger.warning(f"Menggunakan fallback regex parsing untuk {hakim_name}")
            return self._normalize_score_data(fallback, hakim_name)

        return {"error": "Format JSON gagal diparsing", "raw": cleaned[:300]}

    def _normalize_score_data(self, score: Dict[str, Any], hakim_name: str = "") -> Dict[str, Any]:
        """Pastikan skor hakim punya angka valid, total, amar, dan catatan."""
        normalized: Dict[str, Any] = {}
        for dim in self.SCORE_DIMENSIONS:
            raw_val = score.get(dim, 0)
            try:
                value = float(raw_val)
            except (TypeError, ValueError):
                logger.warning(f"Skor {dim} dari {hakim_name} tidak numerik: {raw_val!r}")
                value = 0
            value = max(0, min(value, self.SCORE_MAX[dim]))
            normalized[dim] = round(value, 1)

        normalized["total"] = round(sum(float(normalized[d]) for d in self.SCORE_DIMENSIONS), 1)
        amar = str(score.get("amar") or "ditolak").strip().lower()
        if amar not in {"dikabulkan", "ditolak", "tidak_dapat_diterima"}:
            amar = "ditolak"
        normalized["amar"] = amar
        normalized["catatan"] = str(score.get("catatan") or "-").strip()
        return normalized

    def _aggregate_scores(self, scores: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Agregasi skor dari semua hakim (rata-rata + voting amar)."""
        dimensions = self.SCORE_DIMENSIONS

        # Rata-rata per dimensi (hanya dari yang valid)
        valid_scores = [self._normalize_score_data(s) for s in scores if "error" not in s]
        
        avg = {}
        if valid_scores:
            for dim in dimensions:
                vals = []
                for s in valid_scores:
                    val = s.get(dim)
                    if val is not None:
                        try:
                            vals.append(float(val))
                        except (ValueError, TypeError):
                            pass
                avg[dim] = round(sum(vals) / len(vals), 1) if vals else 0
            avg["total"] = round(sum(avg[d] for d in dimensions), 1)
            avg["breakdown"] = {dim: avg[dim] for dim in dimensions}
        else:
            for dim in dimensions:
                avg[dim] = 0
            avg["total"] = 0
            avg["breakdown"] = {dim: 0 for dim in dimensions}
            avg["error"] = "Seluruh hakim gagal memberikan format scoring yang valid."

        # Voting amar (dari SEMUA hakim, gunakan 'invalid' jika gagal)
        amar_votes = []
        for s in scores:
            if "error" in s:
                amar_votes.append("invalid")
            else:
                amar_votes.append(s.get("amar", "ditolak"))

        from collections import Counter
        amar_count = Counter(amar_votes)
        
        # Penentuan amar mayoritas (abaikan 'invalid' jika masih ada yang valid)
        valid_votes = [v for v in amar_votes if v != "invalid"]
        if valid_votes:
            vote_counts = Counter(valid_votes)
            top_vote, top_count = vote_counts.most_common(1)[0]
            # Mayoritas mutlak (>50%) diperlukan; jika tidak ada, default "ditolak"
            if top_count > len(valid_votes) / 2:
                avg["amar"] = top_vote
            else:
                avg["amar"] = "ditolak"
        else:
            avg["amar"] = "tidak_diketahui"

        avg["voting_detail"] = dict(amar_count)

        # Kumpulkan catatan hakim (termasuk info jika gagal)
        catatan_list = []
        for i, s in enumerate(scores):
            if "error" in s:
                catatan_list.append(f"{i+1}. Gagal parsing output hakim: {s['error']}")
            elif s.get("catatan"):
                catatan_list.append(f"{i+1}. {s['catatan']}")
            else:
                catatan_list.append(f"{i+1}. -")
        
        avg["catatan_hakim"] = catatan_list

        return avg

    def _iter_agents(self) -> List[Any]:
        """Daftar semua agen yang bisa memiliki catatan usage API."""
        agents = [self.pemohon, self.pemerintah, *self.panel_hakim]
        for agent in [
            self.pihak_terkait,
            self.amicus_curiae,
            self.ahli_pemohon,
            self.ahli_pemerintah,
            self.validator,
        ]:
            if agent is not None:
                agents.append(agent)
        return agents

    def _collect_api_usage(self) -> Dict[str, Any]:
        """Agregasi token dan biaya API dari semua agen."""
        records = []
        for agent in self._iter_agents():
            records.extend(getattr(agent, "usage_records", []) or [])

        if not records:
            return {
                "provider": self.llm_config.get("provider", "local"),
                "model": self.llm_config.get("model_name"),
                "calls": 0,
                "prompt_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "records": [],
            }

        costs = [r.get("cost") for r in records if isinstance(r.get("cost"), (int, float))]
        return {
            "provider": self.llm_config.get("provider", records[-1].get("provider", "local")),
            "model": self.llm_config.get("model_name", records[-1].get("model")),
            "calls": len(records),
            "prompt_tokens": sum(int(r.get("prompt_tokens") or 0) for r in records),
            "prompt_cache_hit_tokens": sum(int(r.get("prompt_cache_hit_tokens") or 0) for r in records),
            "prompt_cache_miss_tokens": sum(int(r.get("prompt_cache_miss_tokens") or 0) for r in records),
            "completion_tokens": sum(int(r.get("completion_tokens") or 0) for r in records),
            "total_tokens": sum(int(r.get("total_tokens") or 0) for r in records),
            "cost_usd": round(sum(costs), 6) if costs else 0.0,
            "records": records,
        }

    async def _ask_party_pair(
        self,
        round_name: str,
        hakim: Any,
        party: Any,
        judge_prompt: str,
        party_prompt: str,
        rag_role: str = "umum",
    ):
        rag_context = self._get_rag_context(
            f"{round_name} {judge_prompt} {self.draft_context[:200]}",
            role=rag_role,
        )
        question = await self._generate_agent_response(hakim, judge_prompt, rag_context=rag_context)
        await self._validated_log(round_name, hakim.name, question)

        answer = await self._generate_agent_response(
            party,
            f"Hakim bertanya:\n\"{question}\"\n\n{party_prompt}",
            rag_context=rag_context,
        )
        await self._validated_log(round_name, party.name, answer)
        return question, answer

    async def _run_dynamic_pendahuluan(self, draft_input: str, target_turn_count: int) -> Dict[str, Any]:
        await self._prepare_hearing_context(draft_input)
        round_name = "Pemeriksaan Pendahuluan"
        issues = [
            ("kualifikasi Pemohon dan kewenangan Mahkamah", "Jelaskan kualifikasi Pemohon dan dasar kewenangan Mahkamah."),
            ("hak konstitusional yang dirugikan", "Jelaskan hak konstitusional yang dirugikan secara konkret."),
            ("hubungan kausal norma dengan kerugian", "Pertegas hubungan sebab akibat norma a quo dengan kerugian Pemohon."),
            ("batu uji dan konstruksi posita", "Tunjukkan batu uji UUD dan konstruksi pertentangan normanya."),
            ("petitum dan kemungkinan perbaikan", "Ringkaskan petitum dan bagian yang siap diperbaiki."),
        ]

        opener = await self._generate_agent_response(
            self.panel_hakim[0],
            f"Buka sidang Pemeriksaan Pendahuluan. Ringkasan permohonan:\n{draft_input[:900]}\n\n"
            "Persilakan Pemohon menyampaikan pokok permohonan, legal standing, dan batu uji secara ringkas."
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, opener)

        opening_answer = await self._generate_agent_response(
            self.pemohon,
            f"Hakim Ketua membuka sidang:\n\"{opener}\"\n\n"
            "Sampaikan pokok permohonan, legal standing, dan batu uji secara singkat seperti sidang pendahuluan."
        )
        await self._validated_log(round_name, self.pemohon.name, opening_answer)

        issue_index = 0
        while self._turns_left_for_pair(target_turn_count):
            issue, answer_instruction = issues[issue_index % len(issues)]
            hakim = self.panel_hakim[(issue_index + 1) % len(self.panel_hakim)]
            await self._ask_party_pair(
                round_name,
                hakim,
                self.pemohon,
                f"Ajukan satu pertanyaan lanjutan tentang {issue}. "
                "Pertanyaan harus singkat dan meniru interupsi/pendalaman sidang MK.",
                answer_instruction,
                rag_role="hakim",
            )
            issue_index += 1

        reason = "isu pendahuluan sudah cukup diperiksa"
        if len(self.transcript) >= target_turn_count - 1:
            reason = "batas target giliran sidang tercapai"
        await self._chair_closes_hearing(round_name, reason)
        return self._hearing_result(reason)

    async def _run_dynamic_perbaikan(self, draft_input: str, target_turn_count: int) -> Dict[str, Any]:
        await self._prepare_hearing_context(draft_input)
        round_name = "Perbaikan Permohonan"
        issues = [
            ("bagian yang diperbaiki sejak sidang pendahuluan", "Jelaskan bagian permohonan yang sudah diperbaiki."),
            ("batu uji", "Tunjukkan letak batu uji dan perubahan redaksionalnya."),
            ("posita dan petitum", "Jelaskan penajaman posita dan petitum tanpa membaca seluruh naskah."),
            ("kelengkapan bukti", "Sebutkan bukti atau lampiran yang memperkuat perbaikan."),
        ]

        opener = await self._generate_agent_response(
            self.panel_hakim[0],
            "Buka sidang Perbaikan Permohonan. Minta Pemohon menjelaskan bagian yang diperbaiki, "
            "bukan membaca ulang seluruh permohonan."
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, opener)

        answer = await self._generate_agent_response(
            self.pemohon,
            f"Hakim Ketua meminta penjelasan perbaikan:\n\"{opener}\"\n\n"
            "Jelaskan perbaikan permohonan secara berurutan dan singkat."
        )
        await self._validated_log(round_name, self.pemohon.name, answer)

        issue_index = 0
        while self._turns_left_for_pair(target_turn_count):
            issue, answer_instruction = issues[issue_index % len(issues)]
            hakim = self.panel_hakim[issue_index % len(self.panel_hakim)]
            await self._ask_party_pair(
                round_name,
                hakim,
                self.pemohon,
                f"Klarifikasi satu hal tentang {issue}. "
                "Jika Pemohon menyebut halaman atau bagian, cek konsistensinya seperti risalah asli.",
                answer_instruction,
                rag_role="hakim",
            )
            issue_index += 1

        reason = "perbaikan permohonan sudah cukup diklarifikasi"
        if len(self.transcript) >= target_turn_count - 1:
            reason = "batas target giliran sidang tercapai"
        await self._chair_closes_hearing(round_name, reason)
        return self._hearing_result(reason)

    async def _run_dynamic_pemerintah_dpr(self, draft_input: str, target_turn_count: int) -> Dict[str, Any]:
        await self._prepare_hearing_context(draft_input)
        round_name = "Mendengarkan Keterangan Pemerintah/DPR"
        issues = [
            ("ratio legis norma a quo", self.pemerintah, "Jelaskan tujuan pembentukan norma dan konteks kebijakan."),
            ("open legal policy", self.pemerintah, "Tegaskan batas kebijakan pembentuk undang-undang."),
            ("dampak norma menurut Pemohon", self.pemohon, "Tanggapi keterangan Pemerintah secara singkat."),
            ("klarifikasi konstitusional", self.pemerintah, "Jawab klarifikasi Mahkamah berdasarkan UUD dan preseden."),
        ]

        opener = await self._generate_agent_response(
            self.panel_hakim[0],
            "Buka sidang mendengarkan keterangan Pemerintah/DPR. Persilakan Pemerintah menyampaikan pokok keterangan."
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, opener)

        gov_answer = await self._generate_agent_response(
            self.pemerintah,
            f"Hakim Ketua mempersilakan:\n\"{opener}\"\n\n"
            "Sampaikan keterangan Pemerintah/DPR yang menanggapi permohonan Pemohon."
        )
        await self._validated_log(round_name, self.pemerintah.name, gov_answer)

        issue_index = 0
        while self._turns_left_for_pair(target_turn_count):
            issue, party, answer_instruction = issues[issue_index % len(issues)]
            hakim = self.panel_hakim[(issue_index + 1) % len(self.panel_hakim)]
            await self._ask_party_pair(
                round_name,
                hakim,
                party,
                f"Ajukan pertanyaan pendalaman tentang {issue}. Fokus pada posisi {party.name}.",
                answer_instruction,
                rag_role="pemerintah" if party is self.pemerintah else "pemohon",
            )
            issue_index += 1

        reason = "keterangan Pemerintah/DPR sudah cukup didengar"
        if len(self.transcript) >= target_turn_count - 1:
            reason = "batas target giliran sidang tercapai"
        await self._chair_closes_hearing(round_name, reason)
        return self._hearing_result(reason)

    async def _run_dynamic_ahli(self, draft_input: str, target_turn_count: int) -> Dict[str, Any]:
        await self._prepare_hearing_context(draft_input)
        round_name = "Pemeriksaan Ahli"
        if not self.ahli_pemohon or not self.ahli_pemerintah:
            return await self._run_dynamic_pendahuluan(draft_input, target_turn_count)

        issues = [
            ("keterangan Ahli Pemohon", self.ahli_pemohon, "Berikan keterangan ahli yang mendukung permohonan."),
            ("uji metodologi Ahli Pemohon", self.ahli_pemohon, "Jawab keberatan metodologis hakim."),
            ("keterangan Ahli Pemerintah", self.ahli_pemerintah, "Berikan keterangan ahli yang membantah Pemohon."),
            ("batas deference legislator", self.ahli_pemerintah, "Jelaskan batas open legal policy secara akademis."),
            ("tanggapan Pemohon", self.pemohon, "Tanggapi keterangan ahli secara singkat."),
        ]

        opener = await self._generate_agent_response(
            self.panel_hakim[0],
            "Buka sidang pemeriksaan ahli. Persilakan Ahli Pemohon memberi keterangan pokok."
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, opener)

        first_answer = await self._generate_agent_response(
            self.ahli_pemohon,
            f"Hakim Ketua mempersilakan:\n\"{opener}\"\n\n"
            "Sampaikan keterangan ahli pokok secara lisan dan ringkas."
        )
        await self._validated_log(round_name, self.ahli_pemohon.name, first_answer)

        issue_index = 1
        while self._turns_left_for_pair(target_turn_count):
            issue, party, answer_instruction = issues[issue_index % len(issues)]
            hakim = self.panel_hakim[(issue_index + 1) % len(self.panel_hakim)]
            await self._ask_party_pair(
                round_name,
                hakim,
                party,
                f"Ajukan pertanyaan pemeriksaan ahli tentang {issue}.",
                answer_instruction,
                rag_role="pemohon" if party is not self.ahli_pemerintah else "pemerintah",
            )
            issue_index += 1

        reason = "pemeriksaan ahli sudah cukup"
        if len(self.transcript) >= target_turn_count - 1:
            reason = "batas target giliran sidang tercapai"
        await self._chair_closes_hearing(round_name, reason)
        return self._hearing_result(reason)

    async def _run_dynamic_pembuktian(self, draft_input: str, target_turn_count: int) -> Dict[str, Any]:
        await self._prepare_hearing_context(draft_input)
        round_name = "Pembuktian"
        issues = [
            ("daftar alat bukti Pemohon", self.pemohon, "Sebutkan bukti utama dan relevansinya."),
            ("keberatan Pemerintah terhadap bukti", self.pemerintah, "Tanggapi kekuatan pembuktian Pemohon."),
            ("klarifikasi bukti surat", self.pemohon, "Jelaskan letak bukti yang ditanyakan hakim."),
            ("hubungan bukti dengan kerugian", self.pemohon, "Hubungkan bukti dengan kerugian konstitusional."),
        ]

        opener = await self._generate_agent_response(
            self.panel_hakim[0],
            "Buka sidang pembuktian. Persilakan Pemohon menyampaikan alat bukti secara ringkas."
        )
        await self._validated_log(round_name, self.panel_hakim[0].name, opener)

        first_answer = await self._generate_agent_response(
            self.pemohon,
            f"Hakim Ketua mempersilakan:\n\"{opener}\"\n\nSampaikan bukti utama dan relevansinya."
        )
        await self._validated_log(round_name, self.pemohon.name, first_answer)

        issue_index = 0
        while self._turns_left_for_pair(target_turn_count):
            issue, party, answer_instruction = issues[issue_index % len(issues)]
            hakim = self.panel_hakim[(issue_index + 1) % len(self.panel_hakim)]
            await self._ask_party_pair(
                round_name,
                hakim,
                party,
                f"Ajukan pertanyaan pembuktian tentang {issue}.",
                answer_instruction,
                rag_role="pemohon" if party is self.pemohon else "pemerintah",
            )
            issue_index += 1

        reason = "pembuktian sudah cukup"
        if len(self.transcript) >= target_turn_count - 1:
            reason = "batas target giliran sidang tercapai"
        await self._chair_closes_hearing(round_name, reason)
        return self._hearing_result(reason)

    async def _run_dynamic_putusan(self, draft_input: str, target_turn_count: int) -> Dict[str, Any]:
        await self._prepare_hearing_context(draft_input)
        round_name = "Pengucapan Putusan"
        prompts = [
            (self.panel_hakim[0], "Buka sidang pengucapan putusan dan sebutkan perkara secara singkat."),
            (self.panel_hakim[1 % len(self.panel_hakim)], "Bacakan ringkasan duduk perkara dan kedudukan hukum Pemohon secara singkat."),
            (self.panel_hakim[2 % len(self.panel_hakim)], "Bacakan ringkasan pertimbangan Mahkamah terhadap pokok permohonan."),
            (self.panel_hakim[0], "Bacakan amar putusan secara singkat dan tutup sidang."),
        ]

        for agent, prompt in prompts:
            if len(self.transcript) >= target_turn_count:
                break
            content = await self._generate_agent_response(
                agent,
                f"{prompt}\n\nKonteks perkara:\n{draft_input[:900]}"
            )
            await self._validated_log(round_name, agent.name, content)

        reason = "amar putusan telah diucapkan"
        if len(self.transcript) >= target_turn_count:
            reason = "batas target giliran sidang tercapai"
        return self._hearing_result(reason)

    async def run_hearing_profile(self, draft_input: str) -> Dict[str, Any]:
        target_turn_count = self._select_target_turn_count(draft_input)
        runners = {
            "pemeriksaan_pendahuluan": self._run_dynamic_pendahuluan,
            "perbaikan_permohonan": self._run_dynamic_perbaikan,
            "keterangan_pemerintah_dpr": self._run_dynamic_pemerintah_dpr,
            "pemeriksaan_ahli": self._run_dynamic_ahli,
            "pembuktian": self._run_dynamic_pembuktian,
            "putusan": self._run_dynamic_putusan,
        }
        runner = runners.get(self.hearing_mode, self._run_dynamic_pendahuluan)
        result = await runner(draft_input, target_turn_count)
        result["api_usage"] = self._collect_api_usage()
        result["metadata"]["api_usage"] = result["api_usage"]
        return result

    # ================================================================
    # MAIN: Full Simulation
    # ================================================================
    async def run_full_training_simulation(self, draft_input: str) -> Dict[str, Any]:
        """
        Menjalankan siklus sidang penuh.
        Alur:
          Ronde 1  → Pemeriksaan Pendahuluan
          Ronde 2  → Perbaikan Permohonan
          Ronde 2B → Pemeriksaan Ahli (jika include_ahli=True)
          Ronde 3  → Pokok Perkara + Pihak Terkait + Amicus Curiae
          Ronde 4  → Kesimpulan + RPH + Dissenting Opinion
        """
        print(f"\n\n{'>'*15} MULAI SIMULASI {self.simulation_id} {'<'*15}")

        await self.run_round_1_pendahuluan(draft_input)
        await self.run_round_2_perbaikan()
        await self.run_round_2b_ahli()          # ROADMAP Fase 3 #4
        await self.run_round_3_pokok_perkara()  # ROADMAP Fase 2 #2
        result = await self.run_round_4_kesimpulan()  # ROADMAP Fase 2 #1
        feedback = await self.run_round_5_feedback()   # ROADMAP Fase 4 #8
        result["feedback"] = feedback
        result["api_usage"] = self._collect_api_usage()
        if isinstance(result.get("scores"), dict):
            result["scores"]["api_usage"] = result["api_usage"]

        print(f"{'>'*15} SIMULASI {self.simulation_id} SELESAI {'<'*15}\n")
        return result

    async def run_full_simulation(self, draft_input: str) -> Dict[str, Any]:
        if self.hearing_mode == self.PEDAGOGICAL_MODE:
            return await self.run_full_training_simulation(draft_input)
        return await self.run_hearing_profile(draft_input)
