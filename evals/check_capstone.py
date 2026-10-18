"""Capstone integration check: drives the full pipeline end to end -
load_ticket -> generate_spec -> validate_spec -> WAIT approve_spec ->
run_checks (guardrails) -> WAIT approve_pr -> post_result - and prints every
stage's output so the whole integrated run is visible in one place.

Requires: Temporal dev server + worker running (pipeline/worker.py), and
Ollama serving gpt-oss:20b + llama3.2:3b.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from temporalio.client import Client

from pipeline.workflow import TicketToSpecWorkflow

TASK_QUEUE = "ticket-to-pr"


async def main() -> None:
    client = await Client.connect("localhost:7233")

    workflow_id = f"capstone-run-T1-{int(time.time())}"
    handle = await client.start_workflow(
        TicketToSpecWorkflow.run,
        "T1",
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    print(f"Started workflow: {workflow_id}")
    print(f"UI: http://localhost:8233/namespaces/default/workflows/{workflow_id}\n")

    while True:
        status = await handle.query(TicketToSpecWorkflow.status)
        print(f"status: {status}")
        if status == "waiting_for_spec_approval":
            break
        await asyncio.sleep(1)

    spec = await handle.query(TicketToSpecWorkflow.spec)
    validation = await handle.query(TicketToSpecWorkflow.validation)
    print(f"\nSpec: {spec['acceptance_criteria']}")
    print(f"Validation (Step 5+8, routed judge model): {validation}")

    print("\nApproving spec...")
    await handle.signal(TicketToSpecWorkflow.approve_spec)

    while True:
        status = await handle.query(TicketToSpecWorkflow.status)
        print(f"status: {status}")
        if status == "waiting_for_pr_approval":
            break
        await asyncio.sleep(1)

    checks = await handle.query(TicketToSpecWorkflow.checks)
    print(f"\nrun_checks result (Step 7 guardrails): {checks}")

    print("\nApproving PR...")
    await handle.signal(TicketToSpecWorkflow.approve_pr)

    result = await handle.result()
    print(f"\nWorkflow result: {result}")
    print("\nCapstone integration check passed: generate -> validate -> "
          "approve -> run_checks -> approve -> post, all in one traced, "
          "guardrailed, model-routed Temporal run.")


if __name__ == "__main__":
    asyncio.run(main())
