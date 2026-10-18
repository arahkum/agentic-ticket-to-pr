"""Step 8 exercise: route generation to a strong model, validation (judging)
to a cheap one, and record quality/cost/time before vs after routing.

"Before": one model (gpt-oss:20b) does both generation AND judging.
"After":  generation stays on gpt-oss:20b; judging moves to llama3.2:3b.

Since the spec itself is produced identically in both runs (same generator
model, same prompt, same tickets), spec quality is unaffected by routing -
what changes is total wall time (and, with a paid API, cost) spent on the
judging step.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from evals.judge import JudgeError, judge_spec
from pipeline.model_router import model_for
from pipeline.spec_generator import SpecGenerationError, generate_spec, get_client

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "evals" / "dataset" / "eval_tickets.json"
TICKET_IDS = {"E01", "E03", "E05", "E11"}

GENERATE_MODEL = model_for("generate")  # gpt-oss:20b, strong
VALIDATE_MODEL = model_for("validate")  # llama3.2:3b, cheap/fast


def run(judge_model: str, label: str, tickets: list[dict]) -> dict:
    print(f"=== {label}: generate={GENERATE_MODEL}, judge={judge_model} ===")
    judge_times = []
    judge_scores = []

    for ticket in tickets:
        spec = generate_spec(ticket["text"], model=GENERATE_MODEL, ticket_id=f"{ticket['id']}-{label}")

        start = time.perf_counter()
        try:
            score = judge_spec(ticket["text"], spec.model_dump(), judge_model=judge_model)
            judge_scores.append(score.average)
        except JudgeError as exc:
            print(f"  [judge error] {ticket['id']}: {exc}")
        judge_time = time.perf_counter() - start
        judge_times.append(judge_time)
        print(f"  {ticket['id']}: judge_time={judge_time:.2f}s")

    return {
        "label": label,
        "judge_model": judge_model,
        "avg_judge_time_s": round(statistics.mean(judge_times), 2),
        "total_judge_time_s": round(sum(judge_times), 2),
        "avg_judge_score": round(statistics.mean(judge_scores), 2) if judge_scores else None,
        "cost_usd": 0.0,
    }


def main() -> None:
    all_tickets = json.loads(DATASET_PATH.read_text())
    tickets = [t for t in all_tickets if t["id"] in TICKET_IDS]
    print(f"Using {len(tickets)} tickets for the routing comparison.\n")

    before = run(judge_model=GENERATE_MODEL, label="before (one model for everything)", tickets=tickets)
    print()
    after = run(judge_model=VALIDATE_MODEL, label="after (routed: cheap model judges)", tickets=tickets)

    get_client().flush()

    print("\n| Run | Generate model | Judge model | Avg judge time | Total judge time | Avg judge score | Cost |")
    print("|---|---|---|---|---|---|---|")
    for r in (before, after):
        print(f"| {r['label']} | {GENERATE_MODEL} | {r['judge_model']} | "
              f"{r['avg_judge_time_s']}s | {r['total_judge_time_s']}s | "
              f"{r['avg_judge_score']} | ${r['cost_usd']} |")

    speedup = before["total_judge_time_s"] / after["total_judge_time_s"] if after["total_judge_time_s"] else None
    print(f"\nJudging speedup from routing: {speedup:.1f}x faster, "
          f"judge-score delta: {after['avg_judge_score'] - before['avg_judge_score']:+.2f} "
          f"(generation quality unaffected - same generator model both runs)")

    out_path = ROOT / "evals" / "results" / "step8_routing.json"
    out_path.write_text(json.dumps({"before": before, "after": after}, indent=2))
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
