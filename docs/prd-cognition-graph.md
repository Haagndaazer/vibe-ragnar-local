# PRD: Cognition History Graph

## Overview

A second, separate graph alongside the existing code knowledge graph that captures the **history of cognition** — decisions made, failures encountered, discoveries found, and reasoning chains — across LLM conversations. When querying, both graphs are queried independently, giving the LLM a holistic picture: the code graph provides *what the code is*, the cognition graph provides *why it's that way and what was tried before*.

## Problem Statement

When teammates pick up work on unfamiliar parts of a codebase, they lack context on:
- What approaches were already tried and failed
- Why specific decisions were made
- What pitfalls to avoid
- The reasoning chain that led to the current implementation

This knowledge currently lives in people's heads or scattered across chat logs and is effectively lost.

## Core Concept

- **Two completely separate graphs** — no cross-linking or joining between the code graph and cognition graph
- The LLM writes to the cognition graph explicitly via **MCP tools** during conversations
- Typed node writes (`decision`, `fail`, etc.) ensure only intentional entries are recorded
- The LLM consuming query results from both graphs performs the synthesis — no formal join mechanism needed

## Node Schema

```
{
  id: string,               // SHA256(type, summary, timestamp) truncated to 12 hex chars
  type: "decision" | "fail" | "discovery" | "assumption" | "constraint" | "incident" | "pattern",
  summary: string,          // short description
  detail: string,           // full context and reasoning
  context: string[],        // related code areas, file paths, topics
  references: string[],     // external refs: "pr:97", "issue:LL-298", "commit:abc123"
  severity: "critical" | "high" | "normal" | "low" | null,
  timestamp: string,        // ISO 8601
  author: string            // who was in the conversation
}
```

ID generation: SHA256 of `(type, summary, timestamp)` truncated to 12 hex chars. Hash-based IDs (inspired by Beads) prevent merge conflicts when multiple users/agents create nodes concurrently on different branches.

### Node Types

| Type | Purpose | Example |
|------|---------|---------|
| `decision` | A deliberate choice between alternatives | "Replace Sentence Reconstruction with Word Placement for regular reviews" |
| `fail` | An approach tried during development that didn't work | "Tried using device locale for box names — broke migration" |
| `discovery` | A non-obvious finding about the system | "Double-filter bug: query filters by language after already opening language-scoped box" |
| `assumption` | A premise the current approach relies on | "Assuming max 10k concurrent users for connection pool sizing" |
| `constraint` | A hard requirement, scoping exclusion, or defensive rule | "Box names must NEVER be localized"; "Do NOT delete SentenceReconstruction widget — used by reinforcement" |
| `incident` | A reported problem affecting users or production | "Release wiped out user flashcard data — P1 urgent" |
| `pattern` | A recurring lesson learned that applies broadly | "French translations are ~30% longer than English — always check overflow when adding translations" |

## Edge Types

Directional edges that capture reasoning chains:

| Edge | Meaning | Example |
|------|---------|---------|
| `LED_TO` | One event caused or motivated another | `discovery:missing-localization` → `decision:add-translations` |
| `SUPERSEDES` | New entry replaces a previous one | `decision:v2` → `decision:v1` |
| `CONTRADICTS` | New finding conflicts with prior belief | `discovery:not-localization-PR` → `assumption:localization-caused-wipe` |
| `RELATES_TO` | Topical connection (use sparingly) | `decision:word-placement` → `constraint:keep-SR-for-reinforcement` |
| `RESOLVED_BY` | A problem was fixed by this action | `incident:data-wipe` → `decision:remove-double-filter` |

The value of graph structure depends on `LED_TO`, `SUPERSEDES`, and `RESOLVED_BY` edges creating traversable reasoning chains. If most edges are `RELATES_TO`, the graph degenerates into a tagged document store.

## MCP Tools

### Write Tools

- **`cognition_record_decision`** — Record a decision with alternatives considered
- **`cognition_record_fail`** — Record a failed approach with reason
- **`cognition_record_discovery`** — Record a non-obvious finding
- **`cognition_record_assumption`** — Record an underlying assumption
- **`cognition_record_constraint`** — Record a hard constraint or scoping exclusion
- **`cognition_record_incident`** — Record a production problem or reported issue
- **`cognition_record_pattern`** — Record a generalized lesson learned

Each write tool optionally accepts `led_from` (existing node ID) to create a `LED_TO` edge inline, plus `severity` and `references`.

### Edge Tool

- **`cognition_add_edge`** — Create an edge between existing nodes (any edge type)

### Query Tools

- **`cognition_search`** — Semantic search over cognition nodes via ChromaDB
- **`cognition_get_chain`** — Given a node, traverse `LED_TO` edges to get the full reasoning chain
- **`cognition_get_history`** — Get all cognition nodes for a given context area
- **`cognition_get_recent`** — Get recent nodes by type or globally

## Query Flow

When a user or LLM asks about a part of the codebase:

1. **Code graph** is queried — returns code structure, call chains, dependencies
2. **Cognition graph** is queried — returns decisions, failures, discoveries related to that area
3. The LLM **synthesizes both result sets** in its response, providing code facts and historical context together

No formal cross-graph linking required. The `context` field on cognition nodes and semantic search provide the loose coupling.

## Resolved Design Decisions

