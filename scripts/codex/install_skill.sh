#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SRC_SKILL_DIR="$ROOT_DIR/skills/confluence-publisher"
DST_SKILL_DIR="$CODEX_HOME/skills/confluence-publisher"
BACKUP_ROOT="$CODEX_HOME/skill_backups"

if [[ ! -f "$SRC_SKILL_DIR/SKILL.md" ]]; then
  echo "[ERROR] Skill source not found: $SRC_SKILL_DIR" >&2
  exit 1
fi

mkdir -p "$CODEX_HOME/skills"
mkdir -p "$BACKUP_ROOT"

if [[ -d "$DST_SKILL_DIR" ]]; then
  BACKUP_DIR="${BACKUP_ROOT}/confluence-publisher.backup.$(date +%Y%m%d-%H%M%S)"
  mv "$DST_SKILL_DIR" "$BACKUP_DIR"
  echo "[INFO] Existing skill backed up: $BACKUP_DIR"
fi

cp -a "$SRC_SKILL_DIR" "$DST_SKILL_DIR"
chmod +x "$DST_SKILL_DIR/scripts/run_publish.sh"
printf '%s\n' "$ROOT_DIR" > "$DST_SKILL_DIR/.project_root"

cat <<EOF
[INFO] Skill installed: $DST_SKILL_DIR

Next:
1) Open a new Codex session (or continue current session).
2) Ask: "docs/xxx.md를 Confluence에 올려줘"
3) Or run directly:
   $DST_SKILL_DIR/scripts/run_publish.sh --dry-run --glob "docs/**/*.md"
EOF
