"""Temporal activities for the ticket-to-PR pipeline (Step 3 exercise,
extended in the capstone integration with validate_spec and run_checks)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.judge import JudgeError, judge_spec
from evals.rules import score_rules
from guardrails.pre_pr_gate import GateFailure, SecretsFoundError
from guardrails.pre_pr_gate import pre_pr_gate as _pre_pr_gate
from pipeline.model_router import model_for
from pipeline.spec_generator import SpecGenerationError, TicketSpec, generate_spec as _generate_spec

# tiny built-in dataset so this exercise needs no external ticket source
_SAMPLE_TICKETS = {
    "T1": "Search is broken, fix it",
    "T2": "Users want to see only active listings, not sold ones.",
}

# the target repo "implement" would open a PR against (Step 6/7's real target)
LISTINGS_APP_PATH = str(Path.home() / "Documents" / "RahulProjects" / "listings-sample-app")


@dataclass
class Ticket:
    id: str
    text: str


@activity.defn
async def load_ticket(ticket_id: str) -> Ticket:
    """Load a ticket by id.

    Fails on purpose on the first 2 attempts (checked via Temporal's own
    attempt counter) to demonstrate automatic retry + backoff recovering a
    transient failure, then succeeds on attempt 3.
    """
    info = activity.info()
    if info.attempt <= 2:
        raise RuntimeError(
            f"simulated transient failure loading {ticket_id} (attempt {info.attempt})"
        )
    text = _SAMPLE_TICKETS.get(ticket_id, "Make listings better")
    return Ticket(id=ticket_id, text=text)


@activity.defn
async def generate_spec_activity(ticket: Ticket) -> dict:
    try:
        spec = _generate_spec(ticket.text, ticket_id=ticket.id, model=model_for("generate"))
    except SpecGenerationError as exc:
        raise RuntimeError(f"spec generation failed: {exc}") from exc
    return spec.model_dump()


@activity.defn
async def validate_spec_activity(ticket: Ticket, spec_dict: dict) -> dict:
    """Step 5+8: rule checks (free, deterministic) + LLM judge, routed to the
    cheap/fast model since this only scores an already-structured spec."""
    spec = TicketSpec.model_validate(spec_dict)
    rule_result = score_rules(spec, raw_output="", category="normal")

    judge_score = None
    judge_reasoning = None
    try:
        judged = judge_spec(ticket.text, spec_dict, judge_model=model_for("validate"))
        judge_score = judged.average
        judge_reasoning = judged.reasoning
    except JudgeError as exc:
        judge_reasoning = f"judge unavailable: {exc}"

    return {
        "rule_score": rule_result["rule_score"],
        "rule_checks": rule_result["checks"],
        "judge_score": judge_score,
        "judge_reasoning": judge_reasoning,
    }


@activity.defn
async def run_checks_activity(repo_path: str = LISTINGS_APP_PATH) -> dict:
    """Step 7: tests + diff-size + secret scan, before any PR is allowed to open."""
    try:
        return _pre_pr_gate(repo_path)
    except (GateFailure, SecretsFoundError) as exc:
        raise RuntimeError(f"pre-PR gate failed: {exc}") from exc


@activity.defn
async def post_result(ticket_id: str, spec: dict) -> str:
    # Real pipeline would open a PR / post a comment here (Step 6, 9).
    # For this exercise, "posting" just returns a confirmation.
    return (
        f"Posted approved spec for {ticket_id} with "
        f"{len(spec['acceptance_criteria'])} acceptance criteria."
    )
