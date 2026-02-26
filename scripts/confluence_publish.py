#!/usr/bin/env python3
"""Publish Markdown files to Confluence Cloud pages."""

from __future__ import annotations

import argparse
import base64
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class Document:
    path: Path
    title: str
    body_markdown: str
    parent_id: str | None
    page_id: str | None
    labels: list[str]


@dataclass
class PublishResult:
    action: str
    page_id: str | None
    title: str
    path: Path
    message: str = ""


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_labels(raw: str | None) -> list[str]:
    if not raw:
        return []

    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]

    labels: list[str] = []
    for item in value.split(","):
        label = item.strip().strip('"').strip("'")
        if label:
            labels.append(label)
    return labels


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text

    lines = text.splitlines(keepends=True)
    if not lines or not lines[0].strip() == "---":
        return {}, text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    front = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])

    metadata: dict[str, str] = {}
    for raw in front.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    return metadata, body


def derive_title(path: Path, body: str, metadata: dict[str, str]) -> str:
    title = metadata.get("title")
    if title:
        return title

    match = re.search(r"^#\s+(.+?)\s*$", body, flags=re.MULTILINE)
    if match:
        return match.group(1).strip().rstrip("#").strip()

    return re.sub(r"[-_]+", " ", path.stem).strip().title()


def simple_markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    parts: list[str] = []
    in_ul = False
    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []

    def render_plain_inline(text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
        return escaped

    def render_inline(text: str) -> str:
        out: list[str] = []
        last = 0
        for match in re.finditer(r"`([^`]+)`", text):
            out.append(render_plain_inline(text[last : match.start()]))
            out.append(f"<code>{html.escape(match.group(1))}</code>")
            last = match.end()
        out.append(render_plain_inline(text[last:]))
        return "".join(out)

    def emit_code_macro(lang: str, code_text: str) -> str:
        # Keep XML CDATA valid even if source contains ']]>'.
        safe_code = code_text.replace("]]>", "]]]]><![CDATA[>")
        safe_lang = html.escape(lang or "none")
        return (
            '<ac:structured-macro ac:name="code">'
            f'<ac:parameter ac:name="language">{safe_lang}</ac:parameter>'
            f"<ac:plain-text-body><![CDATA[{safe_code}]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )

    def close_list() -> None:
        nonlocal in_ul
        if in_ul:
            parts.append("</ul>")
            in_ul = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        fence = re.match(r"^```(.*)$", stripped)
        if fence:
            close_list()
            if not in_code_block:
                in_code_block = True
                code_lang = fence.group(1).strip()
                code_lines = []
            else:
                parts.append(emit_code_macro(code_lang, "\n".join(code_lines)))
                in_code_block = False
                code_lang = ""
                code_lines = []
            continue

        if in_code_block:
            code_lines.append(raw_line)
            continue

        if not stripped:
            close_list()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            content = render_inline(heading.group(2).strip())
            parts.append(f"<h{level}>{content}</h{level}>")
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        if bullet:
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{render_inline(bullet.group(1).strip())}</li>")
            continue

        close_list()
        parts.append(f"<p>{render_inline(stripped)}</p>")

    close_list()
    if in_code_block:
        parts.append(emit_code_macro(code_lang, "\n".join(code_lines)))
    return "\n".join(parts) if parts else "<p></p>"


def markdown_to_html(markdown_text: str) -> str:
    pandoc = shutil.which("pandoc")
    if pandoc:
        proc = subprocess.run(
            [pandoc, "--from", "gfm", "--to", "html5"],
            input=markdown_text,
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout

    try:
        import markdown as markdown_lib  # type: ignore

        rendered = markdown_lib.markdown(
            markdown_text,
            extensions=["fenced_code", "tables", "sane_lists"],
            output_format="xhtml",
        )
        if rendered.strip():
            return rendered
    except Exception:
        pass

    return simple_markdown_to_html(markdown_text)


def merge_labels(base: list[str], extra: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for label in [*base, *extra]:
        lowered = label.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(label)
    return result


class ConfluenceClient:
    def __init__(self, site: str, email: str, api_token: str, *, verbose: bool = False) -> None:
        self.site = site.strip()
        self.verbose = verbose
        token = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("ascii")
        self.auth_header = f"Basic {token}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        url = f"https://{self.site}{path}"
        if query:
            encoded = urlencode(query, doseq=True)
            if encoded:
                url = f"{url}?{encoded}"

        data = None
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
        }

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=45) as resp:
                payload = resp.read().decode("utf-8")
        except HTTPError as exc:
            err_payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path} failed ({exc.code}): {err_payload[:800]}"
            ) from exc

        if not payload.strip():
            return {}
        return json.loads(payload)

    def get_space_by_key(self, key: str) -> dict[str, Any]:
        resp = self._request("GET", "/wiki/api/v2/spaces", query={"keys": [key], "limit": 1})
        results = resp.get("results", [])
        if not results:
            raise RuntimeError(f"Space key not found or inaccessible: {key}")
        return results[0]

    def find_page_by_title(self, space_id: str, title: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            "/wiki/api/v2/pages",
            query={
                "space-id": [space_id],
                "status": ["current"],
                "title": title,
                "limit": 25,
            },
        )
        results = resp.get("results", [])
        for page in results:
            if page.get("title") == title:
                return page
        return results[0] if results else None

    def get_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/wiki/api/v2/pages/{page_id}", query={"body-format": "storage"})

    def create_page(
        self,
        *,
        space_id: str,
        title: str,
        body_html: str,
        parent_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "spaceId": str(space_id),
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": body_html,
            },
        }
        if parent_id:
            payload["parentId"] = str(parent_id)
        return self._request("POST", "/wiki/api/v2/pages", body=payload)

    def update_page(
        self,
        *,
        page_id: str,
        title: str,
        body_html: str,
        next_version: int,
        parent_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": str(page_id),
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": body_html,
            },
            "version": {
                "number": next_version,
                "message": "Updated by Codex publisher",
            },
        }
        if parent_id:
            payload["parentId"] = str(parent_id)
        return self._request("PUT", f"/wiki/api/v2/pages/{page_id}", body=payload)

    def add_labels(self, page_id: str, labels: list[str]) -> None:
        if not labels:
            return
        payload = [{"prefix": "global", "name": label} for label in labels]
        self._request("POST", f"/wiki/rest/api/content/{page_id}/label", body=payload)


