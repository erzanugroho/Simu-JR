"""
Konfigurasi Fine-Tuning Qwen 3.5 9B — Model Inferensi Sidang MK
================================================================
Hyperparameters dan path configuration untuk training pipeline.
"""

import os
from pathlib import Path

# === Paths ===
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"

# Source data
RAG_CHUNKS_PATH = BASE_DIR.parent / "rag" / "rag_chunks.jsonl"
UUD_PATH = BASE_DIR.parent / "rag" / "uud_1945.json"
SYSTEM_PROMPTS_PATH = BASE_DIR.parent / "core" / "system_prompts.py"

# Output datasets
TRAIN_PATH = DATA_DIR / "train.jsonl"
VAL_PATH = DATA_DIR / "val.jsonl"
TEST_PATH = DATA_DIR / "test.jsonl"

# === Model Configuration ===
BASE_MODEL = "unsloth/Qwen3.5-9B-Instruct"  # Qwen 3.5 9B target model
FALLBACK_MODEL = "unsloth/Qwen3-8B-Instruct-2507"  # Fallback Qwen 3 8B

# === LoRA Configuration (RTX 3090 24GB) ===
LORA_RANK = 64            # Higher rank = more capacity, lebih banyak VRAM
LORA_ALPHA = 128          # Usually 2x LoRA rank
LORA_DROPOUT = 0.05       # Regularization
LORA_TARGET_MODULES = [   # Target semua projection layers
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

# === Training Hyperparameters ===
MAX_SEQ_LENGTH = 8192     # Risalah bisa sangat panjang (per-sesi sidang)
LEARNING_RATE = 1e-4      # Standard untuk LoRA
LR_SCHEDULER = "cosine"   # Cosine decay
WARMUP_RATIO = 0.1        # 10% warmup
BATCH_SIZE = 2            # Per-device batch size (24GB VRAM, 4-bit)
GRADIENT_ACCUMULATION = 16 # Effective batch = 2 * 16 = 32
NUM_EPOCHS = 2            # 2-3 epochs, hindari overfitting
WEIGHT_DECAY = 0.01
MAX_GRAD_NORM = 1.0

# === Quantization ===
LOAD_IN_4BIT = True       # QLoRA 4-bit (hemat VRAM)
BNB_4BIT_COMPUTE_DTYPE = "bfloat16"
BNB_4BIT_QUANT_TYPE = "nf4"  # Normalized Float 4

# === Dataset Ratios ===
# Distribusi dataset dalam training mix
DATASET_WEIGHTS = {
    "hearing_dialogue": 0.50,   # Dataset A: paling penting
    "role_argument": 0.25,      # Dataset B: argumen per-peran
    "legal_draft": 0.10,        # Dataset C: draft permohonan
    "legal_qa": 0.15,           # Dataset D: Q&A hukum
}

# === Quality Filtering ===
MIN_WORDS = 30            # Minimum kata per sample
MAX_WORDS = 4000          # Maximum kata per sample (sesuai max_seq_length)
DUPLICATE_THRESHOLD = 0.9 # Jaccard similarity threshold untuk dedup

# === Evaluation ===
EVAL_SPLIT = 0.10         # 10% untuk validation
TEST_SPLIT = 0.05         # 5% untuk test
RANDOM_SEED = 42

# === Export ===
GGUF_QUANTIZATION = "q4_k_m"  # Quantization untuk LM Studio


def ensure_dirs():
    """Buat semua direktori yang diperlukan."""
    for d in [DATA_DIR, OUTPUT_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)