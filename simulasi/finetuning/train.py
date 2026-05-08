import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from finetuning.config import (
    BASE_MODEL, FALLBACK_MODEL,
    LORA_RANK, LORA_ALPHA, LORA_DROPOUT, LORA_TARGET_MODULES,
    MAX_SEQ_LENGTH, LEARNING_RATE, WARMUP_RATIO,
    BATCH_SIZE, GRADIENT_ACCUMULATION, NUM_EPOCHS,
    WEIGHT_DECAY, MAX_GRAD_NORM,
    LOAD_IN_4BIT, TRAIN_PATH, VAL_PATH, OUTPUT_DIR, LOGS_DIR, ensure_dirs,
)


def main(args):
    ensure_dirs()
    model_name = args.model or BASE_MODEL
    train_path = Path(args.train_data) if args.train_data else TRAIN_PATH
    val_path = Path(args.val_data) if args.val_data else VAL_PATH
    output_dir = Path(args.output) if args.output else OUTPUT_DIR / "qwen-mk-simulasi"
    lora_rank = args.lora_rank or LORA_RANK
    batch_size = args.batch_size or BATCH_SIZE
    epochs = args.epochs or NUM_EPOCHS
    lr = args.lr or LEARNING_RATE

    print("=" * 60)
    print("Fine-Tuning Qwen for Sidang MK")
    print("=" * 60)
    print(f"  Model: {model_name}")
    print(f"  Train: {train_path}")
    print(f"  Val: {val_path}")
    print(f"  Output: {output_dir}")
    print(f"  LoRA Rank: {lora_rank}")
    print(f"  Batch: {batch_size} x {GRADIENT_ACCUMULATION} = {batch_size * GRADIENT_ACCUMULATION}")
    print(f"  Epochs: {epochs}, LR: {lr}")
    print(f"  Max Seq: {MAX_SEQ_LENGTH}")
    print()

    from unsloth import FastLanguageModel

    print("Loading model...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=LOAD_IN_4BIT,
        dtype=None,
        token=args.hf_token,
    )

    print("Applying LoRA...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_rank,
        target_modules=LORA_TARGET_MODULES,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    print("Loading data...")
    from datasets import load_dataset
    dataset = load_dataset("json", data_files={
        "train": str(train_path),
        "validation": str(val_path),
    })
    print(f"  Train: {len(dataset['train']):,}, Val: {len(dataset['validation']):,}")

    from trl import SFTTrainer
    from transformers import TrainingArguments

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION,
        learning_rate=lr,
        lr_scheduler_type="cosine",
        warmup_ratio=WARMUP_RATIO,
        weight_decay=WEIGHT_DECAY,
        max_grad_norm=MAX_GRAD_NORM,
        fp16=False,
        bf16=True,
        logging_dir=str(LOGS_DIR),
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
        dataloader_num_workers=0,
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

    lora_path = output_dir / "lora_adapter"
    print(f"Saving LoRA to {lora_path}...")
    model.save_pretrained(str(lora_path))
    tokenizer.save_pretrained(str(lora_path))
    print("Done! Next: run merge_and_export.py")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Fine-tune Qwen for Sidang MK")
    p.add_argument("--model", type=str, default=None)
    p.add_argument("--train-data", type=str, default=None)
    p.add_argument("--val-data", type=str, default=None)
    p.add_argument("--output", type=str, default=None)
    p.add_argument("--lora-rank", type=int, default=None)
    p.add_argument("--batch-size", type=int, default=None)
    p.add_argument("--epochs", type=int, default=None)
    p.add_argument("--lr", type=float, default=None)
    p.add_argument("--hf-token", type=str, default=None)
    main(p.parse_args())
