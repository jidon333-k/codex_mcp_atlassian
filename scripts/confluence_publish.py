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
import tempfile
import uuid
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


@dataclass
class MermaidImagePlan:
    filename: str
    mermaid_source: str


def render_mermaid_svg(mermaid_source: str) -> str | None:
    encoded = base64.urlsafe_b64encode(mermaid_source.encode("utf-8")).decode("ascii").rstrip("=")
    url = f"https://mermaid.ink/svg/{encoded}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/svg+xml"})
    try:
        with urlopen(req, timeout=30) as resp:
            svg = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    return svg if "<svg" in svg else None


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


def build_mermaid_image_name(prefix: str, index: int) -> str:
    base = re.sub(r"[^\w .()-]+", "", prefix, flags=re.UNICODE).strip()
    if not base:
        base = "Codex Mermaid"
    return f"{base} Mermaid {index:02d}.svg"[:180]


def render_mermaid_svg_local(mermaid_source: str) -> bytes | None:
    mmdc = shutil.which("mmdc")
    if not mmdc:
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="codex-mermaid-") as td:
            in_path = Path(td) / "diagram.mmd"
            out_path = Path(td) / "diagram.svg"
            in_path.write_text(mermaid_source, encoding="utf-8")
            proc = subprocess.run(
                [mmdc, "-i", str(in_path), "-o", str(out_path)],
                capture_output=True,
                text=True,
                timeout=45,
            )
            if proc.returncode != 0 or not out_path.exists():
                return None
            return out_path.read_bytes()
    except Exception:
        return None


