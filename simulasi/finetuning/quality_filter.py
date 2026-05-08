import json
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
