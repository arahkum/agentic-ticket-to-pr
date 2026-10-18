"""Step 5 regression gate: rule-checks only (no LLM judge - fast & deterministic
enough for CI), run against the current default prompt + model. Exits non-zero
(red build) if the average rule score drops below THRESHOLD.

Used both locally (to prove a worse prompt fails this) and in
.github/workflows/eval-gate.yml (runs on every PR).
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.spec_generator import PROMPT_PATH, SpecGenerationError, generate_spec
from evals.rules import score_rules

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "evals" / "dataset" / "eval_tickets.json"
THRESHOLD = 0.9
# small, fast subset for CI - full dataset is used by evals/run_evals.py locally
CI_TICKET_IDS = {"E02", "E05", "E11", "E14", "E16"}


def main() -> int:
    prompt_path = Path(os.environ.get("EVAL_PROMPT_PATH", str(PROMPT_PATH)))
    model = os.environ.get("EVAL_MODEL", "gpt-oss:20b")

    tickets = json.loads(DATASET_PATH.read_text())
    tickets = [t for t in tickets if t["id"] in CI_TICKET_IDS]

    scores = []
    for ticket in tickets:
        spec = None
        raw = ""
        try:
            spec = generate_spec(ticket["text"], model=model, prompt_path=prompt_path)
        except SpecGenerationError as exc:
            raw = exc.raw
            print(f"[FAIL] {ticket['id']}: {exc}")

        result = score_rules(spec, raw, ticket["category"])
        scores.append(result["rule_score"])
        print(f"[{'OK' if spec else 'FAIL'}] {ticket['id']} rule_score={result['rule_score']:.2f} "
              f"checks={result['checks']}")

    avg = statistics.mean(scores)
    print(f"\nAverage rule score: {avg:.3f} (threshold: {THRESHOLD})")
    print(f"Prompt: {prompt_path.name}")

    if avg < THRESHOLD:
        print(f"REGRESSION GATE FAILED: {avg:.3f} < {THRESHOLD}")
        return 1
    print("Regression gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
