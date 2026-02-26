#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

read_config_project_root() {
  local cfg="$SKILL_ROOT/.project_root"
  if [[ ! -f "$cfg" ]]; then
    return 1
  fi
  local root
  root="$(head -n 1 "$cfg" | tr -d '\r\n')"
  if [[ -z "$root" ]]; then
    return 1
  fi
  if [[ -f "$root/scripts/confluence_publish.py" ]]; then
    printf '%s\n' "$root"
    return 0
  fi
  return 1
}

find_project_root() {
  local config_root
  config_root="$(read_config_project_root || true)"
  if [[ -n "$config_root" ]]; then
    printf '%s\n' "$config_root"
    return 0
  fi

  if [[ -n "${CONFLUENCE_PUBLISHER_PROJECT_ROOT:-}" ]]; then
    if [[ -f "${CONFLUENCE_PUBLISHER_PROJECT_ROOT}/scripts/confluence_publish.py" ]]; then
      printf '%s\n' "$CONFLUENCE_PUBLISHER_PROJECT_ROOT"
      return 0
    fi
  fi

  local dir="$PWD"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/scripts/confluence_publish.py" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done

  local sibling_root
  sibling_root="$(cd "$SCRIPT_DIR/../../.." && pwd)"
  if [[ -f "$sibling_root/scripts/confluence_publish.py" ]]; then
    printf '%s\n' "$sibling_root"
    return 0
  fi

  return 1
}

if [[ "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  run_publish.sh [args...]

Examples:
  run_publish.sh --dry-run --glob "docs/**/*.md"
  run_publish.sh --glob "/mnt/c/Users/me/Documents/file.md" --parent-id 123456

If project root is not discoverable automatically, set:
  export CONFLUENCE_PUBLISHER_PROJECT_ROOT=/path/to/codex_mcp_atlassian
EOF
  exit 0
fi

PROJECT_ROOT="$(find_project_root || true)"
if [[ -z "$PROJECT_ROOT" ]]; then
  echo "[ERROR] Could not find project root (scripts/confluence_publish.py)." >&2
  echo "Set CONFLUENCE_PUBLISHER_PROJECT_ROOT and retry." >&2
  exit 2
fi

cd "$PROJECT_ROOT"
if [[ -x "scripts/publish.sh" ]]; then
  exec bash scripts/publish.sh "$@"
fi

exec python3 scripts/confluence_publish.py "$@"
