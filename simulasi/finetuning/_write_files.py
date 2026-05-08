"""Helper script to write remaining finetuning files."""
from pathlib import Path
import sys

DIR = Path(__file__).parent

# === train.py ===
(DIR / "train.py").write_text(r'''import os
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
        save_steps=500,
        save_total_limit=3,
        eval_strategy="steps",
        eval_steps=500,
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
''', encoding='utf-8')
print(f"train.py: {(DIR / 'train.py').stat().st_size:,} bytes")

# === quality_filter.py ===
(DIR / "quality_filter.py").write_text(r'''import json
import re
from pathlib import Path
from typing import List, Dict, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from finetuning.config import MIN_WORDS, MAX_WORDS, ensure_dirs


def clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\u2060|\u200b|\u200c|\u200d|\ufeff", "", text)
    text = re.sub(r"[\ufffd]", "", text)
    text = re.sub(r" {3,}", "  ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def is_valid_sample(sample: Dict) -> Tuple[bool, str]:
    text = sample.get("text", "")
    if not text:
        return False, "empty"
    wc = len(text.split())
    if wc < MIN_WORDS:
        return False, f"too_short ({wc})"
    if wc > MAX_WORDS * 2:
        return False, f"too_long ({wc})"
    if "im_end" not in text:
        return False, "no_assistant"
    if text.count("im_start") < 2:
        return False, "incomplete"
    return True, "ok"


def deduplicate(samples: List[Dict]) -> Tuple[List[Dict], int]:
    seen = set()
    unique = []
    dupes = 0
    for s in samples:
        words = set(s.get("text", "").lower().split())
        if len(words) < 10:
            unique.append(s)
            continue
        fp = " ".join(sorted(words)[:50])
        h = hash(fp)
        if h in seen:
            dupes += 1
            continue
        seen.add(h)
        unique.append(s)
    return unique, dupes


def filter_dataset(input_path: Path, output_path: Path) -> Dict:
    print(f"Loading from {input_path}...")
    samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            samples.append(json.loads(line))
    print(f"  Loaded {len(samples):,} samples")

    stats = {"total": len(samples), "valid": 0, "filtered": 0, "reasons": {}, "dupes": 0}
    cleaned = []
    for s in samples:
        if "text" in s:
            s["text"] = clean_text(s["text"])
        ok, reason = is_valid_sample(s)
        if ok:
            cleaned.append(s)
            stats["valid"] += 1
        else:
            stats["filtered"] += 1
            stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1

    print(f"  Valid: {stats['valid']:,}, Filtered: {stats['filtered']:,}")
    for reason, count in sorted(stats["reasons"].items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count:,}")

    deduped, dupes = deduplicate(cleaned)
    stats["dupes"] = dupes
    print(f"  After dedup: {len(deduped):,} unique ({dupes} dupes removed)")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for s in deduped:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"  Saved to {output_path}")
    return stats


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Quality filter for training data")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    filter_dataset(args.input, args.output)
''', encoding='utf-8')
print(f"quality_filter.py: {(DIR / 'quality_filter.py').stat().st_size:,} bytes")

# === merge_and_export.py ===
(DIR / "merge_and_export.py").write_text(r'''import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from finetuning.config import (
    BASE_MODEL, OUTPUT_DIR, GGUF_QUANTIZATION, MAX_SEQ_LENGTH, ensure_dirs,
)


def main(args):
    ensure_dirs()
    model_name = args.model or BASE_MODEL
    lora_path = Path(args.lora) if args.lora else OUTPUT_DIR / "qwen-mk-simulasi" / "lora_adapter"
    output_dir = Path(args.output) if args.output else OUTPUT_DIR / "merged"
    quant = args.quantization or GGUF_QUANTIZATION

    if not lora_path.exists():
        print(f"ERROR: LoRA not found at {lora_path}")
        sys.exit(1)

    print("Merge LoRA + Export to GGUF")
    print(f"  Model: {model_name}")
    print(f"  LoRA: {lora_path}")
    print(f"  Output: {output_dir}")

    from unsloth import FastLanguageModel

    print("Step 1: Loading model + LoRA...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(lora_path),
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=False,
        dtype=None,
    )

    print("Step 2: Merging LoRA...")
    model = model.merge_and_unload()

    merged_path = output_dir / "merged-safetensors"
    print(f"Step 3: Saving to {merged_path}...")
    model.save_pretrained(str(merged_path), safe_serialization=True)
    tokenizer.save_pretrained(str(merged_path))

    if not args.skip_gguf:
        print(f"Step 4: Exporting GGUF ({quant})...")
        model.save_pretrained_gguf(
            str(output_dir),
            tokenizer,
            quantization_method=quant,
        )
        print("GGUF exported!")
        print("Next: Load GGUF in LM Studio, update .env LLM_MODEL_NAME")
    else:
        print(f"Merged model at: {merged_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Merge LoRA and export to GGUF")
    p.add_argument("--model", type=str, default=None)
    p.add_argument("--lora", type=str, default=None)
    p.add_argument("--output", type=str, default=None)
    p.add_argument("--quantization", type=str, default=None)
    p.add_argument("--skip-gguf", action="store_true")
    main(p.parse_args())
''', encoding='utf-8')
print(f"merge_and_export.py: {(DIR / 'merge_and_export.py').stat().st_size:,} bytes")

