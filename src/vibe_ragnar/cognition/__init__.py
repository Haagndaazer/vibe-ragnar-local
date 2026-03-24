"""Cognition History Graph — captures decisions, failures, discoveries, and reasoning chains."""

from .models import CognitionEdge, CognitionEdgeType, CognitionNode, CognitionNodeType, generate_node_id
from .queries import (
    get_history_for_context,
    get_incident_resolution,
    get_reasoning_chain,
    get_superseded_chain,
)
from .storage import CognitionStorage

# CognitionCurator is NOT imported here to avoid pulling in the heavy
# embeddings/sentence-transformers dependency chain at import time.
# Import it directly: from vibe_ragnar.cognition.curator import CognitionCurator

__all__ = [
    # Models
    "CognitionEdge",
    "CognitionEdgeType",
    "CognitionNode",
    "CognitionNodeType",
    "generate_node_id",
    # Storage
    "CognitionStorage",
    # Queries
    "get_history_for_context",
    "get_incident_resolution",
    "get_reasoning_chain",
    "get_superseded_chain",
]