### Storage: Hybrid JSONL + NetworkX + ChromaDB (inspired by Beads)
- **JSONL** (`.cognition/journal.jsonl`) — append-only source of truth, Git-committed, team-friendly
  - Each line is a JSON object with an `action` discriminator (`add_node`, `add_edge`, `update_node`)
  - Append-only format minimizes Git merge conflicts across branches
  - Hash-based IDs prevent node collision from concurrent writes
- **NetworkX DiGraph** — hydrated from JSONL at startup for graph traversals (chains, supersedes)
- **ChromaDB** (`cognition_embeddings` collection) — embeddings of node summary+detail for semantic search
  - Stored in `.embeddings/cognition_chromadb/` (gitignored, regenerable from JSONL)
  - On startup, any JSONL nodes missing from ChromaDB are automatically embedded and upserted (handles teammates' Git-pulled entries)

### Entry Point Discovery: Semantic Search via ChromaDB
- Node summary+detail text is embedded using the same `EmbeddingGenerator` (nomic-embed-text-v1.5) as code embeddings
- `cognition_search` tool queries the `cognition_embeddings` ChromaDB collection
- Reuses existing `ChromaDBStorage.vector_search()` — no new search infrastructure needed

### When Does the LLM Write: Via MCP Tools
- Write tools (`cognition_record_*`) are available to the LLM as MCP tools
- The LLM decides when to use them based on system prompt guidance or explicit user instruction
- Each write tool optionally accepts a `led_from` parameter to create a `LED_TO` edge from an existing node

### Edge Creation: Optional `led_from` Parameter on Writes
- Write tools accept an optional `led_from` node ID to create edges inline
- Separate `cognition_add_edge` tool for explicit edge creation between existing nodes
- This is pragmatic — edges get created when the LLM has context, without requiring a separate search-then-link step

### Duplicate/Conflict Resolution: `SUPERSEDES` Edges + Timestamps
- `SUPERSEDES` edges are the primary mechanism — new decisions explicitly reference what they replace
- Timestamps provide fallback ordering when edges are absent
- The querying LLM can resolve remaining ambiguity from both signals

### Growth Management: Future Compaction (Inspired by Beads)
- **v1**: No automatic pruning — monitor growth in practice
- **Future**: LLM-summarized compaction (like Beads' `bd compact`) — old nodes get condensed summaries, preserving essential context while reducing noise

## Remaining Open Questions

### When Does the LLM Write?
- System prompt guidance vs explicit user instruction — needs experimentation to find the right balance
- Risk of over-recording (noise) vs under-recording (lost knowledge)

### Edge Creation Quality
- Will the LLM reliably use `led_from` and `cognition_add_edge`?
- May need system prompt examples or few-shot guidance

## JSONL Format Specification

```jsonl
{"action":"add_node","data":{"id":"a1b2c3d4e5f6","type":"decision","summary":"Use Redis for caching","detail":"Chose over Memcached due to pub/sub support for cache invalidation","context":["src/cache/","caching strategy"],"timestamp":"2026-03-15T10:30:00Z","author":"alice"}}
{"action":"add_edge","data":{"from_id":"f6e5d4c3b2a1","to_id":"a1b2c3d4e5f6","edge_type":"led_to","timestamp":"2026-03-15T10:31:00Z"}}
{"action":"update_node","data":{"id":"a1b2c3d4e5f6","detail":"Updated: also need sorted sets for leaderboards"}}
```

## Implementation Architecture

### New Package: `src/vibe_ragnar/cognition/`
- `models.py` — Pydantic models (`CognitionNode`, `CognitionEdge`), enums (`CognitionNodeType`, `CognitionEdgeType`), ID generation
- `storage.py` — `CognitionStorage` class: JSONL persistence, NetworkX hydration, node/edge CRUD
- `queries.py` — Query functions: `get_reasoning_chain`, `get_superseded_chain`, `get_history_for_context`

### New Tools: `src/vibe_ragnar/tools/cognition_tools.py`
- 5 write tools (one per node type) with optional `led_from` for inline edge creation
- 1 edge tool (`cognition_add_edge`)
- 4 query tools (`cognition_search`, `cognition_get_chain`, `cognition_get_history`, `cognition_get_recent`)

### Modified Files
- `config.py` — Add `cognition_dir` and `cognition_chromadb_path` properties
- `server.py` — Initialize `CognitionStorage` + second `ChromaDBStorage` in lifespan, add to context
- `tools/__init__.py` — Register cognition tools

### Reuse from Existing Codebase
- `ChromaDBStorage` class (second instance, different collection)
- `EmbeddingGenerator` (shared instance)
- NetworkX CRUD patterns from `graph/storage.py`
- Recursive DFS traversal pattern from `graph/queries.py:get_call_chain`
- MCP tool registration pattern from `tools/graph_tools.py`

## v1 Scope

1. Node schema with 5 types + hash-based IDs
2. JSONL persistence with NetworkX hydration
3. ChromaDB semantic search on cognition nodes
4. MCP write tools (one per type) with `led_from` support
5. `cognition_add_edge` tool
6. `cognition_search`, `cognition_get_chain`, `cognition_get_history`, `cognition_get_recent` query tools
7. Server integration (initialization, startup embedding sync from JSONL)
8. Tests
