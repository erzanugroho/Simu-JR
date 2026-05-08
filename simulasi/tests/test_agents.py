"""
Unit Tests - Agent Classes
============================
Tests for BaseAgent, role-specific agents, memory management, thinking filter, 
word limiter, and validator logic. No LLM calls are made.
"""

import pytest
from core.agents import (
    BaseAgent, PemohonAgent, PemerintahAgent, HakimAgent,
    ValidatorAgent, JudicialReviewDraftAgent,
    PihakTerkaitAgent, AmicusCuriaeAgent,
    AhliPemohonAgent, AhliPemerintahAgent,
    WORD_LIMITS, DEFAULT_MAX_HISTORY, INTERRUPTION_NOTICE,
)


# ============================================================
# Agent Initialization Tests
# ============================================================

class TestAgentInitialization:
    """Test bahwa semua agent ter-inisialisasi dengan benar."""

    def test_pemohon_agent_init(self, pemohon_agent):
        assert pemohon_agent.name == "Kuasa Hukum Pemohon"
        assert pemohon_agent.role == "pemohon"
        assert pemohon_agent.temperature == 0.7
        assert pemohon_agent.max_words == WORD_LIMITS["pemohon"]
        assert len(pemohon_agent.memory) == 1  # Hanya system prompt
        assert pemohon_agent.memory[0]["role"] == "system"

    def test_pemerintah_agent_init(self, pemerintah_agent):
        assert pemerintah_agent.name == "Kuasa Hukum Presiden/DPR"
        assert pemerintah_agent.role == "pemerintah"
        assert pemerintah_agent.max_words == WORD_LIMITS["pemerintah"]

    def test_hakim_agent_init(self, hakim_agent):
        assert hakim_agent.name == "Hakim Konstitusi 1"
        assert hakim_agent.role == "hakim"
        assert hakim_agent.hakim_id == 1
        assert hakim_agent.temperature == 0.1
        assert hakim_agent.max_words == WORD_LIMITS["hakim"]

    def test_hakim_agent_multiple_ids(self, mock_llm_config):
        for i in range(1, 4):
            agent = HakimAgent(hakim_id=i, llm_config=mock_llm_config)
            assert agent.name == f"Hakim Konstitusi {i}"
            assert agent.hakim_id == i

    def test_validator_agent_init(self, validator_agent):
        assert validator_agent.name == "Validator Dalil"
        assert validator_agent.role == "validator"
        assert validator_agent.temperature == 0.0
        assert validator_agent.max_words is None  # Tidak dibatasi
        assert validator_agent.max_history == 5

    def test_draft_agent_init(self, draft_agent):
        assert draft_agent.name == "Penyusun Draft Judicial Review"
        assert draft_agent.role == "draft_reviser"
        assert draft_agent.max_words is None

    def test_system_prompt_contains_uud(self, pemohon_agent):
        """System prompt harus mengandung referensi UUD 1945."""
        assert "UUD" in pemohon_agent.system_prompt

    def test_llm_config_stored(self, mock_llm_config):
        agent = PemohonAgent(llm_config=mock_llm_config)
        assert agent.llm_config == mock_llm_config

    def test_default_llm_config(self):
        agent = PemohonAgent()
        assert agent.llm_config == {}

    def test_word_limits_coverage(self):
        """Semua role harus ada di WORD_LIMITS."""
        expected_roles = {
            "pemohon", "pemerintah", "hakim", "ahli", "pihak_terkait",
            "amicus", "validator", "draft_reviser", "riset_hukum"
        }
        assert set(WORD_LIMITS.keys()) == expected_roles

    def test_pihak_terkait_init(self, mock_llm_config):
        agent = PihakTerkaitAgent(llm_config=mock_llm_config)
        assert agent.role == "pihak_terkait"
        assert agent.max_words == WORD_LIMITS["pihak_terkait"]

    def test_amicus_init(self, mock_llm_config):
        agent = AmicusCuriaeAgent(llm_config=mock_llm_config)
        assert agent.role == "amicus"
        assert agent.max_words == WORD_LIMITS["amicus"]

    def test_ahli_pemohon_init(self, mock_llm_config):
        agent = AhliPemohonAgent(llm_config=mock_llm_config)
        assert agent.role == "ahli"
        assert agent.max_words == WORD_LIMITS["ahli"]

    def test_ahli_pemerintah_init(self, mock_llm_config):
        agent = AhliPemerintahAgent(llm_config=mock_llm_config)
        assert agent.role == "ahli"
        assert "Pemerintah" in agent.name


