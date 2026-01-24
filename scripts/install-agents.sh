#!/bin/bash

# Vibe RAGnar - Install Agents
# Installs Claude Code agents optimized for Vibe RAGnar MCP server
#
# Usage: curl -sL https://raw.githubusercontent.com/BlckLvls/vibe-ragnar/main/scripts/install-agents.sh | bash

set -e

REPO_URL="https://raw.githubusercontent.com/BlckLvls/vibe-ragnar/main/agents"
AGENTS_DIR=".claude/agents"

echo "🐺 Vibe RAGnar - Installing Agents"
echo ""

mkdir -p "$AGENTS_DIR"

echo "📥 Downloading agents..."

curl -sL "$REPO_URL/explore.md" -o "$AGENTS_DIR/explore.md"
echo "   ✓ explore.md"

curl -sL "$REPO_URL/plan.md" -o "$AGENTS_DIR/plan.md"
echo "   ✓ plan.md"

echo ""
echo "✅ Agents installed to $AGENTS_DIR"
echo ""
echo "Available agents:"
echo "   • explore - Fast codebase exploration using graph + semantic search"
echo "   • plan    - Implementation planning with deep code analysis"
