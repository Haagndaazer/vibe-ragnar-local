"""PostToolUse hook — auto-creates cognition episode nodes from git commits.

Called by Claude Code after Bash tool executions. Detects successful git commit
commands and creates episode nodes in .cognition/journal.jsonl.

Hook config (.claude/settings.json):
{
  "PostToolUse": [{
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "python agents/hooks/post-commit.py"}]
  }]
}
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _generate_id(node_type: str, summary: str, timestamp: str) -> str:
    """Generate a hash-based node ID."""
    raw = f"{node_type}:{summary}:{timestamp}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _get_latest_commit(repo_path: str) -> dict | None:
    """Get the latest commit info from git."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "-1", "--format=%H|%s|%an|%aI"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split("|", 3)
        if len(parts) < 4:
            return None
        return {
            "hash": parts[0],
            "message": parts[1],
            "author": parts[2],
            "date": parts[3],
        }
    except Exception:
        return None


def _get_changed_files(repo_path: str, commit_hash: str) -> list[str]:
    """Get list of files changed in a commit."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().split("\n") if f]
    except Exception:
        return []


def _commit_already_tracked(journal_path: Path, commit_hash: str) -> bool:
    """Check if a commit hash already has a corresponding episode."""
    if not journal_path.exists():
        return False
    ref = f"commit:{commit_hash}"
    with open(journal_path, encoding="utf-8") as f:
        for line in f:
            if ref in line:
                return True
    return False


def _append_episode(journal_path: Path, commit: dict, files: list[str]) -> None:
    """Append an episode node to the JSONL journal."""
    timestamp = datetime.now(timezone.utc).isoformat()
    node_id = _generate_id("episode", commit["message"], timestamp)

    node_data = {
        "id": node_id,
        "type": "episode",
        "summary": commit["message"][:250],
        "detail": commit["message"],
        "context": files,
        "references": [f"commit:{commit['hash']}"],
        "severity": None,
        "timestamp": timestamp,
        "author": commit["author"],
    }

    entry = json.dumps({"action": "add_node", "data": node_data}, ensure_ascii=False)
    with open(journal_path, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def main():
    """PostToolUse hook entry point. Reads hook input from stdin."""
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        json.dump({}, sys.stdout)
        return

    # Only process Bash tool calls containing "git commit"
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    command = tool_input.get("command", "")

    if tool_name != "Bash" or "git commit" not in command:
        json.dump({}, sys.stdout)
        return

    # Get repo path from env or cwd
    repo_path = os.environ.get("REPO_PATH", os.getcwd())
    journal_path = Path(repo_path) / ".cognition" / "journal.jsonl"

    if not journal_path.parent.exists():
        json.dump({}, sys.stdout)
        return

    # Get the latest commit (we run git log ourselves rather than parsing tool output)
    commit = _get_latest_commit(repo_path)
    if not commit:
        json.dump({}, sys.stdout)
        return

    # Idempotency check
    if _commit_already_tracked(journal_path, commit["hash"]):
        json.dump({}, sys.stdout)
        return

    # Get changed files and create episode
    files = _get_changed_files(repo_path, commit["hash"])
    _append_episode(journal_path, commit, files)

    # Output empty response (hook doesn't need to inject context)
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
