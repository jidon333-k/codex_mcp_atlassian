# Atlassian 연동 원클릭 세팅 가이드 (초보자용)

이 문서는 아래 4가지를 한 번에 처리하는 방법입니다.

1. API 토큰 발급 준비
2. `.env` 환경변수 저장
3. Confluence/Jira 연결 검증
4. Codex MCP(atlassian) 로그인

---

## 1) WSL에서 바로 실행 (가장 쉬움)

프로젝트 루트(이 파일이 있는 저장소)에서 아래를 실행하세요.

```bash
bash scripts/setup_atlassian_wsl.sh
```

다른 경로에서 실행하려면 `<PROJECT_ROOT>`를 본인 경로로 바꿔 사용하세요.

```bash
bash <PROJECT_ROOT>/scripts/setup_atlassian_wsl.sh
```

실행하면 질문이 순서대로 나옵니다.
- `Atlassian 사이트 도메인`: `krafton.atlassian.net` 형태 (https://, /wiki 제외)
- `Confluence Space Key`: URL의 `/spaces/KEY/...` 에서 KEY 값 (예: `PUBGPC`)
- `기본 Parent ID`: 폴더 ID 또는 페이지 ID (없으면 비워도 됨)
- `API Token`: Atlassian 계정에서 발급한 토큰

---

## 2) Windows PowerShell에서 실행

PowerShell에서 아래를 실행하세요.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_atlassian_wsl.ps1
```

다른 경로에서 실행:

```powershell
powershell -ExecutionPolicy Bypass -File "<PROJECT_ROOT>\scripts\setup_atlassian_wsl.ps1"
```

Windows CMD(배치)에서 실행:

```bat
scripts\setup_atlassian_wsl.cmd
```

다른 경로에서 실행:

```bat
<PROJECT_ROOT>\scripts\setup_atlassian_wsl.cmd
```

---

## 3) (선택) Codex Skill 설치

이 저장소를 다른 Codex 세션에서도 재사용하려면 스킬로 설치하세요.

WSL:

```bash
bash scripts/codex/install_skill.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\codex\install_skill.ps1
```

Windows CMD:

```bat
scripts\codex\install_skill.cmd
```

설치 위치:
- `~/.codex/skills/confluence-publisher`
- Claude 지침 위치: `CLAUDE.md`, `agents/claude/confluence_publisher.md`

---

## 4) 완료 후 확인

세팅이 끝나면 아래를 실행해 게시 전 점검합니다.

```bash
python3 scripts/confluence_publish.py --dry-run
```

실제 게시:

```bash
python3 scripts/confluence_publish.py
```

---

## 5) 스크립트가 내부에서 하는 일

1. `.env` 값 입력 받기/저장 (`chmod 600`)
2. Confluence API로 Space 조회 테스트
3. Jira API로 `myself` 조회 테스트
4. MCP 서버를 `--url https://mcp.atlassian.com/v1/sse`로 맞춤
5. `codex mcp login atlassian` OAuth 실행
6. 성공 시 다음 실행 명령 안내

---

## 6) 자주 나는 문제

- `OAuth login is only supported for streamable HTTP servers`
  - 원인: `stdio` 방식으로 등록됨
  - 해결: 세팅 스크립트 재실행 (자동 교체)

- `curl: (22) ... 401`
  - 원인: API 토큰/이메일 불일치, 토큰 만료
  - 해결: 새 토큰 발급 후 다시 실행

- `Confluence 검증에서 404` 또는 `NOT_FOUND`
  - 원인: 도메인 오입력, 또는 API 토큰 scope/권한에 Confluence가 없음
  - 해결: `ATLASSIAN_SITE`를 `krafton.atlassian.net` 형태로 다시 입력하고, Confluence 접근 가능한 토큰으로 재발급

- Space 조회 실패
  - 원인: Space Key 오입력 또는 권한 부족
  - 해결: URL의 `/spaces/KEY/...`에서 KEY 재확인
