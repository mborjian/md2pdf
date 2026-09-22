from __future__ import annotations

import re
from pathlib import Path
from string import Template as CSSTemplate

from . import docids
from .templates import Template

MARKER = "\x01"
SPECIAL_TOKENS = ("page", "pages", "chapter", "section")
COUNTER_STYLES = {
    "arabic": "",
    "lower-roman": "lower-roman",
    "upper-roman": "upper-roman",
    "lower-alpha": "lower-alpha",
    "upper-alpha": "upper-alpha",
}
SLOT_BOXES = {
    "top": {"left": "@top-left", "center": "@top-center", "right": "@top-right"},
    "bottom": {"left": "@bottom-left", "center": "@bottom-center", "right": "@bottom-right"},
}
ALL_MARGIN_BOXES = tuple(SLOT_BOXES["top"].values()) + tuple(SLOT_BOXES["bottom"].values())

FALLBACK_CODE_THEMES = [
    "default",
    "friendly",
    "monokai",
    "solarized-light",
    "stata-light",
    "xcode",
    "vs",
    "zenburn",
]

FALLBACK_CODE_CSS = """
.codehilite .hll { background-color: #ffffcc }
.codehilite .c, .codehilite .c1, .codehilite .cm { color: #6b7280; font-style: italic }
.codehilite .k, .codehilite .kd, .codehilite .kn, .codehilite .kc { color: #7c3aed; font-weight: 600 }
.codehilite .s, .codehilite .s1, .codehilite .s2, .codehilite .sb { color: #047857 }
.codehilite .m, .codehilite .mi, .codehilite .mf { color: #b45309 }
.codehilite .n, .codehilite .nf { color: #1f2937 }
.codehilite .o, .codehilite .p { color: #6b7280 }
.codehilite .nt { color: #b91c1c }
.codehilite .nd { color: #0369a1 }
"""

BASE_CSS = CSSTemplate(
    """
:root {
  --accent: $accent;
  --muted: $muted_color;
  --border: $border_color;
}
html {
  font-family: $body_font;
  font-size: $base_font_size_pt;
  line-height: $line_height;
  color: $text_color;
  $hyphenation
}
body {
  margin: 0;
}
.document {
  $justify
}
p, li, dd, blockquote {
  orphans: 2;
  widows: 2;
}
p {
  margin: 0 0 0.75em;
}
h1, h2, h3, h4, h5, h6 {
  font-family: $heading_font;
  color: $heading_color;
  line-height: 1.25;
  margin: 1.35em 0 0.5em;
  break-after: avoid;
  break-inside: avoid;
}
h1 {
  font-size: $h1_size;
}
h2 {
  font-size: $h2_size;
}
h3 {
  font-size: $h3_size;
}
h4 {
  font-size: $h4_size;
}
h5 {
  font-size: $h5_size;
}
h6 {
  font-size: $h6_size;
  color: $muted_color;
}
.document h1 {
  string-set: chapter content();
  $break_before_h1
}
.document h2 {
  string-set: section content();
  $break_before_h2
}
.document > h1:first-child {
  break-before: auto;
}
$section_numbering
a {
  color: $link_color;
  text-decoration: none;
}
strong, b {
  color: $heading_color;
}
em, i {
  font-style: italic;
}
hr {
  border: 0;
  border-top: 0.6pt solid $border_color;
  margin: 1.4em 0;
}
ul, ol {
  margin: 0 0 0.9em;
  padding-left: 1.4em;
}
li {
  margin-bottom: 0.25em;
}
dl {
  margin: 0 0 0.9em;
}
dt {
  font-weight: 600;
  color: $heading_color;
}
dd {
  margin: 0 0 0.5em 1.2em;
}
img {
  max-width: 100%;
  height: auto;
}
figure {
  margin: 1em 0;
  break-inside: avoid;
}
figcaption {
  font-size: 0.9em;
  color: $muted_color;
  margin-top: 0.35em;
}
blockquote {
  margin: 0 0 1em;
  padding: 0.4em 0 0.4em 0.9em;
  border-left: 2.5pt solid $accent;
  background: $quote_bg;
  color: $muted_color;
  break-inside: avoid;
}
blockquote p:last-child {
  margin-bottom: 0;
}
mark {
  background: #fef08a;
}
kbd {
  font-family: $mono_font;
  font-size: 0.9em;
  border: 0.5pt solid $border_color;
  border-radius: 3px;
  padding: 0.05em 0.3em;
}
sup, sub {
  font-size: 0.75em;
  line-height: 0;
}
abbr[title] {
  border-bottom: 0.4pt dotted $muted_color;
}
.admonition {
  margin: 0 0 1em;
  padding: 0.5em 0.8em;
  border-left: 2.5pt solid $accent;
  background: $quote_bg;
  break-inside: avoid;
}
.admonition-title {
  font-weight: 600;
  color: $heading_color;
  margin: 0 0 0.3em;
}
.admonition p:last-child {
  margin-bottom: 0;
}
.footnote {
  font-size: 0.9em;
  color: $muted_color;
}
.footnote-ref {
  font-size: 0.75em;
  vertical-align: super;
}
$link_urls
""".strip()
)

