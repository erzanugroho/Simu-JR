"""
Agent Module - Simulasi Sidang MK
==================================
Agen AI yang merepresentasikan para pihak dalam sidang Mahkamah Konstitusi.
Dilengkapi dengan:
- System prompt berbasis hukum acara MK
- Integrasi RAG (referensi putusan & risalah)
- Sliding window memory management
- Token/Word Limiter dengan mekanisme interupsi Hakim (ROADMAP Fase 3 #5)
- Agen baru: Pihak Terkait, Amicus Curiae, Ahli Pemohon, Ahli Pemerintah, Validator (ROADMAP Fase 2 #2, #3)

Modul ini mengimpor konfigurasi LLM dari llm_client.py dan system prompt dari system_prompts.py.
"""

import asyncio
import logging
import os
import json
import re
from typing import List, Dict, Any, Optional
import httpx

from .utils import strip_cot

from .llm_client import (
    LLM_BASE_URL, LLM_API_KEY, MODEL_NAME, LLM_MAX_TOKENS,
    OPENROUTER_BASE_URL, OPENROUTER_DEFAULT_MODEL,
    MIMO_BASE_URL, MIMO_DEFAULT_MODEL,
    DEEPSEEK_BASE_URL, DEEPSEEK_DEFAULT_MODEL, DEEPSEEK_PRICING,
    client, _openrouter_provider_route,
)

# Re-export LLM_BASE_URL for backward compatibility (preprocessor.py imports it from here)
__all__ = [
    # LLM client re-exports
    "LLM_BASE_URL", "LLM_API_KEY", "MODEL_NAME", "LLM_MAX_TOKENS", "client",
    # Agent classes
    "BaseAgent", "PemohonAgent", "PemerintahAgent", "HakimAgent",
    "JudicialReviewDraftAgent", "PermohonanDrafterAgent", "PihakTerkaitAgent", "AmicusCuriaeAgent",
    "AhliPemohonAgent", "AhliPemerintahAgent", "ValidatorAgent", "RisetHukumAgent",
    # Constants & helpers
    "DEFAULT_MAX_HISTORY", "WORD_LIMITS", "UUD_TEXT", "extract_relevant_uud_pasals",
]
from .system_prompts import (
    SYSTEM_PROMPT_PEMOHON, SYSTEM_PROMPT_PEMERINTAH, SYSTEM_PROMPT_HAKIM,
    SYSTEM_PROMPT_PIHAK_TERKAIT, SYSTEM_PROMPT_AMICUS_CURIAE,
    SYSTEM_PROMPT_AHLI_PEMOHON, SYSTEM_PROMPT_AHLI_PEMERINTAH,
    SYSTEM_PROMPT_VALIDATOR, SYSTEM_PROMPT_JUDICIAL_REVIEW_DRAFT,
    SYSTEM_PROMPT_PERMOHONAN_DRAFTER, SYSTEM_PROMPT_RISET_HUKUM,
    get_hakim_system_prompt,
)

logger = logging.getLogger(__name__)

# === Default Memory Config ===
DEFAULT_MAX_HISTORY = 20  # Sliding window: simpan N pesan terakhir

# === Token/Word Limiter Config (ROADMAP Fase 3 #5) ===
# Batas kata per respons - Hakim akan menginterupsi jika melebihi batas
# Disesuaikan dengan risalah sidang MK asli (rata-rata 10-180 kata per turn)
WORD_LIMITS = {
    "pemohon": 75,
    "pemerintah": 90,
    "hakim": 80,
    "ahli": 90,
    "pihak_terkait": 75,
    "amicus": 85,
    "validator": None,      # Tidak dibatasi
    "draft_reviser": None,  # Tidak dibatasi: harus bisa menghasilkan naskah permohonan penuh
    "riset_hukum": None,    # Tidak dibatasi: riset hukum butuh jawaban komprehensif
}
INTERRUPTION_NOTICES = [
    "\n\n[...DIPOTONG - Ketua Majelis: 'Saudara, waktu Anda telah habis. Harap simpulkan poin Anda secara singkat.']",
    "\n\n[...DIPOTONG - Ketua Majelis: 'Saudara, mohon singkat. Waktu sudah habis.']",
    "\n\n[...DIPOTONG - Ketua Majelis: 'Terima kasih, Saudara. Waktu sudah cukup.']",
    "\n\n[...DIPOTONG - Ketua Majelis: 'Saudara, tolong langsung ke kesimpulan saja.']",
]
INTERRUPTION_NOTICE = INTERRUPTION_NOTICES[0]

# Hakim adalah pengendali persidangan. Jika pertanyaan hakim terlalu panjang,
# sistem merapikannya tanpa membuat fiksi bahwa hakim dipotong oleh hakim lain.
NON_INTERRUPTED_ROLES = {"hakim"}