def parse_document(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_front_matter(text)

    title = derive_title(path, body, metadata)
    parent_id = metadata.get("parent_id") or metadata.get("parentId")
    page_id = metadata.get("confluence_id") or metadata.get("page_id")
    labels = parse_labels(metadata.get("labels"))

    return Document(
        path=path,
        title=title,
        body_markdown=body,
        parent_id=parent_id,
        page_id=page_id,
        labels=labels,
    )


def publish_document(
    client: ConfluenceClient,
    *,
    doc: Document,
    space_id: str,
    default_parent_id: str | None,
    default_labels: list[str],
    create_if_missing: bool,
    update_if_title_match: bool,
    dry_run: bool,
) -> PublishResult:
    body_html = markdown_to_html(doc.body_markdown)
    target_parent = doc.parent_id or default_parent_id
    labels = merge_labels(default_labels, doc.labels)

    existing: dict[str, Any] | None = None
    if doc.page_id:
        existing = client.get_page(doc.page_id)
    elif update_if_title_match:
        existing = client.find_page_by_title(space_id, doc.title)

    if existing:
        page_id = str(existing["id"])
        if not update_if_title_match and not doc.page_id:
            return PublishResult("skipped", page_id, doc.title, doc.path, "exists and update disabled")

        current_page = existing if doc.page_id else client.get_page(page_id)
        current_version = int(current_page.get("version", {}).get("number", 1))
        next_version = current_version + 1

        if dry_run:
            return PublishResult(
                "dry-update",
                page_id,
                doc.title,
                doc.path,
                f"would update version {current_version} -> {next_version}",
            )

        updated = client.update_page(
            page_id=page_id,
            title=doc.title,
            body_html=body_html,
            next_version=next_version,
            parent_id=target_parent,
        )
        if labels:
            client.add_labels(str(updated["id"]), labels)
        return PublishResult("updated", str(updated["id"]), doc.title, doc.path)

    if not create_if_missing:
        return PublishResult("skipped", None, doc.title, doc.path, "not found and create disabled")

    if dry_run:
        return PublishResult("dry-create", None, doc.title, doc.path, "would create new page")

    created = client.create_page(
        space_id=space_id,
        title=doc.title,
        body_html=body_html,
        parent_id=target_parent,
    )
    page_id = str(created["id"])
    if labels:
        client.add_labels(page_id, labels)
    return PublishResult("created", page_id, doc.title, doc.path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish Markdown files to Confluence")
    parser.add_argument("--dotenv", default=".env", help="Path to .env file (default: .env)")
    parser.add_argument("--glob", dest="glob_pattern", default=None, help="Markdown glob pattern")
    parser.add_argument("--space-key", default=None, help="Confluence space key")
    parser.add_argument("--parent-id", default=None, help="Default parent page id")
    parser.add_argument("--default-labels", default=None, help="Comma-separated labels")
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions only")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument(
        "--create-if-missing",
        choices=["true", "false"],
        default=None,
        help="Create page if title does not exist",
    )
    parser.add_argument(
        "--update-if-title-match",
        choices=["true", "false"],
        default=None,
        help="Update page when title already exists",
    )
    return parser.parse_args()


def bool_arg(value: str | None, fallback_env: str, default: bool) -> bool:
    if value is not None:
        return value == "true"
    return env_bool(fallback_env, default)


def main() -> int:
    args = parse_args()
    load_dotenv(Path(args.dotenv))

    site = os.getenv("ATLASSIAN_SITE", "").strip()
    email = os.getenv("ATLASSIAN_EMAIL", "").strip()
    token = os.getenv("ATLASSIAN_API_TOKEN", "").strip()

    space_key = (args.space_key or os.getenv("CONFLUENCE_SPACE_KEY", "")).strip()
    parent_id = (args.parent_id or os.getenv("CONFLUENCE_PARENT_ID", "")).strip() or None
    glob_pattern = (args.glob_pattern or os.getenv("MARKDOWN_GLOB", "docs/**/*.md")).strip()
    default_labels = parse_labels(args.default_labels or os.getenv("PUBLISH_DEFAULT_LABELS", ""))

    create_if_missing = bool_arg(args.create_if_missing, "PUBLISH_CREATE_IF_MISSING", True)
    update_if_title_match = bool_arg(args.update_if_title_match, "PUBLISH_UPDATE_IF_TITLE_MATCH", True)

    missing = [
        name
        for name, value in [
            ("ATLASSIAN_SITE", site),
            ("ATLASSIAN_EMAIL", email),
            ("ATLASSIAN_API_TOKEN", token),
            ("CONFLUENCE_SPACE_KEY", space_key),
        ]
        if not value
    ]
    if missing:
        print(f"Missing required settings: {', '.join(missing)}", file=sys.stderr)
        return 2

    paths = sorted(Path(p) for p in glob.glob(glob_pattern, recursive=True) if Path(p).is_file())
    if not paths:
        print(f"No markdown files matched: {glob_pattern}")
        return 0

    client = ConfluenceClient(site, email, token, verbose=args.verbose)
    space = client.get_space_by_key(space_key)
    space_id = str(space["id"])

    print(f"Space: {space_key} (id={space_id})")
    print(f"Files: {len(paths)}")
    if args.dry_run:
        print("Mode: dry-run")

    failures = 0
    for path in paths:
        try:
            doc = parse_document(path)
            result = publish_document(
                client,
                doc=doc,
                space_id=space_id,
                default_parent_id=parent_id,
                default_labels=default_labels,
                create_if_missing=create_if_missing,
                update_if_title_match=update_if_title_match,
                dry_run=args.dry_run,
            )
            suffix = f" ({result.message})" if result.message else ""
            page_part = f" page_id={result.page_id}" if result.page_id else ""
            print(f"[{result.action}] {result.path} -> \"{result.title}\"{page_part}{suffix}")
        except Exception as exc:
            failures += 1
            print(f"[error] {path}: {exc}", file=sys.stderr)

    if failures:
        print(f"Completed with {failures} failed file(s).", file=sys.stderr)
        return 1

    print("Completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
