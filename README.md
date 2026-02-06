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

> **Note:** After adding the MCP server, restart Claude Code to apply changes. The first run will download the embedding model (~250MB) and index your codebase. Use `get_index_status` to check indexing progress.

## MCP Tools

### Graph Tools

- `get_function_calls` - Get functions called by a function
- `get_callers` - Get functions that call a function
- `get_call_chain` - Get recursive call tree
- `get_class_hierarchy` - Get inheritance tree

### Search Tools

- `semantic_search` - Search code by natural language description

### Service Tools

- `get_index_status` - Get indexing statistics
- `reindex` - Force reindex the codebase

## Storage

Vibe RAGnar stores all data locally in a `.embeddings/` directory within your project:

```
your-project/
├── .embeddings/
│   ├── chromadb/      # Vector embeddings database
│   └── graph.pickle   # Code dependency graph
└── ... your code
```

Add `.embeddings/` to your `.gitignore` to avoid committing the index.

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
