# Agentic Ticket-to-PR Pipeline

A learning project: an agentic pipeline that turns a vague ticket into a
structured spec, has a human approve it, runs guardrails, and (in a real
run) ends in a reviewed pull request — built end-to-end to learn Temporal,
LLM observability (LangFuse), evals/regression gates, guardrails, and model
routing. See [`plan/`](plan/) for the full learning guide this project came
from.

Target app: [`listings-sample-app`](https://github.com/arahkum/listings-sample-app),
a small FastAPI classifieds-listings API (create, search).

See [`docs/demo.md`](docs/demo.md) for the 3-minute demo walkthrough (vague
ticket -> spec -> Temporal approval -> agent PR + LangFuse trace ->
injection blocked -> red build from a degraded prompt + metrics table).

## Problem and goal

Turning a ticket into a reviewed, tested pull request has several points
that commonly fail silently: a vague ticket produces a vague spec, an LLM
call times out or returns garbage, a prompt change quietly makes output
worse, an agent-written diff touches more than it should, or a malicious
ticket tries to extract the system prompt. The goal here wasn't just to
wire an LLM into a workflow — it was to make each of those failure modes
visible and handled: traced, scored against a regression baseline,
guardrailed, and routed to the right-sized model.

## Architecture

```
Ticket (file)
   |
   v
Temporal workflow  (pipeline/workflow.py) --------------------------------+
   1. load_ticket        retries with backoff on transient failure        |
   2. generate_spec      Claude-style structured JSON, routed model       |
   3. validate_spec      rule checks + LLM judge, routed model            |
   4. WAIT: human approves spec (signal)                                  |
   5. [implement]        done by Copilot agent mode, outside Temporal -   |
                          see Step 6 / listings-sample-app's real PRs     |
   6. run_checks         tests + diff-size limit + gitleaks secret scan   |
   7. WAIT: human approves PR (signal)                                    |
   8. post_result        (real pipeline: open_pr via gh CLI)              |
                                                                           |
Every generate/validate call traced in LangFuse (cost, latency, score) <--+
GitHub Actions: eval-gate.yml (regression) + guardrails.yml (secret scan)
```

Models: local via Ollama (`gpt-oss:20b` for generation, `llama3.2:3b` for
judging) — free, fully offline. See [`docs/model-routing.md`](docs/model-routing.md)
for why.

## Repo structure

```
agentic-ticket-to-pr/
  pipeline/            workflow.py, activities.py, worker.py, spec_generator.py,
                        llm_client.py, model_router.py
  mcp_server/           MCP tools for the pipeline (Step 2)
  prompts/              versioned prompts (spec v1/v2)
  guardrails/           tool allowlist, clean env, diff limit, secret scan, pre-PR gate
  evals/                dataset, rules, judge, run_evals.py, check_*.py, results/
  .github/workflows/    eval-gate.yml, guardrails.yml
  docs/                 design.md, model-routing.md
  plan/                 the original learning guide
```

(`listings-sample-app` is a separate repo — see its own
[`docs/failure-log.md`](https://github.com/arahkum/listings-sample-app/blob/main/docs/failure-log.md)
for the Step 6 review write-up.)

## How to run

Prerequisites: Python 3.11+, Docker, [Ollama](https://ollama.com) with
`gpt-oss:20b` and `llama3.2:3b` pulled, the [Temporal CLI](https://docs.temporal.io/cli),
and a self-hosted [LangFuse](https://langfuse.com/self-hosting) instance
(see `docs/design.md` for the exact docker-compose setup used here).

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your LangFuse keys

# Terminal 1: Temporal dev server
temporal server start-dev --ui-port 8233

# Terminal 2: the worker
python pipeline/worker.py

# Terminal 3: run the full integrated pipeline
python evals/check_capstone.py
```

Other entry points:
- `python evals/run_evals.py` — the 2 prompts x 2 models comparison (Step 5)
- `python evals/check_regression.py` — the CI quality gate, runnable locally
- `python evals/run_step8_routing.py` — the model-routing before/after (Step 8)
- `python mcp_server/server.py` — the MCP server (Step 2)

## Design choices

- **Why Temporal**: a step here (human approval) can take arbitrarily long,
  and LLM/test-runner calls fail transiently. Temporal gives durable
  waiting and automatic retries without hand-written retry loops or a
  thread blocked on a human. See `docs/design.md` for the retry evidence
  from a real run.
- **Why two human checkpoints**: approving the spec and approving the PR
  are different judgment calls (is this the right spec? vs. is this diff
  safe to ship?) — collapsing them into one approval would hide whichever
  question gets asked second.
- **Why this eval design**: rule checks catch the cheap, deterministic
  failures (schema, duplicates, prompt leakage) for free; the LLM judge
  adds a quality signal a schema check can't (clarity, specificity) but
  judges with a *different* model than the generator to reduce
  self-preference bias. See `evals/rubric.md`.

## Results

**Prompt/model comparison** (Step 5, `evals/rubric.md`):

| Prompt | Model | Schema valid | Avg rule score | Avg judge score | Avg latency |
|---|---|---|---|---|---|
| v1 (current) | gpt-oss:20b | 88% | 1.00 | 4.48 | 8.63s |
| v1 (current) | llama3.2:3b | 88% | 0.88 | 3.57 | 2.01s |
| v2 (regressed) | gpt-oss:20b | 0% | 0.00 | 0.00 | 49.21s |
| v2 (regressed) | llama3.2:3b | 0% | 0.00 | 0.00 | 14.26s |

A real PR with the regressed prompt made `eval-gate.yml` fail (red,
score 0.000 < 0.9 threshold) — see `docs/design.md` for the run link.

**Model routing** (Step 8, `docs/model-routing.md`): routing judging to
the cheap/fast model is **1.9x faster with 0.00 quality delta** (4.5 -> 4.5),
since generation (the shipped artifact) stays on the strong model either way.

**Guardrails** (Step 7): a `ghp_`-shaped fake secret was caught by the
gitleaks-based gate (even inside a stale `.pyc`); a prompt-injection ticket
fails safely and shows up in LangFuse tagged `level=ERROR`,
`metadata.blocked=True`.

## Failure log

The most interesting failures weren't in the LLM calls — they were in
reviewing agent-written code. `listings-sample-app`'s
[`docs/failure-log.md`](https://github.com/arahkum/listings-sample-app/blob/main/docs/failure-log.md)
has the full write-up; the standout: a ticket spec that was individually
correct still introduced a **cross-ticket contract regression** (changed a
previously-shipped endpoint's default behavior) that no test caught,
because neither the spec nor the test suite had visibility into
everything shipped before it.

## Limits and next steps

- The "implement" step is manual (Copilot agent mode) — a production
  version would need either GitHub's Copilot coding agent (issue ->
  autonomous PR) or a scripted `claude -p` / similar headless CLI call,
  neither of which is callable from inside a Temporal worker the way the
  other activities are.
- Evals run against local models only; model-routing numbers would need
  re-validating against paid APIs before trusting the $-savings story on a
  model mix that includes them.
- No real ticket source (Jira) is wired in — `load_ticket` reads from a
  tiny built-in dict. Step 9 (cloud deployment, Cloud Run/Pub/Sub) was
  skipped since it needs a GCP account/billing to be provisioned first.
