# Confluence Publisher

Local Markdown files can be published to Confluence Cloud pages.

## Quick setup (Korean)

- See [SETUP_QUICKSTART_KO.md](SETUP_QUICKSTART_KO.md)
- One-command setup on WSL:

```bash
bash scripts/setup_atlassian_wsl.sh
```

## Agent layout

- Shared publish runner:
  - `scripts/publish.sh`
- Codex skill assets:
  - `skills/confluence-publisher/SKILL.md`
- Claude project instructions:
  - `CLAUDE.md`
  - `agents/claude/confluence_publisher.md`

## Repository structure (what each file does)

- `scripts/confluence_publish.py`
  - Core engine. Calls Confluence REST API to create/update pages and upload Mermaid images.
- `scripts/publish.sh`
  - Shared entrypoint for both Codex and Claude. Executes `confluence_publish.py`.
- `scripts/setup_atlassian_wsl.sh`
  - Interactive first-time setup (`.env`, API validation, MCP login).
- `scripts/setup_atlassian_wsl.ps1`, `scripts/setup_atlassian_wsl.cmd`
  - Windows wrappers that call the WSL setup script.

- `skills/confluence-publisher/SKILL.md`
  - Codex skill definition (when/how Codex should run publish workflow).
- `skills/confluence-publisher/scripts/run_publish.sh`
  - Codex skill runtime helper. Delegates to `scripts/publish.sh`.
- `scripts/codex/install_skill.sh`
  - Installs the Codex skill into `~/.codex/skills/confluence-publisher`.
- `scripts/codex/install_skill.ps1`, `scripts/codex/install_skill.cmd`
  - Windows wrappers for Codex skill installation.

- `CLAUDE.md`
  - Claude entry instruction file for this repository.
- `agents/claude/confluence_publisher.md`
  - Detailed Claude workflow instructions for Confluence publishing.

- `docs/*.md`
  - Source markdown documents to publish.

## Codex skill install (optional)

Install this repo as a reusable Codex skill:

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

## Claude support (optional)

This repo also includes Claude-oriented instructions:
- [CLAUDE.md](CLAUDE.md)
- [agents/claude/confluence_publisher.md](agents/claude/confluence_publisher.md)

Claude/Codex shared helper command:

```bash
bash scripts/publish.sh --dry-run --glob "docs/**/*.md"
bash scripts/publish.sh --glob "docs/**/*.md"
```

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
