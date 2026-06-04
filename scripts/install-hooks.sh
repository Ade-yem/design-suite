#!/bin/bash

# Install git hooks for the design-suite project
# Run this script after cloning the repository

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

echo "🔧 Installing git hooks..."

# Make sure hooks directory exists
mkdir -p "$HOOKS_DIR"

# Copy pre-commit hook
HOOK_SOURCE="$PROJECT_ROOT/scripts/pre-commit-hook.py"
HOOK_DEST="$HOOKS_DIR/pre-commit"

if [ -f "$HOOK_SOURCE" ]; then
  cp "$HOOK_SOURCE" "$HOOK_DEST"
  chmod +x "$HOOK_DEST"
  echo "✓ Pre-commit hook installed"
else
  echo "⚠ Hook source file not found: $HOOK_SOURCE"
  exit 1
fi

echo ""
echo "✅ Git hooks installed successfully!"
echo ""
echo "The pre-commit hook will run the following checks before each commit:"
echo "  • Backend: pytest, type checking"
echo "  • Frontend: ESLint, TypeScript type checking"
echo ""
echo "To bypass checks (not recommended): git commit --no-verify"
