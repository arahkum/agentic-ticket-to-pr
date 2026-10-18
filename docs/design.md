# Design notes

## Step 3: why Temporal, and why the workflow waits without a thread

**Why Temporal instead of a plain script/cron job:**
- The pipeline has a step that can take arbitrarily long (a human approving a
  spec or PR) — a normal process can't just block in memory for hours/days
  without burning a thread or dying on deploy/restart.
- Steps call unreliable things (LLM APIs, test runners) that fail
  transiently. Temporal retries activities automatically with backoff,
  without the workflow author writing retry loops by hand.
- If the worker process crashes, Temporal replays the workflow's event
  history to rebuild exactly where it left off — no lost state, no
  duplicate side effects (as long as activities are idempotent).

**`workflow.execute_activity(..., retry_policy=RetryPolicy(...))`**
- `load_ticket` is made to fail on attempts 1-2 on purpose (checked via
  `activity.info().attempt`) to prove retries work. Evidence from a real run
  (`ticket-to-pr-T1-1792257394`): the activity's Scheduled->Completed span
  was ~3 seconds, matching the 1s + 2s backoff before succeeding on attempt
  3 — visible with `temporal workflow show --workflow-id <id>` or in the
  Temporal UI (http://localhost:8233).

**Why `await workflow.wait_condition(lambda: self._approved)` doesn't block a
thread:**
- Workflow code runs inside Temporal's deterministic event loop, not as a
  normal OS thread. `wait_condition` suspends the workflow's coroutine and
  Temporal persists that "I'm waiting for X" state in the workflow's event
  history, then the worker process is free to do other work (or even be
  killed and restarted) — nothing is parked holding a thread or a memory
  ticket while waiting for the `approve_spec` signal. When the signal
  arrives, Temporal replays the history and resumes the coroutine exactly
  where it suspended. This is what "durable execution" means: the workflow's
  logical state survives independent of any one running process.

**Determinism requirement:** workflow code (`pipeline/workflow.py`) must not
do real I/O, call `time.time()`/`random` directly, or import non-deterministic
modules at workflow-sandbox-import-time — that's why activities (which do
the real work: calling Ollama, etc.) are separate from the workflow, and why
`workflow.unsafe.imports_passed_through()` is used to import the activity
*function references* (for typing) without sandboxing their internals.

## Step 4: LangFuse tracing

- Self-hosted via Docker Compose (`langfuse` repo cloned as a sibling
  directory, not part of this repo) with headless initialization
  (`LANGFUSE_INIT_*` env vars) so org/project/API keys are created on
  container startup — no manual sign-up needed.
- `pipeline/spec_generator.py` wraps every call in a `generate_spec` span
  (metadata: `ticket_id`, `model`, `prompt_version`) with a nested
  `spec_llm_call` generation observation for the actual LLM call.
- **Caveat found while building this**: on self-hosted Langfuse v4.63.0 with
  Python SDK v5.0.2, the dedicated `model=` kwarg on
  `start_as_current_observation(as_type="generation", ...)` was not
  persisted server-side (queried back as `None`). Latency *did* work
  correctly via the observation's `latency` field. Fix: also put `model` in
  the `metadata` dict explicitly — belt-and-suspenders, and it's what the
  exercise actually required (ticket_id/model/prompt_version as metadata).
- Cost: the local Ollama model (`gpt-oss:20b`) is free, so `total_cost` is
  legitimately `None`/0 here — no `usage_details`/pricing were sent. With a
  paid API (Step 8 routing), passing real token `usage_details` lets
  LangFuse compute cost per call from its model price table.
- Verify: `evals/check_step4.py` generates a couple of specs, flushes, then
  queries `langfuse.api.observations.get_many(..., fields="core,basic,io,metadata,usage")`
  to confirm metadata + latency are queryable, not just visible in the UI.

## Step 5: evals, regression tests, quality gates

See `evals/rubric.md` for the full dataset composition, rubric, results
table (2 prompts x 2 models), and the regression-gate proof. Summary:

- `evals/rules.py`: deterministic rule checks (schema valid, no empty
  strings, no duplicates; for the injection ticket, only whether the system
  prompt leaked — refusing to produce a spec is the *correct* outcome there,
  not a failure).
- `evals/judge.py`: LLM-as-judge (clarity/specificity/relevance, 1-5), always
  judged by the *other* model than the one that generated the spec.
- `evals/run_evals.py`: compares `prompts/spec_prompt.md` (v1) vs the
  deliberately-weakened `prompts/spec_prompt_v2.md` across `gpt-oss:20b` and
  `llama3.2:3b`. v2 scored 0% schema-valid on both models (dropping the
  strict-JSON/conciseness/count-minimum instructions causes truncated,
  invalid output) — a clean, reproducible regression.
- `evals/check_regression.py`: fast, rule-only gate (no judge call, to avoid
  CI flakiness) — exits 1 ("red") if the average rule score drops below 0.9.
  Verified locally: current prompt passes (1.000), v2 fails (0.200).
- `.github/workflows/eval-gate.yml`: runs the same gate on every PR touching
  prompts/eval/pipeline code, installing a small Ollama model in CI (no paid
  API key needed).
