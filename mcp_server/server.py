"""Pipeline MCP server: exposes pipeline capabilities as MCP tools.

Run (stdio transport, used by Claude Code / Copilot / any MCP client):
    python mcp_server/server.py

Tools:
  - generate_ticket_spec      (the Step 1 capability, exposed as a tool)
  - create_ticket_from_failed_test   (Step 2 exercise: new tool, added with
    input validation and a clear error path)
"""
from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.spec_generator import SpecGenerationError, generate_spec

mcp = FastMCP("pipeline-tools")

# in-memory ticket store so this stays a self-contained learning exercise
# (no real Jira/GitHub Issues call) — swap for a real tracker API later.
_TICKETS: list[dict] = []


@mcp.tool()
def generate_ticket_spec(ticket_text: str) -> dict:
    """Turn a short, possibly vague feature ticket into a structured spec
    (user, problem, acceptance_criteria, edge_cases, test_cases) for the
    listings API. Read-only: does not write any ticket or file.
    """
    try:
        spec = generate_spec(ticket_text)
    except SpecGenerationError as exc:
        return {"error": f"spec generation failed: {exc}"}
    return spec.model_dump()


class FailedTestInput(BaseModel):
    """Validated input for create_ticket_from_failed_test."""

    test_name: str = Field(min_length=1, max_length=200)
    failure_message: str = Field(min_length=1, max_length=4000)
    file_path: str | None = Field(default=None, max_length=300)


def _validate_file_path(file_path: str | None) -> str | None:
    if file_path is None:
        return None
    # reject path traversal / absolute paths — this tool only ever reasons
    # about a relative test file path, it never opens the file itself.
    if file_path.startswith("/") or ".." in file_path:
        raise ValueError(f"file_path must be a safe relative path, got: {file_path!r}")
    return file_path


@mcp.tool()
def create_ticket_from_failed_test(
    test_name: str, failure_message: str, file_path: str | None = None
) -> dict:
    """Create a bug ticket from a failed test's name and failure output.

    Args:
        test_name: pytest/robot test identifier, e.g. "test_search_excludes_sold".
        failure_message: the assertion/error text from the test run.
        file_path: optional relative path to the failing test file, e.g.
            "tests/test_search.py". Absolute paths or ".." are rejected.

    Returns a dict with either the created ticket, or an "error" key
    describing exactly what was invalid and how to fix it.
    """
    try:
        data = FailedTestInput(
            test_name=test_name, failure_message=failure_message, file_path=file_path
        )
        safe_path = _validate_file_path(data.file_path)
    except (ValidationError, ValueError) as exc:
        return {
            "error": "invalid input",
            "detail": str(exc),
            "hint": "test_name and failure_message are required and non-empty; "
            "file_path (if given) must be a relative path with no '..'.",
        }

    ticket = {
        "id": f"BUG-{len(_TICKETS) + 1}",
        "title": f"Test failure: {data.test_name}",
        "body": data.failure_message,
        "file_path": safe_path,
        "source": "failed_test",
    }
    _TICKETS.append(ticket)
    return ticket


@mcp.tool()
def list_tickets() -> list[dict]:
    """List tickets created so far in this server's in-memory store."""
    return _TICKETS


if __name__ == "__main__":
    mcp.run()
