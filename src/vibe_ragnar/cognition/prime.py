"""Prime command — outputs compact project context for Claude Code session injection."""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .models import CognitionNodeType
from .storage import CognitionStorage

SEVERITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}


def _format_node(node: dict) -> str:
    """Format a single node as a compact bullet point."""
    severity = node.get("severity")
    suffix = f" (severity: {severity})" if severity else ""
    return f"- [{node.get('type', '?')}] {node.get('summary', 'No summary')}{suffix}"


def _format_constraints(storage: CognitionStorage) -> str:
    """Format active constraints, sorted by severity."""
    nodes = storage.get_nodes_by_type(CognitionNodeType.CONSTRAINT)
    if not nodes:
        return ""

    nodes.sort(key=lambda n: SEVERITY_ORDER.get(n.get("severity", "normal"), 2))
    lines = [_format_node(n) for n in nodes]
    return "## Active Constraints\n" + "\n".join(lines)


def _format_patterns(storage: CognitionStorage, limit: int = 5) -> str:
    """Format recent patterns."""
    nodes = storage.get_recent_nodes(limit=limit, node_type=CognitionNodeType.PATTERN)
    if not nodes:
        return ""

    lines = [_format_node(n) for n in nodes]
    return "## Recent Patterns\n" + "\n".join(lines)


def _format_decisions(storage: CognitionStorage, limit: int = 5) -> str:
    """Format recent decisions."""
    nodes = storage.get_recent_nodes(limit=limit, node_type=CognitionNodeType.DECISION)
    if not nodes:
        return ""

    lines = [_format_node(n) for n in nodes]
    return "## Recent Decisions\n" + "\n".join(lines)


def _format_incidents(storage: CognitionStorage, days: int = 30) -> str:
    """Format recent incidents from the last N days."""
    nodes = storage.get_nodes_by_type(CognitionNodeType.INCIDENT)
    if not nodes:
        return ""

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    recent = [n for n in nodes if n.get("timestamp", "") >= cutoff]
    if not recent:
        return ""

    recent.sort(key=lambda n: SEVERITY_ORDER.get(n.get("severity", "normal"), 2))
    lines = [_format_node(n) for n in recent]
    return "## Recent Incidents\n" + "\n".join(lines)


def generate_prime(storage: CognitionStorage) -> str:
    """Generate the prime markdown output.

    Args:
        storage: Hydrated CognitionStorage instance

    Returns:
        Markdown string with project context
    """
    sections = [
        _format_constraints(storage),
        _format_patterns(storage),
        _format_decisions(storage),
        _format_incidents(storage),
    ]

    body = "\n\n".join(s for s in sections if s)
    if not body:
        body = "No cognition history recorded yet."

    return (
        "# Vibe RAGnar — Project Context\n\n"
        + body
        + "\n\nUse cognition_search and cognition_get_history for full details."
    )


def main():
    """Entry point for vibe-ragnar-prime CLI command.

    Outputs JSON for Claude Code SessionStart/PreCompact hooks.
    Reads REPO_PATH env var or uses cwd. Exits silently if .cognition/ doesn't exist.
    """
    repo_path = Path(os.environ.get("REPO_PATH", Path.cwd()))
    cognition_dir = repo_path / ".cognition"

    if not cognition_dir.exists():
        # Not a cognition-enabled project — exit silently
        sys.exit(0)

    storage = CognitionStorage(cognition_dir)
    markdown = generate_prime(storage)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": markdown,
        }
    }
    json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
