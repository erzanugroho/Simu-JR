import sys
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
