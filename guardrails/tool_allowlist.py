"""Step 7: tool allowlist, path, and branch guards for a coding agent.

An agent implementing a ticket (Step 6) should only be able to call these
tools and touch these paths/branches. Anything else must be blocked before
it runs - this is what an MCP client or orchestrator wrapping the agent
would enforce (ties back to Step 2's tool-permission discussion).
"""
from __future__ import annotations

ALLOWED_TOOLS = {
    "read_file",
    "write_file",
    "run_tests",
    "git_diff",
    "git_commit",
    "git_push_feature_branch",  # deliberately no "git_push_main"
    "open_pr",
}

# substrings that mark a path as secret-like; the agent must never read or
# write these, regardless of which tool it's using.
BLOCKED_PATH_PATTERNS = (".env", "secret", "credential", "id_rsa", ".pem", ".key")

BLOCKED_BRANCHES = {"main", "master"}


class ToolNotAllowedError(RuntimeError):
    pass


def assert_tool_allowed(tool_name: str) -> None:
    if tool_name not in ALLOWED_TOOLS:
        raise ToolNotAllowedError(
            f"Tool {tool_name!r} is not in the allowlist: {sorted(ALLOWED_TOOLS)}"
        )


def assert_path_allowed(path: str) -> None:
    lowered = path.lower()
    for pattern in BLOCKED_PATH_PATTERNS:
        if pattern in lowered:
            raise ToolNotAllowedError(
                f"Path {path!r} matches a blocked pattern ({pattern!r}) - the "
                "coding agent must never read or write secret-like files."
            )


def assert_branch_allowed(branch: str) -> None:
    if branch in BLOCKED_BRANCHES:
        raise ToolNotAllowedError(
            f"Branch {branch!r} is blocked - the coding agent may only write "
            "to a feature branch, never directly to main/master."
        )