# Role ini harus terasa seperti jawaban lisan yang disiplin. Jika model tetap
# melewati batas, respons dipangkas bersih tanpa notice interupsi agar Pemohon
# tidak terus terlihat "kehabisan waktu" dalam transkrip.
SILENT_CAP_ROLES = {"pemohon", "pemerintah", "ahli", "pihak_terkait", "amicus"}

# === Load UUD 1945 Context ===
UUD_PATH = os.path.join(os.path.dirname(__file__), '..', 'rag', 'uud_1945.json')
UUD_TEXT = ""
if os.path.exists(UUD_PATH):
    try:
        with open(UUD_PATH, 'r', encoding='utf-8') as f:
            uud_data = json.load(f)
            UUD_TEXT = uud_data.get('content', '')
    except Exception as e:
        logger.error(f"Gagal memuat UUD 1945: {e}")

# Ringkasan pendek untuk system prompt (tanpa full text - hemat ~10K token per call)
UUD_PROMPT_ADDITION = """
============================================================
REFERENSI: UUD NRI 1945 (BATU UJI)
============================================================
Anda wajib menggunakan teks UUD 1945 secara persis ketika merujuk pada pasal/ayat.
DILARANG KERAS mengarang, mengubah, atau menghalusinasi isi pasal UUD 1945!
Teks pasal relevan akan diberikan dalam konteks per-panggilan jika diperlukan.
""" if UUD_TEXT else ""


def extract_relevant_uud_pasals(draft_text: str, uud_text: str, max_chars: int = 6000) -> str:
    """
    Ekstrak hanya pasal-pasal UUD 1945 yang relevan berdasarkan draft/konteks.
    Mencari 'Pasal X' atau 'Pasal X ayat (Y)' dalam draft, lalu mengambil
    teks pasal yang sesuai dari full text UUD.
    """
    if not uud_text or not draft_text:
        return ""

    # Ekstrak nomor pasal yang disebut dalam draft
    pasal_numbers = set()
    for m in re.finditer(r'[Pp]asal\s+(\d+[A-Za-z]?)', draft_text):
        pasal_numbers.add(m.group(1))

    # Fallback: pasal UUD yang sering relevan dalam judicial review
    common_pasals = [
        "28A", "28B", "28C", "28D", "28E", "28F", "28G", "28H", "28I", "28J",
        "20", "21", "22", "23", "24", "27", "28", "29", "30", "31", "32", "33", "34",
        "1", "2", "3", "4", "5", "6", "7",
    ]

    # Prioritaskan pasal yang disebut dalam draft
    priority_pasals = list(pasal_numbers)
    fallback_pasals = [p for p in common_pasals if p not in pasal_numbers]

    # Split UUD menjadi per-pasal sections
    pasal_sections = re.split(r'(?=(?:^|\n)\s*[Pp]asal\s+\d)', uud_text)

    result_parts = []
    total_len = 0

    # Cari pasal yang relevan (prioritas dulu, lalu fallback)
    for pasal_num in priority_pasals + fallback_pasals:
        pattern = re.compile(
            r'(?:^|\n)\s*[Pp]asal\s+' + re.escape(pasal_num) + r'(?:\b|\s)',
            re.IGNORECASE
        )
        for section in pasal_sections:
            if pattern.search(section) and section.strip():
                section_clean = section.strip()
                # Batasi panjang per section
                if len(section_clean) > 1500:
                    section_clean = section_clean[:1500] + "..."
                if total_len + len(section_clean) > max_chars:
                    break
                result_parts.append(section_clean)
                total_len += len(section_clean)
                break
        if total_len >= max_chars:
            break

    if not result_parts:
        return ""

    return (
        "\n\n=== PASAL UUD 1945 YANG RELEVAN ===\n"
        "Wajib kutip secara persis. DILARANG mengarang isi pasal.\n\n"
        + "\n\n---\n\n".join(result_parts)
        + "\n=== AKHIR PASAL UUD 1945 ==="
    )


