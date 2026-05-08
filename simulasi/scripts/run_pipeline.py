"""
Entry Point CLI - Litigation Intelligence Pipeline
==================================================
Menjalankan pipeline 7 agent untuk membangun intelligence bank.

Urutan:
  1. Agent 1 (Classifier) - dijalankan saat extract_and_chunk.py
  2. Agent 5 (Survive Bank) - dampak paling langsung
  3. Agent 4 (Judge Concern Bank)
  4. Agent 3 (Attack Bank)
  5. Agent 2 (Ratio Bank)

Penggunaan:
  python run_pipeline.py --stage survive      # Jalankan survive pipeline saja
  python run_pipeline.py --stage all          # Jalankan semua pipeline
  python run_pipeline.py --priority-only      # Hanya dokumen flag_priority
"""

import argparse
import logging
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.survive_pipeline import run_survive_pipeline
from rag.judge_concern_pipeline import run_judge_concern_pipeline
from rag.attack_bank_pipeline import run_attack_bank_pipeline
from rag.ratio_pipeline import run_ratio_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Litigation Intelligence Pipeline")
    parser.add_argument("--stage", choices=["survive", "concern", "attack", "ratio", "all"],
                        default="all", help="Pipeline stage yang akan dijalankan")
    parser.add_argument("--jsonl", default=None, help="Path ke rag_chunks.jsonl")
    parser.add_argument("--priority-only", action="store_true",
                        help="Hanya proses dokumen dengan flag_priority = true")
    parser.add_argument("--workers", type=int, default=1,
                        help="Jumlah parallel workers untuk LLM calls")
    parser.add_argument("--debug", action="store_true", help="Aktifkan log DEBUG")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("rag").setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled.")

    logger.info("=" * 60)
    logger.info("  LITIGATION INTELLIGENCE PIPELINE")
    logger.info("  Simulasi Sidang MK")
    logger.info("=" * 60)

    stages = []
    if args.stage == "all":
        stages = ["survive", "concern", "attack", "ratio"]
    else:
        stages = [args.stage]

    for stage in stages:
        logger.info(f"\n{'-' * 50}")
        logger.info(f"  STAGE: {stage.upper()}")
        logger.info(f"{'-' * 50}")

        if stage == "survive":
            run_survive_pipeline(args.jsonl, priority_only=args.priority_only, workers=args.workers)
        elif stage == "concern":
            run_judge_concern_pipeline(args.jsonl, priority_only=args.priority_only, workers=args.workers)
        elif stage == "attack":
            run_attack_bank_pipeline(args.jsonl, priority_only=args.priority_only, workers=args.workers)
        elif stage == "ratio":
            run_ratio_pipeline(args.jsonl, priority_only=args.priority_only, workers=args.workers)

    logger.info("\n" + "=" * 60)
    logger.info("  PIPELINE SELESAI")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
