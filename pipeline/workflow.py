"""Temporal workflow: load_ticket -> generate_spec -> WAIT approve_spec -> post_result."""
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
    )


@workflow.defn
class TicketToSpecWorkflow:
    def __init__(self) -> None:
        self._approved = False
        self._status = "started"
        self._spec: dict | None = None

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

        self._status = "waiting_for_approval"
        await workflow.wait_condition(lambda: self._approved)

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
        self._approved = True

    @workflow.query
    def status(self) -> str:
        return self._status

    @workflow.query
    def spec(self) -> dict | None:
        return self._spec
