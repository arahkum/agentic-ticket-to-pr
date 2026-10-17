# Forward Deployed Engineer (Agentic Dev Workflows): Learning Guide and Resume Project Plan

Prepared for: Rahul Kumar | Date: 17 Oct 2026
Role: builds and runs agentic development pipelines (ticket to spec to code to tests to review to release) for a classifieds marketplace
How to use this file: do the steps in order. Each step has a "Done when" check. Do not add a tool to your resume until its step is done and the code is on GitHub.

---

## Part 1: Skills map (JD requirement vs where you are)

| JD requirement                                                      | Your level now                                   | Step that closes it     |
| ------------------------------------------------------------------- | ------------------------------------------------ | ----------------------- |
| Agent and workflow orchestration (Temporal)                         | None                                             | Step 3                  |
| LLM observability and evaluation (LangFuse)                         | None                                             | Steps 4 and 5           |
| Daily use of Claude Code / Codex                                    | Copilot with Claude models                       | Step 6                  |
| Evals, regression tests, guardrails, quality gates for agent output | Strong on gates and regression, new to LLM evals | Steps 5 and 7           |
| Prompt and context engineering, tool use, MCP, model routing        | MCP server built, prompts basic                  | Steps 1, 2 and 8        |
| Spec-driven development                                             | Test plans and acceptance criteria               | Step 6                  |
| CI/CD (GitHub Actions) and GCP or AWS                               | Strong                                           | Steps 5 and 9           |
| Shipping and operating production systems                           | Weak (SDET titles)                               | Step 9 and the capstone |
| Nice-to-have: Cloud Run, Pub/Sub, MongoDB, React                    | Partial                                          | Step 9 (optional)       |

Your edge: you already know quality gates, regression thinking and failure analysis. Most candidates for this role can build an agent but cannot prove it works. Your project should show the proof.

---

## Part 2: Step-by-step learning path

Assumed pace: 2 to 3 hours on weekdays, 5 to 6 hours on weekends. Fast track is 2 weeks, relaxed track is 4 weeks. Times below are for the fast track.

### Step 0: Setup (half a day)

- [ ] Python 3.11 or newer, Docker, Git, and the GitHub CLI (`gh`) installed.
- [ ] An Anthropic API key (set a low monthly spend limit, for example $20).
- [ ] Claude Code installed and logged in.
- [ ] Create two public GitHub repos: `agentic-ticket-to-pr` (the pipeline) and `listings-sample-app` (the target app the agent will change).
- [ ] Add a `.gitignore` and a secrets rule on day one. Never commit keys.

Done when: both repos exist, and `claude` runs in a terminal.

### Step 1: LLM basics, prompts and structured output (Day 1, about 3 hours)

Learn:

- How to call the Claude API from Python, system vs user prompts, and temperature.
- Structured output: get JSON back that matches a schema, and validate it with Pydantic.
- Tool use (function calling): define a tool, let the model call it, return the result.
- Context engineering: what to put in the prompt, what to leave out, and how to keep context small.

Exercise: write `spec_generator.py` that takes a vague ticket and returns a JSON spec with fields `user`, `problem`, `acceptance_criteria[]`, `edge_cases[]`, `test_cases[]`.

Done when: 5 sample tickets produce valid JSON that passes schema validation.

### Step 2: MCP in depth (Day 2, about 3 hours)

Learn: what an MCP server exposes (tools, resources, prompts), how a client discovers tools, permissions and security.
Exercise: extend the MCP server you already built with a new tool, for example `create_ticket_from_failed_test`. Add input validation and a clear error path. Write a short doc on how an agent finds and calls your tools.

Done when: Claude Code (or any MCP client) calls your new tool successfully.

### Step 3: Temporal workflow orchestration (Days 3 and 4, about 6 hours)

Learn:

- Workflows vs activities, why workflow code must be deterministic, workers and task queues.
- Retry policies, timeouts, heartbeats, idempotency.
- Signals (for human approval) and queries (to read state).
- Failure handling: what is retryable and what is not.

Run it locally: `pip install temporalio`, and start a local server with `temporal server start-dev` (install the Temporal CLI first). Follow the Python SDK setup page in the official Temporal docs, and take the free Temporal 101 course if you want a structured start.

Exercise: build a 3-activity workflow (`load_ticket`, `generate_spec`, `post_result`). Make one activity fail twice on purpose and watch it recover. Add a signal `approve_spec` and make the workflow wait for it.