def simple_markdown_to_html(
    markdown_text: str,
    *,
    mermaid_mode: str = "code",
    mermaid_image_prefix: str | None = None,
    mermaid_image_width: int = 1000,
    mermaid_image_plans: list[MermaidImagePlan] | None = None,
) -> str:
    lines = markdown_text.splitlines()
    parts: list[str] = []
    in_ul = False
    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []
    mermaid_image_count = 0

    def split_table_row(line: str) -> list[str]:
        raw = line.strip()
        if raw.startswith("|"):
            raw = raw[1:]
        if raw.endswith("|"):
            raw = raw[:-1]
        cells: list[str] = []
        buf: list[str] = []
        escaped = False
        for ch in raw:
            if escaped:
                buf.append(ch)
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == "|":
                cells.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        cells.append("".join(buf).strip())
        return cells

    def is_table_separator_cell(cell: str) -> bool:
        return bool(re.fullmatch(r":?-{3,}:?", cell.strip()))

    def parse_table_alignment(cell: str) -> str | None:
        c = cell.strip()
        if c.startswith(":") and c.endswith(":"):
            return "center"
        if c.endswith(":"):
            return "right"
        if c.startswith(":"):
            return "left"
        return None

    def looks_like_table_header(line: str, next_line: str) -> bool:
        row = line.strip()
        sep = next_line.strip()
        if not (row.startswith("|") and sep.startswith("|")):
            return False
        header_cells = split_table_row(row)
        sep_cells = split_table_row(sep)
        if len(header_cells) < 2 or len(sep_cells) != len(header_cells):
            return False
        return all(is_table_separator_cell(c) for c in sep_cells)

    def looks_like_table_row(line: str) -> bool:
        row = line.strip()
        return row.startswith("|") and "|" in row[1:]

    def render_markdown_table(table_lines: list[str]) -> str:
        header_cells = split_table_row(table_lines[0])
        sep_cells = split_table_row(table_lines[1])
        alignments = [parse_table_alignment(c) for c in sep_cells]

        def render_cell(tag: str, content: str, align: str | None) -> str:
            body = render_inline(content)
            if align:
                return f'<{tag} style="text-align:{align};">{body}</{tag}>'
            return f"<{tag}>{body}</{tag}>"

        out: list[str] = ["<table><thead><tr>"]
        for idx, cell in enumerate(header_cells):
            out.append(render_cell("th", cell, alignments[idx]))
        out.append("</tr></thead><tbody>")

        for row_line in table_lines[2:]:
            row_cells = split_table_row(row_line)
            if len(row_cells) < len(header_cells):
                row_cells.extend([""] * (len(header_cells) - len(row_cells)))
            if len(row_cells) > len(header_cells):
                row_cells = row_cells[: len(header_cells)]
            out.append("<tr>")
            for idx, cell in enumerate(row_cells):
                out.append(render_cell("td", cell, alignments[idx]))
            out.append("</tr>")

        out.append("</tbody></table>")
        return "".join(out)

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

    def emit_mermaid_macro(code_text: str) -> str:
        safe_code = code_text.replace("]]>", "]]]]><![CDATA[>")
        return (
            '<ac:structured-macro ac:name="mermaid">'
            f"<ac:plain-text-body><![CDATA[{safe_code}]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )

    def emit_mermaid_image_macro(filename: str, width: int) -> str:
        safe_filename = html.escape(filename)
        safe_width = max(240, width)
        return (
            f'<ac:image ac:align="center" ac:width="{safe_width}">'
            f'<ri:attachment ri:filename="{safe_filename}" />'
            "</ac:image>"
        )

    def emit_fenced_block(lang: str, code_text: str) -> str:
        nonlocal mermaid_image_count
        lang_norm = lang.strip().lower()
        if mermaid_mode == "macro" and lang_norm in {"mermaid", "mmd"}:
            return emit_mermaid_macro(code_text)
        if mermaid_mode == "attachment" and lang_norm in {"mermaid", "mmd"}:
            mermaid_image_count += 1
            filename = build_mermaid_image_name(mermaid_image_prefix or "Codex Diagram", mermaid_image_count)
            if mermaid_image_plans is not None:
                mermaid_image_plans.append(MermaidImagePlan(filename=filename, mermaid_source=code_text))
            return emit_mermaid_image_macro(filename, mermaid_image_width)
        return emit_code_macro(lang, code_text)

    def close_list() -> None:
        nonlocal in_ul
        if in_ul:
            parts.append("</ul>")
            in_ul = False

    i = 0
    while i < len(lines):
        raw_line = lines[i]
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
                parts.append(emit_fenced_block(code_lang, "\n".join(code_lines)))
                in_code_block = False
                code_lang = ""
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(raw_line)
            i += 1
            continue

        if not stripped:
            close_list()
            i += 1
            continue

        if i + 1 < len(lines) and looks_like_table_header(lines[i], lines[i + 1]):
            close_list()
            table_block = [lines[i], lines[i + 1]]
            i += 2
            while i < len(lines) and looks_like_table_row(lines[i]):
                table_block.append(lines[i])
                i += 1
            parts.append(render_markdown_table(table_block))
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            content = render_inline(heading.group(2).strip())
            parts.append(f"<h{level}>{content}</h{level}>")
            i += 1
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        if bullet:
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{render_inline(bullet.group(1).strip())}</li>")
            i += 1
            continue

        close_list()
        parts.append(f"<p>{render_inline(stripped)}</p>")
        i += 1

    close_list()
    if in_code_block:
        parts.append(emit_fenced_block(code_lang, "\n".join(code_lines)))
    return "\n".join(parts) if parts else "<p></p>"


def markdown_to_html(
    markdown_text: str,
    *,
    mermaid_mode: str = "code",
    mermaid_image_prefix: str | None = None,
    mermaid_image_width: int = 1000,
    mermaid_image_plans: list[MermaidImagePlan] | None = None,
) -> str:
    mermaid_mode = mermaid_mode.lower().strip() or "code"
    if mermaid_mode in {"macro", "attachment"}:
        # Use the internal converter to map ```mermaid fences into macro storage markup.
        return simple_markdown_to_html(
            markdown_text,
            mermaid_mode=mermaid_mode,
            mermaid_image_prefix=mermaid_image_prefix,
            mermaid_image_width=mermaid_image_width,
            mermaid_image_plans=mermaid_image_plans,
        )

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

    return simple_markdown_to_html(
        markdown_text,
        mermaid_mode=mermaid_mode,
        mermaid_image_prefix=mermaid_image_prefix,
        mermaid_image_width=mermaid_image_width,
        mermaid_image_plans=mermaid_image_plans,
    )


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

    def upload_attachment_bytes(
        self,
        *,
        page_id: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        existing = self.find_attachment_by_filename(page_id=page_id, filename=filename)
        safe_filename = filename.replace('"', "_")
        boundary = f"----CodexBoundary{uuid.uuid4().hex}"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                data,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )

        if existing:
            attachment_id = str(existing["id"])
            url = (
                f"https://{self.site}/wiki/rest/api/content/{page_id}/child/attachment/"
                f"{attachment_id}/data"
            )
        else:
            url = f"https://{self.site}/wiki/rest/api/content/{page_id}/child/attachment"
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Atlassian-Token": "nocheck",
        }
        req = Request(url, data=body, method="POST", headers=headers)
        try:
            with urlopen(req, timeout=60) as resp:
                payload = resp.read().decode("utf-8")
        except HTTPError as exc:
            err_payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"POST attachment upload failed "
                f"({exc.code}): {err_payload[:800]}"
            ) from exc

        obj = json.loads(payload)
        if isinstance(obj, dict) and obj.get("id"):
            return obj
        results = obj.get("results", [])
        if not results:
            raise RuntimeError("Attachment upload succeeded but no attachment result was returned.")
        return results[0]

    def find_attachment_by_filename(self, *, page_id: str, filename: str) -> dict[str, Any] | None:
        resp = self._request(
            "GET",
            f"/wiki/rest/api/content/{page_id}/child/attachment",
            query={"filename": filename, "limit": 5},
        )
        results = resp.get("results", [])
        for row in results:
            if row.get("title") == filename:
                return row
        return results[0] if results else None


