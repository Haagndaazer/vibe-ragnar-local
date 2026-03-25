---
description: Find git commits without corresponding cognition episodes and create nodes for them. Run this to backfill the cognition graph with commit history.
---

# Vibe Backfill — Create Cognition Nodes from Git Commits

## What This Does

Finds recent git commits that don't have corresponding episode nodes in the cognition graph, then creates episodes and entity nodes for them.

## Steps

1. Run the backfill command to find untracked commits:

```bash
uv run --directory /path/to/vibe-ragnar vibe-ragnar-backfill
```

2. For each untracked commit listed in the output, create cognition nodes using `cognition_record`:

   **First, create an EPISODE for the commit:**
   ```
   cognition_record(
     node_type: "episode",
     summary: "<commit message, max 250 chars>",
     detail: "<full commit message + summary of what the commit accomplished>",
     context: "<changed files, comma-separated>",
     author: "<commit author>",
     references: "commit:<full hash>"
   )
   ```

   **Then, extract ENTITY nodes** for any decisions, discoveries, constraints, or patterns visible in the commit:
   ```
   cognition_record(
     node_type: "decision" | "discovery" | "constraint" | "pattern" | ...,
     summary: "<concise fact, max 250 chars>",
     detail: "<1-3 sentence rationale>",
     context: "<relevant files from the commit>",
     author: "<commit author>",
     references: "commit:<full hash>"
   )
   ```

3. Use the same `references` value (commit hash) for both the episode and its entities so the curator can link them via PART_OF edges.

## Guidelines

- Not every commit needs entity nodes — simple refactors or typo fixes may only need the episode
- Look at the commit message and changed files to determine what entities to extract
- Keep entity summaries under 250 chars — concise, scannable facts
- The curator LLM will automatically create edges between the new nodes and existing related nodes
