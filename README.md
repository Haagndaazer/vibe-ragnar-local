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

### Service Tools

- `get_index_status` - Get indexing statistics
- `reindex` - Force reindex the codebase

## Storage

Vibe RAGnar stores data in two locations within your project:

```
your-project/
├── .embeddings/
│   ├── chromadb/            # Code vector embeddings
│   └── graph.pickle         # Code dependency graph
└── ... your code
```

- **`.embeddings/`** should be in `.gitignore` — it's a regenerable cache (rebuilt automatically on next server startup if deleted)

Add `.embeddings/` to your project's `.gitignore`:
```bash
echo '.embeddings/' >> .gitignore
```

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
| `CHROMADB_COLLECTION` | No | `code_embeddings` | ChromaDB collection name |
| `DEBOUNCE_SECONDS` | No | `5.0` | File watcher debounce delay in seconds |
| `LOG_LEVEL` | No | `INFO` | Logging level |

### Using a `.env` File

Instead of passing `--env` flags, you can create a `.env` file in the vibe-ragnar directory:

```env
REPO_PATH=C:/Users/me/my-project
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

3. Remove the cached embedding model (shared across all projects):
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
