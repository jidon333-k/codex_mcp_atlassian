#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -n "${CODEX_HOME:-}" ]]; then
  BASE_HOME="$CODEX_HOME"
elif [[ -d "$HOME/.codex" || -d "$HOME/.codex/skills" ]]; then
  BASE_HOME="$HOME/.codex"
elif [[ -d "$HOME/.agents" || -d "$HOME/.agents/skills" ]]; then
  BASE_HOME="$HOME/.agents"
else
  BASE_HOME="$HOME/.codex"
fi

SKILLS_DIR="${CODEX_SKILLS_DIR:-$BASE_HOME/skills}"
BACKUP_ROOT="${CODEX_SKILL_BACKUP_DIR:-$BASE_HOME/skill_backups}"
SRC_SKILL_DIR="$ROOT_DIR/skills/confluence-publisher"
DST_SKILL_DIR="$SKILLS_DIR/confluence-publisher"

if [[ ! -f "$SRC_SKILL_DIR/SKILL.md" ]]; then
  echo "[ERROR] Skill source not found: $SRC_SKILL_DIR" >&2
  exit 1
fi

mkdir -p "$SKILLS_DIR"
mkdir -p "$BACKUP_ROOT"

if [[ -d "$DST_SKILL_DIR" ]]; then
  BACKUP_DIR="${BACKUP_ROOT}/confluence-publisher.backup.$(date +%Y%m%d-%H%M%S)"
  mv "$DST_SKILL_DIR" "$BACKUP_DIR"
  echo "[INFO] Existing skill backed up: $BACKUP_DIR"
fi

# Avoid transient cache files during copy.
find "$SRC_SKILL_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +

cp -a "$SRC_SKILL_DIR" "$DST_SKILL_DIR"
chmod +x "$DST_SKILL_DIR/scripts/run_publish.sh"
chmod +x "$DST_SKILL_DIR/scripts/setup_env.sh"
chmod +x "$DST_SKILL_DIR/scripts/confluence_publish.py"

cat <<EOF
[INFO] Skill installed: $DST_SKILL_DIR

Next:
1) Open a new Codex session (or continue current session).
2) Configure environment once:
   bash $DST_SKILL_DIR/scripts/setup_env.sh
3) Ask: "docs/xxx.md를 Confluence에 올려줘"
4) Or run directly:
   $DST_SKILL_DIR/scripts/run_publish.sh --dry-run --glob "docs/**/*.md"
EOF
