#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SKILL_ROOT/.env"
RUN_CMD="bash $SCRIPT_DIR/run_publish.sh"

info() { printf '[INFO] %s\n' "$*"; }
error() { printf '[ERROR] %s\n' "$*" >&2; }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "Missing command: $1"
    exit 1
  fi
}

read_env_default() {
  local key="$1"
  if [[ -f "$ENV_FILE" ]]; then
    awk -F= -v k="$key" '$1==k {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
  fi
}

prompt_default() {
  local label="$1"
  local default_value="$2"
  local out
  if [[ -n "$default_value" ]]; then
    read -r -p "$label [$default_value]: " out
    printf '%s' "${out:-$default_value}"
  else
    read -r -p "$label: " out
    printf '%s' "$out"
  fi
}

bool_default() {
  local label="$1"
  local default_value="$2"
  local out
  if [[ "$default_value" == "true" ]]; then
    read -r -p "$label [Y/n]: " out
    case "${out,,}" in
      n|no) printf 'false' ;;
      *) printf 'true' ;;
    esac
  else
    read -r -p "$label [y/N]: " out
    case "${out,,}" in
      y|yes) printf 'true' ;;
      *) printf 'false' ;;
    esac
  fi
}

need_cmd python3
need_cmd curl
need_cmd base64

existing_site="$(read_env_default ATLASSIAN_SITE || true)"
existing_email="$(read_env_default ATLASSIAN_EMAIL || true)"
existing_space="$(read_env_default CONFLUENCE_SPACE_KEY || true)"
existing_parent="$(read_env_default CONFLUENCE_PARENT_ID || true)"
existing_glob="$(read_env_default MARKDOWN_GLOB || true)"
existing_labels="$(read_env_default PUBLISH_DEFAULT_LABELS || true)"
existing_create="$(read_env_default PUBLISH_CREATE_IF_MISSING || true)"
existing_update="$(read_env_default PUBLISH_UPDATE_IF_TITLE_MATCH || true)"
existing_mode="$(read_env_default CONFLUENCE_MERMAID_MODE || true)"
existing_width="$(read_env_default CONFLUENCE_MERMAID_IMAGE_WIDTH || true)"

existing_glob="${existing_glob:-docs/**/*.md}"
existing_labels="${existing_labels:-auto,docs}"
existing_create="${existing_create:-true}"
existing_update="${existing_update:-true}"
existing_mode="${existing_mode:-attachment}"
existing_width="${existing_width:-1000}"

printf '\nEnter values. Press Enter to use defaults.\n\n'
site="$(prompt_default 'Atlassian site domain (example: myteam.atlassian.net)' "$existing_site")"
email="$(prompt_default 'Atlassian email' "$existing_email")"
space_key="$(prompt_default 'Confluence Space Key (example: DOCS)' "$existing_space")"
parent_id="$(prompt_default 'Default Parent ID (optional)' "$existing_parent")"
markdown_glob="$(prompt_default 'Markdown glob pattern' "$existing_glob")"
default_labels="$(prompt_default 'Default labels (comma-separated)' "$existing_labels")"
create_if_missing="$(bool_default 'Create page if missing?' "$existing_create")"
update_if_title_match="$(bool_default 'Update page when title matches?' "$existing_update")"
mermaid_mode="$(prompt_default 'Mermaid mode (attachment/code/macro)' "$existing_mode")"
mermaid_width="$(prompt_default 'Mermaid image width (px)' "$existing_width")"

read -r -s -p 'Atlassian API token (hidden): ' api_token
printf '\n'

if [[ -z "$site" || -z "$email" || -z "$space_key" || -z "$api_token" ]]; then
  error 'ATLASSIAN_SITE, ATLASSIAN_EMAIL, CONFLUENCE_SPACE_KEY, ATLASSIAN_API_TOKEN are required.'
  exit 1
fi

cat > "$ENV_FILE" <<EOF_ENV
ATLASSIAN_SITE=$site
ATLASSIAN_EMAIL=$email
ATLASSIAN_API_TOKEN=$api_token
CONFLUENCE_SPACE_KEY=$space_key
CONFLUENCE_PARENT_ID=$parent_id
MARKDOWN_GLOB=$markdown_glob
PUBLISH_CREATE_IF_MISSING=$create_if_missing
PUBLISH_UPDATE_IF_TITLE_MATCH=$update_if_title_match
PUBLISH_DEFAULT_LABELS=$default_labels
CONFLUENCE_MERMAID_MODE=$mermaid_mode
CONFLUENCE_MERMAID_IMAGE_WIDTH=$mermaid_width
EOF_ENV
chmod 600 "$ENV_FILE"
info "Saved: $ENV_FILE"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

AUTH="$(printf '%s:%s' "$ATLASSIAN_EMAIL" "$ATLASSIAN_API_TOKEN" | base64 | tr -d '\n')"

info 'Checking Confluence access...'
space_resp="$(curl -sS -H "Authorization: Basic $AUTH" -w $'\n%{http_code}' "https://$ATLASSIAN_SITE/wiki/api/v2/spaces?keys=$CONFLUENCE_SPACE_KEY" || true)"
space_code="${space_resp##*$'\n'}"
space_json="${space_resp%$'\n'*}"
if [[ "$space_code" != "200" ]]; then
  error "Confluence check failed (HTTP $space_code)."
  printf '%s\n' "${space_json:0:300}" >&2
  exit 1
fi

space_id="$(python3 -c 'import json,sys; o=json.load(sys.stdin); r=o.get("results", []); print(r[0]["id"] if r else "")' <<<"$space_json")"
if [[ -z "$space_id" ]]; then
  error 'Space key not found or no permission.'
  exit 1
fi
info "Confluence OK: spaceKey=$CONFLUENCE_SPACE_KEY, spaceId=$space_id"

info 'Checking Jira access...'
jira_json="$(curl -fsS -H "Authorization: Basic $AUTH" "https://$ATLASSIAN_SITE/rest/api/3/myself")"
jira_name="$(python3 -c 'import json,sys; o=json.load(sys.stdin); print(o.get("displayName", ""))' <<<"$jira_json")"
if [[ -z "$jira_name" ]]; then
  error 'Jira check failed.'
  exit 1
fi
info "Jira OK: user=$jira_name"

cat <<EOF_DONE

Done.

Next:
1) Dry-run
   $RUN_CMD --dry-run --glob "/path/to/file.md"
2) Publish
   $RUN_CMD --glob "/path/to/file.md"
EOF_DONE
