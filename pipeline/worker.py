"""Temporal worker for the ticket-to-PR pipeline."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.activities import generate_spec_activity, load_ticket, post_result
from pipeline.workflow import TicketToSpecWorkflow

TASK_QUEUE = "ticket-to-pr"


async def main() -> None:
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[TicketToSpecWorkflow],
        activities=[load_ticket, generate_spec_activity, post_result],
    )
    print(f"Worker started, polling task queue: {TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