Done when: the Temporal UI shows a run with retries and an approval, and you can explain why the workflow waits without using a thread.

### Step 4: LangFuse tracing (Day 5, about 3 hours)

Learn: traces and spans, tracking latency, tokens and cost per call, and linking a trace to a workflow run ID.
Setup options: LangFuse Cloud free tier (fastest), or self-host with Docker Compose if you want to say you self-hosted it. Check the LangFuse docs for the current setup, since self-hosting needs several services.
Exercise: wrap `spec_generator.py` so every call is a trace. Add metadata: ticket ID, model, prompt version.

Done when: you can open LangFuse and see cost and latency for each run.

### Step 5: Evals, regression tests and quality gates (Days 6 and 7, about 6 hours)

Learn:

- Datasets and scores in LangFuse, offline evals vs online monitoring.
- Rule-based checks (schema valid, has at least 3 acceptance criteria, no empty fields).
- LLM-as-judge: write a rubric, use a different model than the one being judged, and know the pitfalls (bias, flakiness, drift).
- Regression suite: freeze a dataset and compare prompt or model versions on the same cases.

Exercise:

1. Build a dataset of 15 to 20 tickets (include 3 vague ones, 2 contradictory ones and 1 prompt-injection attempt).
2. Score specs with rule checks plus an LLM judge.
3. Compare two prompts and two models. Record quality, cost and latency in a table.
4. Add a GitHub Actions workflow that runs the eval on every PR and fails if the average score drops below your threshold.

Done when: a PR that makes the prompt worse turns the build red.

### Step 6: Claude Code for real work, and spec-driven development (Days 8 and 9, about 6 hours)

Learn:

- Use Claude Code daily on real tasks from now on.
- Headless mode for scripts: `claude -p "<prompt>"` with `--output-format json`, a restricted tool list, and a turn or budget limit. Check the current Claude Code docs for exact flags.
- Writing a `CLAUDE.md` with project rules, and writing specs an agent can act on (clear acceptance criteria, files in scope, tests to add).
- Reviewing agent-generated diffs: check scope, tests, security, and unrelated edits.

Exercise: in `listings-sample-app` (a small FastAPI service for listings with create and search), have headless Claude Code implement 3 tickets from specs, on a branch, with tests. Review each diff by hand and write down what it got wrong.

Done when: you have 3 reviewed agent PRs and a list of failure patterns you noticed.

### Step 7: Guardrails and security (Day 10, about 3 hours)

Learn: prompt injection, tool allowlists, least privilege, sandboxing, secrets handling, and human approval points. Read the OWASP Top 10 for LLM Applications.
Exercise: add these controls to the pipeline:

- Tool allowlist for the coding agent and no network or secrets in its environment.
- Writes only to a feature branch, a diff-size limit, and a turn or cost limit.
- Secret scan (gitleaks) and test run before any PR is opened.
- A prompt-injection ticket in your eval set that must be blocked or flagged.

Done when: the injection ticket fails safely and shows up in LangFuse as a blocked run.

### Step 8: Model selection and routing (Day 10, about 1 hour)

Learn: when to use a smaller model (validation, classification) and a larger one (implementation), and how to decide using your eval table.
Exercise: route spec validation to a cheaper model and implementation to a stronger one. Record cost per ticket before and after, and quality before and after.

Done when: you have a table that justifies the routing choice with numbers.

### Step 9 (optional, nice-to-have): Deploy on GCP (Day 12, about 3 hours)

Learn Cloud Run basics. Containerize the Temporal worker or a small status API and deploy it, with Pub/Sub for a "ticket created" event if time allows.
Done when: a ticket event triggers a run in the cloud. This gives you real experience operating a production system.

---

## Part 3: Capstone project plan

Name: **Agentic Ticket-to-PR Pipeline** (repo: `agentic-ticket-to-pr`)
Domain tie-in: the sample app is a small classifieds listings API, so your demo covers realistic business use cases (listings, search, moderation rules).

### Architecture