HEADING_TOC_CSS = CSSTemplate(
    """
.toc {
  $toc_break
}
.toctitle {
  font-family: $heading_font;
  font-size: $h2_size;
  color: $heading_color;
  font-weight: 600;
  display: block;
  margin-bottom: 0.6em;
}
.toc ul {
  list-style: none;
  margin: 0;
  padding-left: 0.9em;
}
.toc > ul {
  padding-left: 0;
}
.toc li {
  margin: 0.22em 0;
}
.toc a {
  color: $text_color;
}
.toc a::after {
  content: "  " target-counter(attr(href), page);
  color: $muted_color;
  font-size: 0.9em;
}
.toc ul ul {
  font-size: 0.95em;
}
""".strip()
)

TABLE_CSS = CSSTemplate(
    """
table {
  width: $table_width;
  border-collapse: collapse;
  margin: 0 0 1em;
  font-size: $table_font_size_pt;
  break-inside: auto;
}
thead {
  display: table-header-group;
}
tfoot {
  display: table-footer-group;
}
caption {
  caption-side: top;
  text-align: left;
  color: $muted_color;
  font-size: 0.9em;
  padding-bottom: 0.3em;
}
th {
  background: $table_header_bg;
  text-align: left;
  font-weight: 600;
  color: $heading_color;
}
th, td {
  padding: 0.35em 0.5em;
  vertical-align: top;
  $table_cell_border
}
tr {
  break-inside: avoid;
}
$table_zebra
""".strip()
)

CODE_CSS = CSSTemplate(
    """
code, kbd, samp, tt {
  font-family: $mono_font;
  font-size: 0.92em;
}
:not(pre) > code {
  background: $inline_code_bg;
  border-radius: 3px;
  padding: 0.1em 0.28em;
}
pre {
  font-family: $mono_font;
  font-size: $code_font_size_pt;
  line-height: 1.45;
  background: $code_bg;
  border: 0.5pt solid $border_color;
  border-radius: 4px;
  padding: 0.6em 0.8em;
  margin: 0 0 1em;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  break-inside: auto;
}
pre code {
  background: none;
  padding: 0;
  border: 0;
  font-size: 1em;
}
.codehilite {
  background: $code_bg;
  border: 0.5pt solid $border_color;
  border-radius: 4px;
  padding: 0.6em 0.8em;
  margin: 0 0 1em;
}
.codehilite pre {
  background: transparent;
  border: 0;
  border-radius: 0;
  padding: 0;
  margin: 0;
}
.codehilitetable {
  width: 100%;
  border: 0;
  margin: 0;
}
.codehilitetable td {
  border: 0;
  background: none;
  padding: 0;
}
.linenos {
  color: $muted_color;
  text-align: right;
  padding-right: 0.7em !important;
  width: 2.5em;
}
$pygments_css
""".strip()
)

COVER_CSS = CSSTemplate(
    """
.cover {
  page: cover;
  display: table;
  width: $page_width_mm;
  height: $cover_height_mm;
  background: $cover_background;
  background-size: cover;
  background-position: center;
  text-align: center;
  $cover_break
}
.cover-inner {
  display: table-cell;
  vertical-align: $cover_valign;
  padding: $cover_padding;
}
.cover-body {
  display: block;
}
.cover-logo {
  width: $cover_logo_width_mm;
  margin-bottom: 9mm;
}
.cover-accent {
  width: 42mm;
  height: 2.4mm;
  background: $accent;
  margin: 0 auto 7mm;
}
.cover-title {
  font-size: $cover_title_size;
  margin: 0 0 0.35em;
  color: $heading_color;
  string-set: chapter content();
}
.cover-subtitle {
  font-size: $cover_subtitle_size;
  color: $muted_color;
  margin: 0 0 1.6em;
  font-weight: 400;
  string-set: section content();
}
.cover-meta {
  margin-top: 12mm;
  color: $muted_color;
  font-size: 0.95em;
}
.cover-meta p {
  margin: 0.15em 0;
}
.cover-docid {
  font-family: $mono_font;
  letter-spacing: 0.06em;
}
""".strip()
)

