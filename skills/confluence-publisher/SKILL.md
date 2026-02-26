---
name: confluence-publisher
description: Use when the user asks to publish or update Markdown documents in Confluence using the local Confluence REST publisher workflow (`scripts/publish.sh`), including parent-page targeting and post-publish verification.
---

# Confluence Publisher Skill

Use this skill when the user asks for:
- Markdown -> Confluence upload
- Existing wiki page update from local `.md`
- Upload under a specific parent page (including short URL `/wiki/x/...`)

## Preconditions

- Skill is installed at `~/.codex/skills/confluence-publisher` (recommended).
- Project contains `scripts/publish.sh` and `.env`.
- `.env` exists and includes:
  - `ATLASSIAN_SITE`
  - `ATLASSIAN_EMAIL`
  - `ATLASSIAN_API_TOKEN`
  - `CONFLUENCE_SPACE_KEY`
- Never print raw API tokens in responses.

## Standard Workflow

1. Resolve markdown path.
- WSL path example: `/mnt/c/Users/<user>/Documents/DevMarkdowns/file.md`
- Repo file example: `docs/file.md`

2. Resolve publish target.
- If user gives Confluence short URL (`/wiki/x/...`), resolve final URL and extract page ID.
- If user requests "as child page", pass `--parent-id <resolved_page_id>`.
- If no parent is specified, rely on `.env` `CONFLUENCE_PARENT_ID`.

3. Run dry-run first when risk is non-trivial.

```bash
~/.codex/skills/confluence-publisher/scripts/run_publish.sh --dry-run --glob "<MD_PATH>"
```

4. Publish.

```bash
~/.codex/skills/confluence-publisher/scripts/run_publish.sh --glob "<MD_PATH>"
```

5. Verify and report.
- Report `page_id`, title, and parentId.
- Share final Confluence URL.

## Command Patterns

- Create/update by title match:
```bash
~/.codex/skills/confluence-publisher/scripts/run_publish.sh --glob "<MD_PATH>" --update-if-title-match true
```

- Force new page under specific parent:
```bash
~/.codex/skills/confluence-publisher/scripts/run_publish.sh --glob "<MD_PATH>" --parent-id <PARENT_ID> --update-if-title-match false
```

- Force update exact page with front matter:
```markdown
---
confluence_id: 123456789
parent_id: 987654321
---
```

## Notes

- This workflow uses Confluence REST API directly, not MCP tools.
- MCP connection failure does not block script-based publishing if API credentials are valid.
- `run_publish.sh` reads installed `.project_root` first, then falls back to auto-discovery/env var.
