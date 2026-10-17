"""Step 1 'Done when' check: all 5 sample tickets must produce a schema-valid spec."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.spec_generator import SpecGenerationError, generate_spec

TICKETS_PATH = Path(__file__).resolve().parent / "dataset" / "sample_tickets.json"


def main() -> int:
    tickets = json.loads(TICKETS_PATH.read_text())
    passed = 0
    for ticket in tickets:
        try:
            spec = generate_spec(ticket["text"], ticket_id=ticket["id"])
            print(f"[PASS] {ticket['id']}: {ticket['text'][:60]!r}")
            print(f"       acceptance_criteria={len(spec.acceptance_criteria)} "
                  f"edge_cases={len(spec.edge_cases)} test_cases={len(spec.test_cases)}")
            passed += 1
        except SpecGenerationError as exc:
            print(f"[FAIL] {ticket['id']}: {exc}")

    total = len(tickets)
    print(f"\n{passed}/{total} tickets produced a schema-valid spec.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
