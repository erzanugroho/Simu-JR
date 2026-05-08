"""
hf_train.py — Stable Fine-Tuning Script for Windows + RTX 3090
================================================================
Mendukung:
  - Model kecil (0.5B) untuk tes alur (flow test)
  - Model 9B dengan strategi pemuatan aman (low_cpu_mem_usage + device_map=auto)
  - BF16 standar (tanpa bitsandbytes untuk stabilitas Windows)
  - LoRA via PEFT
  - Dataset via Pandas (stabil di Windows)

Penggunaan:
  $env:PYTHONUTF8=1; python hf_train.py                        # Default: 9B full training
  $env:PYTHONUTF8=1; python hf_train.py --model 0.5b            # Flow test dengan model kecil
  $env:PYTHONUTF8=1; python hf_train.py --max_seq_len 1024      # Override sequence length
  $env:PYTHONUTF8=1; python hf_train.py --max_steps 10          # Quick smoke test
"""

import sys
import os
import gc
import argparse

# ============================================================
#  Force UTF-8 mode on Windows
# ============================================================
# Use `python -X utf8` flag when running this script to avoid
# cp1252 encoding issues with Jinja templates in TRL/transformers.
# Example: python -X utf8 hf_train.py
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

print("--- DEBUG: Starting Import Trace ---")

try:
    print("1. Importing torch...", end="", flush=True)
    import torch
    print(f" OK ({torch.__version__})")

    print("2. Importing transformers...", end="", flush=True)
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
    )
    print(" OK")

    print("3. Importing PEFT...", end="", flush=True)
    from peft import LoraConfig, get_peft_model
    print(" OK")

    print("4. Skipping TRL (Windows segfault workaround)...", end="", flush=True)
    # from trl import SFTTrainer  # Bypassed: trl 1.3.0 segfaults on Windows with torch 2.6.0
    print(" OK (using transformers.Trainer instead)")

    print("5. Importing local modules...", end="", flush=True)
    from format_chatml import to_chatml
    print(" OK")

    print("--- DEBUG: All imports success! ---")

