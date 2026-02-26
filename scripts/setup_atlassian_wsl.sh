#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
MCP_NAME="atlassian"
MCP_URL="https://mcp.atlassian.com/v1/sse"

info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
error() { printf '[ERROR] %s\n' "$*" >&2; }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "필수 명령어가 없습니다: $1"
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

info "사전 점검을 시작합니다."
need_cmd codex
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

existing_glob="${existing_glob:-docs/**/*.md}"
existing_labels="${existing_labels:-auto,docs}"
existing_create="${existing_create:-true}"
existing_update="${existing_update:-true}"

read -r -p "API 토큰 발급 페이지를 브라우저로 열까요? [Y/n]: " open_page
if [[ "${open_page,,}" != "n" && "${open_page,,}" != "no" ]]; then
  cmd.exe /C start "" "https://id.atlassian.com/manage-profile/security/api-tokens" >/dev/null 2>&1 || true
fi

printf '\n값을 입력하세요. 엔터를 누르면 기본값을 사용합니다.\n\n'
site="$(prompt_default "Atlassian 사이트 도메인 (예: krafton.atlassian.net)" "$existing_site")"
email="$(prompt_default "Atlassian 이메일" "$existing_email")"
space_key="$(prompt_default "Confluence Space Key (예: PUBGPC)" "$existing_space")"
parent_id="$(prompt_default "기본 Parent ID (폴더/페이지 ID, 비워도 됨)" "$existing_parent")"
markdown_glob="$(prompt_default "Markdown 경로 패턴" "$existing_glob")"
default_labels="$(prompt_default "기본 라벨 (콤마 구분)" "$existing_labels")"
create_if_missing="$(bool_default "페이지가 없으면 새로 생성할까요?" "$existing_create")"
update_if_title_match="$(bool_default "같은 제목 페이지가 있으면 업데이트할까요?" "$existing_update")"

read -r -s -p "Atlassian API Token 입력 (화면에 보이지 않음): " api_token
printf '\n'

if [[ -z "$site" || -z "$email" || -z "$space_key" || -z "$api_token" ]]; then
  error "사이트/이메일/스페이스키/API 토큰은 필수입니다."
  exit 1
fi

cat > "$ENV_FILE" <<EOF
ATLASSIAN_SITE=$site
ATLASSIAN_EMAIL=$email
ATLASSIAN_API_TOKEN=$api_token
CONFLUENCE_SPACE_KEY=$space_key
CONFLUENCE_PARENT_ID=$parent_id
MARKDOWN_GLOB=$markdown_glob
PUBLISH_CREATE_IF_MISSING=$create_if_missing
PUBLISH_UPDATE_IF_TITLE_MATCH=$update_if_title_match
PUBLISH_DEFAULT_LABELS=$default_labels
EOF
chmod 600 "$ENV_FILE"
info ".env 파일을 저장했습니다: $ENV_FILE"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

AUTH="$(printf '%s:%s' "$ATLASSIAN_EMAIL" "$ATLASSIAN_API_TOKEN" | base64 | tr -d '\n')"

info "Confluence 접근을 검증합니다."
space_resp="$(curl -sS -H "Authorization: Basic $AUTH" -w $'\n%{http_code}' "https://$ATLASSIAN_SITE/wiki/api/v2/spaces?keys=$CONFLUENCE_SPACE_KEY" || true)"
space_code="${space_resp##*$'\n'}"
space_json="${space_resp%$'\n'*}"

if [[ "$space_code" != "200" ]]; then
  legacy_resp="$(curl -sS -H "Authorization: Basic $AUTH" -w $'\n%{http_code}' "https://$ATLASSIAN_SITE/wiki/rest/api/space?spaceKey=$CONFLUENCE_SPACE_KEY" || true)"
  legacy_code="${legacy_resp##*$'\n'}"

  if [[ "$legacy_code" == "403" ]]; then
    error "Confluence 접근 권한이 없습니다. API Token scope/권한에 Confluence가 포함되어야 합니다."
    error "Atlassian 사이트 도메인과 계정 권한(해당 Space 접근 가능 여부)도 함께 확인하세요."
    exit 1
  fi

  if [[ "$space_code" == "404" ]]; then
    error "Confluence API가 404를 반환했습니다. 보통 도메인 오입력 또는 Confluence 접근 불가(권한/토큰 scope) 상황입니다."
    error "입력값 예시: ATLASSIAN_SITE=krafton.atlassian.net (https://, /wiki 제외)"
    exit 1
  fi

  error "Confluence Space 조회 실패 (HTTP $space_code). 응답: ${space_json:0:300}"
  exit 1
fi

space_id="$(python3 -c 'import json,sys; o=json.load(sys.stdin); r=o.get("results",[]); print(r[0]["id"] if r else "")' <<<"$space_json")"
if [[ -z "$space_id" ]]; then
  error "Space Key를 찾지 못했습니다. Space Key 오타 또는 권한 부족일 수 있습니다."
  exit 1
fi
info "Confluence OK: spaceKey=$CONFLUENCE_SPACE_KEY, spaceId=$space_id"

info "Jira 접근을 검증합니다."
jira_json="$(curl -fsS -H "Authorization: Basic $AUTH" "https://$ATLASSIAN_SITE/rest/api/3/myself")"
jira_name="$(python3 -c 'import json,sys; o=json.load(sys.stdin); print(o.get("displayName",""))' <<<"$jira_json")"
if [[ -z "$jira_name" ]]; then
  error "Jira 내 정보 조회에 실패했습니다. 토큰 권한을 확인하세요."
  exit 1
fi
info "Jira OK: user=$jira_name"

info "MCP 서버 설정을 확인합니다."
if codex mcp get "$MCP_NAME" --json >/dev/null 2>&1; then
  current_type="$(codex mcp get "$MCP_NAME" --json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("transport",{}).get("type",""))')"
  current_url="$(codex mcp get "$MCP_NAME" --json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("transport",{}).get("url",""))')"
  if [[ "$current_type" != "streamable_http" || "$current_url" != "$MCP_URL" ]]; then
    warn "기존 MCP 설정을 교체합니다: $MCP_NAME"
    codex mcp remove "$MCP_NAME" >/dev/null
    codex mcp add "$MCP_NAME" --url "$MCP_URL"
  fi
else
  codex mcp add "$MCP_NAME" --url "$MCP_URL"
fi

auth_row="$(codex mcp list | awk 'NR>1 && $1=="'"$MCP_NAME"'" {print}')"
if grep -qi "Not logged in" <<<"$auth_row"; then
  info "MCP OAuth 로그인을 진행합니다."
  codex mcp login "$MCP_NAME"
else
  info "MCP가 이미 인증되어 있어 로그인 단계를 건너뜁니다."
fi

auth_status="$(codex mcp list | awk 'NR>1 && $1=="'"$MCP_NAME"'" {print $NF}')"
info "MCP 상태: ${auth_status:-unknown}"

printf '\n완료되었습니다.\n'
printf '다음 명령으로 게시 테스트를 진행하세요:\n'
printf '  python3 "%s/scripts/confluence_publish.py" --dry-run\n' "$ROOT_DIR"
printf '  python3 "%s/scripts/confluence_publish.py"\n' "$ROOT_DIR"
