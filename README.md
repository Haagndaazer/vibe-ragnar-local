![Main img](https://i.imgur.com/eeCrPjx.png)
![Python Version](https://img.shields.io/badge/python-3.11--3.13-blue?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat)
![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)
![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
![MCP](https://img.shields.io/badge/MCP-Server-purple?style=flat)
# Vibe RAGnar

A fully local MCP server for code indexing that combines graph analysis with semantic search. No external services or API keys required.

## Features

- **100% Local**: All processing and storage happens on your machine - no API keys, no cloud services
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

- Python 3.11-3.13 (3.14+ not supported)
- [uv](https://github.com/astral-sh/uv) package manager

#### Installing uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

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

3. **First-time setup** - Download the embedding model before first use:
   ```bash
   uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"
   ```
   This downloads the model (~250MB) so the MCP server can start quickly.

That's it! No API keys or external service configuration needed.

## Usage with Claude Code

Navigate to your project directory and add Vibe RAGnar as an MCP server:

```bash
cd /path/to/your-project

claude mcp add vibe-ragnar \
  --env REPO_PATH="$PWD" \
  -- uv run --directory /path/to/vibe-ragnar python -m vibe_ragnar.server
```

`$PWD` automatically expands to your current directory, so Vibe RAGnar will index the project you're in.

> **Note:** After adding the MCP server, restart Claude Code to apply changes. Initial indexing runs in the background. Use `get_index_status` to check indexing progress.

## MCP Tools

### Code Tools

- `semantic_search` - Search CODE entities (functions, classes, types) by natural language
- `get_function_calls` - Get functions called by a function
- `get_callers` - Get functions that call a function
- `get_call_chain` - Get recursive call tree
- `get_class_hierarchy` - Get inheritance tree

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
- **`.embeddings/`** should be in `.gitignore` — it's a regenerable cache

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

### Setup: Curator (Optional but Recommended)

The curator uses a local Ollama LLM to automatically create meaningful edges between cognition nodes. Without it, nodes are stored but not connected.

1. Install [Ollama](https://ollama.ai)
2. The curator model (`qwen3:8b`) is pulled automatically on first server start
3. Requires ~5.5GB VRAM (or runs on CPU, slower)

To disable the curator: set `CURATOR_ENABLED=false`.

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

The `REPO_PATH` env var (set in `.mcp.json`) tells prime which project's `.cognition/` to read.

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
        "command": "python /path/to/vibe-ragnar/agents/hooks/post-commit.py"
      }]
    }]
  }
}
```

#### Backfill — Find commits missing episodes

The `vibe-ragnar-backfill` command finds recent git commits without corresponding episode nodes and outputs instructions for creating them:

```bash
cd /path/to/your-project
REPO_PATH="$PWD" uv run --directory /path/to/vibe-ragnar vibe-ragnar-backfill
```

Also available as the `/vibe-backfill` slash command in Claude Code.

### Setup: Skill File (Optional)

Copy the cognition skill to your project for LLM guidance on when and how to record knowledge:

```bash
cp -r /path/to/vibe-ragnar/agents/vibe-cognition /path/to/your-project/.claude/skills/
```

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
| `LOG_LEVEL` | No | `INFO` | Logging level |

### Using Ollama (Optional)

If you prefer to use Ollama for embeddings:

1. Install and start [Ollama](https://ollama.ai)
2. Pull an embedding model: `ollama pull nomic-embed-text`
3. Configure Vibe RAGnar:
   ```bash
   claude mcp add vibe-ragnar \
     --env REPO_PATH="$PWD" \
     --env EMBEDDING_BACKEND="ollama" \
     -- uv run --directory /path/to/vibe-ragnar python -m vibe_ragnar.server
   ```

## Agents (Optional)

Vibe RAGnar comes with Claude Code agents optimized for code exploration and planning using the MCP tools.

### Install Agents

```bash
curl -sL https://raw.githubusercontent.com/BlckLvls/vibe-ragnar/main/scripts/install-agents.sh | bash
```

This installs agents to `.claude/agents/` in your current directory.

> **Warning:** These agents replace Claude Code's built-in `Explore` and `Plan` agents. Once installed, any task that uses these agents (including Plan Mode) will use Vibe RAGnar's graph and semantic search instead of the default behavior. To restore defaults, delete the `.claude/agents/` directory.

### Available Agents

| Agent | Description |
|-------|-------------|
| `explore` | Fast codebase exploration combining graph traversal with semantic search |
| `plan` | Implementation planning with deep code analysis and dependency mapping |

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
