"""Step 7: diff-size limit. A coding agent's PR should touch a bounded amount
of code - a huge diff is harder to review and more likely to hide something."""
from __future__ import annotations

import subprocess


class DiffTooLargeError(RuntimeError):
    pass


def changed_line_count(repo_path: str, base_branch: str = "main", max_lines: int = 300) -> int:
    """Returns total changed lines (insertions + deletions) between the
    current branch and base_branch. Raises DiffTooLargeError if over the limit."""
    result = subprocess.run(
        ["git", "diff", "--shortstat", f"{base_branch}...HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    stat = result.stdout.strip()
    insertions = _extract(stat, "insertion")
    deletions = _extract(stat, "deletion")
    total = insertions + deletions

    if total > max_lines:
        raise DiffTooLargeError(
            f"Diff has {total} changed lines (base={base_branch}), limit is {max_lines}. "
            f"Raw stat: {stat!r}"
        )
    return total


def _extract(stat: str, word: str) -> int:
    for part in stat.split(","):
        if word in part:
            digits = "".join(ch for ch in part if ch.isdigit())
            return int(digits) if digits else 0
    return 0