except Exception as e:
    print(f"\n\n!!! CRASH DURING IMPORT: {type(e).__name__}")
    print(f"Error detail: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except BaseException as e:
    print(f"\n\n!!! SYSTEM CRASH: {type(e).__name__}")
    sys.exit(1)


# ============================================================
#  Argument Parsing
# ============================================================
parser = argparse.ArgumentParser(description="Fine-tune Qwen model with LoRA")
parser.add_argument(
    "--model", type=str, default="9b",
    choices=["0.5b", "9b"],
    help="Model size to train (default: 9b)"
)
parser.add_argument("--max_seq_len", type=int, default=None, help="Override max_seq_length")
parser.add_argument("--max_steps", type=int, default=None, help="Override max training steps")
parser.add_argument("--batch_size", type=int, default=None, help="Override per-device batch size")
parser.add_argument("--grad_accum", type=int, default=None, help="Override gradient accumulation steps")
parser.add_argument("--lr", type=float, default=None, help="Override learning rate")
parser.add_argument("--lora_r", type=int, default=None, help="Override LoRA rank")
parser.add_argument("--output_dir", type=str, default=None, help="Override output directory")
parser.add_argument("--dataset", type=str, default=None, help="Override dataset path")
parser.add_argument(
    "--load_mode", type=str, default="auto",
    choices=["auto", "cpu_first", "direct"],
    help=(
        "Model loading strategy: "
        "'auto' = device_map=auto (recommended, lets accelerate split layers), "
        "'cpu_first' = load entirely on CPU then move to GPU, "
        "'direct' = direct to GPU (only for small models)"
    )
)
args = parser.parse_args()


# ============================================================
#  Configuration
# ============================================================
if args.model == "0.5b":
    MODEL_NAME = "Qwen/Qwen2.5-0.5B"
    DEFAULT_MAX_SEQ = 2048
    DEFAULT_BATCH = 4
    DEFAULT_GRAD_ACCUM = 4
    DEFAULT_LR = 2e-4
    DEFAULT_LORA_R = 32
    DEFAULT_STEPS = 60
    DEFAULT_OUTPUT = "./qwen0.5b-flow-test-lora"
    print(f"\n=== MODE: Flow Test ({MODEL_NAME}) ===\n")
else:
    MODEL_NAME = "unsloth/Qwen3.5-9B-Instruct"
    DEFAULT_MAX_SEQ = 2048       # Mulai konservatif; bisa naik ke 4096/8192 nanti
    DEFAULT_BATCH = 1            # batch=1 untuk VRAM safety di 24GB
    DEFAULT_GRAD_ACCUM = 8       # effective batch = 1 * 8 = 8
    DEFAULT_LR = 1e-4
    DEFAULT_LORA_R = 64
    DEFAULT_STEPS = 100          # Sesuaikan dengan jumlah data
    DEFAULT_OUTPUT = "./qwen3.5-9b-juridical-lora"
    print(f"\n=== MODE: Full Training ({MODEL_NAME}) ===\n")

# Apply overrides
MAX_SEQ_LENGTH = args.max_seq_len or DEFAULT_MAX_SEQ
BATCH_SIZE = args.batch_size or DEFAULT_BATCH
GRAD_ACCUM = args.grad_accum or DEFAULT_GRAD_ACCUM
LEARNING_RATE = args.lr or DEFAULT_LR
LORA_RANK = args.lora_r or DEFAULT_LORA_R
MAX_STEPS = args.max_steps or DEFAULT_STEPS
OUTPUT_DIR = args.output_dir or DEFAULT_OUTPUT
DATASET_PATH = args.dataset or "data/train_filtered.jsonl"

print(f"  Model          : {MODEL_NAME}")
print(f"  Max Seq Length : {MAX_SEQ_LENGTH}")
print(f"  Batch Size     : {BATCH_SIZE}")
print(f"  Grad Accum     : {GRAD_ACCUM} (effective batch = {BATCH_SIZE * GRAD_ACCUM})")
print(f"  Learning Rate  : {LEARNING_RATE}")
print(f"  LoRA Rank      : {LORA_RANK}")
print(f"  Max Steps      : {MAX_STEPS}")
print(f"  Output Dir     : {OUTPUT_DIR}")
print(f"  Dataset        : {DATASET_PATH}")
print(f"  Load Mode      : {args.load_mode}")
print()


# ============================================================
#  1. Load Tokenizer
# ============================================================
print(f"Loading tokenizer from {MODEL_NAME}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"
print("  Tokenizer loaded.")


# ============================================================
#  2. Load Model (Stable Windows Strategy)
# ============================================================
def load_model_safe(model_name: str, load_mode: str) -> AutoModelForCausalLM:
    """
    Strategi pemuatan model yang aman untuk Windows + RTX 3090.
    
    Masalah: `device_map="cuda:0"` memaksa semua bobot ke GPU sekaligus,
    yang bisa memicu TDR (Timeout Detection and Recovery) pada model besar.
    
    Solusi:
      - 'auto': device_map="auto" dengan max_memory — biarkan accelerate 
        mendistribusikan layer secara bertahap antara CPU dan GPU.
      - 'cpu_first': Muat seluruhnya di CPU, lalu pindahkan ke GPU.
      - 'direct': Langsung ke GPU (hanya untuk model kecil).
    """
    
    # Hitung VRAM yang tersedia
    if torch.cuda.is_available():
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"  GPU: {torch.cuda.get_device_name(0)} ({vram_gb:.1f} GB)")
        # Sisakan ~3GB untuk CUDA overhead + optimizer states + activations
        max_gpu_gb = max(vram_gb - 3.0, 10.0)
        max_memory = {0: f"{max_gpu_gb:.0f}GB", "cpu": "48GB"}
        print(f"  Max memory plan: GPU={max_memory[0]}, CPU={max_memory['cpu']}")
    else:
        print("  WARNING: No CUDA available, falling back to CPU-only.")
        max_memory = {"cpu": "48GB"}
    
    # Common kwargs
    common_kwargs = dict(
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,   # KUNCI: Muat layer-per-layer, bukan semua sekaligus
    )
    
    if load_mode == "auto":
        # RECOMMENDED: Biarkan accelerate membagi layer otomatis
        print(f"  Loading with device_map='auto' (accelerate-managed)...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map="auto",
            max_memory=max_memory,
            **common_kwargs,
        )
        
    elif load_mode == "cpu_first":
        # Muat di CPU dulu, lalu pindahkan manual
        print(f"  Loading to CPU first...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map="cpu",
            **common_kwargs,
        )
        cpu_mem = sum(p.numel() * p.element_size() for p in model.parameters()) / (1024 ** 3)
        print(f"  Model on CPU: {cpu_mem:.2f} GB")
        
        if torch.cuda.is_available():
            print(f"  Moving model to cuda:0 layer by layer...")
            # Gunakan .to() secara bertahap via device_map manual
            # Tapi lebih aman gunakan accelerate
            from accelerate import dispatch_model, infer_auto_device_map
            device_map = infer_auto_device_map(
                model, 
                max_memory=max_memory,
                no_split_module_classes=model._no_split_modules if hasattr(model, '_no_split_modules') else None,
            )
            model = dispatch_model(model, device_map, main_device=0)
            print(f"  Model dispatched to device map.")
        
    elif load_mode == "direct":
        # Hanya untuk model kecil (< 2GB)
        print(f"  Loading directly to cuda:0 (only safe for small models)...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map="cuda:0",
            **common_kwargs,
        )
    
    return model


print(f"Loading model {MODEL_NAME}...")
print(f"  Strategy: {args.load_mode}")

# Bersihkan cache sebelum loading
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

model = load_model_safe(MODEL_NAME, args.load_mode)

# Info memori setelah loading
if torch.cuda.is_available():
    allocated = torch.cuda.memory_allocated() / (1024 ** 3)
    reserved = torch.cuda.memory_reserved() / (1024 ** 3)
    print(f"  GPU Memory after load: allocated={allocated:.2f}GB, reserved={reserved:.2f}GB")

model.config.use_cache = False  # Disable KV cache saat training (hemat VRAM)
print("  Model loaded successfully!")


# ============================================================
#  3. Setup LoRA
# ============================================================
LORA_ALPHA = LORA_RANK * 2  # Standard: 2x rank
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

print(f"\nSetting up LoRA (r={LORA_RANK}, alpha={LORA_ALPHA})...")
peft_config = LoraConfig(
    lora_alpha=LORA_ALPHA,
    lora_dropout=0.05,
    r=LORA_RANK,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=LORA_TARGET_MODULES,
)
model = get_peft_model(model, peft_config)

# Print trainable params
trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
total_params = sum(p.numel() for p in model.parameters())
print(f"  Trainable params: {trainable_params:,} / {total_params:,} ({100 * trainable_params / total_params:.2f}%)")

# Enable gradient checkpointing untuk hemat VRAM
model.gradient_checkpointing_enable()
print("  Gradient checkpointing enabled.")


# ============================================================
#  4. Load Dataset (Pandas — Windows Stable)
# ============================================================
print(f"\nLoading dataset from {DATASET_PATH} via Pandas...")

try:
    import pandas as pd
    from datasets import Dataset

    # Baca JSONL manual pakai Pandas (stabil di Windows)
    df = pd.read_json(DATASET_PATH, lines=True)
    print(f"  Pandas loaded {len(df)} rows. Columns: {list(df.columns)}")

    # Pastikan kolom yang dibutuhkan ada
    required_cols = {"system", "user", "assistant"}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"  ERROR: Missing columns in dataset: {missing}")
        print(f"  Available columns: {list(df.columns)}")
        sys.exit(1)

    # Konversi ke Hugging Face Dataset
    dataset = Dataset.from_pandas(df)
    print(f"  Dataset converted: {len(dataset)} examples.")

    # Map ke format ChatML lalu tokenize
    def formatting_prompts_func(examples):
        output_texts = []
        for i in range(len(examples['user'])):
            text = to_chatml(
                system=examples['system'][i],
                user=examples['user'][i],
                assistant=examples['assistant'][i]
            )["text"]
            output_texts.append(text)
        return {"text": output_texts}

    dataset = dataset.map(
        formatting_prompts_func,
        batched=True,
        num_proc=1,  # Windows: single process untuk stabilitas
        remove_columns=[c for c in dataset.column_names if c != "text"],
    )
    print(f"  Dataset mapped to ChatML format. Final size: {len(dataset)}")

    # Tokenize dataset (needed when using Trainer instead of SFTTrainer)
    def tokenize_function(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
            padding=False,
        )

    dataset = dataset.map(
        tokenize_function,
        batched=True,
        num_proc=1,
        remove_columns=["text"],
    )
    print(f"  Dataset tokenized. Columns: {list(dataset.column_names)}")

