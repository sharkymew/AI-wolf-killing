#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== Building frontend ==="
cd frontend
npm ci
npx vite build
cd "$ROOT"

echo "=== Building executable ==="
pyinstaller --clean --noconfirm ai-werewolf.spec

echo ""
echo "=== Done ==="
echo "Output: dist/AI-Werewolf"
ls -lh dist/AI-Werewolf* 2>/dev/null || ls -lh dist/