# === format_chatml.py (rewrite - was truncated) ===
IM_START = chr(60) + "|im_start|" + chr(62)
IM_END = chr(60) + "|im_end|" + chr(62)

(DIR / "format_chatml.py").write_text(f'''import json
import random
from pathlib import Path
from typing import List, Dict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from finetuning.config import (
    DATA_DIR, TRAIN_PATH, VAL_PATH, TEST_PATH,
    EVAL_SPLIT, TEST_SPLIT, RANDOM_SEED, ensure_dirs,
)

SYSTEM_PROMPTS = dict(
    hakim="Anda adalah Hakim Konstitusi pada Mahkamah Konstitusi Republik Indonesia. "
          "Tugas Anda menggali kebenaran materiil melalui pertanyaan kritis. "
          "Gaya: tajam, kritis, langsung ke inti, Socratic questioning. Jangan berpihak.",
    pemohon="Anda adalah Kuasa Hukum Pemohon dalam sidang PUU di Mahkamah Konstitusi RI. "
            "Tugas: membuktikan norma yang diuji bertentangan dengan UUD 1945.",
    pemerintah="Anda adalah Kuasa Hukum Presiden/DPR (Pemerintah) dalam sidang PUU "
               "di Mahkamah Konstitusi RI. Tugas: mempertahankan konstitusionalitas UU yang diuji.",
    pihak_terkait="Anda adalah Kuasa Hukum Pihak Terkait dalam sidang PUU di Mahkamah Konstitusi RI. "
                  "Memberikan perspektif unik dari sudut kepentingan pihak ketiga.",
    amicus="Anda adalah Amicus Curiae (Sahabat Pengadilan) dalam sidang PUU "
           "di Mahkamah Konstitusi RI. Memberikan analisis hukum komparatif dan perspektif akademis netral.",
    ahli="Anda adalah Ahli Hukum Konstitusi dalam sidang PUU di Mahkamah Konstitusi RI. "
         "Memberikan keterangan ahli yang mendukung argumen pihak yang menghadirkan Anda.",
)


def to_chatml(system: str, user: str, assistant: str) -> dict:
    text = (
        f"{{IM_START}}system\\n{{system}}{{IM_END}}\\n"
        f"{{IM_START}}user\\n{{user}}{{IM_END}}\\n"
        f"{{IM_START}}assistant\\n{{assistant}}{{IM_END}}"
    )
    return {{"text": text}}


def load_jsonl(path: Path) -> List[Dict]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            items.append(json.loads(line))
    return items


def convert_risalah(pairs: List[Dict]) -> List[Dict]:
    converted = []
    for p in pairs:
        persona = p["persona"]
        system_msg = SYSTEM_PROMPTS.get(persona, SYSTEM_PROMPTS["pemohon"])
        conv = to_chatml(system_msg, p["user"], p["assistant"])
        conv["source"] = "risalah"
        conv["persona"] = persona
        converted.append(conv)
    return converted


def build_and_split(all_samples: List[Dict]) -> None:
    random.seed(RANDOM_SEED)
    random.shuffle(all_samples)
    n = len(all_samples)
    n_test = int(n * TEST_SPLIT)
    n_val = int(n * EVAL_SPLIT)
    test_set = all_samples[:n_test]
    val_set = all_samples[n_test:n_test + n_val]
    train_set = all_samples[n_test + n_val:]
    for path, data in [(TRAIN_PATH, train_set), (VAL_PATH, val_set), (TEST_PATH, test_set)]:
        with open(path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\\n")
        print(f"  Saved {{len(data):,}} samples to {{path}}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--risalah-pairs", type=Path, default=DATA_DIR / "risalah_pairs.jsonl")
    args = parser.parse_args()
    ensure_dirs()
    all_samples = []
    if args.risalah_pairs.exists():
        print(f"Loading risalah pairs from {{args.risalah_pairs}}...")
        pairs = load_jsonl(args.risalah_pairs)
        converted = convert_risalah(pairs)
        all_samples.extend(converted)
        print(f"  Converted {{len(converted):,}} risalah pairs")
    else:
        print(f"WARNING: {{args.risalah_pairs}} not found, skipping.")
    if not all_samples:
        print("No data to process. Run extract_risalah_dialogs.py first.")
        sys.exit(1)
    print(f"\\nTotal samples: {{len(all_samples):,}}")
    print("\\nSplitting into train/val/test...")
    build_and_split(all_samples)
    print("\\nDone! Dataset ready for training.")
''', encoding='utf-8')
print(f"format_chatml.py: {(DIR / 'format_chatml.py').stat().st_size:,} bytes")

# Verify all files
print("\n=== All files in finetuning/ ===")
for f in sorted(DIR.glob("*.py")):
    print(f"  {f.name}: {f.stat().st_size:,} bytes")