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

# Question 1: Model for Explore agent
echo "Select model for Explore agent:"
echo "  1) haiku (default) - Fast and cost-effective"
echo "  2) sonnet - Smarter, detailed exploration, excellent MCP integration"
echo "             ⚠️  Uses more of your usage limits"
echo ""
read -p "Choice [1]: " model_choice
model_choice=${model_choice:-1}

if [ "$model_choice" = "2" ]; then
    EXPLORE_MODEL="sonnet"
    echo "→ Using sonnet for Explore agent"
else
    EXPLORE_MODEL="haiku"
    echo "→ Using haiku for Explore agent"
fi
echo ""

# Question 2: Add .claude to .gitignore
echo "Add .claude/ to .gitignore?"
echo "  If not added, custom agents folder will be tracked by git."
echo "  1) Yes (default) - Add to .gitignore"
echo "  2) No - Keep tracking .claude folder"
echo ""
read -p "Choice [1]: " gitignore_choice
gitignore_choice=${gitignore_choice:-1}
echo ""

# Create agents directory
mkdir -p "$AGENTS_DIR"

echo "📥 Downloading agents..."

# Download explore.md
curl -sL "$REPO_URL/explore.md" -o "$AGENTS_DIR/explore.md"

# Update model if sonnet selected
if [ "$EXPLORE_MODEL" = "sonnet" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' 's/^model: haiku$/model: sonnet/' "$AGENTS_DIR/explore.md"
    else
        sed -i 's/^model: haiku$/model: sonnet/' "$AGENTS_DIR/explore.md"
    fi
fi
echo "   ✓ explore.md (model: $EXPLORE_MODEL)"

# Download plan.md
curl -sL "$REPO_URL/plan.md" -o "$AGENTS_DIR/plan.md"
echo "   ✓ plan.md"

# Handle .gitignore
if [ "$gitignore_choice" = "1" ]; then
    if [ -f ".gitignore" ]; then
        if ! grep -q "^\.claude/$" ".gitignore" && ! grep -q "^\.claude$" ".gitignore"; then
            echo "" >> ".gitignore"
            echo ".claude/" >> ".gitignore"
            echo "   ✓ Added .claude/ to .gitignore"
        else
            echo "   ✓ .claude/ already in .gitignore"
        fi
    else
        echo ".claude/" > ".gitignore"
        echo "   ✓ Created .gitignore with .claude/"
    fi
fi

echo ""
echo "✅ Agents installed to $AGENTS_DIR"
echo ""
echo "Available agents:"
echo "   • explore - Fast codebase exploration using graph + semantic search"
echo "   • plan    - Implementation planning with deep code analysis"
echo ""
