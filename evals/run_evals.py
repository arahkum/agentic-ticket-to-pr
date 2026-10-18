"""Step 5 exercise: compare 2 prompts x 2 models on the eval dataset.

For each (prompt, model) combo, generates a spec for every ticket, scores it
with rule checks (evals/rules.py) and an LLM judge using the *other* model
(evals/judge.py), and records quality/cost/latency. Writes a markdown table
and evals/results/eval_results.json, and logs a score back to LangFuse per
case (Step 5's "datasets and scores" lesson).
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
from evals.rules import score_rules
from pipeline.spec_generator import SpecGenerationError, generate_spec, get_client

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "evals" / "dataset" / "eval_tickets.json"
RESULTS_PATH = ROOT / "evals" / "results" / "eval_results.json"

PROMPTS = {
    "v1": ROOT / "prompts" / "spec_prompt.md",
    "v2": ROOT / "prompts" / "spec_prompt_v2.md",
}
MODELS = ["gpt-oss:20b", "llama3.2:3b"]


def judge_model_for(generator_model: str) -> str:
    """Always judge with a different model than the one being judged."""
    return MODELS[1] if generator_model == MODELS[0] else MODELS[0]


def run_combo(prompt_version: str, prompt_path: Path, model: str, tickets: list[dict]) -> dict:
    langfuse = get_client()
    judge_model = judge_model_for(model)
    cases = []

    for ticket in tickets:
        start = time.perf_counter()
        spec = None
        raw = ""
        error = None
        with langfuse.start_as_current_observation(
            as_type="span", name="eval_case", input={"ticket_id": ticket["id"]}
        ):
            try:
                spec = generate_spec(
                    ticket["text"],
                    model=model,
                    ticket_id=f"{ticket['id']}-{prompt_version}-{model}",
                    prompt_path=prompt_path,
                    prompt_version=prompt_version,
                )
            except SpecGenerationError as exc:
                error = str(exc)
                raw = exc.raw
            latency_s = time.perf_counter() - start

            rule_result = score_rules(spec, raw, ticket["category"])

            judge_score = None
            if spec is not None:
                try:
                    judge_score = judge_spec(ticket["text"], spec.model_dump(), judge_model)
                except JudgeError as exc:
                    print(f"  [judge error] {ticket['id']}: {exc}")

            # Step 5's "datasets and scores" in LangFuse: attach a score to this trace
            langfuse.create_score(
                name="rule_score",
                value=rule_result["rule_score"],
                trace_id=langfuse.get_current_trace_id(),
            )

        case = {
            "ticket_id": ticket["id"],
            "category": ticket["category"],
            "schema_valid": spec is not None,
            "error": error,
            "rule_score": rule_result["rule_score"],
            "rule_checks": rule_result["checks"],
            "judge_score": judge_score.average if judge_score else None,
            "judge_reasoning": judge_score.reasoning if judge_score else None,
            "latency_s": round(latency_s, 2),
        }
        cases.append(case)

        status = "OK" if spec is not None else "FAIL"
        print(f"  [{status}] {ticket['id']} ({ticket['category']}) "
              f"rule={rule_result['rule_score']:.2f} "
              f"judge={case['judge_score']} latency={case['latency_s']}s")

    return {
        "prompt_version": prompt_version,
        "model": model,
        "judge_model": judge_model,
        "cases": cases,
        "avg_rule_score": statistics.mean(c["rule_score"] for c in cases),
        "schema_valid_rate": sum(c["schema_valid"] for c in cases) / len(cases),
        "avg_judge_score": statistics.mean(
            [c["judge_score"] for c in cases if c["judge_score"] is not None] or [0]
        ),
        "avg_latency_s": round(statistics.mean(c["latency_s"] for c in cases), 2),
        "cost_usd": 0.0,  # local Ollama models are free
    }


# full 16-ticket dataset is used elsewhere (check_step1, documentation); the
# 2x2 comparison below uses this smaller, still-diverse subset to keep local
# runtime reasonable (gpt-oss:20b is slow, and 2 prompts x 2 models adds up).
COMPARISON_TICKET_IDS = {"E01", "E03", "E05", "E06", "E11", "E12", "E14", "E16"}


def main() -> None:
    all_tickets = json.loads(DATASET_PATH.read_text())
    tickets = [t for t in all_tickets if t["id"] in COMPARISON_TICKET_IDS]
    print(f"Loaded {len(tickets)} eval tickets (of {len(all_tickets)} total).\n")

    results = []
    for prompt_version, prompt_path in PROMPTS.items():
        for model in MODELS:
            print(f"=== prompt={prompt_version} model={model} "
                  f"(judge={judge_model_for(model)}) ===")
            results.append(run_combo(prompt_version, prompt_path, model, tickets))
            print()

    get_client().flush()

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2))

    print("\n| Prompt | Model | Schema valid | Avg rule score | Avg judge score | Avg latency | Cost |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['prompt_version']} | {r['model']} | "
              f"{r['schema_valid_rate']:.0%} | {r['avg_rule_score']:.2f} | "
              f"{r['avg_judge_score']:.2f} | {r['avg_latency_s']}s | ${r['cost_usd']} |")

    print(f"\nFull results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