# ============================================================
# Memory Management Tests
# ============================================================

class TestMemoryManagement:
    """Test sliding window memory management."""

    def test_initial_memory(self, pemohon_agent):
        assert len(pemohon_agent.memory) == 1
        assert pemohon_agent.memory[0]["role"] == "system"

    def test_trim_memory_no_trim_needed(self, pemohon_agent):
        """Belum perlu trim jika belum melebihi max_history."""
        for i in range(5):
            pemohon_agent.memory.append({"role": "user", "content": f"msg {i}"})
            pemohon_agent.memory.append({"role": "assistant", "content": f"reply {i}"})
        pemohon_agent._trim_memory()
        assert len(pemohon_agent.memory) == 11  # 1 system + 10 messages

    def test_trim_memory_when_exceeded(self, pemohon_agent):
        """Memory harus di-trim ketika melebihi max_history."""
        # Tambah banyak pesan untuk melebihi batas
        for i in range(30):
            pemohon_agent.memory.append({"role": "user", "content": f"msg {i}"})
            pemohon_agent.memory.append({"role": "assistant", "content": f"reply {i}"})
        
        pemohon_agent._trim_memory()
        
        # Harus = 1 (system) + max_history
        assert len(pemohon_agent.memory) == pemohon_agent.max_history + 1
        # System prompt harus tetap di awal
        assert pemohon_agent.memory[0]["role"] == "system"

    def test_trim_preserves_recent_messages(self, pemohon_agent):
        """Trim harus mempertahankan pesan terbaru."""
        # Tambah 30 pasang pesan
        for i in range(30):
            pemohon_agent.memory.append({"role": "user", "content": f"msg {i}"})
            pemohon_agent.memory.append({"role": "assistant", "content": f"reply {i}"})
        
        pemohon_agent._trim_memory()
        
        # Pesan terakhir harus tetap ada
        last_user = pemohon_agent.memory[-2]
        last_assistant = pemohon_agent.memory[-1]
        assert last_user["content"] == "msg 29"
        assert last_assistant["content"] == "reply 29"

    def test_memory_stats(self, pemohon_agent):
        stats = pemohon_agent.get_memory_stats()
        assert "total_messages" in stats
        assert "max_history" in stats
        assert "estimated_tokens" in stats
        assert stats["total_messages"] == 1


# ============================================================
# Thinking Filter Tests
# ============================================================

class TestThinkingFilter:
    """Test _strip_thinking_process untuk menyaring internal thinking LLM."""

    def test_strip_xml_think_tags(self, pemohon_agent):
        text = "<think>Ini proses berpikir.</think>\n\nHadirin yang terhormat, argumen saya..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "Hadirin" in result
        assert "proses berpikir" not in result

    def test_strip_thinking_tags(self, pemohon_agent):
        text = "<thinking>Analisis internal</thinking> Majelis yang terhormat..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "Majelis" in result
        assert "Analisis internal" not in result

    def test_strip_closing_tag_only(self, pemohon_agent):
        """Jika hanya ada tag penutup, hapus semua sebelumnya."""
        text = "some internal thought</think>\n\nSaudara Pemohon..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "Saudara" in result

    def test_strip_markdown_think_block(self, pemohon_agent):
        text = "```think\nInternal reasoning\n```\n\nTerima kasih Yang Mulia..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "Terima kasih" in result

    def test_strip_planning_headers(self, pemohon_agent):
        text = "Analyze the Request: We need to...\n\nBerdasarkan fakta hukum..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "Berdasarkan" in result

    def test_strip_step_labels(self, pemohon_agent):
        text = "Step 1: Identify issue\nStep 2: Draft response\n\nYang terhormat Majelis..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "Majelis" in result

    def test_strip_wait_pattern(self, pemohon_agent):
        text = "Wait, let me reconsider this.\n\nHadirin sidang yang terhormat..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "Hadirin" in result

    def test_clean_text_passes_through(self, pemohon_agent):
        text = "Saudara Pemohon, berdasarkan Pasal 28D UUD 1945..."
        result = pemohon_agent._strip_thinking_process(text)
        assert result == text

    def test_empty_text_returns_empty(self, pemohon_agent):
        assert pemohon_agent._strip_thinking_process("") == ""

    def test_excessive_whitespace_cleaned(self, pemohon_agent):
        text = "Saudara Pemohon.\n\n\n\n\nBerdasarkan..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "\n\n\n" not in result

    def test_indonesian_thinking_keywords(self, pemohon_agent):
        text = "Proses Berpikir: Saya akan menganalisis...\n\nDengan hormat, argumen saya..."
        result = pemohon_agent._strip_thinking_process(text)
        assert "Dengan hormat" in result


