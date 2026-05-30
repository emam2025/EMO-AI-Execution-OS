#!/bin/sh
# Install emo-guard pre-commit hook
git config core.hooksPath .githooks
echo "✅ emo-guard pre-commit hook installed."
echo "   → .githooks/pre-commit will run before every commit"
echo "   → Run 'python3 scripts/emo-guard' to check architecture manually"
