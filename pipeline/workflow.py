"""Capstone-integration Temporal workflow:

load_ticket -> generate_spec -> validate_spec -> WAIT approve_spec ->
run_checks (guardrails) -> WAIT approve_pr -> post_result

This wires together Step 3 (Temporal), Step 4 (LangFuse tracing, inside the
activities), Step 5 (rule checks + LLM judge in validate_spec), Step 7
(guardrails pre-PR gate in run_checks), and Step 8 (model routing, inside
generate_spec/validate_spec) into one pipeline run.

Honest scope note: the "implement" step (an agent writing code from the
approved spec) is intentionally NOT a Temporal activity here - that's
Copilot/Claude Code agent mode, which isn't an API you call from a worker
process. Step 6 did that step manually, for real, against listings-sample-app.
run_checks validates whatever is currently in that repo's working tree,
representing the gate a real implementation would have to pass before PR.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pipeline.activities import (
        Ticket,
        generate_spec_activity,
        load_ticket,
        post_result,
        run_checks_activity,
        validate_spec_activity,
    )


@workflow.defn
class TicketToSpecWorkflow:
    def __init__(self) -> None:
        self._spec_approved = False
        self._pr_approved = False
        self._status = "started"
        self._spec: dict | None = None
        self._validation: dict | None = None
        self._checks: dict | None = None

    @workflow.run
    async def run(self, ticket_id: str) -> str:
        self._status = "loading_ticket"
        ticket: Ticket = await workflow.execute_activity(
            load_ticket,
            ticket_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_attempts=5,
            ),
        )

        self._status = "generating_spec"
        self._spec = await workflow.execute_activity(
            generate_spec_activity,
            ticket,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        self._status = "validating_spec"
        self._validation = await workflow.execute_activity(
            validate_spec_activity,
            args=[ticket, self._spec],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        self._status = "waiting_for_spec_approval"
        await workflow.wait_condition(lambda: self._spec_approved)

        self._status = "running_checks"
        self._checks = await workflow.execute_activity(
            run_checks_activity,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        self._status = "waiting_for_pr_approval"
        await workflow.wait_condition(lambda: self._pr_approved)

        self._status = "posting_result"
        result = await workflow.execute_activity(
            post_result,
            args=[ticket_id, self._spec],
            start_to_close_timeout=timedelta(seconds=10),
        )
        self._status = "done"
        return result

    @workflow.signal
    def approve_spec(self) -> None:
        self._spec_approved = True

    @workflow.signal
    def approve_pr(self) -> None:
        self._pr_approved = True

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.query
    def spec(self) -> dict | None:
        return self._spec

    @workflow.query
    def validation(self) -> dict | None:
        return self._validation

    @workflow.query
    def checks(self) -> dict | None:
        return self._checks
