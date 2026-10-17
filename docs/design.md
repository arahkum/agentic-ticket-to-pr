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
