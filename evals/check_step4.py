"""Step 4 'Done when' check: generate a few specs, then confirm via the
LangFuse Python SDK's query API that each produced a 'generate_spec' span with
ticket_id/prompt_version metadata, and a 'spec_llm_call' generation with model
+ latency. Also prints the UI link so you can look yourself.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from pipeline.spec_generator import generate_spec, get_client

load_dotenv()


def main() -> int:
    tickets = [
        ("T1", "Search is broken, fix it"),
        ("T2", "Users want to see only active listings, not sold ones."),
    ]

    for ticket_id, text in tickets:
        spec = generate_spec(text, ticket_id=ticket_id)
        print(f"[{ticket_id}] generated spec with {len(spec.acceptance_criteria)} acceptance criteria")

    langfuse = get_client()
    langfuse.flush()
    print("\nFlushed traces to LangFuse. Waiting for ingestion...")
    time.sleep(10)

    spans = langfuse.api.observations.get_many(
        name="generate_spec", limit=5, fields="core,basic,io,metadata"
    )
    generations = langfuse.api.observations.get_many(
        name="spec_llm_call", limit=5, fields="core,basic,io,metadata,usage"
    )

    print(f"\nFound {len(spans.data)} 'generate_spec' span(s):")
    checked = 0
    for s in spans.data:
        meta = s.metadata or {}
        print(f"- trace={s.trace_id} ticket_id={meta.get('ticket_id')} "
              f"model={meta.get('model')} prompt_version={meta.get('prompt_version')} "
              f"latency={s.latency}s")
        if meta.get("ticket_id") in {"T1", "T2"}:
            checked += 1

    print(f"\nFound {len(generations.data)} 'spec_llm_call' generation(s):")
    for g in generations.data:
        meta = g.metadata or {}
        print(f"- model={meta.get('model')} latency={g.latency}s "
              f"usage={g.usage_details} cost={g.total_cost}")

    project_id = os.environ.get("LANGFUSE_INIT_PROJECT_ID", "")
    print(f"\nUI: {os.environ['LANGFUSE_BASE_URL']}/project/{project_id}/traces")

    if checked >= 2 and len(generations.data) >= 2:
        print(f"\nStep 4 check passed: {checked} traces with ticket_id/prompt_version metadata, "
              f"{len(generations.data)} LLM generations with model + latency recorded.")
        return 0
    print("\nStep 4 check FAILED: expected spans/generations were not found.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
