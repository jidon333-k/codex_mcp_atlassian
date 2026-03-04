# Confluence Publisher

Local Markdown files can be published to Confluence Cloud pages.

## Start Here (for AI agents)

If you ask an AI to "set everything up", use this exact order first.

1. Get Atlassian credentials and required values from user.
- `ATLASSIAN_SITE` (e.g. `krafton.atlassian.net`)
- `ATLASSIAN_EMAIL`
- `ATLASSIAN_API_TOKEN`
- `CONFLUENCE_SPACE_KEY`
- `CONFLUENCE_PARENT_ID` (optional)
2. Run setup script first to create local `.env` and validate APIs.
```bash
bash scripts/setup_atlassian_wsl.sh
```
3. Confirm validation and MCP login status.
```bash
codex mcp list
codex mcp get atlassian --json
```
4. Install `confluence-publisher` skill after `.env` is ready.

Copy-paste request template for AI:

```text
이 저장소 기준으로 Atlassian 연동부터 설정해줘.
반드시 순서대로:
1) API 토큰과 필수 입력값(도메인/이메일/Space Key/Parent ID) 먼저 확인
2) scripts/setup_atlassian_wsl.sh 실행해서 로컬 .env 생성
3) Confluence/Jira 검증 및 MCP 로그인 확인
4) confluence-publisher 스킬 설치
5) dry-run까지 실행
```

## Quick setup (Korean)

- Full guide: [SETUP_QUICKSTART_KO.md](SETUP_QUICKSTART_KO.md)
- First command on WSL (recommended):

```bash
bash scripts/setup_atlassian_wsl.sh
```

## Codex standard skill format

This repository follows Codex skills format (see official docs):
- https://developers.openai.com/codex/skills/

Skill package:
- `skills/confluence-publisher/SKILL.md` (required)
- `skills/confluence-publisher/scripts/confluence_publish.py` (self-contained engine)
- `skills/confluence-publisher/scripts/run_publish.sh` (skill runner)
- `skills/confluence-publisher/scripts/setup_env.sh` (skill-local `.env` setup)
- `skills/confluence-publisher/agents/openai.yaml` (optional UI metadata)

## Install skill (recommended: skill-installer)

Install directly from GitHub:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo jidon333-k/codex_mcp_atlassian \
  --path skills/confluence-publisher
```

Then configure skill-local environment:

```bash
bash ~/.codex/skills/confluence-publisher/scripts/setup_env.sh
# or (if your Codex uses ~/.agents):
# bash ~/.agents/skills/confluence-publisher/scripts/setup_env.sh
```

After installation, restart Codex once so the new skill is loaded.

Run:

```bash
bash ~/.codex/skills/confluence-publisher/scripts/run_publish.sh --dry-run --glob "/path/to/file.md"
bash ~/.codex/skills/confluence-publisher/scripts/run_publish.sh --glob "/path/to/file.md"
# or:
# bash ~/.agents/skills/confluence-publisher/scripts/run_publish.sh --dry-run --glob "/path/to/file.md"
# bash ~/.agents/skills/confluence-publisher/scripts/run_publish.sh --glob "/path/to/file.md"
```

## Install skill (from local clone)

```bash
bash scripts/codex/install_skill.sh
```

Windows entrypoints:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\codex\install_skill.ps1
```

```bat
scripts\codex\install_skill.cmd
```

Installed path:
- `~/.codex/skills/confluence-publisher`
- or `~/.agents/skills/confluence-publisher` (environment-dependent)

## Repository structure (what each file does)

- `scripts/confluence_publish.py`
  - Project-local engine (same logic as skill engine).
- `scripts/setup_atlassian_wsl.sh`
  - Project-local interactive setup (`.env`, API validation, MCP login).
- `skills/confluence-publisher/*`
  - Self-contained Codex skill package.
- `CLAUDE.md`, `agents/claude/confluence_publisher.md`
  - Claude-oriented project instructions.
- `docs/*.md`
  - Example/source markdown files.

## 1) Required setup

- MCP login should already be done (`codex mcp login atlassian`)
- `.env` file is required with:

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

## 2) Dry-run first

```bash
python3 scripts/confluence_publish.py --dry-run
```

## 3) Publish

```bash
python3 scripts/confluence_publish.py
```

## 4) Common overrides

```bash
python3 scripts/confluence_publish.py --glob "notes/**/*.md"
python3 scripts/confluence_publish.py --space-key DEV
python3 scripts/confluence_publish.py --parent-id 123456
python3 scripts/confluence_publish.py --default-labels "team,release"
python3 scripts/confluence_publish.py --mermaid-mode code
```

`--mermaid-mode` options:
- `attachment` (default): render mermaid to local/remote SVG and upload as image attachment
- `code`: keep mermaid as code block
- `macro`: use Confluence mermaid macro

`--mermaid-image-width`:
- default: `1000`
- env: `CONFLUENCE_MERMAID_IMAGE_WIDTH`

## Mermaid image generation

- The publisher finds each fenced block that starts with ` ```mermaid `.
- In `attachment` mode, it renders SVG via local `mmdc` first (if installed).
- If `mmdc` is not found or fails, it falls back to `https://mermaid.ink/svg/...`.
- The SVG is uploaded as a Confluence attachment and embedded with `<ac:image ac:width="...">`.

## 5) Optional front matter per file

```markdown
---
title: Release Notes 2026-02-25
parent_id: 123456
confluence_id: 987654
labels: release, notes
---

# Release Notes

Content...
```

Fields:
- `title`: page title override
- `parent_id`: parent page id override
- `confluence_id`: force update a specific page id
- `labels`: extra labels for that file