WATERMARK_CSS = CSSTemplate(
    """
.watermark {
  position: fixed;
  top: 38%;
  left: 0;
  width: 100%;
  text-align: center;
  font-size: $watermark_size_pt;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: $watermark_color;
  opacity: $watermark_opacity;
  transform: rotate($watermark_rotate_deg);
}
""".strip()
)


def available_code_themes() -> list[str]:
    try:
        from pygments.styles import get_all_styles

        return sorted(get_all_styles())
    except Exception:
        return list(FALLBACK_CODE_THEMES)


def code_highlight_css(style_name: str, selector: str = ".codehilite") -> str:
    try:
        from pygments.formatters import HtmlFormatter
        from pygments.styles import get_style_by_name
    except Exception:
        return FALLBACK_CODE_CSS.strip()
    name = style_name or "friendly"
    try:
        get_style_by_name(name)
    except Exception:
        name = "friendly"
    try:
        return HtmlFormatter(style=name).get_style_defs(selector).strip()
    except Exception:
        return FALLBACK_CODE_CSS.strip()


def asset_uri(path: str, base_dir: str | Path | None = None) -> str:
    if not path:
        return ""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute() and base_dir:
        candidate = Path(base_dir).expanduser() / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return ""
    if not resolved.is_file():
        return ""
    return resolved.as_uri()


def escape_content_text(value: str) -> str:
    text = value.replace("\\", "\\\\").replace('"', '\\"')
    return text.replace("\n", "\\A ").replace("\r", "")


def content_expression(
    text: str,
    *,
    context: docids.DocIdContext | None = None,
    page_style: str = "arabic",
    extra: dict[str, str] | None = None,
    sequence: int = 1,
) -> str:
    if not (text or "").strip():
        return "none"
    base = docids.resolver(context or docids.DocIdContext(), sequence=sequence, extra=extra)
    counter_style = COUNTER_STYLES.get(page_style, "")

    def resolve(name: str, spec: str) -> str:
        key = name.lower()
        if key in SPECIAL_TOKENS:
            return MARKER + key + MARKER
        return base(name, spec)

    expanded = docids.expand_with(text, resolve, optional_groups=True)
    if not expanded.strip():
        return "none"
    nodes: list[str] = []
    for index, chunk in enumerate(re.split(MARKER + r"([a-z]+)" + MARKER, expanded)):
        if index % 2 == 0:
            if chunk:
                nodes.append('"' + escape_content_text(chunk) + '"')
            continue
        if chunk == "page":
            nodes.append(f"counter(page, {counter_style})" if counter_style else "counter(page)")
        elif chunk == "pages":
            nodes.append(f"counter(pages, {counter_style})" if counter_style else "counter(pages)")
        else:
            nodes.append(f"string({chunk})")
    return " ".join(nodes) if nodes else "none"


def _assign_slots(
    logo_slot: str,
    text_slot: str,
    has_logo: bool,
    has_text: bool,
) -> tuple[str, str]:
    logo = logo_slot if has_logo else ""
    text = text_slot if has_text else ""
    if logo and text == logo:
        for candidate in ("center", "right", "left"):
            if candidate != logo:
                text = candidate
                break
    return logo, text


def margin_box_css(
    options,
    side: str,
    *,
    values: dict,
    context: docids.DocIdContext | None,
    page_style: str,
    base_dir: str | Path | None,
    warnings: list[str] | None = None,
) -> str:
    if not options.enabled:
        return ""
    boxes = SLOT_BOXES.get(side, SLOT_BOXES["top"])
    logo_uri = asset_uri(options.logo, base_dir) if options.logo else ""
    if options.logo and not logo_uri and warnings is not None:
        warnings.append(f"{side} logo not found: {options.logo}")
    text_value = content_expression(
        options.text, context=context, page_style=page_style, extra=values.get("extra")
    )
    logo_slot, text_slot = _assign_slots(
        options.logo_position, options.text_position, bool(logo_uri), text_value != "none"
    )
    rule = ""
    if options.show_rule:
        rule = (
            f"    border-bottom: 0.4pt solid {values['border_color']};\n"
            if side == "top"
            else f"    border-top: 0.4pt solid {values['border_color']};\n"
        )
    declarations = [
        f"    font-family: {values['body_font']};",
        f"    font-size: {options.font_size_pt}pt;",
        f"    color: {options.color or values['muted_color']};",
        "    vertical-align: middle;",
        rule.rstrip("\n"),
    ]
    declarations = [item for item in declarations if item.strip()]
    block: list[str] = []
    slots = ("left", "center", "right")
    used = {slot for slot in (logo_slot, text_slot) if slot}
    for slot in slots:
        if slot not in used and not options.show_rule:
            continue
        lines = list(declarations)
        lines.append(f"    text-align: {slot};")
        if slot == logo_slot:
            lines.append(f"    content: \"\";")
            lines.append(f"    width: {options.logo_width_mm}mm;")
            lines.append(f"    height: {max(4.0, options.logo_width_mm * 0.6):g}mm;")
            lines.append(f"    background-image: url(\"{logo_uri}\");")
            lines.append("    background-repeat: no-repeat;")
            lines.append("    background-size: contain;")
            lines.append(f"    background-position: {slot} center;")
            lines.append(f"    padding-{'bottom' if side == 'top' else 'top'}: 1mm;")
        elif slot == text_slot:
            lines.append(f"    content: {text_value};")
        else:
            lines.append('    content: "";')
        if options.show_rule:
            lines.append("    background-clip: border-box;")
        block.append(f"  {boxes[slot]} {{\n" + "\n".join(dict.fromkeys(lines)) + "\n  }")
    if not block:
        return ""
    return "@page {\n" + "\n".join(block) + "\n}\n"


