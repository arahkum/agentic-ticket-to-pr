"""Step 2 'Done when' check: an MCP client discovers and calls the new tool.

Spawns mcp_server/server.py over stdio, lists tools, then calls
create_ticket_from_failed_test with (1) valid input and (2) invalid input
to prove both the happy path and the error path work.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = Path(__file__).resolve().parent / "server.py"


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"Discovered tools: {names}")
            assert "create_ticket_from_failed_test" in names, "new tool not found"

            # happy path
            result = await session.call_tool(
                "create_ticket_from_failed_test",
                {
                    "test_name": "test_search_excludes_sold",
                    "failure_message": "AssertionError: expected 0 sold listings, got 3",
                    "file_path": "tests/test_search.py",
                },
            )
            print("Valid call result:", result.content[0].text)

            # error path: empty failure_message should be rejected, not crash
            bad_result = await session.call_tool(
                "create_ticket_from_failed_test",
                {"test_name": "test_x", "failure_message": ""},
            )
            print("Invalid call result:", bad_result.content[0].text)
            assert "error" in bad_result.content[0].text, "invalid input should return an error"

            # path traversal should also be rejected
            traversal_result = await session.call_tool(
                "create_ticket_from_failed_test",
                {
                    "test_name": "test_y",
                    "failure_message": "boom",
                    "file_path": "../../etc/passwd",
                },
            )
            print("Path traversal result:", traversal_result.content[0].text)
            assert "error" in traversal_result.content[0].text, "path traversal should be rejected"

    print("\nAll Step 2 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
