---
description: Use this skill any time you need to retrieve or write project history to persistent memory. 
---

# Vibe Cognition — Project Knowledge Graph

## Tools

| Tool | Purpose |
|------|---------|
| `cognition_record` | Record a knowledge node or episode |
| `cognition_search` | Semantic search across all cognition nodes |
| `cognition_get_chain` | Traverse reasoning chains (LED_TO edges) from a node |
| `cognition_get_history` | Browse nodes by context area, type, or recency |

You do NOT create edges manually. A curator LLM automatically analyzes each new node and creates meaningful edges to related existing nodes.

## Two Kinds of Nodes

### Entities (concise facts)

Types: `decision`, `fail`, `discovery`, `assumption`, `constraint`, `incident`, `pattern`

Entities are **concise, searchable facts** — like index cards, not essays.

- **summary**: MAX 250 chars. Write like a commit message.
- **detail**: 1-3 sentences of rationale. NOT the full story.

### Episodes (full narratives)

Type: `episode`

Episodes capture the **complete narrative** of a body of work — a Linear task lifecycle, git push, a debugging session, a feature implementation. Create one when work is complete.

- **summary**: Brief title ("LL-298: Data wipe investigation and 3-phase fix")
- **detail**: The full story — everything that happened, all context. Verbose is fine here.

The curator auto-links entities to episodes via `PART_OF` edges when they share references.

## When to Record

**If in doubt, record it.** A node that turns out to be low-value costs nothing. A missing node when you need context later is expensive.

### Record entities when:
- You make or recommend a decision (and why)
- Something fails — a build, test, approach, or assumption
- You discover something non-obvious about the codebase
- You identify a reusable pattern or anti-pattern
- You hit a constraint (technical, API, platform)
- A production incident occurs
- An assumption is made that could later prove wrong

### Create episodes when:
- A Git push is done
- a Linear issue is completed.
- A significant debugging session concludes
- A feature implementation is done
- An incident is fully resolved

## Field Guide

### `node_type` (required)
One of: `decision`, `fail`, `discovery`, `assumption`, `constraint`, `incident`, `pattern`, `episode`

### `summary` (required)
For entities: MAX 250 chars. Someone scanning 50 nodes should understand what happened.
- Good: "Double-filter bug: query filters by language after already opening language-scoped box"
- Bad: "Found a bug in the flashcard data source that was causing data to be invisible after migration"

For episodes: Brief title of the work.

### `detail` (required)
For entities: 1-3 sentences of rationale or context.
- Good: "FlashcardLocalDataSourceImpl opens language-scoped box then redundantly filters by flashcard.language. Migrated cards have old format, making them invisible."
- Bad: [500-word root cause analysis]

For episodes: Full narrative. Be thorough — this is where verbose context belongs.

### `context` (required)
Comma-separated list of **both** specific file paths **and** topical terms. Used for filtering and discovery.
- Example: "flashcard_local_datasource.dart, HiveService, data migration, LL-298"

### `author` (required)
Use the current git user name.

### `severity` (optional)
`critical` / `high` / `normal` / `low`

### `references` (optional)
Comma-separated references to external resources. This is how the curator links entities to episodes.
- Examples: "issue:LL-298, pr:97" or "commit:ba64aeb"

## Querying

The cognition graph and code index are **separate search spaces**. Always query both:

1. `cognition_search` — Find decisions, failures, patterns by meaning
2. `cognition_get_history` — Browse by context area, type, or recency
3. `cognition_get_chain` — Follow causal chains from a specific node
4. `semantic_search` — Find code entities (functions, classes, types)

## Workflow Integration

- **During planning:** Record `decision` and `assumption` nodes
- **During implementation:** Record `discovery`, `pattern`, and `constraint` nodes
- **During debugging:** Record `fail` nodes
- **During incidents:** Record `incident` nodes
- **When work is complete:** Record an `episode` summarizing the full lifecycle
- **Always include** `references` (issue/PR numbers) so the curator can link related nodes

## Examples

### Concise entity during a task
```
cognition_record(
  node_type: "decision",
  summary: "Word Placement uses true drag-and-drop, placed in medium mastery tier",
  detail: "Draggable/DragTarget for positional knowledge testing. Harder than recognition, easier than full reconstruction.",
  context: "word_placement_review.dart, app_settings.dart mastery tiers",
  author: "Colton Dyck",
  references: "issue:LL-282, pr:100"
)
```

### Episode when task is complete
```
cognition_record(
  node_type: "episode",
  summary: "LL-282: Replace Sentence Reconstruction with Word Placement review type",
  detail: "Sentence Reconstruction required reordering ALL words — too broad for flashcard-specific review. Replaced with Word Placement: sentence displayed with target word removed as drop zone, user drags word to correct position. Key decisions: true drag-and-drop interaction, multi-word targets as single unit, first occurrence only blanked, medium mastery tier. SR kept for reinforcement phases. Reused fill_in_blank_utils.dart. Touched 7 files following the modular review type system.",
  context: "review_type_factory.dart, word_placement_review.dart, ReviewType enum, LL-282",
  author: "Colton Dyck",
  references: "issue:LL-282, pr:100"
)
```

### Recording a failure
```
cognition_record(
  node_type: "fail",
  summary: "Mocking Hive boxes masked type adapter registration issue — tests passed, prod crashed",
  detail: "Mock bypassed serialization path. ReviewSession adapter (ID 22) not registered in test setup.",
  context: "test/, Hive, mocking, serialization, ReviewSession",
  author: "Colton Dyck",
  severity: "high",
  references: "issue:LL-260"
)
```