class BaseAgent:
    """Base class untuk semua agent dalam simulasi sidang MK."""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_history: int = DEFAULT_MAX_HISTORY,
        llm_config: Optional[Dict[str, Any]] = None,
        max_words: Optional[int] = None,
        max_tokens: Optional[int] = None
    ):
        self.name = name
        self.role = role
        # Inject ringkasan pendek UUD 1945 ke system prompt (bukan full text)
        self.system_prompt = system_prompt + "\n" + UUD_PROMPT_ADDITION
        self.temperature = temperature
        self.max_history = max_history
        self.llm_config = llm_config or {}
        self.max_tokens = max_tokens or LLM_MAX_TOKENS
        # Word limit: gunakan dari WORD_LIMITS berdasarkan role, atau override manual
        self.max_words = max_words if max_words is not None else WORD_LIMITS.get(role)
        self.memory: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        self.usage_records: List[Dict[str, Any]] = []
        # State untuk streaming filter (menyaring thinking chunks dari reasoning models seperti Qwen/DeepSeek)
        self._stream_in_think_block = False
        self._stream_think_buffer = ""

    def _strip_thinking_process(self, text: str) -> str:
        """Menghapus internal thinking/CoT dari respons LLM secara agresif."""
        return strip_cot(text, aggressive=True)

    def _infer_hakim_addressee(self, text: str, prompt: str = "") -> str:
        """Tebak sapaan hakim yang tepat dari prompt/teks."""
        combined = f"{prompt}\n{text}".lower()
        if "ahli pemerintah" in combined:
            return "Saudara Ahli Pemerintah"
        if "ahli" in combined:
            return "Saudara Ahli"
        if "pihak terkait" in combined:
            return "Saudara Pihak Terkait"
        if "pemerintah" in combined or "presiden" in combined or "dpr" in combined:
            return "Saudara Pemerintah"
        if "pemohon" in combined:
            return "Saudara Pemohon"
        return ""

    def _repair_trailing_fragment(self, text: str) -> str:
        """Pastikan hasil limiter tidak berhenti pada fragmen/list yang menggantung."""
        if not text:
            return text

        cleaned = text.strip()
        trailing_bad = (
            re.search(r'(?:^|\s)\d+\.\s*$', cleaned) or
            re.search(r'\b(?:dalam|pada|menurut|berdasarkan|sebagaimana|dengan|terhadap)\s+Pasal\.?$', cleaned, re.IGNORECASE) or
            re.search(r'\b(?:Pasal|ayat|huruf|Nomor|No)\s*\.?$', cleaned, re.IGNORECASE) or
            re.search(r'[,;:]\s*$', cleaned)
        )

        if trailing_bad:
            prefix = cleaned[: trailing_bad.start()].rstrip()
            sentence_end = max(prefix.rfind("."), prefix.rfind("?"), prefix.rfind("!"))
            if sentence_end >= max(30, len(prefix) // 3):
                cleaned = prefix[: sentence_end + 1].strip()
            elif prefix:
                cleaned = prefix.strip()
            else:
                cleaned = re.sub(r'(?:\s+\d+\.|[,;:])\s*$', '', cleaned).strip()

        if cleaned and cleaned[-1] not in ".?!":
            cleaned += "."
        return cleaned

    def _sanitize_court_output(self, text: str, prompt: str = "") -> str:
        """Bersihkan bocoran internal, placeholder, markdown, dan sapaan role yang keliru."""
        if not text:
            return ""

        cleaned = str(text)
        cleaned = re.sub(r'\[\.\.\.DIPOTONG[^\]]*\]', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r'\b(?:SURVIVE|RATIO|JUDGE\s+CONCERN|GOVERNMENT\s+ATTACK)\s+BANK\b:?\s*',
            '',
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r'\bperkara\s+Nomor\s*\.\.\.\s*(?:dengan|,)?',
            'perkara ini ',
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r'\bNomor\s*\.\.\.', 'perkara ini', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("**", "")
        cleaned = re.sub(r'^\s*#+\s*', '', cleaned, flags=re.MULTILINE)

        if self.role == "hakim":
            addressee = self._infer_hakim_addressee(cleaned, prompt)
            replacement = f"Baik, {addressee}." if addressee else "Baik,"
            cleaned = re.sub(
                r'^\s*(?:Baik|Oke|Terima kasih)\s*,?\s+Yang Mulia\.?',
                replacement,
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(r'\bYang Mulia\b', addressee or 'Saudara', cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return self._repair_trailing_fragment(cleaned)

    def _cap_at_sentence_boundary(self, text: str, max_words: int) -> str:
        """Pangkas teks pada batas kata, lalu mundur ke akhir kalimat terdekat."""
        words = text.split()
        if len(words) <= max_words:
            return text

        capped = " ".join(words[:max_words]).strip()
        sentence_ends = [
            capped.rfind("."),
            capped.rfind("?"),
            capped.rfind("!"),
            capped.rfind(";"),
        ]
        end_idx = max(sentence_ends)
        min_reasonable_len = max(40, len(capped) // 2)
        if end_idx >= min_reasonable_len:
            capped = capped[: end_idx + 1].strip()
        else:
            capped = capped.rstrip(",;:")
            if capped and capped[-1] not in ".?!":
                capped += "."
        return capped

    def _apply_word_limit(self, answer: str, prompt: str = "") -> str:
        """Terapkan batas kata sesuai role tanpa merusak logika roleplay sidang."""
        is_json_payload = answer.strip().startswith("{") and answer.strip().endswith("}")
        if not self.max_words or self.role == "validator" or is_json_payload:
            return answer

        words = answer.split()
        max_words = self.max_words
        if self.role == "hakim" and re.search(r'nasihat\s+perbaikan|perbaikan\s+permohonan', prompt, re.IGNORECASE):
            max_words = 110

        if len(words) <= max_words:
            return answer

        capped = self._repair_trailing_fragment(self._cap_at_sentence_boundary(answer, max_words))

        if self.role in NON_INTERRUPTED_ROLES or self.role in SILENT_CAP_ROLES:
            logger.info(
                f"[{self.name}] Respons diringkas di {max_words} kata "
                f"(panjang asli: {len(words)} kata, tanpa notice interupsi)"
            )
            return capped

        import random
        notice = random.choice(INTERRUPTION_NOTICES)
        logger.info(
            f"[{self.name}] Respons dipotong di {max_words} kata "
            f"(panjang asli: {len(words)} kata)"
        )
        return capped + notice

    def _filter_streaming_chunk(self, chunk: str) -> str:
        """Filter chunk selama streaming untuk menyaring thinking content secara real-time."""
        if not chunk:
            return ""

        if self._stream_in_think_block:
            self._stream_think_buffer += chunk
            # Cek penutup: baik XML tags maupun envelope [/THINK]
            close_match = re.search(
                r'<\s*/\s*(?:think|thinking|thought|reasoning)\s*>|\[/THINK\]',
                self._stream_think_buffer, re.IGNORECASE
            )
            if close_match:
                end_idx = close_match.end()
                after_think = self._stream_think_buffer[end_idx:]
                self._stream_in_think_block = False
                self._stream_think_buffer = ""
                return after_think.lstrip()
            else:
                if len(self._stream_think_buffer) > 8000:
                    logger.warning(f"[{self.name}] Think block terlalu panjang tanpa tag penutup, memaksa keluar dari think block")
                    self._stream_in_think_block = False
                    result = self._stream_think_buffer
                    self._stream_think_buffer = ""
                    return result
                return ""

        # Cek pembuka: XML tags atau envelope [THINK]
        open_match = re.search(
            r'<\s*(?:think|thinking|thought|reasoning)\s*>|\[THINK\]',
            chunk, re.IGNORECASE
        )
        if open_match:
            before_think = chunk[:open_match.start()]
            after_open = chunk[open_match.end():]
            close_match = re.search(
                r'<\s*/\s*(?:think|thinking|thought|reasoning)\s*>|\[/THINK\]',
                after_open, re.IGNORECASE
            )
            if close_match:
                after_think = after_open[close_match.end():]
                return (before_think + after_think).lstrip()
            else:
                self._stream_in_think_block = True
                self._stream_think_buffer = after_open
                return before_think.lstrip()

        reasoning_patterns = [
            r'^(Wait[,\.]?\s+)',
            r'^(Let me think[\.\s]+)',
            r'^(Hmm[,\.]?\s+)',
            r'^(Okay[,\.]?\s+(?:so|let me|I need to)\s+)',
        ]
        for pattern in reasoning_patterns:
            if re.match(pattern, chunk, re.IGNORECASE):
                self._stream_in_think_block = True
                self._stream_think_buffer = chunk
                return ""

        return chunk

    def _trim_memory(self):
        """Sliding window memory management. Pertahankan system prompt + N pesan terakhir."""
        if len(self.memory) > self.max_history + 1:
            system_msg = self.memory[0]
            recent = self.memory[-(self.max_history):]
            self.memory = [system_msg] + recent
            logger.debug(f"{self.name}: Memory trimmed ke {len(self.memory)} pesan")

    def _usage_to_dict(self, usage: Any) -> Dict[str, Any]:
        """Normalize usage object dari OpenAI/OpenRouter SDK menjadi dict biasa."""
        if not usage:
            return {}
        if isinstance(usage, dict):
            return usage
        if hasattr(usage, "model_dump"):
            try:
                return usage.model_dump()
            except Exception:
                pass
        data = {}
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost",
            "cost_details",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
        ):
            if hasattr(usage, key):
                data[key] = getattr(usage, key)
        if hasattr(usage, "model_extra") and usage.model_extra:
            data.update(usage.model_extra)
        return data

    def _record_usage(self, provider: str, model_name: str, usage: Any):
        """Simpan penggunaan token dan biaya API per panggilan LLM."""
        data = self._usage_to_dict(usage)
        if not data:
            return

        def as_int(value):
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        def as_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        cost = as_float(data.get("cost"))
        cache_hit_tokens = as_int(data.get("prompt_cache_hit_tokens"))
        cache_miss_tokens = as_int(data.get("prompt_cache_miss_tokens"))
        if cost is None and isinstance(data.get("cost_details"), dict):
            details = data["cost_details"]
            detail_values = [
                as_float(details.get("upstream_inference_prompt_cost")),
                as_float(details.get("upstream_inference_completions_cost")),
                as_float(details.get("upstream_inference_cost")),
            ]
            present = [v for v in detail_values if v is not None]
            if present:
                cost = sum(present)
        if cost is None and provider == "deepseek":
            pricing = DEEPSEEK_PRICING.get(model_name)
            if pricing:
                prompt_tokens = as_int(data.get("prompt_tokens"))
                completion_tokens = as_int(data.get("completion_tokens"))
                uncategorized_prompt_tokens = max(prompt_tokens - cache_hit_tokens - cache_miss_tokens, 0)
                cost = (
                    (cache_hit_tokens * pricing["cache_hit"])
                    + ((cache_miss_tokens + uncategorized_prompt_tokens) * pricing["cache_miss"])
                    + (completion_tokens * pricing["completion"])
                ) / 1_000_000

        record = {
            "agent": self.name,
            "role": self.role,
            "provider": provider,
            "model": model_name,
            "prompt_tokens": as_int(data.get("prompt_tokens")),
            "prompt_cache_hit_tokens": cache_hit_tokens,
            "prompt_cache_miss_tokens": cache_miss_tokens,
            "completion_tokens": as_int(data.get("completion_tokens")),
            "total_tokens": as_int(data.get("total_tokens")),
            "cost": round(cost, 8) if cost is not None else None,
        }
        self.usage_records.append(record)

    async def _call_openai_compatible(
        self,
        openai_client: Any,
        model_name: str,
        provider: str,
        on_chunk: Optional[Any] = None,
    ) -> tuple:
        """Panggil OpenAI-compatible API (local / OpenRouter). Mengembalikan (answer, usage_data)."""
        answer = ""
        usage_data = None

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": self.memory,
            "stream": on_chunk is not None,
            "max_tokens": self.max_tokens,
        }
        if provider == "openrouter" and on_chunk:
            kwargs["stream_options"] = {"include_usage": True}
        if provider == "openrouter":
            openrouter_provider = _openrouter_provider_route(model_name)
            if openrouter_provider:
                kwargs["extra_body"] = {"provider": openrouter_provider}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        # === Solusi 2: Minimalkan reasoning/thinking di level API ===
        # MiMo/DeepSeek hanya menerima "low"/"medium"/"high", bukan "none"
        # OpenRouter mendukung "none" tapi kita pakai "low" untuk kompatibilitas
        if provider == "openrouter":
            kwargs["reasoning"] = {"effort": "low"}
        elif provider == "mimo":
            if "extra_body" not in kwargs:
                kwargs["extra_body"] = {}
            kwargs["extra_body"]["reasoning_effort"] = "low"
        elif provider == "deepseek":
            if "extra_body" not in kwargs:
                kwargs["extra_body"] = {}
            kwargs["extra_body"]["thinking"] = {"type": "enabled"}
            kwargs["extra_body"]["reasoning_effort"] = "low"

        try:
            if on_chunk:
                stream = await openai_client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    if getattr(chunk, "usage", None):
                        usage_data = chunk.usage
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    delta = getattr(choices[0], "delta", None)
                    # === Solusi 1: Buang reasoning_content dari streaming ===
                    reasoning_delta = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                    if reasoning_delta:
                        logger.debug(f"[{self.name}] Thinking chunk discarded (streaming): {len(reasoning_delta)} chars")
                    raw_content = getattr(delta, "content", None)
                    if raw_content:
                        filtered_content = self._filter_streaming_chunk(raw_content)
                        if filtered_content:
                            answer += filtered_content
                            await on_chunk(filtered_content)
            else:
                response = await openai_client.chat.completions.create(**kwargs)
                # === Solusi 1: Buang reasoning_content dari non-streaming ===
                message = response.choices[0].message
                reasoning = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
                if reasoning:
                    logger.debug(f"[{self.name}] Thinking discarded (non-streaming): {len(reasoning)} chars")
                answer = message.content
                usage_data = getattr(response, "usage", None)
        except Exception as e:
            err_str = str(e).lower()
            # Hapus parameter yang ditolak API lalu retry
            if (
                "reasoning_effort" in err_str
                or "thinking" in err_str
                or ("reasoning" in err_str and "literal_error" in err_str)
            ):
                kwargs.pop("reasoning", None)
                if isinstance(kwargs.get("extra_body"), dict):
                    kwargs["extra_body"].pop("reasoning_effort", None)
                    kwargs["extra_body"].pop("thinking", None)
                    if not kwargs["extra_body"]:
                        kwargs.pop("extra_body", None)
                logger.warning(f"[{self.name}] reasoning/thinking parameter ditolak API, retry tanpa reasoning")
            elif "temperature" in err_str:
                kwargs.pop("temperature", None)
            else:
                raise

            # Retry dengan kwargs yang sudah dibersihkan
            if on_chunk:
                answer = ""
                self._stream_in_think_block = False
                self._stream_think_buffer = ""
                stream = await openai_client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    if getattr(chunk, "usage", None):
                        usage_data = chunk.usage
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    delta = getattr(choices[0], "delta", None)
                    # === Solusi 1: Buang reasoning_content dari streaming (retry) ===
                    reasoning_delta = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                    if reasoning_delta:
                        logger.debug(f"[{self.name}] Thinking chunk discarded (streaming retry): {len(reasoning_delta)} chars")
                    raw_content = getattr(delta, "content", None)
                    if raw_content:
                        filtered_content = self._filter_streaming_chunk(raw_content)
                        if filtered_content:
                            answer += filtered_content
                            await on_chunk(filtered_content)
            else:
                response = await openai_client.chat.completions.create(**kwargs)
                # === Solusi 1: Buang reasoning_content dari non-streaming (retry) ===
                message = response.choices[0].message
                reasoning = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
                if reasoning:
                    logger.debug(f"[{self.name}] Thinking discarded (non-streaming retry): {len(reasoning)} chars")
                answer = message.content
                usage_data = getattr(response, "usage", None)

        return answer, usage_data

    async def _call_claude(
        self,
        model_name: str,
        on_chunk: Optional[Any] = None,
    ) -> tuple:
        """Panggil Anthropic Claude API. Mengembalikan (answer, usage_data)."""
        from anthropic import AsyncAnthropic
        api_key = self.llm_config.get("api_key", "")
        if not api_key:
            raise ValueError("API Key Anthropic belum diatur.")

        anthropic_client = AsyncAnthropic(api_key=api_key)
        system_msg = ""
        anthropic_messages = []
        for m in self.memory:
            if m["role"] == "system":
                system_msg += m["content"] + "\n"
            else:
                anthropic_messages.append({"role": m["role"], "content": m["content"]})

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "max_tokens": 10000,
            "system": system_msg.strip(),
            "messages": anthropic_messages,
            "stream": on_chunk is not None
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        answer = ""
        try:
            if on_chunk:
                async with anthropic_client.messages.stream(**kwargs) as stream:
                    async for chunk in stream.text_stream:
                        answer += chunk
                        await on_chunk(chunk)
            else:
                response = await anthropic_client.messages.create(**kwargs)
                answer = response.content[0].text
        except Exception as e:
            if "temperature" in str(e).lower():
                kwargs.pop("temperature", None)
                if on_chunk:
                    answer = ""
                    async with anthropic_client.messages.stream(**kwargs) as stream:
                        async for chunk in stream.text_stream:
                            answer += chunk
                            await on_chunk(chunk)
                else:
                    response = await anthropic_client.messages.create(**kwargs)
                    answer = response.content[0].text
            else:
                raise

        return answer, None

    async def generate_response(self, prompt: str, rag_context: str = "", on_chunk: Optional[Any] = None) -> str:
        """
        Membuat respons LLM dengan konteks RAG opsional.
        Dukung streaming jika on_chunk disediakan.
        """
        full_prompt = prompt
        if rag_context:
            full_prompt = (
                f"{rag_context}\n\n"
                f"=== INSTRUKSI ===\n"
                f"{prompt}"
            )

        self.memory.append({"role": "user", "content": full_prompt})
        self._trim_memory()

        # Reset streaming filter state
        self._stream_in_think_block = False
        self._stream_think_buffer = ""

        try:
            provider = self.llm_config.get("provider", "local")
            model_name = self.llm_config.get("model_name", MODEL_NAME)
            logger.info(f"[{self.name}] Meminta respons dari provider: {provider}, model: {model_name}")

            if provider == "claude":
                model_name = self.llm_config.get("model_name", "claude-3-haiku-20240307")
                answer, _ = await self._call_claude(model_name, on_chunk)
            else:
                from openai import AsyncOpenAI
                provider = self.llm_config.get("provider", "local")
                # Determine default base URL based on provider
                if provider == "openrouter":
                    default_base_url = OPENROUTER_BASE_URL
                elif provider == "mimo":
                    default_base_url = MIMO_BASE_URL
                elif provider == "deepseek":
                    default_base_url = DEEPSEEK_BASE_URL
                else:
                    default_base_url = LLM_BASE_URL
                # For cloud providers, always use their default URL unless explicitly overridden with a non-local URL
                explicit_url = self.llm_config.get("base_url") or ""
                if explicit_url and explicit_url != LLM_BASE_URL and provider in ("openrouter", "mimo", "deepseek"):
                    base_url = explicit_url
                elif provider in ("openrouter", "mimo", "deepseek"):
                    base_url = default_base_url
                else:
                    base_url = explicit_url or default_base_url
                # Determine API key based on provider
                if provider in ("openrouter", "mimo", "deepseek"):
                    api_key = str(self.llm_config.get("api_key") or "").strip()
                else:
                    api_key = str(self.llm_config.get("api_key") or LLM_API_KEY).strip()
                if provider == "openrouter" and not api_key:
                    raise ValueError("API Key OpenRouter belum diatur.")
                if provider == "mimo" and not api_key:
                    raise ValueError("API Key Xiaomi MiMo belum diatur.")
                if provider == "deepseek" and not api_key:
                    raise ValueError("API Key DeepSeek belum diatur.")
                default_headers = None
                if provider == "openrouter":
                    default_headers = {
                        "HTTP-Referer": "http://localhost:8000",
                        "X-OpenRouter-Title": "Simulasi Sidang MK",
                    }

                if base_url == LLM_BASE_URL and api_key == LLM_API_KEY:
                    openai_client = client
                else:
                    openai_client = AsyncOpenAI(
                        base_url=base_url,
                        api_key=api_key,
                        timeout=httpx.Timeout(600.0),
                        default_headers=default_headers,
                    )

                # Determine default model name based on provider
                if provider == "openrouter":
                    default_model_name = OPENROUTER_DEFAULT_MODEL
                elif provider == "mimo":
                    default_model_name = MIMO_DEFAULT_MODEL
                elif provider == "deepseek":
                    default_model_name = DEEPSEEK_DEFAULT_MODEL
                else:
                    default_model_name = MODEL_NAME
                model_name = self.llm_config.get("model_name") or default_model_name
                answer, usage_data = await self._call_openai_compatible(openai_client, model_name, provider, on_chunk)
                self._record_usage(provider, model_name, usage_data)

            # Bersihkan dari internal thinking dan bocoran gaya non-sidang.
            answer = self._sanitize_court_output(self._strip_thinking_process(answer), prompt)

            # === WORD LIMITER (ROADMAP Fase 3 #5) ===
            answer = self._apply_word_limit(answer, prompt)
            answer = self._sanitize_court_output(answer, prompt)

            self.memory.append({"role": "assistant", "content": answer})
            return answer
        except Exception as e:
            logger.error(f"Error LLM pada {self.name}: {e}")
            return f"[{self.name} mengalami gangguan - {str(e)}]"

    def get_memory_stats(self) -> Dict[str, int]:
        """Informasi debug tentang memory agent."""
        return {
            "total_messages": len(self.memory),
            "max_history": self.max_history,
            "estimated_tokens": sum(len(m["content"]) // 4 for m in self.memory)
        }


# ============================================================
# Agent Classes - Masing-masing merepresentasikan peran sidang
# ============================================================

class PemohonAgent(BaseAgent):
    """Kuasa Hukum Pemohon - membela permohonan Judicial Review."""

    def __init__(self, temperature: float = 0.7, max_history: int = DEFAULT_MAX_HISTORY, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="Kuasa Hukum Pemohon",
            role="pemohon",
            system_prompt=SYSTEM_PROMPT_PEMOHON,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config
        )


class PemerintahAgent(BaseAgent):
    """Kuasa Hukum Presiden/DPR - mempertahankan konstitusionalitas UU."""

    def __init__(self, temperature: float = 0.7, max_history: int = DEFAULT_MAX_HISTORY, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="Kuasa Hukum Presiden/DPR",
            role="pemerintah",
            system_prompt=SYSTEM_PROMPT_PEMERINTAH,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config
        )


class HakimAgent(BaseAgent):
    """Hakim Konstitusi - menguji argumen para pihak secara kritis dan imparsial."""

    VALID_PERSONAS = ("default", "formalis", "progresif", "positivis")

    def __init__(
        self,
        hakim_id: int,
        temperature: float = 0.1,
        max_history: int = DEFAULT_MAX_HISTORY,
        llm_config: Optional[Dict[str, Any]] = None,
        persona: str = "default"
    ):
        persona = persona if persona in self.VALID_PERSONAS else "default"
        super().__init__(
            name=f"Hakim Konstitusi {hakim_id}",
            role="hakim",
            system_prompt=get_hakim_system_prompt(persona),
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config
        )
        self.hakim_id = hakim_id
        self.persona = persona


class JudicialReviewDraftAgent(BaseAgent):
    """Agent khusus untuk menyusun/merevisi naskah permohonan PUU."""

    def __init__(
        self,
        temperature: float = 0.2,
        max_history: int = 6,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name="Penyusun Draft Judicial Review",
            role="draft_reviser",
            system_prompt=SYSTEM_PROMPT_JUDICIAL_REVIEW_DRAFT,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config,
            max_words=None,
            max_tokens=8000  # Draft panjang butuh lebih banyak token
        )


class PermohonanDrafterAgent(BaseAgent):
    """Agent khusus untuk membuat dan memperbaiki dokumen permohonan MK."""

    def __init__(
        self,
        temperature: float = 0.2,
        max_history: int = 6,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name="Drafter Permohonan MK",
            role="draft_reviser",
            system_prompt=SYSTEM_PROMPT_PERMOHONAN_DRAFTER,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config,
            max_words=None,
            max_tokens=9000
        )


class PihakTerkaitAgent(BaseAgent):
    """Pihak Terkait - membela kepentingan pihak ketiga yang terdampak langsung."""

    def __init__(
        self,
        temperature: float = 0.7,
        max_history: int = DEFAULT_MAX_HISTORY,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name="Pihak Terkait",
            role="pihak_terkait",
            system_prompt=SYSTEM_PROMPT_PIHAK_TERKAIT,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config
        )


class AmicusCuriaeAgent(BaseAgent):
    """Amicus Curiae - memberikan pandangan akademis & komparatif yang netral."""

    def __init__(
        self,
        temperature: float = 0.5,
        max_history: int = DEFAULT_MAX_HISTORY,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name="Amicus Curiae",
            role="amicus",
            system_prompt=SYSTEM_PROMPT_AMICUS_CURIAE,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config
        )


class AhliPemohonAgent(BaseAgent):
    """Ahli Pemohon - keterangan ahli konstitusi yang mendukung dalil Pemohon."""

    def __init__(
        self,
        temperature: float = 0.5,
        max_history: int = DEFAULT_MAX_HISTORY,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name="Ahli Hukum Konstitusi (Pemohon)",
            role="ahli",
            system_prompt=SYSTEM_PROMPT_AHLI_PEMOHON,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config
        )


class AhliPemerintahAgent(BaseAgent):
    """Ahli Pemerintah - keterangan ahli tata negara yang mendukung konstitusionalitas UU."""

    def __init__(
        self,
        temperature: float = 0.5,
        max_history: int = DEFAULT_MAX_HISTORY,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name="Ahli Hukum Tata Negara (Pemerintah)",
            role="ahli",
            system_prompt=SYSTEM_PROMPT_AHLI_PEMERINTAH,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config
        )


class ValidatorAgent(BaseAgent):
    """Validator Dalil - middleware anti-halusinasi yang memeriksa kutipan putusan & pasal."""

    def __init__(
        self,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name="Validator Dalil",
            role="validator",
            system_prompt=SYSTEM_PROMPT_VALIDATOR,
            temperature=0.0,       # Deterministik untuk validasi
            max_history=5,         # Memory minimal - hanya perlu konteks pendek
            llm_config=llm_config,
            max_words=None
        )

    async def validate(self, text: str) -> Dict[str, Any]:
        """
        Validasi teks argumen. Mengembalikan dict hasil validasi.
        Pertama coba regex cepat; jika ada potensi masalah, eskalasi ke LLM.
        """
        regex_result = self._quick_regex_check(text)

        if regex_result["verdict"] != "LOLOS":
            prompt = (
                f"Periksa teks argumen hukum berikut untuk potensi halusinasi kutipan:\n\n"
                f"<TEKS>\n{text[:1500]}\n</TEKS>\n\n"
                f"Kembalikan HANYA JSON sesuai format sistem."
            )
            raw = await self.generate_response(prompt)
            try:
                start = raw.find('{')
                end = raw.rfind('}') + 1
                if start != -1 and end > 0:
                    return json.loads(raw[start:end])
            except Exception:
                pass  # Fallback ke hasil regex jika LLM gagal

        return regex_result

    def _quick_regex_check(self, text: str) -> Dict[str, Any]:
        """Validasi format kutipan putusan MK dengan regex tanpa memanggil LLM."""
        putusan_pattern = re.compile(
            r'(?:Putusan\s+)?(?:Nomor|No\.?)\s*'
            r'(\d+(?:-\d+)?)\s*/\s*PUU-([IVXLCDMivxlcdm]+)\s*/\s*(\d{4})',
            re.IGNORECASE
        )

        warnings = []
        suspicious = []

        for match in putusan_pattern.finditer(text):
            number, roman, year_str = match.groups()
            try:
                year = int(year_str)
                if year < 2003 or year > 2026:
                    suspicious.append(
                        f"Putusan No. {number}/PUU-{roman}/{year_str} "
                        f"- tahun {year} di luar rentang MK (2003-2026)"
                    )
                    warnings.append(f"Tahun putusan mencurigakan: {year}")
            except ValueError:
                suspicious.append(f"Format tahun tidak valid: {year_str}")

        verdict = "LOLOS" if not suspicious else "PERINGATAN"
        return {
            "valid": not suspicious,
            "warnings": warnings,
            "suspicious_citations": suspicious,
            "verdict": verdict,
            "revision_needed": bool(suspicious)
        }


class RisetHukumAgent(BaseAgent):
    """Agent khusus riset hukum konstitusi - tanpa word limit, tanpa truncation."""

    def __init__(
        self,
        temperature: float = 0.3,
        max_history: int = 10,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name="Ahli Riset Hukum Konstitusi",
            role="riset_hukum",
            system_prompt=SYSTEM_PROMPT_RISET_HUKUM,
            temperature=temperature,
            max_history=max_history,
            llm_config=llm_config,
            max_words=None,       # Tidak ada batasan kata
            max_tokens=16000,     # Cukup besar untuk jawaban komprehensif
        )
