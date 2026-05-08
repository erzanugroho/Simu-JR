"""
Test Fixtures - Simulasi Sidang MK
====================================
Shared pytest fixtures for unit testing agents, orchestrator, and utilities.
"""

import pytest
import sys
import os

# Add simulasi directory to path so imports work from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.agents import (
    BaseAgent, PemohonAgent, PemerintahAgent, HakimAgent,
    ValidatorAgent, JudicialReviewDraftAgent,
    WORD_LIMITS, DEFAULT_MAX_HISTORY,
)
from core.system_prompts import (
    SYSTEM_PROMPT_PEMOHON, SYSTEM_PROMPT_PEMERINTAH, SYSTEM_PROMPT_HAKIM,
    SYSTEM_PROMPT_VALIDATOR,
)
from core.llm_client import MODEL_NAME


# === Mock LLM Config ===
@pytest.fixture
def mock_llm_config():
    """LLM config yang tidak memanggil API manapun."""
    return {
        "provider": "local",
        "api_key": "test-key",
        "base_url": "http://127.0.0.1:9999/v1",  # Port yang tidak ada
        "model_name": "test-model",
    }


# === Agent Fixtures ===
@pytest.fixture
def pemohon_agent(mock_llm_config):
    return PemohonAgent(llm_config=mock_llm_config)


@pytest.fixture
def pemerintah_agent(mock_llm_config):
    return PemerintahAgent(llm_config=mock_llm_config)


@pytest.fixture
def hakim_agent(mock_llm_config):
    return HakimAgent(hakim_id=1, llm_config=mock_llm_config)


@pytest.fixture
def validator_agent(mock_llm_config):
    return ValidatorAgent(llm_config=mock_llm_config)


@pytest.fixture
def draft_agent(mock_llm_config):
    return JudicialReviewDraftAgent(llm_config=mock_llm_config)