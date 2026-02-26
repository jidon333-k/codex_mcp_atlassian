#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SCRIPT_DIR/confluence_publish.py"
DEFAULT_DOTENV="$SKILL_ROOT/.env"
SELF_CMD="bash $SCRIPT_DIR/run_publish.sh"
SETUP_CMD="bash $SCRIPT_DIR/setup_env.sh"

if [[ "${1:-}" == "--help" ]]; then
  cat <<USAGE
Usage:
  $SELF_CMD [args...]

This runner is self-contained:
- engine: $ENGINE
- dotenv: $DEFAULT_DOTENV (default)

Examples:
  $SELF_CMD --dry-run --glob "/mnt/c/Users/me/Documents/file.md"
  $SELF_CMD --glob "docs/**/*.md"
  $SELF_CMD --dotenv "/path/to/.env" --glob "docs/**/*.md"

If default dotenv is missing:
  $SETUP_CMD
or export ATLASSIAN_* and CONFLUENCE_SPACE_KEY in shell.
USAGE
  exit 0
fi

if [[ ! -f "$ENGINE" ]]; then
  echo "[ERROR] Engine not found: $ENGINE" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is required" >&2
  exit 2
fi

HAS_DOTENV_ARG=0
ARGS=("$@")
for ((i = 0; i < ${#ARGS[@]}; i++)); do
  if [[ "${ARGS[$i]}" == "--dotenv" ]]; then
    HAS_DOTENV_ARG=1
    break
  fi
done

if [[ "$HAS_DOTENV_ARG" -eq 0 ]]; then
  if [[ ! -f "$DEFAULT_DOTENV" ]]; then
    if [[ -n "${ATLASSIAN_SITE:-}" && -n "${ATLASSIAN_EMAIL:-}" && -n "${ATLASSIAN_API_TOKEN:-}" && -n "${CONFLUENCE_SPACE_KEY:-}" ]]; then
      exec python3 "$ENGINE" "$@"
    fi
    echo "[ERROR] Default dotenv not found: $DEFAULT_DOTENV" >&2
    echo "Run: $SETUP_CMD" >&2
    echo "or pass --dotenv /path/to/.env" >&2
    echo "or export ATLASSIAN_* and CONFLUENCE_SPACE_KEY in your shell." >&2
    exit 2
  fi
  set -- --dotenv "$DEFAULT_DOTENV" "$@"
fi

exec python3 "$ENGINE" "$@"