except Exception as e:
    print(f"\n!!! ERROR LOADING DATASET: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


# ============================================================
#  5. Trainer Config
# ============================================================
print(f"\nInitializing Trainer (transformers native, TRL bypassed)...")

# Import Trainer dari transformers (bukan TRL yang crash di Windows)
from transformers import Trainer, DataCollatorForLanguageModeling

# Deteksi BF16 support
bf16_supported = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
use_fp16 = not bf16_supported and torch.cuda.is_available()
use_bf16 = bf16_supported

print(f"  BF16 supported: {bf16_supported}")
print(f"  Using fp16={use_fp16}, bf16={use_bf16}")

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    warmup_steps=10,
    max_steps=MAX_STEPS,
    learning_rate=LEARNING_RATE,
    fp16=use_fp16,
    bf16=use_bf16,
    logging_steps=1,
    optim="adamw_torch",        # Stabil di Windows (bukan paged_adamw_8bit)
    weight_decay=0.01,
    lr_scheduler_type="cosine",
    seed=3407,
    report_to="none",
    gradient_checkpointing=True,  # Hemat VRAM
    gradient_checkpointing_kwargs={"use_reentrant": False},  # Kompatibel dengan PEFT
    max_grad_norm=1.0,
    save_strategy="steps",
    save_steps=50,
    save_total_limit=2,
    dataloader_pin_memory=False,  # Windows: hindari pin_memory issues
    remove_unused_columns=False,  # False karena kita sudah tokenized
)