def suppressed_margin_boxes(selector: str, boxes: tuple[str, ...] = ALL_MARGIN_BOXES) -> str:
    lines = [f"  @{box.lstrip('@')} {{ content: none; }}" for box in boxes]
    return f"@page {selector} {{\n" + "\n".join(lines) + "\n}\n"


def _page_rules(
    template: Template,
    values: dict,
    context: docids.DocIdContext | None,
    base_dir: str | Path | None,
    warnings: list[str] | None,
) -> str:
    page = template.page
    document = template.document
    blocks = [
        "@page {\n"
        f"  size: {page.size_css()};\n"
        f"  margin: {page.margins.css()};\n"
        "}\n"
    ]
    header_css = margin_box_css(
        document.header,
        "top",
        values=values,
        context=context,
        page_style=document.page_number_style,
        base_dir=base_dir,
        warnings=warnings,
    )
    footer_css = margin_box_css(
        document.footer,
        "bottom",
        values=values,
        context=context,
        page_style=document.page_number_style,
        base_dir=base_dir,
        warnings=warnings,
    )
    if header_css:
        blocks.append(header_css)
    if footer_css:
        blocks.append(footer_css)
    offset = max(int(document.first_page_number or 1) - 1, 0)
    if document.cover.enabled:
        cover_margin = "@page cover {\n" f"  size: {page.size_css()};\n  margin: 0;\n"
        if document.cover.background and document.cover.background.startswith("#"):
            cover_margin += f"  background: {document.cover.background};\n"
        if document.reset_numbering_after_cover:
            cover_margin += f"  counter-reset: page {offset};\n"
        cover_margin += "}\n"
        blocks.append(cover_margin)
        blocks.append(suppressed_margin_boxes("cover"))
    else:
        if offset:
            blocks.append(f"@page :first {{\n  counter-reset: page {offset};\n}}\n")
        hidden = []
        for options in (document.header, document.footer):
            if options.enabled and not options.show_on_first_page:
                hidden.append(options)
        if hidden:
            blocks.append(suppressed_margin_boxes(":first"))
    return "\n".join(blocks)


