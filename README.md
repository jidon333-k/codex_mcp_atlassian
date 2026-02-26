# Confluence Publisher

Local Markdown files can be published to Confluence Cloud pages.

## Quick setup (Korean)

- See [SETUP_QUICKSTART_KO.md](SETUP_QUICKSTART_KO.md)
- One-command setup on WSL:

```bash
bash scripts/setup_atlassian_wsl.sh
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
```

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
