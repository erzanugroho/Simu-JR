# Fine-Tuning Qwen 3.5 9B untuk Sidang MK
# ==========================================
# Script ini bisa dijalankan di Unsloth Studio (localhost:8888)
# atau di Google Colab Pro.
#
# Dataset sudah disiapkan di simulasi/finetuning/data/
# - train_filtered.jsonl (589 samples)
# - val_filtered.jsonl (110 samples)
#
# Format: ChatML {"text": "...im_start|system\n...im_end|...im_start|assistant\n...im_end|..."}

from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

# === CONFIG ===
MODEL_NAME = "unsloth/Qwen2.5-7B-Instruct"   # Target model
LORA_RANK = 64
LORA_ALPHA = 128
LORA_DROPOUT = 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
MAX_SEQ_LENGTH = 8192
BATCH_SIZE = 2
GRAD_ACCUM = 16   # Effective batch = 32
EPOCHS = 2
LR = 1e-4

# === STEP 1: LOAD MODEL ===
print("Loading model:", MODEL_NAME)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=True,       # QLoRA 4-bit
    dtype=None,
)

# === STEP 2: APPLY LORA ===
print("Applying LoRA adapters...")
model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=TARGET_MODULES,
    lora_alpha=LORA_ALPHA,
    lora_dropout=LORA_DROPOUT,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

# === STEP 3: LOAD DATASET ===
print("Loading dataset...")
dataset = load_dataset("json", data_files={
    "train": "data/train_filtered.jsonl",
    "validation": "data/val_filtered.jsonl",
})
print(f"Train: {len(dataset['train']):,} samples")
print(f"Val: {len(dataset['validation']):,} samples")

# === STEP 4: TRAINING ===
print("Starting training...")
training_args = TrainingArguments(
    output_dir="qwen-mk-simulasi",
    num_train_epochs=EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    learning_rate=LR,
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    weight_decay=0.01,
    max_grad_norm=1.0,
    fp16=False,
    bf16=True,
    logging_steps=10,
    save_strategy="steps",
    save_steps=200,
    save_total_limit=3,
    eval_strategy="steps",
    eval_steps=200,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    report_to="none",
    seed=42,
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    args=training_args,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    packing=True,
)

stats = trainer.train()
print(f"\nTraining complete! Steps: {stats.global_step}, Loss: {stats.training_loss:.4f}")

# === STEP 5: SAVE ===
model.save_pretrained("qwen-mk-simulasi-lora")
tokenizer.save_pretrained("qwen-mk-simulasi-lora")
print("LoRA adapter saved!")

# === STEP 6: EXPORT GGUF (for LM Studio) ===
print("Exporting to GGUF...")
model.save_pretrained_gguf(
    "qwen-mk-simulasi-gguf",
    tokenizer,
    quantization_method="q4_k_m",
)
print("GGUF exported! Load di LM Studio.")