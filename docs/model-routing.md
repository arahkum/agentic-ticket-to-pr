# Model routing (Step 8)

## Policy

| Task | Model | Why |
|---|---|---|
| `generate` (produce the spec) | `gpt-oss:20b` (strong) | Touches untrusted ticket text; higher stakes. Step 5's eval table: 1.00 rule score vs 0.88, 4.48 judge score vs 3.57, and it resisted the injection attempt where `llama3.2:3b` did not. |
| `validate` (judge an already-generated spec) | `llama3.2:3b` (cheap/fast) | Narrower, classification-like task over trusted, already-structured input (a spec, not raw ticket text). No exposure to untrusted input, no shipped artifact at stake. |

Implemented in `pipeline/model_router.py` (`model_for("generate")` /
`model_for("validate")`).

## Before vs after (4-ticket comparison, `evals/run_step8_routing.py`)

Generation always uses `gpt-oss:20b` in both runs, so **spec quality is
identical by construction** — only the judging step's model changes.

| Run | Generate model | Judge model | Avg judge time | Total judge time | Avg judge score | Cost |
|---|---|---|---|---|---|---|
| Before (one model for everything) | gpt-oss:20b | gpt-oss:20b | 4.15s | 16.59s | 4.50 | $0.00 |
| After (routed) | gpt-oss:20b | llama3.2:3b | 2.22s | 8.90s | 4.50 | $0.00 |

**Result: 1.9x faster judging, 0.00 quality delta.** Full per-ticket numbers
in `evals/results/step8_routing.json`.

## Why cost is $0 here, and what it means with a paid API

Both models run locally via Ollama, so neither run has a literal dollar
cost. The time savings is still real and compounds at scale (judging every
spec twice as fast matters when you're running 100s of evals). If `generate`
and `validate` were routed to paid APIs instead (e.g. a frontier model for
generation, a small/cheap model for judging), the same policy would also cut
**$ per ticket**, not just latency — judging typically runs on short,
structured input (the spec), which is exactly where a cheap model's
accuracy gap matters least and its price gap matters most.

## Takeaway

Route by **risk and task shape**, not just "always use the biggest model":
- Untrusted input + shipped artifact -> strong model.
- Trusted, narrow, already-structured input -> cheap/fast model, verified
  against the eval table before trusting it in production.