def build_css(
    template: Template,
    *,
    doc_id: str = "",
    context: docids.DocIdContext | None = None,
    base_dir: str | Path | None = None,
    sequence: int = 1,
    warnings: list[str] | None = None,
    fields: dict[str, str] | None = None,
) -> str:
    theme = template.theme
    document = template.document
    page = template.page
    base_size = float(theme.base_font_size_pt or 10.5)
    scale = float(theme.heading_scale or 1.0)
    accent = theme.accent or "#2563eb"
    margins = page.margins
    values = {
        "accent": accent,
        "text_color": theme.text_color,
        "heading_color": theme.heading_color,
        "muted_color": theme.muted_color,
        "border_color": theme.border_color,
        "link_color": theme.link_color or accent,
        "body_font": theme.body_font or "serif",
        "heading_font": theme.heading_font or theme.body_font or "serif",
        "mono_font": theme.mono_font or "monospace",
        "base_font_size_pt": f"{base_size:g}pt",
        "line_height": f"{float(theme.line_height or 1.5):g}",
        "h1_size": f"{2.0 * scale:g}em",
        "h2_size": f"{1.55 * scale:g}em",
        "h3_size": f"{1.25 * scale:g}em",
        "h4_size": f"{1.1 * scale:g}em",
        "h5_size": f"{1.0 * scale:g}em",
        "h6_size": f"{0.95 * scale:g}em",
        "hyphenation": "hyphens: auto;" if document.hyphenate else "",
        "justify": "text-align: justify;" if document.justify else "",
        "quote_bg": theme.quote_bg,
        "table_header_bg": theme.table_header_bg,
        "table_zebra_bg": theme.table_zebra_bg,
        "table_width": "100%" if theme.table_full_width else "auto",
        "table_font_size_pt": f"{float(theme.table_font_size_pt or 9.5):g}pt",
        "table_cell_border": (
            f"border: 0.5pt solid {theme.border_color};" if theme.table_border else ""
        ),
        "table_zebra": (
            f"tbody tr:nth-child(even) {{ background: {theme.table_zebra_bg}; }}"
            if theme.table_zebra
            else ""
        ),
        "code_bg": theme.code_bg,
        "code_font_size_pt": f"{float(theme.code_font_size_pt or 9.0):g}pt",
        "inline_code_bg": theme.quote_bg,
        "pygments_css": code_highlight_css(theme.code_theme),
        "break_before_h1": "break-before: page;" if document.markdown.page_break_before_h1 else "",
        "break_before_h2": "break-before: page;" if document.markdown.page_break_before_h2 else "",
        "section_numbering": _section_numbering(document.markdown.numbered_sections),
        "link_urls": (
            '.document a[href^="http"]::after {\n'
            '  content: " (" attr(href) ")";\n'
            "  font-size: 0.85em;\n"
            "  color: inherit;\n"
            "  word-break: break-all;\n"
            "}\n"
            if document.show_link_urls
            else ""
        ),
        "toc_break": "break-after: page;" if document.markdown.toc_break_after else "",
        "page_width_mm": f"{page.dimensions_mm()[0]:g}mm",
        "cover_height_mm": f"{page.dimensions_mm()[1] - 0.2:g}mm",
        "cover_background": _cover_background(document.cover, base_dir, warnings),
        "cover_break": "break-after: page;" if document.cover.break_after else "",
        "cover_valign": {
            "top": "top",
            "center": "middle",
            "bottom": "bottom",
        }.get(document.cover.vertical_align, "middle"),
        "cover_padding": f"{margins.top + 6:g}mm {margins.right * 1.4:g}mm",
        "cover_logo_width_mm": f"{float(document.cover.logo_width_mm or 55):g}mm",
        "cover_title_size": f"{2.6 * scale:g}em",
        "cover_subtitle_size": f"{1.25 * scale:g}em",
        "watermark_size_pt": f"{float(document.watermark.size_pt or 90):g}pt",
        "watermark_color": document.watermark.color or "#ef4444",
        "watermark_opacity": f"{min(max(float(document.watermark.opacity or 0.09), 0.02), 1.0):g}",
        "watermark_rotate_deg": f"{float(document.watermark.rotate_deg or 0):g}deg",
        "extra": {**(fields or {}), "doc_id": doc_id},
    }
    parts = [
        _page_rules(template, values, context, base_dir, warnings),
        BASE_CSS.substitute(values),
        TABLE_CSS.substitute(values),
        CODE_CSS.substitute(values),
    ]
    if document.markdown.toc:
        parts.append(HEADING_TOC_CSS.substitute(values))
    if document.cover.enabled:
        parts.append(COVER_CSS.substitute(values))
    if document.watermark.enabled:
        parts.append(WATERMARK_CSS.substitute(values))
    if document.custom_css.strip():
        parts.append(document.custom_css.strip())
    return "\n".join(part.rstrip() + "\n" for part in parts if part)


def _section_numbering(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        ".document {\n  counter-reset: section;\n}\n"
        ".document h2 {\n  counter-increment: section;\n  counter-reset: subsection;\n}\n"
        ".document h3 {\n  counter-increment: subsection;\n}\n"
        '.document h2::before {\n  content: counter(section) ".  ";\n}\n'
        '.document h3::before {\n  content: counter(section) "." counter(subsection) "  ";\n}\n'
    )


def _cover_background(cover, base_dir: str | Path | None, warnings: list[str] | None) -> str:
    value = (cover.background or "").strip()
    if not value:
        return "transparent"
    if value.startswith("#") or value.lower().startswith(("rgb", "hsl")):
        return value
    uri = asset_uri(value, base_dir)
    if not uri:
        if warnings is not None:
            warnings.append(f"cover background not found: {value}")
        return "transparent"
    return f'url("{uri}")'
