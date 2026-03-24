"""Backfill command — finds git commits without corresponding cognition episode nodes."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .storage import CognitionStorage


def _get_tracked_commit_hashes(storage: CognitionStorage) -> set[str]:
    """Get all commit hashes already tracked in the cognition graph."""
    hashes = set()
    for node in storage.get_all_nodes():
        for ref in node.get("references", []):
            if ref.startswith("commit:"):
                hashes.add(ref[7:])  # strip "commit:" prefix
    return hashes


def _get_recent_commits(repo_path: Path, days: int = 30) -> list[dict]:
    """Get recent git commits from the repo."""
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo_path), "log",
                f"--since={days} days ago",
                "--format=%H|%s|%an|%aI",
                "--no-merges",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                })
        return commits
    except Exception:
        return []


def _get_changed_files(repo_path: Path, commit_hash: str) -> list[str]:
    """Get list of files changed in a commit."""
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo_path), "diff-tree",
                "--no-commit-id", "--name-only", "-r", commit_hash,
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().split("\n") if f]
    except Exception:
        return []


def main():
    """Entry point for vibe-ragnar-backfill CLI command.

    Reports git commits without corresponding episode nodes, with
    instructions for creating episodes and entity nodes from them.
    """
    repo_path = Path(os.environ.get("REPO_PATH", Path.cwd()))
    cognition_dir = repo_path / ".cognition"

    if not cognition_dir.exists():
        print("No .cognition/ directory found. Run the vibe-ragnar MCP server first.")
        sys.exit(1)

    storage = CognitionStorage(cognition_dir)
    tracked_hashes = _get_tracked_commit_hashes(storage)
    commits = _get_recent_commits(repo_path)

    if not commits:
        print("No recent commits found (last 30 days).")
        sys.exit(0)

    untracked = [c for c in commits if c["hash"] not in tracked_hashes]
    tracked_count = len(commits) - len(untracked)

    if not untracked:
        print(f"All {len(commits)} recent commits are already tracked.")
        sys.exit(0)

    print(f"# Untracked Commits ({len(untracked)} found, {tracked_count} already tracked)")
    print()

    for commit in untracked:
        files = _get_changed_files(repo_path, commit["hash"])
        print(f"## Commit {commit['hash'][:8]} — \"{commit['message']}\"")
        print(f"  Author: {commit['author']} | Date: {commit['date']}")
        if files:
            print(f"  Files: {', '.join(files)}")
        print()

    print("---")
    print("For each commit above, create:")
    print("1. An EPISODE node (node_type: \"episode\") with the commit message as summary")
    print("   and changed files as context. Include \"commit:<hash>\" in references.")
    print("2. ENTITY nodes for any decisions, discoveries, constraints, or patterns")
    print("   visible in the commit. Keep entity summaries under 250 chars.")
    print("   Use the same references so the curator can link them to the episode.")


if __name__ == "__main__":
    main()
