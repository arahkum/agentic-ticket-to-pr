"""Step 7: pre-PR gate. Runs tests, secret scan, and diff-size check before
any PR is allowed to open - this is the "run_checks" activity in the
capstone pipeline architecture (see Part 3 of the plan)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from guardrails.clean_env import clean_env_for_agent
from guardrails.diff_limit import DiffTooLargeError, changed_line_count
from guardrails.secret_scan import SecretsFoundError, run_gitleaks


class GateFailure(RuntimeError):
    def __init__(self, check: str, detail: str) -> None:
        super().__init__(f"[{check}] {detail}")
        self.check = check
        self.detail = detail


def _repo_python(repo_path: str) -> str:
    """Use the target repo's own venv interpreter if it has one, so tests
    run with that repo's dependencies, not whatever venv the caller has active."""
    venv_python = Path(repo_path) / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else "python3"


def run_tests(repo_path: str) -> None:
    result = subprocess.run(
        [_repo_python(repo_path), "-m", "pytest", "-q"],
        cwd=repo_path,
        env=clean_env_for_agent(),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GateFailure("tests", f"pytest failed:\n{result.stdout}\n{result.stderr}")


def pre_pr_gate(repo_path: str, base_branch: str = "main", max_diff_lines: int = 300) -> dict:
    """Run all checks. Returns a summary dict if everything passes; raises
    GateFailure (tests/diff) or SecretsFoundError (secrets) on the first
    failure, so a CI step can just let the exception propagate to a red build."""
    run_tests(repo_path)

    try:
        changed_lines = changed_line_count(repo_path, base_branch, max_diff_lines)
    except DiffTooLargeError as exc:
        raise GateFailure("diff_size", str(exc)) from exc

    run_gitleaks(repo_path)

    return {"tests": "passed", "changed_lines": changed_lines, "secret_scan": "clean"}
