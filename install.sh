#!/usr/bin/env bash
set -euo pipefail

# forge bootstrap: install CLI + bind skill to agent runtime
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/dxxbb/forge-core/main/install.sh | bash
#   or: bash <(curl -fsSL https://raw.githubusercontent.com/dxxbb/forge-core/main/install.sh)

REPO="git+https://github.com/dxxbb/forge-core.git"

echo "forge: installing CLI..."

if command -v pipx &>/dev/null; then
  pipx install "$REPO" 2>/dev/null || pipx upgrade context-forge 2>/dev/null || true
elif command -v uv &>/dev/null; then
  uv tool install "$REPO" 2>/dev/null || uv tool upgrade context-forge 2>/dev/null || true
else
  echo "forge: pipx and uv not found, trying pip install --user"
  pip install --user "$REPO"
fi

if ! command -v forge &>/dev/null; then
  echo "forge: ERROR — forge CLI not on PATH after install"
  echo "  try: pipx ensurepath && exec \$SHELL"
  exit 1
fi

echo "forge: CLI installed ($(forge --version))"
echo "forge: binding skill to agent runtime..."
forge self-install

echo ""
echo "done. restart Claude Code — then say \"forge 一下\" or \"set up forge\"."
