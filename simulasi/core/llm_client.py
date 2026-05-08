"""
LLM Client Configuration - Simulasi Sidang MK
==============================================
Konfigurasi dan inisialisasi LLM client (OpenAI-compatible, OpenRouter, Claude).
Dipisahkan dari agents.py untuk memudahkan maintenance dan testing.
"""

import logging
import os
from typing import Any, Dict, Optional
import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger(__name__)

# === Konfigurasi LLM ===
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed-for-local")
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "local-model")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))  # Explicit max_tokens for KV cache optimization
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"
OPENROUTER_PROVIDER_ROUTES = {
    "openai/gpt-oss-120b": {
        "order": ["groq"],
        "only": ["groq"],
        "allow_fallbacks": False,
    },
    "moonshotai/kimi-k2.6": {
        "order": ["moonshotai"],
        "only": ["moonshotai"],
        "allow_fallbacks": False,
    },
}

# === Xiaomi MiMo API ===
MIMO_BASE_URL = "https://token-plan-sgp.xiaomimimo.com/v1"
MIMO_DEFAULT_MODEL = "mimo-v2.5-pro"
MIMO_MODELS = [
    {"id": "mimo-v2.5-pro", "name": "MiMo V2.5 Pro (Flagship)", "context_length": 1000000, "max_output": 131072, "prompt_per_million": None, "completion_per_million": None, "note": "Flagship text model, 1M context, deep thinking"},
    {"id": "mimo-v2-pro", "name": "MiMo V2 Pro (Flagship)", "context_length": 1000000, "max_output": 131072, "prompt_per_million": None, "completion_per_million": None, "note": "Flagship text model, 1M context"},
    {"id": "mimo-v2.5", "name": "MiMo V2.5 (Multimodal)", "context_length": 1000000, "max_output": 131072, "prompt_per_million": None, "completion_per_million": None, "note": "Text + multimodal understanding, 1M context"},
    {"id": "mimo-v2-omni", "name": "MiMo V2 Omni (Multimodal)", "context_length": 262144, "max_output": 131072, "prompt_per_million": None, "completion_per_million": None, "note": "Text + multimodal, 256K context"},
    {"id": "mimo-v2-flash", "name": "MiMo V2 Flash (Fast & Cheap)", "context_length": 262144, "max_output": 65536, "prompt_per_million": None, "completion_per_million": None, "note": "Fast/cheap, 256K context"},
]

# === DeepSeek API ===
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
DEEPSEEK_MODELS = [
    {
        "id": "deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "context_length": 1000000,
        "max_output": 384000,
        "prompt_cache_hit_per_million": 0.0028,
        "prompt_cache_miss_per_million": 0.14,
        "completion_per_million": 0.28,
        "note": "Fast/cheap, context caching enabled by default",
    },
    {
        "id": "deepseek-v4-pro",
        "name": "DeepSeek V4 Pro",
        "context_length": 1000000,
        "max_output": 384000,
        "prompt_cache_hit_per_million": 0.003625,
        "prompt_cache_miss_per_million": 0.435,
        "completion_per_million": 0.87,
        "note": "Pro model, discounted pricing listed by DeepSeek until 2026-05-31 15:59 UTC",
    },
]
DEEPSEEK_PRICING = {
    model["id"]: {
        "cache_hit": model["prompt_cache_hit_per_million"],
        "cache_miss": model["prompt_cache_miss_per_million"],
        "completion": model["completion_per_million"],
    }
    for model in DEEPSEEK_MODELS
}

# Default LLM client (singleton untuk local provider)
client = AsyncOpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    timeout=httpx.Timeout(600.0),
)


def _clone_openrouter_route(route: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in route.items()
    }


def _openrouter_provider_route(model_name: str) -> Optional[Dict[str, Any]]:
    route = OPENROUTER_PROVIDER_ROUTES.get(model_name)
    return _clone_openrouter_route(route) if route else None
