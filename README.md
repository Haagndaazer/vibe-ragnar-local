# Vibe RAGnar

> "Let your AI raid your codebase"

A lightweight MCP server for code indexing that combines graph analysis with semantic search through vector embeddings.

## Features

- **Graph Analysis**: Build and query code dependency graphs using NetworkX
- **Semantic Search**: Find code using natural language through vector embeddings
- **Real-time Updates**: Automatic index updates when files change
- **Multi-language Support**: Python, TypeScript, JavaScript, Go, Rust, Java, C, C++
- **Single Process**: No Docker or external services needed (except MongoDB Atlas)

## Installation

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- MongoDB Atlas account (for vector storage)
- Voyage AI API key (for embeddings)

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

3. Set up environment variables (optional, can also pass via `claude mcp add`):
   ```bash
   export MONGODB_URI="mongodb+srv://your-connection-string"
   export VOYAGE_API_KEY="your-voyage-api-key"
   ```

## Usage with Claude Code

Add Vibe RAGnar as an MCP server to your project:

```bash
claude mcp add vibe-ragnar \
  --env MONGODB_URI="mongodb+srv://your-connection-string" \
  --env VOYAGE_API_KEY="your-voyage-api-key" \
  -- uv run --directory /path/to/vibe-ragnar python -m vibe_ragnar.server
```

You can explicitly specify the repository to index with `REPO_PATH`:

```bash
claude mcp add vibe-ragnar \
  --env MONGODB_URI="mongodb+srv://your-connection-string" \
  --env VOYAGE_API_KEY="your-voyage-api-key" \
  --env REPO_PATH="/path/to/repo-to-index" \
  -- uv run --directory /path/to/vibe-ragnar python -m vibe_ragnar.server
```

> **Note:** After adding the MCP server, restart Claude Code to apply changes. The first startup may take ~5 minutes for initial indexing: creating MongoDB collections, building vector indexes, and generating embeddings for your codebase.

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

## Configuration

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `MONGODB_URI` | Yes | MongoDB Atlas connection string |
| `VOYAGE_API_KEY` | Yes | Voyage AI API key |
| `REPO_PATH` | No | Repository path (default: cwd) |
| `REPO_NAME` | No | Repository name (default: directory name) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `EMBEDDING_MODEL` | No | Voyage AI model (default: voyage-code-3) |
| `EMBEDDING_DIMENSIONS` | No | Embedding dimensions (default: 1024) |

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