# Data collator untuk Causal LM (padding batch & buat labels)
data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False,  # Causal LM, bukan Masked LM
)

try:
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=data_collator,
        tokenizer=tokenizer,
    )
    print("  Trainer initialized successfully!")

    # ============================================================
    #  6. Training
    # ============================================================
    print("\n" + "=" * 60)
    print(f"  STARTING TRAINING: {MAX_STEPS} steps")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Effective batch: {BATCH_SIZE} x {GRAD_ACCUM} = {BATCH_SIZE * GRAD_ACCUM}")
    print("=" * 60 + "\n")

    trainer.train()

    # ============================================================
    #  7. Save
    # ============================================================
    final_path = os.path.join(OUTPUT_DIR, "final_lora")
    trainer.model.save_pretrained(final_path)
    tokenizer.save_pretrained(final_path)
    print(f"\nTraining finished! LoRA adapter saved to: {final_path}")

    # Final memory report
    if torch.cuda.is_available():
        peak = torch.cuda.max_memory_allocated() / (1024 ** 3)
        print(f"Peak GPU memory usage: {peak:.2f} GB")

except Exception as e:
    print(f"\n{'=' * 60}")
    print(f"CRITICAL ERROR DURING TRAINING:")
    print(f"  {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    print(f"{'=' * 60}")
    
    # Cleanup
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    sys.exit(1)