def render_mermaid_svg_bytes(mermaid_source: str) -> bytes | None:
    local = render_mermaid_svg_local(mermaid_source)
    if local:
        return local
    remote = render_mermaid_svg(mermaid_source)
    if remote:
        return remote.encode("utf-8")
    return None


def upload_mermaid_image_attachments(
    client: ConfluenceClient,
    *,
    page_id: str,
    plans: list[MermaidImagePlan],
) -> None:
    for plan in plans:
        svg_bytes = render_mermaid_svg_bytes(plan.mermaid_source)
        if not svg_bytes:
            svg_bytes = (
                "<svg xmlns='http://www.w3.org/2000/svg' width='960' height='180'>"
                "<rect width='100%' height='100%' fill='#f5f5f5' stroke='#999'/>"
                "<text x='20' y='40' font-family='monospace' font-size='18'>"
                "Mermaid render failed. Showing source below."
                "</text>"
                "<text x='20' y='80' font-family='monospace' font-size='14'>"
                + html.escape(plan.mermaid_source[:300])
                + "</text></svg>"
            ).encode("utf-8")
        client.upload_attachment_bytes(
            page_id=page_id,
            filename=plan.filename,
            data=svg_bytes,
            content_type="image/svg+xml",
        )


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
    mermaid_mode: str,
    mermaid_image_width: int,
) -> PublishResult:
    mermaid_image_plans: list[MermaidImagePlan] = []
    body_html = markdown_to_html(
        doc.body_markdown,
        mermaid_mode=mermaid_mode,
        mermaid_image_prefix=doc.title,
        mermaid_image_width=mermaid_image_width,
        mermaid_image_plans=mermaid_image_plans,
    )
    target_parent = doc.parent_id or default_parent_id
    labels = merge_labels(default_labels, doc.labels)
    mermaid_image_msg = (
        f"; mermaid images={len(mermaid_image_plans)}"
        if mermaid_mode == "attachment" and mermaid_image_plans
        else ""
    )

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
                f"would update version {current_version} -> {next_version}{mermaid_image_msg}",
            )

        if mermaid_mode == "attachment" and mermaid_image_plans:
            upload_mermaid_image_attachments(client, page_id=page_id, plans=mermaid_image_plans)

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
        return PublishResult(
            "dry-create",
            None,
            doc.title,
            doc.path,
            f"would create new page{mermaid_image_msg}",
        )

    created = client.create_page(
        space_id=space_id,
        title=doc.title,
        body_html=body_html,
        parent_id=target_parent,
    )
    page_id = str(created["id"])
    if mermaid_mode == "attachment" and mermaid_image_plans:
        upload_mermaid_image_attachments(client, page_id=page_id, plans=mermaid_image_plans)
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
        "--mermaid-mode",
        choices=["code", "macro", "attachment"],
        default=None,
        help="Render mermaid fenced blocks as code, Confluence macro, or image attachment",
    )
    parser.add_argument(
        "--mermaid-image-width",
        type=int,
        default=None,
        help="Image width(px) when --mermaid-mode attachment (default: env CONFLUENCE_MERMAID_IMAGE_WIDTH or 1000)",
    )
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


def parse_positive_int(raw: str, *, setting_name: str, min_value: int, max_value: int) -> int:
    try:
        parsed = int(raw)
    except ValueError:
        raise ValueError(f"{setting_name} must be an integer") from None
    if parsed < min_value or parsed > max_value:
        raise ValueError(f"{setting_name} must be between {min_value} and {max_value}")
    return parsed


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
    mermaid_mode = (args.mermaid_mode or os.getenv("CONFLUENCE_MERMAID_MODE", "attachment")).strip().lower()
    if mermaid_mode not in {"code", "macro", "attachment"}:
        print("CONFLUENCE_MERMAID_MODE must be 'code', 'macro', or 'attachment'", file=sys.stderr)
        return 2
    mermaid_image_width_raw = (
        str(args.mermaid_image_width)
        if args.mermaid_image_width is not None
        else os.getenv("CONFLUENCE_MERMAID_IMAGE_WIDTH", "1000").strip()
    )
    try:
        mermaid_image_width = parse_positive_int(
            mermaid_image_width_raw,
            setting_name="CONFLUENCE_MERMAID_IMAGE_WIDTH",
            min_value=240,
            max_value=4000,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

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
                mermaid_mode=mermaid_mode,
                mermaid_image_width=mermaid_image_width,
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
