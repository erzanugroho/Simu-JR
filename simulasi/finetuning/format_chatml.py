import json
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


IM_START = chr(60) + "|im_start|" + chr(62)
IM_END = chr(60) + "|im_end|" + chr(62)


def to_chatml(system: str, user: str, assistant: str) -> dict:
    text = (
        f"{IM_START}system\n{system}{IM_END}\n"
        f"{IM_START}user\n{user}{IM_END}\n"
        f"{IM_START}assistant\n{assistant}{IM_END}"
    )
    return {
        "text": text,
        "system": system,
        "user": user,
        "assistant": assistant
    }


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
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  Saved {len(data):,} samples to {path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--risalah-pairs", type=Path, default=DATA_DIR / "risalah_pairs.jsonl")
    args = parser.parse_args()
    ensure_dirs()
    all_samples = []
    if args.risalah_pairs.exists():
        print(f"Loading risalah pairs from {args.risalah_pairs}...")
        pairs = load_jsonl(args.risalah_pairs)
        converted = convert_risalah(pairs)
        all_samples.extend(converted)
        print(f"  Converted {len(converted):,} risalah pairs")
    else:
        print(f"WARNING: {args.risalah_pairs} not found, skipping.")
    if not all_samples:
        print("No data to process. Run extract_risalah_dialogs.py first.")
        sys.exit(1)
    print(f"\nTotal samples: {len(all_samples):,}")
    print("\nSplitting into train/val/test...")
    build_and_split(all_samples)
    print("\nDone! Dataset ready for training.")
