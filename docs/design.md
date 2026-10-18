# Design notes

## Capstone integration: one pipeline, all steps wired together

`pipeline/workflow.py` now runs:

```
load_ticket -> generate_spec -> validate_spec -> WAIT approve_spec ->
run_checks -> WAIT approve_pr -> post_result
```

- `generate_spec` / `validate_spec` route to models via Step 8's
  `model_router` and are fully traced in LangFuse (Step 4).
- `validate_spec` runs Step 5's rule checks + LLM judge.
- `run_checks` runs Step 7's `guardrails.pre_pr_gate` for real, against
  `listings-sample-app`.
- Two human-approval signals (`approve_spec`, `approve_pr`), each backed by
  Temporal's durable `wait_condition` (Step 3).

Verified end to end with `evals/check_capstone.py` — one real run:
`generating_spec -> validating_spec (judge_score=4.0, rule_score=1.0) ->
waiting_for_spec_approval -> running_checks (tests passed, secret_scan
clean, changed_lines=0) -> waiting_for_pr_approval -> posting_result`.

**Honest scope note:** the "implement" step (an agent writing code from the
approved spec) is intentionally *not* a Temporal activity — Copilot/Claude
Code agent mode isn't an API a worker process can call. Step 6 did that
step for real, manually, against `listings-sample-app`; `run_checks`
validates whatever is currently in that repo, representing the gate a real
implementation has to pass before a PR opens.

## Step 8: model selection and routing

See `docs/model-routing.md` for the full table. Summary: `pipeline/model_router.py`
routes `generate` (produces the spec, touches untrusted ticket text) to the
strong model (`gpt-oss:20b`) and `validate` (judges an already-generated
spec) to the cheap/fast model (`llama3.2:3b`). Measured with
`evals/run_step8_routing.py`: **1.9x faster judging, 0.00 quality delta**
(generation — and therefore the shipped spec — is unaffected, since both
runs generate with the same model; only who judges it changes).

## Step 7: guardrails and security

`guardrails/` implements the controls from the plan's Step 7 exercise:

- `tool_allowlist.py`: `ALLOWED_TOOLS` set + `assert_tool_allowed`,
  `assert_path_allowed` (blocks `.env`/secret/credential/key-like paths),
  `assert_branch_allowed` (blocks writing to `main`/`master`) — what an MCP
  client/orchestrator would enforce around a coding agent (ties back to
  Step 2).
- `clean_env.py`: `clean_env_for_agent()` strips any env var whose name ends
  in `_KEY`/`_TOKEN`/`_SECRET`/`_PASSWORD`/`_CREDENTIALS` before handing an
  environment to a subprocess (tests, git) the agent runs — least privilege,
  not "trust the agent not to look."
- `diff_limit.py`: `changed_line_count()` + `DiffTooLargeError` — caps how
  much a single PR can change (default 300 lines).
- `secret_scan.py`: wraps `gitleaks detect` (installed via `brew install
  gitleaks`), raises `SecretsFoundError` with the findings.
- `pre_pr_gate.py`: orchestrates tests -> diff-size -> secret scan, in that
  order — this is the capstone architecture's `run_checks` activity.

**Verified by deliberately breaking things** (all on a local-only throwaway
branch, never pushed):
- A commit with a `ghp_...`-shaped fake GitHub token in
  `listings-sample-app` was correctly caught by `pre_pr_gate` (found in both
  the source file *and* a stale `.pyc` in `__pycache__` — a reminder that
  compiled artifacts can carry secrets too). Note: a canonical
  `AKIAIOSFODNN7EXAMPLE`-style fake AWS key was **not** caught — gitleaks'
  default ruleset allowlists well-known documentation example keys, so a
  real secret scan needs a ruleset tuned for what your codebase actually
  risks leaking, not just "any test key will do."
- A real past diff run through `changed_line_count` with an artificially
  low limit correctly raised `DiffTooLargeError`.

**Prompt injection ticket blocked and visible in LangFuse** (the plan's
specific "Done when" for this step): `pipeline/spec_generator.py`'s error
path now sets `level="ERROR"` and `metadata={"blocked": True, ...}` on the
span whenever generation fails — including when a model correctly refuses
an injection attempt rather than leaking the system prompt. Verified with
`evals/check_step7.py`: the injection ticket raises `SpecGenerationError`
(no crash, no spec produced), and the resulting trace is confirmed via the
LangFuse API as `level=ERROR`, `metadata.blocked=True`.

## Step 6: spec-driven implementation on listings-sample-app

Used Copilot (agent mode) instead of the Claude Code CLI throughout this
project (see earlier plan discussion) — for Step 6 that means I acted as the
implementing agent directly rather than scripting `claude -p`, since that's
the actual tool being used daily here.

- Generated 3 specs via Step 1's `spec_generator` into
  `listings-sample-app/specs/TICKET-{1,2,3}.json`.
- Implemented each on its own branch (`feature/ticket-N-*`), with tests,
  reviewed, and merged via real PRs on GitHub (arahkum/listings-sample-app
  #1, #2, #3).
- Full review write-up, including a real cross-ticket contract regression
  TICKET-3 introduced (changing `GET /listings`'s default no-filter
  behavior from "active only" to "no filter"), is in
  `listings-sample-app/docs/failure-log.md`.
- `listings-sample-app/AGENTS.md` holds the project rules (branch naming,
  test requirements, scope discipline) — the cross-tool equivalent of
  `CLAUDE.md` that both Claude Code and Copilot/other agents can read.

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
