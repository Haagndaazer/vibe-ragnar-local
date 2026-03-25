![Main img](https://i.imgur.com/eeCrPjx.png)
![Python Version](https://img.shields.io/badge/python-3.11--3.13-blue?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat)
![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)
![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
![MCP](https://img.shields.io/badge/MCP-Server-purple?style=flat)
# Vibe RAGnar

A fully local [MCP](https://modelcontextprotocol.io/) server for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that combines code graph analysis with semantic search. After a one-time model download, all processing and storage happens on your machine — no API keys, no cloud services.

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Usage with Claude Code](#usage-with-claude-code)
- [MCP Tools](#mcp-tools)
- [Storage](#storage)
- [Cognition History Graph](#cognition-history-graph)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Agents (Optional)](#agents-optional)
- [Uninstall / Cleanup](#uninstall--cleanup)
- [Development](#development)

## Features

- **Local-First**: All processing and storage happens on your machine — no API keys, no cloud services
- **Graph Analysis**: Build and query code dependency graphs using NetworkX
- **Semantic Search**: Find code using natural language through local vector embeddings
- **Real-time Updates**: Automatic index updates when files change
- **Multi-language Support**: Python, TypeScript, JavaScript, Go, Rust, Java, C, C++, Dart
- **Privacy First**: Your code never leaves your machine

## How It Works

Vibe RAGnar uses:
- **ChromaDB** for local vector storage (stored in `.embeddings/` directory)
- **sentence-transformers** for generating embeddings locally
- **Tree-sitter** for parsing code across multiple languages
- **NetworkX** for building and querying the code dependency graph

### Embedding Model

By default, Vibe RAGnar uses [nomic-ai/nomic-embed-text-v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) from Hugging Face. The model is downloaded automatically on first run (~250MB).

Alternatively, you can use **Ollama** as an embedding backend if you prefer to manage models separately.

## Installation

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — Vibe RAGnar is an MCP server designed for Claude Code
- Python 3.11-3.13 (3.14+ not supported)
- [uv](https://github.com/astral-sh/uv) package manager
- Internet access for first run (downloads the embedding model, ~250MB)

#### Installing uv

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

> After installing, restart your terminal so `uv` is available on your PATH.

#### Resource Requirements

- **Disk**: ~2-4GB for Python dependencies (includes PyTorch), ~250MB for the embedding model (cached at `~/.cache/huggingface/`)
- **RAM**: ~1-2GB for the embedding model at runtime
- **Disk (if using curator)**: additional ~5.5GB for the Ollama model
- **GPU**: Not required. CPU is the default; GPU is used automatically when available

#### Platform Notes

Shell examples in this README use bash syntax (macOS, Linux, Git Bash on Windows). Key things to know:

- `uv sync`, `uv run`, and most commands work identically in PowerShell
- Claude Code on Windows uses its own bundled bash for hooks and the Bash tool, so hook commands in `.claude/settings.json` should use **forward-slash paths** (e.g., `C:/Users/me/vibe-ragnar`)
- `$PWD` works in both bash and PowerShell. If you use cmd.exe, substitute `%CD%` or the full path

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/BlckLvls/vibe-ragnar.git
   cd vibe-ragnar
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. **First-time setup** — Download the embedding model before first use:
   ```bash
   uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"
   ```
   This downloads the model (~250MB) so the MCP server can start quickly. If you've already downloaded it, re-running this command completes instantly — a quick way to verify setup.

   > `trust_remote_code=True` is required by the nomic model's custom architecture. The code comes from the [nomic-ai HuggingFace repository](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5). Review it there if you want to audit before first run.

4. **(Optional) Curator setup** — The cognition curator is **enabled by default** and uses [Ollama](https://ollama.com) to automatically link knowledge nodes. If you have Ollama installed, the curator model (`qwen3:8b`, ~5.5GB) is pulled automatically on first server start. If Ollama is not installed, the curator logs a warning and skips — nodes are stored but not connected. To explicitly disable:
   ```bash
   # Add --env CURATOR_ENABLED=false when registering the MCP server (see next section)
   ```

That's it! No API keys or external service configuration needed.

## Usage with Claude Code

Navigate to your project directory and add Vibe RAGnar as an MCP server:

```bash
cd /path/to/your-project

claude mcp add vibe-ragnar \
  --env REPO_PATH="$PWD" \
  -- uv run --directory /path/to/vibe-ragnar python -m vibe_ragnar.server
```

Replace `/path/to/vibe-ragnar` with the absolute path to your Vibe RAGnar clone. The `--` separates `claude mcp add` options from the server command.

`$PWD` expands to your current directory at the time you run this command, so make sure you run it from your project's root directory. Vibe RAGnar will index the project at that path.

> **Note:** After adding the MCP server, exit your current Claude Code session and start a new one for changes to take effect. Initial indexing runs in the background — search tools may return "still loading" for up to 30 seconds while the embedding model loads. Graph tools (`tool_get_function_calls`, `tool_get_callers`, etc.) are available immediately. Use `get_index_status` to check indexing progress.

## MCP Tools

### Code Tools

- `semantic_search` - Search CODE entities (functions, classes, types) by natural language
- `tool_get_function_calls` - Get functions called by a function
- `tool_get_callers` - Get functions that call a function
- `tool_get_call_chain` - Get recursive call tree
- `tool_get_class_hierarchy` - Get inheritance tree

### Cognition Tools

- `cognition_record` - Record a knowledge node (decision, fail, discovery, pattern, episode, etc.)
- `cognition_search` - Search PROJECT HISTORY (decisions, failures, patterns) by natural language
- `cognition_get_chain` - Traverse causal reasoning chains between nodes
- `cognition_get_history` - Browse cognition nodes by context area, type, or recency

### Service Tools

- `get_index_status` - Get indexing statistics
- `reindex` - Force reindex the codebase

## Storage

Vibe RAGnar stores data in two locations within your project:

```
your-project/
├── .cognition/
│   └── journal.jsonl       # Cognition graph (Git-committed, team-shared)
├── .embeddings/
│   ├── chromadb/            # Code vector embeddings
│   ├── cognition_chromadb/  # Cognition vector embeddings
│   └── graph.pickle         # Code dependency graph
└── ... your code
```

- **`.cognition/`** should be committed to Git — it's the shared project knowledge base
- **`.embeddings/`** should be in `.gitignore` — it's a regenerable cache (rebuilt automatically on next server startup if deleted)

Add `.embeddings/` to your project's `.gitignore`:
```bash
echo '.embeddings/' >> .gitignore
```

## Cognition History Graph

The cognition graph captures project knowledge — decisions made, approaches that failed, non-obvious discoveries, constraints, incidents, and patterns — so future sessions have context on *why* the code is the way it is.

### How It Works

1. **Record nodes** during conversations via `cognition_record` (or automatically via hooks)
2. **Curator LLM** (Qwen3 8B via Ollama) automatically creates edges between related nodes in the background
3. **Query** with `cognition_search` (semantic) or `cognition_get_history` (by context/type)
4. **Two search spaces**: `semantic_search` finds code, `cognition_search` finds project history — they're completely separate

### Node Types

| Type | Purpose |
|------|---------|
| `decision` | A choice between alternatives (and why) |
| `fail` | An approach that didn't work |
| `discovery` | A non-obvious finding |
| `assumption` | A premise being relied on |
| `constraint` | A hard limitation or scoping exclusion |
| `incident` | A production problem |
| `pattern` | A reusable lesson learned |
| `episode` | Full narrative of completed work (Linear task, feature, debugging session) |

### Edge Types (created automatically by curator)

| Edge | Meaning |
|------|---------|
| `led_to` | Causal chain — X led to Y |
| `supersedes` | X replaces Y |
| `contradicts` | X conflicts with Y |
| `relates_to` | Same topic, no causal link |
| `resolved_by` | Problem X was fixed by Y |
| `part_of` | Entity belongs to an episode |
| `duplicate_of` | X is semantically identical to Y |

### Setup: Curator (Optional but Recommended)

The curator is **enabled by default** (`CURATOR_ENABLED=true`). It uses a local Ollama LLM to automatically create meaningful edges between cognition nodes. Without it, nodes are stored but not connected.

1. Install [Ollama](https://ollama.com)
2. The curator model (`qwen3:8b`) is pulled automatically on first server start
3. Requires ~5.5GB VRAM (or runs on CPU, slower)

If Ollama is not installed or not running, the curator logs a warning and does not function — the server continues normally, but edges are not created.

To disable the curator explicitly, add `--env CURATOR_ENABLED=false` when registering the MCP server.

### Setup: Auto-Capture Hooks (Optional)

#### Prime — Inject project context at session start

The `vibe-ragnar-prime` command outputs recent constraints, patterns, decisions, and incidents. Configure it as a Claude Code hook so every session starts with project context:

Add to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "uv run --directory /path/to/vibe-ragnar vibe-ragnar-prime"
      }]
    }],
    "PreCompact": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "uv run --directory /path/to/vibe-ragnar vibe-ragnar-prime"
      }]
    }]
  }
}
```

> When run as a Claude Code hook from your project directory, `REPO_PATH` is not needed — the hook defaults to the current working directory.

#### Post-Commit — Auto-create episodes from git commits

The post-commit hook creates episode nodes automatically when commits happen during Claude Code sessions:

Add to your project's `.claude/settings.json` (merge with existing hooks):

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "python3 /path/to/vibe-ragnar/agents/hooks/post-commit.py"
      }]
    }]
  }
}
```

> This script uses only Python stdlib, so it does not require `uv run`. Use `python3` on macOS/Linux. On Windows, use `python` with forward-slash paths (e.g., `python C:/Users/me/vibe-ragnar/agents/hooks/post-commit.py`).

#### Backfill — Find commits missing episodes

The `vibe-ragnar-backfill` command finds recent git commits without corresponding episode nodes and outputs instructions for creating them:

**bash:**
```bash
cd /path/to/your-project
REPO_PATH="$PWD" uv run --directory /path/to/vibe-ragnar vibe-ragnar-backfill
```

**PowerShell:**
```powershell
cd C:\path\to\your-project
$env:REPO_PATH = "$PWD"; uv run --directory C:/path/to/vibe-ragnar vibe-ragnar-backfill
```

Also available as the `/vibe-backfill` skill in Claude Code if you copy `agents/vibe-backfill` to your project's `.claude/skills/` directory.

### Setup: Skill File (Optional)

Copy the `agents/vibe-cognition` directory from the Vibe RAGnar repo to your project's `.claude/skills/` directory. Create `.claude/skills/` first if it doesn't exist.

This teaches the LLM to use concise entity summaries (<250 chars), create episodes for completed work, and always include references for curator linking.

## Configuration

All configuration is optional. Vibe RAGnar works out of the box with sensible defaults.

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `REPO_PATH` | No | Current directory | Repository path to index |
| `REPO_NAME` | No | Directory name | Repository name for the index |
| `PERSIST_DIR` | No | `.embeddings` | Local storage directory |
| `INCLUDE_DIRS` | No | (none) | Directories to include even if normally ignored (comma-separated) |
| `EMBEDDING_BACKEND` | No | `sentence-transformers` | Backend: `sentence-transformers` or `ollama` |
| `EMBEDDING_MODEL` | No | `nomic-ai/nomic-embed-text-v1.5` | Model for sentence-transformers |
| `EMBEDDING_DIMENSIONS` | No | `768` | Embedding vector dimensions |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL (if using Ollama) |
| `OLLAMA_MODEL` | No | `nomic-embed-text` | Ollama embedding model |
| `CURATOR_ENABLED` | No | `true` | Enable automatic cognition edge curation via local LLM |
| `CURATOR_MODEL` | No | `qwen3:8b` | Ollama model for cognition graph curation |
| `CURATOR_MAX_CANDIDATES` | No | `8` | Max candidate nodes to evaluate per curation |
| `CHROMADB_COLLECTION` | No | `code_embeddings` | ChromaDB collection name |
| `DEBOUNCE_SECONDS` | No | `5.0` | File watcher debounce delay in seconds |
| `LOG_LEVEL` | No | `INFO` | Logging level |

### Using a `.env` File

Instead of passing `--env` flags, you can create a `.env` file in the vibe-ragnar directory:

```env
REPO_PATH=C:/Users/me/my-project
CURATOR_ENABLED=false
```

> **Windows users**: Always use forward slashes in `.env` file paths (e.g., `C:/Users/me/project`). Backslashes are interpreted as escape sequences by python-dotenv (`\t` = tab, `\n` = newline, `\v` = vertical tab), which will silently corrupt your paths.

### Using Ollama for Embeddings (Optional)

If you prefer to use Ollama for embeddings:

1. Install and start [Ollama](https://ollama.com)
2. Pull an embedding model: `ollama pull nomic-embed-text`
3. Configure Vibe RAGnar:
   ```bash
   claude mcp add vibe-ragnar \
     --env REPO_PATH="$PWD" \
     --env EMBEDDING_BACKEND="ollama" \
     -- uv run --directory /path/to/vibe-ragnar python -m vibe_ragnar.server
   ```

## Troubleshooting

**"Embedding model is still loading"** — Search tools need the embedding model, which loads in the background on startup (2-30 seconds). Graph tools work immediately. Wait and try again.

**ChromaDB lock / database errors** — Only one Vibe RAGnar instance can index a project at a time. Check for duplicate MCP server instances or other processes using `.embeddings/chromadb/`.

**Curator not creating edges** — Verify Ollama is running (`ollama list`). Without Ollama, the curator logs a warning and does not create edges. Nodes are still stored.

**Model download failures** — The embedding model (~250MB) is downloaded from Hugging Face on first run. Check your internet connection and proxy settings. Corporate firewalls may block Hugging Face downloads.

**Errors after Python upgrade** — The graph cache (`.embeddings/graph.pickle`) is Python-version-specific. Delete `.embeddings/` and restart the server to rebuild from scratch.

**General** — `.embeddings/` is always safe to delete. It is fully regenerated on the next server startup.

## Agents (Optional)

Vibe RAGnar comes with Claude Code agents optimized for code exploration and planning using the MCP tools.

### Install Agents

**bash (macOS / Linux / Git Bash on Windows):**

```bash
curl -sL https://raw.githubusercontent.com/BlckLvls/vibe-ragnar/main/scripts/install-agents.sh | bash
```

> When piped from `curl`, the script skips interactive prompts and uses defaults. To choose options interactively, download the script first and run it directly.

**PowerShell (Windows):**

```powershell
New-Item -ItemType Directory -Force -Path .claude\agents
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/BlckLvls/vibe-ragnar/main/agents/explore.md" -OutFile ".claude\agents\explore.md"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/BlckLvls/vibe-ragnar/main/agents/plan.md" -OutFile ".claude\agents\plan.md"
```

This installs agents to `.claude/agents/` in your current directory.

> **Warning:** These agents replace Claude Code's built-in `Explore` and `Plan` agents. Once installed, any task that uses these agents (including Plan Mode) will use Vibe RAGnar's graph and semantic search instead of the default behavior. To restore defaults, delete the `.claude/agents/` directory. If you already have custom agents there, back them up first.

### Available Agents

| Agent | Description |
|-------|-------------|
| `explore` | Fast codebase exploration combining graph traversal with semantic search |
| `plan` | Implementation planning with deep code analysis and dependency mapping |

## Uninstall / Cleanup

To remove Vibe RAGnar:

1. Remove the MCP server:
   ```bash
   claude mcp remove vibe-ragnar
   ```

2. Delete the regenerable cache from your project:
   ```bash
   rm -rf .embeddings/
   ```

3. Optionally delete the cognition history (warning: this deletes shared project knowledge):
   ```bash
   rm -rf .cognition/
   ```

4. Remove any hooks you added to `.claude/settings.json` (SessionStart, PreCompact, PostToolUse entries for vibe-ragnar)

5. Remove the cached embedding model (shared across all projects):
   ```bash
   rm -rf ~/.cache/huggingface/hub/models--nomic-ai--nomic-embed-text-v1.5/
   ```

## Development

```bash
# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Run type checking
uv run pyright
```

## License

MIT