# ============================================================
# Word Limiter Tests
# ============================================================

class TestWordLimiter:
    """Test batas kata berbasis role tanpa LLM call."""

    def test_pemohon_over_limit_is_silently_capped(self, pemohon_agent):
        text = " ".join([f"kata{i}" for i in range(90)])
        result = pemohon_agent._apply_word_limit(text)

        assert len(result.split()) <= pemohon_agent.max_words
        assert "DIPOTONG" not in result
        assert "Ketua Majelis" not in result

    def test_hakim_over_limit_is_not_interrupted_by_chair(self, hakim_agent):
        text = " ".join([f"kata{i}" for i in range(110)])
        result = hakim_agent._apply_word_limit(text)

        assert len(result.split()) <= hakim_agent.max_words
        assert "DIPOTONG" not in result
        assert "Ketua Majelis" not in result

    def test_pemerintah_over_limit_is_silently_capped(self, pemerintah_agent):
        text = " ".join([f"kata{i}" for i in range(140)])
        result = pemerintah_agent._apply_word_limit(text)

        assert len(result.split()) <= pemerintah_agent.max_words
        assert "DIPOTONG" not in result
        assert "Ketua Majelis" not in result

    def test_hakim_sanitizer_removes_wrong_yang_mulia(self, hakim_agent):
        text = "Baik, Yang Mulia. Saya ingin memperjelas satu hal tentang legal standing."
        result = hakim_agent._sanitize_court_output(text, "Pemohon baru saja menjawab legal standing.")

        assert "Yang Mulia" not in result
        assert result.startswith("Baik, Saudara Pemohon.")

    def test_limiter_repairs_numbered_list_fragment(self, hakim_agent):
        text = (
            "Pertama, pertegas batu uji yang Saudara gunakan dalam permohonan ini. "
            "Kedua, jelaskan hubungan kausal langsung antara norma dan kerugian. 2."
        )
        result = hakim_agent._repair_trailing_fragment(text)

        assert not result.endswith("2.")
        assert result.endswith("kerugian.")

    def test_limiter_repairs_trailing_pasal_fragment(self, pemohon_agent):
        text = "Kerugian itu langsung timbul dari norma dan bertentangan dengan kepastian hukum dalam Pasal."
        result = pemohon_agent._repair_trailing_fragment(text)

        assert not result.endswith("dalam Pasal.")
        assert result.endswith(".")

    def test_sanitizer_removes_internal_labels_and_placeholder(self, pemohon_agent):
        text = "Dalam Ratio Bank Perkara Nomor ... disebutkan SURVIVE BANK: jawaban ini kuat."
        result = pemohon_agent._sanitize_court_output(text)

        assert "Ratio Bank" not in result
        assert "SURVIVE BANK" not in result
        assert "Nomor ..." not in result


# ============================================================
# Streaming Filter Tests
# ============================================================

class TestStreamingFilter:
    """Test _filter_streaming_chunk untuk real-time thinking filter."""

    def test_normal_chunk_passes(self, pemohon_agent):
        chunk = "Saudara Pemohon, "
        assert pemohon_agent._filter_streaming_chunk(chunk) == chunk

    def test_empty_chunk_returns_empty(self, pemohon_agent):
        assert pemohon_agent._filter_streaming_chunk("") == ""

    def test_think_open_tag_captures(self, pemohon_agent):
        """Chunk yang membuka think block harus ditahan."""
        chunk = "<think>internal reasoning"
        result = pemohon_agent._filter_streaming_chunk(chunk)
        assert result == ""
        assert pemohon_agent._stream_in_think_block is True

    def test_think_close_tag_releases(self, pemohon_agent):
        """Tag penutup think harus melepas buffer."""
        # Buka think block
        pemohon_agent._filter_streaming_chunk("<think>reasoning")
        # Tutup think block + konten setelahnya
        result = pemohon_agent._filter_streaming_chunk("</think>Hadirin sidang")
        assert "Hadirin" in result
        assert pemohon_agent._stream_in_think_block is False

    def test_same_chunk_open_close(self, pemohon_agent):
        """Think block yang buka dan tutup di chunk sama."""
        chunk = "<think>quick thought</think>Hadirin"
        result = pemohon_agent._filter_streaming_chunk(chunk)
        assert "Hadirin" in result

    def test_before_and_after_think_in_same_chunk(self, pemohon_agent):
        """Konten sebelum dan sesudah think block di chunk sama."""
        chunk = "Saudara <think>thought</think>Pemohon"
        result = pemohon_agent._filter_streaming_chunk(chunk)
        assert "Saudara" in result
        assert "Pemohon" in result

    def test_overflow_buffer_releases(self, pemohon_agent):
        """Buffer yang terlalu panjang tanpa tag penutup harus di-release."""
        pemohon_agent._stream_in_think_block = True
        pemohon_agent._stream_think_buffer = "x" * 8001
        result = pemohon_agent._filter_streaming_chunk("y" * 100)
        # Harus me-release karena buffer overflow
        assert pemohon_agent._stream_in_think_block is False


