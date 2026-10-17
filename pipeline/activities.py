"""Temporal activities for the ticket-to-PR pipeline (Step 3 exercise)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.spec_generator import SpecGenerationError, generate_spec as _generate_spec

# tiny built-in dataset so this exercise needs no external ticket source
_SAMPLE_TICKETS = {
    "T1": "Search is broken, fix it",
    "T2": "Users want to see only active listings, not sold ones.",
}


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
        spec = _generate_spec(ticket.text, ticket_id=ticket.id)
    except SpecGenerationError as exc:
        raise RuntimeError(f"spec generation failed: {exc}") from exc
    return spec.model_dump()


@activity.defn
async def post_result(ticket_id: str, spec: dict) -> str:
    # Real pipeline would open a PR / post a comment here (Step 6, 9).
    # For this exercise, "posting" just returns a confirmation.
    return (
        f"Posted approved spec for {ticket_id} with "
        f"{len(spec['acceptance_criteria'])} acceptance criteria."
    )
