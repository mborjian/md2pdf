from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from . import docids, native_env, styles
from .templates import Template

SRC_RE = re.compile(r'(src|href)="([^"]+)"')
CSS_URL_RE = re.compile(r'url\(\s*"([^"]+)"\s*\)')
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico"}
ATX_HEADING_RE = re.compile(r"^[ \t]{0,3}#[ \t]+(.*?)[ \t]*#*[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
PAGE_BREAK_RE = re.compile(
    r"^[ \t]*(?:\\newpage|\\pagebreak|<!--\s*(?:page[ -]?break|newpage)\s*-->)[ \t]*$",
    re.IGNORECASE,
)
ATX_ANY_RE = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
LIST_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
PAGE_BREAK_TEXT = "\\newpage"
PAGE_BREAK_HTML = '<div class="page-break"></div>'

GENERATOR = "md2pdf"
INLINE_SAMPLE = """# Sample document

Replace this text with your own Markdown, or drop a `.md` file on the uploader.

## Tables

| Option | Meaning |
| --- | --- |
| Page size | A4, Letter, ... |
| Margins | Per side, in millimetres |

## Code

```python
def convert(source: str) -> bytes:
    return render(source)
```

> Block quotes, footnotes[^1] and admonitions are styled by the template.

[^1]: Footnotes render at the end of the document.
"""


@dataclass
class MarkdownBlock:
    start: int
    end: int
    kind: str
    heading: str = ""
    preview: str = ""
    has_break: bool = False

    def label(self) -> str:
        parts = [f"{self.kind} · line {self.start + 1}"]
        if self.heading:
            parts.append(f"under \"{self.heading}\"")
        if self.preview:
            parts.append(self.preview)
        return " · ".join(parts)


@dataclass
class ConversionResult:
    pdf_bytes: bytes
    html: str
    css: str
    doc_id: str
    output_name: str
    title: str
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _load_markdown():
    try:
        import markdown as markdown_lib
    except Exception as exc:
        raise RuntimeError(
            "The 'markdown' package is not installed. Run: pip install -e ."
        ) from exc
    return markdown_lib


def _load_weasyprint():
    try:
        from weasyprint import HTML
    except Exception as exc:
        hint = native_env.library_path_hint()
        message = (
            "WeasyPrint cannot load its system libraries (Pango and friends). "
            "Install them with 'brew install pango libffi' on macOS or "
            "'apt install libpango-1.0-0 libpangoft2-1.0-0' on Debian. "
        )
        if hint:
            message += f"Restart this process with {hint}, or use 'md2pdf ui'. "
        raise RuntimeError(message + "Details: " + str(exc)) from exc
    return HTML


def first_heading(text: str) -> str:
    fence = ""
    for line in (text or "").splitlines():
        marker = FENCE_RE.match(line)
        if marker:
            token = marker.group(1)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            continue
        if fence:
            continue
        match = ATX_HEADING_RE.match(line)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return ""


def make_context(
    template: Template,
    *,
    title: str = "",
    project: str = "",
    filename: str = "",
    context: docids.DocIdContext | None = None,
) -> docids.DocIdContext:
    base = context or docids.DocIdContext()
    return docids.DocIdContext(
        title=base.title or title or template.document.title,
        project=base.project or project,
        template=base.template or template.name,
        filename=base.filename or filename,
        version=base.version or template.version,
    )


def is_page_break(line: str) -> bool:
    return bool(PAGE_BREAK_RE.match(line or ""))


def _fence_update(line: str, fence: str) -> tuple[str, bool]:
    marker = FENCE_RE.match(line)
    if not marker:
        return fence, False
    token = marker.group(1)
    if not fence:
        return token, True
    if token[0] == fence[0] and len(token) >= len(fence):
        return "", True
    return fence, True


def apply_page_breaks(text: str) -> str:
    lines = (text or "").splitlines()
    fence = ""
    output: list[str] = []
    for line in lines:
        fence, inside_fence = _fence_update(line, fence)
        if not fence and not inside_fence and is_page_break(line):
            output.append(PAGE_BREAK_HTML)
        else:
            output.append(line)
    joined = "\n".join(output)
    return joined + "\n" if (text or "").endswith("\n") else joined


def _line_kind(line: str) -> str:
    stripped = line.strip()
    if not stripped or is_page_break(line):
        return ""
    if FENCE_RE.match(line):
        return "code"
    heading = ATX_ANY_RE.match(line)
    if heading and heading.group(2).strip():
        return f"h{len(heading.group(1))} heading"
    if stripped.startswith("|"):
        return "table"
    if stripped.startswith(">"):
        return "quote"
    if LIST_RE.match(line):
        return "list"
    return "paragraph"


def _heading_before(lines: list[str], index: int) -> str:
    fence = ""
    found = ""
    for line in lines[:index]:
        fence, _ = _fence_update(line, fence)
        if fence:
            continue
        match = ATX_ANY_RE.match(line)
        if match and match.group(2).strip():
            found = match.group(2).strip()
    return found


def _shorten(line: str, limit: int = 64) -> str:
    text = " ".join((line or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _block_preview(lines: list[str], start: int, end: int) -> str:
    for line in lines[start:end]:
        if line.strip() and not FENCE_RE.match(line):
            return _shorten(line)
    return _shorten(lines[start]) if start < len(lines) else ""


def markdown_blocks(text: str) -> list[MarkdownBlock]:
    lines = (text or "").splitlines()
    kinds: list[str] = []
    fence = ""
    for line in lines:
        previous_fence = fence
        fence, inside_fence = _fence_update(line, fence)
        kinds.append("code" if (previous_fence or inside_fence) else _line_kind(line))
    blocks: list[MarkdownBlock] = []
    current: MarkdownBlock | None = None
    for index, kind in enumerate(kinds):
        if current is not None and kind == current.kind and kind not in ("", "heading"):
            current.end = index + 1
            continue
        if kind:
            current = MarkdownBlock(start=index, end=index + 1, kind=kind)
            blocks.append(current)
        else:
            current = None
    for block in blocks:
        block.heading = _heading_before(lines, block.start)
        block.preview = _block_preview(lines, block.start, block.end)
        previous = ""
        for line in reversed(lines[: block.start]):
            if line.strip():
                previous = line
                break
        block.has_break = is_page_break(previous)
    return blocks


def insert_page_break(text: str, start_line: int, marker: str = PAGE_BREAK_TEXT) -> str:
    lines = (text or "").splitlines()
    index = max(0, min(int(start_line), len(lines)))
    insertion: list[str] = []
    if index > 0 and lines[index - 1].strip():
        insertion.append("")
    insertion.extend([marker, ""])
    merged = lines[:index] + insertion + lines[index:]
    result = "\n".join(merged)
    return result + "\n" if (text or "").endswith("\n") else result


def render_markdown(text: str, options) -> tuple[str, str]:
    markdown_lib = _load_markdown()
    extensions = options.extension_names()
    configs: dict[str, dict] = {}
    if "toc" in extensions:
        depth = max(int(options.toc_depth or 3), 1)
        configs["toc"] = {
            "title": options.toc_title or "Contents",
            "toc_depth": f"1-{depth}",
            "permalink": False,
            "anchorlink": False,
        }
    if "codehilite" in extensions:
        configs["codehilite"] = {
            "css_class": "codehilite",
            "guess_lang": False,
            "linenums": bool(options.line_numbers),
            "use_pygments": True,
            "noclasses": False,
        }
    engine = markdown_lib.Markdown(extensions=extensions, extension_configs=configs, output_format="html5")
    prepared = apply_page_breaks(text) if getattr(options, "page_breaks", True) else (text or "")
    body = engine.convert(prepared)
    toc_html = getattr(engine, "toc", "") if "toc" in extensions else ""
    return body, toc_html


def document_fields(
    template: Template,
    context: docids.DocIdContext,
    doc_id: str = "",
) -> dict[str, str]:
    document = template.document
    return {
        "doc_id": doc_id,
        "title": context.title,
        "subtitle": document.subtitle,
        "author": document.author,
        "company": document.company,
    }


def _fill(
    text: str,
    context: docids.DocIdContext,
    doc_id: str,
    fields: dict[str, str] | None = None,
) -> str:
    extra = {**(fields or {}), "doc_id": doc_id}
    return docids.expand(text, context, extra=extra, optional_groups=True)


def cover_html(
    template: Template,
    context: docids.DocIdContext,
    doc_id: str,
    base_dir: str | Path | None,
    warnings: list[str] | None = None,
    fields: dict[str, str] | None = None,
) -> str:
    cover = template.document.cover
    blocks: list[str] = []
    if cover.accent_bar:
        blocks.append('<div class="cover-accent"></div>')
    logo_uri = styles.asset_uri(cover.logo, base_dir) if cover.logo else ""
    if cover.logo and not logo_uri and warnings is not None:
        warnings.append(f"cover logo not found: {cover.logo}")
    if logo_uri:
        blocks.append(f'<img class="cover-logo" src="{logo_uri}" alt="" />')
    title = _fill(cover.title, context, doc_id, fields) or context.title
    if title:
        blocks.append(f'<h1 class="cover-title">{escape_html(title)}</h1>')
    subtitle = _fill(cover.subtitle, context, doc_id, fields)
    if subtitle:
        blocks.append(f'<p class="cover-subtitle">{escape_html(subtitle)}</p>')
    meta: list[str] = []
    author = _fill(cover.author, context, doc_id, fields)
    if author:
        meta.append(f"<p>{escape_html(author)}</p>")
    company = _fill(cover.company, context, doc_id, fields)
    if company:
        meta.append(f"<p>{escape_html(company)}</p>")
    if cover.show_doc_id and doc_id:
        label = escape_html(cover.doc_id_label or "Document ID")
        meta.append(f'<p class="cover-docid">{label}: {escape_html(doc_id)}</p>')
    if cover.show_date:
        meta.append(f"<p>{escape_html(_fill('{date:%B %d, %Y}', context, doc_id, fields))}</p>")
    if meta:
        blocks.append('<div class="cover-meta">' + "\n".join(meta) + "</div>")
    inner = '<div class="cover-body">\n' + "\n".join(blocks) + "\n</div>"
    return '<section class="cover">\n<div class="cover-inner">\n' + inner + "\n</div>\n</section>"


def escape_html(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html(
    markdown_html: str,
    template: Template,
    *,
    doc_id: str = "",
    context: docids.DocIdContext | None = None,
    toc_html: str = "",
    base_dir: str | Path | None = None,
    warnings: list[str] | None = None,
) -> tuple[str, str]:
    document = template.document
    doc_context = context or docids.DocIdContext()
    messages = warnings if warnings is not None else []
    fields = document_fields(template, doc_context, doc_id)
    css = styles.build_css(
        template,
        doc_id=doc_id,
        context=doc_context,
        base_dir=base_dir,
        warnings=messages,
        fields=fields,
    )
    placements = document.docid.normalized_placements()
    title = document.title or doc_context.title or "Document"
    head: list[str] = ['<meta charset="utf-8" />', f"<title>{escape_html(title)}</title>"]
    if document.author:
        head.append(f'<meta name="author" content="{escape_html(document.author)}" />')
    if document.subject:
        head.append(f'<meta name="description" content="{escape_html(document.subject)}" />')
    keywords = [document.keywords] if document.keywords else []
    if doc_id and "metadata" in placements:
        keywords.append(doc_id)
        head.append(f'<meta name="dcterms.identifier" content="{escape_html(doc_id)}" />')
    if keywords:
        head.append(f'<meta name="keywords" content="{escape_html(", ".join(keywords))}" />')
    head.append(f'<meta name="generator" content="{GENERATOR}" />')
    head.append(f"<style>\n{css}</style>")
    body: list[str] = []
    if document.cover.enabled:
        body.append(cover_html(template, doc_context, doc_id, base_dir, messages, fields))
    if document.markdown.toc and toc_html:
        body.append('<section class="toc">\n' + toc_html + "\n</section>")
    body.append('<main class="document">\n' + (markdown_html or "") + "\n</main>")
    if document.watermark.enabled:
        body.append(f'<div class="watermark">{escape_html(document.watermark.text)}</div>')
    html = (
        f'<!DOCTYPE html>\n<html lang="{escape_html(document.language or "en")}">\n<head>\n'
        + "\n".join(head)
        + "\n</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )
    return html, css


def output_filename(
    template: Template,
    context: docids.DocIdContext,
    doc_id: str = "",
) -> str:
    pattern = template.document.output.filename_pattern or "{slug}"
    name = docids.expand(pattern, context, extra={"doc_id": doc_id}, optional_groups=True)
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return docids.safe_filename(name, max_length=120) + ".pdf"


def html_to_pdf(html: str, base_url: str | Path | None = None) -> tuple[bytes, int]:
    html_cls = _load_weasyprint()
    document = html_cls(string=html, base_url=str(base_url) if base_url else None).render()
    return document.write_pdf(), len(document.pages)


def render_document(
    markdown_text: str,
    template: Template,
    *,
    doc_id: str = "",
    context: docids.DocIdContext | None = None,
    base_dir: str | Path | None = None,
) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    doc_context = make_context(template, context=context)
    body, toc_html = render_markdown(markdown_text, template.document.markdown)
    html, css = build_html(
        body,
        template,
        doc_id=doc_id,
        context=doc_context,
        toc_html=toc_html,
        base_dir=base_dir,
        warnings=warnings,
    )
    return html, css, warnings


def convert(
    markdown_text: str,
    template: Template,
    *,
    doc_id: str = "",
    context: docids.DocIdContext | None = None,
    base_dir: str | Path | None = None,
) -> ConversionResult:
    doc_context = make_context(template, context=context)
    html, css, warnings = render_document(
        markdown_text,
        template,
        doc_id=doc_id,
        context=doc_context,
        base_dir=base_dir,
    )
    pdf_bytes, page_count = html_to_pdf(html, base_url=base_dir)
    return ConversionResult(
        pdf_bytes=pdf_bytes,
        html=html,
        css=css,
        doc_id=doc_id,
        output_name=output_filename(template, doc_context, doc_id),
        title=template.document.title or doc_context.title,
        page_count=page_count,
        warnings=warnings,
    )


def _local_path(reference: str, base_dir: str | Path | None) -> Path | None:
    if not reference or reference.startswith(("data:", "#")):
        return None
    parsed = urlparse(reference)
    if parsed.scheme in {"http", "https"}:
        return None
    if parsed.scheme == "file":
        return Path(url2pathname(unquote(parsed.path)))
    candidate = Path(unquote(reference))
    if not candidate.is_absolute():
        if not base_dir:
            return None
        candidate = Path(base_dir) / candidate
    return candidate


def inline_assets(html: str, base_dir: str | Path | None = None, max_bytes: int = 8_000_000) -> str:
    cache: dict[str, str] = {}

    def data_uri(reference: str) -> str:
        if reference in cache:
            return cache[reference]
        uri = ""
        path = _local_path(reference, base_dir)
        if path is not None:
            try:
                if path.is_file() and path.stat().st_size <= max_bytes:
                    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                    payload = base64.b64encode(path.read_bytes()).decode("ascii")
                    uri = f"data:{mime};base64,{payload}"
            except OSError:
                uri = ""
        cache[reference] = uri
        return uri

    def replace_attribute(match: re.Match) -> str:
        attribute, reference = match.group(1), match.group(2)
        uri = data_uri(reference)
        return f'{attribute}="{uri}"' if uri else match.group(0)

    text = SRC_RE.sub(replace_attribute, html)
    return CSS_URL_RE.sub(lambda match: f'url("{data_uri(match.group(1)) or match.group(1)}")', text)


def example_markdown_text() -> str:
    for candidate in (
        Path(__file__).resolve().parents[2] / "examples" / "sample.md",
        Path(__file__).resolve().parents[1] / "examples" / "sample.md",
    ):
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                continue
    return INLINE_SAMPLE
