"""Data models for the Cognition History Graph."""

import hashlib
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class CognitionNodeType(str, Enum):
    """Types of nodes in the cognition graph."""

    DECISION = "decision"
    FAIL = "fail"
    DISCOVERY = "discovery"
    ASSUMPTION = "assumption"
    CONSTRAINT = "constraint"
    INCIDENT = "incident"
    PATTERN = "pattern"
    EPISODE = "episode"


class CognitionEdgeType(str, Enum):
    """Types of edges in the cognition graph."""

    LED_TO = "led_to"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    RELATES_TO = "relates_to"
    RESOLVED_BY = "resolved_by"
    PART_OF = "part_of"
    DUPLICATE_OF = "duplicate_of"


class CognitionNode(BaseModel):
    """A node in the cognition history graph."""

    id: str
    type: CognitionNodeType
    summary: str
    detail: str
    context: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    severity: str | None = None
    timestamp: str
    author: str


class CognitionEdge(BaseModel):
    """An edge in the cognition history graph."""

    from_id: str
    to_id: str
    edge_type: CognitionEdgeType
    timestamp: str


def generate_node_id(node_type: str, summary: str, timestamp: str | None = None) -> str:
    """Generate a hash-based node ID that is conflict-free across branches/users.

    Args:
        node_type: The type of the node
        summary: The summary text
        timestamp: ISO 8601 timestamp (defaults to now)

    Returns:
        12-character hex string
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    raw = f"{node_type}:{summary}:{timestamp}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]
