"""Step 8: route each task to the right-sized model, justified by Step 5's
eval table (evals/rubric.md).

Policy:
- "generate" (producing the actual spec - the harder, higher-stakes task,
  and the one exposed to untrusted ticket text) -> the strong model,
  gpt-oss:20b. It scored higher on rule checks (1.00 vs 0.88) and the judge
  (4.48 vs 3.57), and critically it resisted the injection attempt where
  llama3.2:3b did not.
- "validate" (judging/scoring an already-generated spec - a narrower,
  classification-like task working from trusted, already-structured input)
  -> the cheap/fast model, llama3.2:3b. ~4x faster (2.01s vs 8.63s avg
  latency in the Step 5 comparison) with no generation-quality cost, since
  it never touches the untrusted ticket text or produces the shipped spec.
"""
from __future__ import annotations

MODEL_FOR_TASK = {
    "generate": "gpt-oss:20b",
    "validate": "llama3.2:3b",
}


def model_for(task: str) -> str:
    try:
        return MODEL_FOR_TASK[task]
    except KeyError as exc:
        raise ValueError(
            f"no routing configured for task {task!r}; known tasks: {list(MODEL_FOR_TASK)}"
        ) from exc