# ============================================================
# Validator Agent Tests
# ============================================================

class TestValidatorAgent:
    """Test ValidatorAgent._quick_regex_check (tanpa LLM)."""

    def test_valid_putusan_format(self, validator_agent):
        text = "Putusan Nomor 1/PUU-XII/2014 telah dinyatakan..."
        result = validator_agent._quick_regex_check(text)
        assert result["valid"] is True
        assert result["verdict"] == "LOLOS"
        assert len(result["suspicious_citations"]) == 0

    def test_putusan_before_2003(self, validator_agent):
        text = "Putusan No. 1/PUU-I/2001"
        result = validator_agent._quick_regex_check(text)
        assert result["valid"] is False
        assert result["verdict"] == "PERINGATAN"
        assert any("2001" in s for s in result["suspicious_citations"])

    def test_putusan_future_year(self, validator_agent):
        text = "Putusan No. 5/PUU-XV/2030"
        result = validator_agent._quick_regex_check(text)
        assert result["valid"] is False
        assert any("2030" in s for s in result["suspicious_citations"])

    def test_no_putusan_citation(self, validator_agent):
        text = "Berdasarkan Pasal 28D UUD 1945, hak atas..."
        result = validator_agent._quick_regex_check(text)
        assert result["valid"] is True
        assert result["verdict"] == "LOLOS"

    def test_multiple_putusan_one_invalid(self, validator_agent):
        text = "Putusan No. 1/PUU-XII/2014 dan Putusan No. 99/PUU-X/2035"
        result = validator_agent._quick_regex_check(text)
        assert result["valid"] is False

    def test_multiple_putusan_all_valid(self, validator_agent):
        text = "Putusan No. 1/PUU-XII/2014 dan Putusan No. 5/PUU-XIII/2015"
        result = validator_agent._quick_regex_check(text)
        assert result["valid"] is True

    def test_nomor_format(self, validator_agent):
        """Harus mendukung format 'Nomor' dan 'No.'."""
        for prefix in ["Nomor", "No.", "No"]:
            text = f"Putusan {prefix} 1/PUU-XII/2014"
            result = validator_agent._quick_regex_check(text)
            assert result["valid"] is True


# ============================================================
# LLM Config Re-export Tests
# ============================================================

class TestBackwardCompatibility:
    """Test bahwa import dari core.agents tetap bekerja."""

    def test_import_client_from_agents(self):
        from core.agents import client
        assert client is not None

    def test_import_model_name_from_agents(self):
        from core.agents import MODEL_NAME
        assert isinstance(MODEL_NAME, str)

    def test_import_llm_base_url_from_agents(self):
        from core.agents import LLM_BASE_URL
        assert isinstance(LLM_BASE_URL, str)

    def test_import_word_limits(self):
        from core.agents import WORD_LIMITS
        assert "pemohon" in WORD_LIMITS
        assert "hakim" in WORD_LIMITS

    def test_import_all_agent_classes(self):
        """Semua class agent harus bisa di-import dari core.agents."""
        from core.agents import (
            BaseAgent, PemohonAgent, PemerintahAgent, HakimAgent,
            ValidatorAgent, JudicialReviewDraftAgent,
            PihakTerkaitAgent, AmicusCuriaeAgent,
            AhliPemohonAgent, AhliPemerintahAgent,
        )
        assert BaseAgent is not None
        assert PemohonAgent is not None
