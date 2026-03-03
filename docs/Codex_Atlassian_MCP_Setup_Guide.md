---
title: Codex Atlassian MCP(Jira/Confluence) 연결 가이드
labels: codex,mcp,atlassian,confluence,jira,setup
---

# Codex Atlassian MCP(Jira/Confluence) 연결 가이드

이 문서는 **Codex에서 Atlassian MCP(Remote MCP)** 를 연결하고,
필요한 자동화 스크립트를 받아서 바로 실행하는 표준 절차입니다.

## TL;DR

- Codex AI에게 저장소 링크(`https://github.com/jidon333-k/codex_mcp_atlassian`)를 알려주고, `confluence-publisher` 스킬 설치를 요청하면 됩니다.
- 그다음 "이 문서 Confluence에 업데이트해줘"라고 요청하면 게시/업데이트까지 처리할 수 있습니다.

## 1) 준비물

- Atlassian Cloud 계정 (Confluence/Jira 접근 권한)
- Atlassian API Token
- Codex CLI
- WSL(권장) 또는 Windows PowerShell

## 2) 순수 MCP 설정 (GitHub/스크립트 없이 가능)

아래 명령만으로 Atlassian MCP 연결이 가능합니다.

```bash
codex mcp add atlassian -- npx -y mcp-remote https://mcp.atlassian.com/v1/mcp
codex mcp list
codex mcp get atlassian --json
```

참고:
- 첫 MCP 호출 시 OAuth 승인 창이 열립니다.
- 브라우저 자동 실행이 안 되면, 터미널에 출력된 `authorize` URL을 직접 열어 승인
- 이 방식은 **MCP 연결만** 다룹니다. Markdown 자동 게시는 별도 스크립트 필요

## 3) 저장소 받기 (GitHub)

아래 저장소를 클론합니다.

```bash
git clone https://github.com/jidon333-k/codex_mcp_atlassian.git
cd codex_mcp_atlassian
```

## 4) 원클릭 초기 세팅 실행

### WSL

```bash
bash scripts/setup_atlassian_wsl.sh
```

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_atlassian_wsl.ps1
```

### Windows CMD

```bat
scripts\setup_atlassian_wsl.cmd
```

실행 중 입력 항목:
- Atlassian 사이트 도메인 예: `krafton.atlassian.net`
- Atlassian 이메일: 개인 계정 이메일
- Confluence Space Key 예: `PUBGPC`
- Parent ID: 비워도 가능(필요 시 폴더/페이지 ID 입력)
- API Token

## 5) MCP 연결 확인

```bash
codex mcp list
codex mcp get atlassian --json
```

정상 기준:
- `atlassian` 서버가 보임
- Auth 상태가 로그인 상태(OAuth)

## 6) 마크다운 -> Confluence 게시

드라이런(미리보기):

```bash
python3 scripts/confluence_publish.py --dry-run
```

실제 게시:

```bash
python3 scripts/confluence_publish.py
```

특정 파일만 게시:

```bash
python3 scripts/confluence_publish.py --glob "docs/your_file.md"
```

## 6-1) Codex Skill 지원 (confluence-publisher)

이 프로젝트는 이제 **Codex Skill 패키지**도 함께 제공합니다.
즉, 스크립트를 직접 실행하는 방식뿐 아니라, Codex 표준 스킬 경로로도 동일하게 게시할 수 있습니다.

스킬 구성 경로:
- `skills/confluence-publisher/SKILL.md`
- `skills/confluence-publisher/scripts/confluence_publish.py`
- `skills/confluence-publisher/scripts/run_publish.sh`
- `skills/confluence-publisher/scripts/setup_env.sh`

추천 설치(스킬 인스톨러):

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo jidon333-k/codex_mcp_atlassian \
  --path skills/confluence-publisher
```

스킬 전용 환경 설정:

```bash
bash ~/.codex/skills/confluence-publisher/scripts/setup_env.sh
# 또는(환경에 따라):
# bash ~/.agents/skills/confluence-publisher/scripts/setup_env.sh
```

스킬 러너로 게시:

```bash
bash ~/.codex/skills/confluence-publisher/scripts/run_publish.sh --dry-run --glob "docs/your_file.md"
bash ~/.codex/skills/confluence-publisher/scripts/run_publish.sh --glob "docs/your_file.md"
# 또는(환경에 따라):
# bash ~/.agents/skills/confluence-publisher/scripts/run_publish.sh --dry-run --glob "docs/your_file.md"
# bash ~/.agents/skills/confluence-publisher/scripts/run_publish.sh --glob "docs/your_file.md"
```

## 7) 설정 파일(.env) 설명

`.env`는 개인별로 다릅니다. 팀 문서에는 실제 값을 공유하지 않습니다.

```env
ATLASSIAN_SITE=krafton.atlassian.net
ATLASSIAN_EMAIL=you@company.com
ATLASSIAN_API_TOKEN=***
CONFLUENCE_SPACE_KEY=PUBGPC
CONFLUENCE_PARENT_ID=
MARKDOWN_GLOB=docs/**/*.md
PUBLISH_CREATE_IF_MISSING=true
PUBLISH_UPDATE_IF_TITLE_MATCH=true
PUBLISH_DEFAULT_LABELS=auto,docs
CONFLUENCE_MERMAID_MODE=attachment
CONFLUENCE_MERMAID_IMAGE_WIDTH=1000
```

Mermaid 처리 모드:
- `attachment` (기본값): Mermaid를 이미지 첨부로 게시
- `code`: Mermaid 코드를 코드블럭으로 게시
- `macro`: Confluence mermaid 매크로 사용

이미지 크기:
- `CONFLUENCE_MERMAID_IMAGE_WIDTH`: Confluence에 표시되는 기본 너비(px), 기본값 `1000`

Mermaid 이미지 생성 방식:
- `attachment` 모드에서 시작 토큰이 ` ```mermaid ` 인 코드블럭을 찾습니다.
- 로컬에 `mmdc`가 있으면 로컬 렌더링으로 SVG를 만듭니다.
- `mmdc`가 없거나 실패하면 `mermaid.ink` 원격 렌더링으로 SVG를 만듭니다.
- 생성된 SVG를 페이지 첨부파일로 업로드하고, 본문에는 `<ac:image>` 매크로로 삽입합니다.

## 8) 경로/환경 주의사항

- 로컬 경로는 사용자마다 다릅니다.
- 문서의 `<PROJECT_ROOT>` 표시는 각자 PC 경로로 바꿔서 사용합니다.
- `.env` 및 API 토큰은 Git에 커밋하지 않습니다.

## 9) 트러블슈팅

- `Unexpected content type: text/plain; charset=utf-8` (MCP 핸드셰이크 실패)
  - 구형 `/v1/sse` 설정 또는 direct streamable_http + OAuth 조합 이슈일 수 있음
  - `codex mcp remove atlassian`
  - `codex mcp add atlassian -- npx -y mcp-remote https://mcp.atlassian.com/v1/mcp`

- Confluence 검증 시 `404` 또는 `NOT_FOUND`
  - 도메인 오입력 또는 토큰 권한(scope) 문제 가능
  - `ATLASSIAN_SITE` 형식 확인: `xxx.atlassian.net`

- `Permission denied (publickey)`로 git clone 실패
  - HTTPS 클론 사용 또는 GitHub SSH 키 등록 필요

## 10) 참고

- 저장소: https://github.com/jidon333-k/codex_mcp_atlassian
- 상세 설정 문서: `SETUP_QUICKSTART_KO.md`
- 게시 스크립트: `scripts/confluence_publish.py`
