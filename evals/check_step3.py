"""Step 3 'Done when' check: start the workflow, watch it wait for approval,
signal approval, and confirm it completes. Also prints the workflow id so you
can open it in the Temporal UI (http://localhost:8233) and see the retried
load_ticket activity (attempts 1-2 fail on purpose, attempt 3 succeeds).
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

    workflow_id = f"ticket-to-pr-T1-{int(time.time())}"
    handle = await client.start_workflow(
        TicketToSpecWorkflow.run,
        "T1",
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    print(f"Started workflow: {workflow_id}")
    print(f"View it at: http://localhost:8233/namespaces/default/workflows/{workflow_id}")

    # poll status until it reaches waiting_for_approval (proves retries resolved)
    while True:
        status = await handle.query(TicketToSpecWorkflow.status)
        print(f"status: {status}")
        if status == "waiting_for_approval":
            break
        await asyncio.sleep(1)

    spec = await handle.query(TicketToSpecWorkflow.spec)
    print(f"Spec awaiting approval: acceptance_criteria={len(spec['acceptance_criteria'])}")

    print("Sending approve_spec signal...")
    await handle.signal(TicketToSpecWorkflow.approve_spec)

    result = await handle.result()
    print(f"Workflow result: {result}")
    print("\nStep 3 check passed: workflow recovered from retries and completed after approval.")


if __name__ == "__main__":
    asyncio.run(main())
