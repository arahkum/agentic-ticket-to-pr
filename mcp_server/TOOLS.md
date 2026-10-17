# Pipeline MCP server

## What it exposes

| Tool | Type | Description |
|---|---|---|
| `generate_ticket_spec` | read-only | Ticket text -> structured JSON spec (Step 1's `spec_generator`). |
| `create_ticket_from_failed_test` | write (in-memory) | Failed test name + failure message -> a bug ticket. New in Step 2. |
| `list_tickets` | read-only | List tickets created so far in this server's in-memory store. |

Run it: `python mcp_server/server.py` (stdio transport).

## How a client discovers and calls a tool

1. **Connect**: the client spawns the server process and does the MCP
   handshake (`initialize`) over stdio (or attaches over HTTP for remote
   servers).
2. **Discover**: the client calls `tools/list`. The server returns each
   tool's `name`, `description`, and JSON Schema `inputSchema` (FastMCP
   derives the schema from the Python function signature + Pydantic types).
   The agent's LLM reads these descriptions to decide which tool to call and
   with what arguments — this is why descriptions must be precise and
   mention constraints (e.g. "file_path ... must be relative").
3. **Call**: the client calls `tools/call` with the tool name and a JSON
   argument object. The server validates the arguments, runs the tool, and
   returns a `CallToolResult` (text/structured content).
4. **Handle errors**: this server never raises an uncaught exception back to
   the transport for bad input — `create_ticket_from_failed_test` catches
   `pydantic.ValidationError` / `ValueError` and returns a plain dict with an
   `"error"` key, a `"detail"`, and a `"hint"`. The agent can read that and
   retry with corrected arguments instead of the whole tool call failing
   opaquely.

See `mcp_server/check_step2.py` for a minimal MCP client (using the official
Python SDK's `stdio_client` + `ClientSession`) that connects, lists tools,
and calls the new tool with both valid and invalid input.

## Permissions and security (what to add before this touches anything real)

- **Least privilege**: this server only has an in-memory list — it can't
  reach a real ticket tracker yet. If you wire it to Jira/GitHub Issues,
  scope the API token to only the needed project/repo and only the
  operations the tool needs (e.g. create issue, not delete repo).
- **Input validation at the boundary**: every tool validates its own inputs
  (lengths, path traversal) rather than trusting the caller — the caller is
  an LLM, which can be manipulated by injected text (see Step 7).
- **No secrets in tool output**: errors return a `hint`, never internal
  stack traces or credentials.
- **Tool allowlisting on the client side**: when an agent connects to this
  server, the *client* should still restrict which tools it's allowed to
  call per task (Step 7 covers this for the coding agent).
