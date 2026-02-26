---
name: confluence-publisher
description: Use when the user asks to publish or update Markdown documents in Confluence. This skill is self-contained in the installed skill folder and runs via scripts/run_publish.sh.
---

# Confluence Publisher Skill

Use this skill for:
- Markdown -> Confluence upload
- Existing page update from local `.md`
- Upload under a specific parent page (including short URL `/wiki/x/...`)

## Preconditions

- Skill installed at `<SKILL_ROOT>/confluence-publisher`
- Environment file exists at `<SKILL_ROOT>/confluence-publisher/.env`
- Typical `<SKILL_ROOT>`: `~/.codex/skills` or `~/.agents/skills`
- Required keys in `.env`:
  - `ATLASSIAN_SITE`
  - `ATLASSIAN_EMAIL`
  - `ATLASSIAN_API_TOKEN`
  - `CONFLUENCE_SPACE_KEY`
- Never print raw API tokens in responses.

If `.env` is missing, run:

```bash
bash ~/.codex/skills/confluence-publisher/scripts/setup_env.sh
# or:
# bash ~/.agents/skills/confluence-publisher/scripts/setup_env.sh
```

If shell env vars are already exported (`ATLASSIAN_*`, `CONFLUENCE_SPACE_KEY`), the runner can work without `.env`.

## Standard Workflow

1. Resolve markdown path.
- WSL path example: `/mnt/c/Users/<user>/Documents/DevMarkdowns/file.md`
- Repo path example: `docs/file.md`

2. Resolve publish target.
- If user gives Confluence short URL (`/wiki/x/...`), resolve final URL and extract page ID.
- If user requests "as child page", pass `--parent-id <resolved_page_id>`.
- If no parent is specified, rely on `.env` `CONFLUENCE_PARENT_ID`.

3. Run dry-run first when risk is non-trivial.

```bash
bash ~/.codex/skills/confluence-publisher/scripts/run_publish.sh --dry-run --glob "<MD_PATH>"
# or:
# bash ~/.agents/skills/confluence-publisher/scripts/run_publish.sh --dry-run --glob "<MD_PATH>"
```

4. Publish.

```bash
bash ~/.codex/skills/confluence-publisher/scripts/run_publish.sh --glob "<MD_PATH>"
# or:
# bash ~/.agents/skills/confluence-publisher/scripts/run_publish.sh --glob "<MD_PATH>"
```

5. Verify and report.
- Report `page_id`, title, `parentId`.
- Share final Confluence URL.

## Command Patterns

- Create/update by title match:
```bash
bash ~/.codex/skills/confluence-publisher/scripts/run_publish.sh --glob "<MD_PATH>" --update-if-title-match true
```

- Force new page under specific parent:
```bash
bash ~/.codex/skills/confluence-publisher/scripts/run_publish.sh --glob "<MD_PATH>" --parent-id <PARENT_ID> --update-if-title-match false
```

- Force update exact page with front matter:
```markdown
---
confluence_id: 123456789
parent_id: 987654321
---
```

## Notes

- This workflow uses Confluence REST API directly (not MCP tools).
- MCP startup failure does not block script-based publishing when API credentials are valid.