```
Ticket (file or Jira)
   |
   v
Temporal workflow  --------------------------------------------+
   1. load_ticket                                              |
   2. generate_spec   (Claude API, structured JSON)            |
   3. validate_spec   (rules + LLM judge, cheaper model)       |
   4. WAIT: human approves spec (signal)                       |
   5. implement       (Claude Code headless, feature branch)   |
   6. run_checks      (tests, lint, gitleaks, diff-size limit) |
   7. evaluate_diff   (golden tests + LLM review)              |
   8. WAIT: human approves PR (signal)                         |
   9. open_pr         (gh CLI) and post status                 |
                                                               |
Every step traced in LangFuse (cost, latency, score) <---------+
GitHub Actions: runs eval suite on every change, gates merge
```

### Repo structure

```
agentic-ticket-to-pr/
  README.md            problem, design, trade-offs, results, demo GIF
  pipeline/            workflow.py, activities.py, worker.py
  prompts/             versioned prompts (spec, judge, review)
  evals/               dataset/, rubric.md, run_evals.py, results/
  guardrails/          allowlist, secret scan, injection tests
  .github/workflows/   eval-gate.yml, ci.yml
  docs/                design.md, failure-log.md, model-routing.md
```

### Milestones (each ends with something you can show)

| #  | Milestone                                                | Deliverable                                         |
| -- | -------------------------------------------------------- | ---------------------------------------------------- |
| M1 | Temporal workflow with retries and human approval signal | Working run in Temporal UI                          |
| M2 | Spec generation with structured output                   | 20-ticket dataset, valid JSON specs                 |
| M3 | LangFuse tracing and eval scoring                        | Eval table: 2 prompts x 2 models                    |
| M4 | Claude Code implements tickets headlessly                | 3 or more agent PRs on the sample app               |
| M5 | Guardrails and quality gates in GitHub Actions           | Red build on a bad prompt, blocked injection ticket |
| M6 | Results, README and demo                                 | Metrics table, 3-minute demo                        |

### Metrics to record

- Golden-test pass rate for agent PRs (for example, passes on first try out of N tickets).
- Cost per ticket and time per ticket (from LangFuse).
- Spec quality score (rule checks and judge) per model.
- Number of retries and failures recovered by Temporal.
- Injection and unsafe-output cases blocked out of those tested.
- Cost and quality change after model routing.

### Demo script (3 minutes)

1. Show a vague ticket and the generated spec.
2. Approve the spec in Temporal (signal).
3. Show the agent PR, the test results and the LangFuse trace with cost.
4. Show the injection ticket being blocked.
5. Show the red build from a degraded prompt, and the metrics table.

### README outline

Problem and goal, architecture diagram, how to run, design choices (why Temporal, why human checkpoints, why this eval design), results table, failure log (what went wrong and what you changed), limits and next steps.

---

## Part 4: Timeline

**Fast track (2 weeks)**

- Days 1 to 2: Steps 0, 1, 2
- Days 3 to 5: Steps 3, 4
- Days 6 to 7: Step 5
- Days 8 to 9: Step 6
- Day 10: Steps 7, 8
- Days 11 to 12: Capstone integration (M4 to M6), optional Step 9
- Days 13 to 14: README and demo polish

**Relaxed track (4 weeks):** the same order, with each block stretched to double. Finish M1 to M3 in the first two weeks.

If time runs short, cut Step 9 and Step 8, and use a markdown file as the ticket source instead of Jira.

---

## Part 5: What you'll be able to explain after each milestone

- After M1 to M3: how a Temporal workflow with retries and human approval works, and how LangFuse traces cost and latency.
- After M4: how Claude Code implements tickets headlessly from a spec, and what you learned reviewing its diffs.
- After M6: the full pipeline end to end, with real numbers from your own runs.

Key things to be able to explain from the project:

- Why Temporal: long-running steps, retries, human approval, and state that survives crashes.
- How you measure agent quality: golden tests, rubric scores, cost and latency trends.
- How you handle non-determinism: frozen datasets, repeated runs, thresholds not exact matches.
- Where humans stay in the loop and why (to avoid automation bias).
- What failed in the project and what you changed (use your failure log).

---

## Reminders

- Tool details change often. Always check the official docs for Temporal, LangFuse, Claude Code and GitHub Actions before copying commands.
- Keep API spending low: use small datasets, cache results, and set a monthly limit.

Sources used for setup details: [Temporal Python SDK local setup](https://docs.temporal.io/develop/python/set-up-your-local-python.md), [Claude Code headless mode and CI/CD overview](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/), [Langfuse guide (2026)](https://qaskills.sh/blog/langfuse-llm-observability-guide-2026)
