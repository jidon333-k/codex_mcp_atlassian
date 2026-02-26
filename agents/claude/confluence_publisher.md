# Confluence Publisher Instructions (Claude)

This project publishes Markdown files to Confluence via:

- `scripts/publish.sh`
- `scripts/confluence_publish.py`

## Workflow

When asked to publish/update docs in Confluence:

1. Resolve markdown path.
2. Resolve target parent page if specified.
3. Run dry-run when risk is non-trivial.
4. Publish.
5. Report `page_id`, title, and final URL.

## Required Environment

Load `.env` from project root. Required keys:

- `ATLASSIAN_SITE`
- `ATLASSIAN_EMAIL`
- `ATLASSIAN_API_TOKEN`
- `CONFLUENCE_SPACE_KEY`

Optional defaults:

- `CONFLUENCE_PARENT_ID`
- `MARKDOWN_GLOB`
- `CONFLUENCE_MERMAID_MODE`
- `CONFLUENCE_MERMAID_IMAGE_WIDTH`

Never print raw API tokens.

## Commands

Dry-run:

```bash
bash scripts/publish.sh --dry-run --glob "<MD_PATH>"
```

Publish:

```bash
bash scripts/publish.sh --glob "<MD_PATH>"
```

Create child page under specific parent:

```bash
bash scripts/publish.sh --glob "<MD_PATH>" --parent-id <PARENT_ID> --update-if-title-match false
```

Update existing page by title:

```bash
bash scripts/publish.sh --glob "<MD_PATH>" --update-if-title-match true
```

## Short URL Handling

If user provides `/wiki/x/...` short URL, resolve it:

```bash
curl -sS -L -o /dev/null -w '%{url_effective}\n' "https://<site>/wiki/x/<short>"
```

Extract final page ID and use `--parent-id` for child uploads.

## Verification

After publish, verify and return:

- `id`
- `title`
- `parentId`
