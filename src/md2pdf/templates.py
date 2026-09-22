from __future__ import annotations

import copy
import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1

PAGE_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
    "B5": (176.0, 250.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "Tabloid": (279.4, 431.8),
    "Executive": (184.15, 266.7),
    "Custom": (210.0, 297.0),
}
PAGE_SIZE_NAMES = list(PAGE_SIZES_MM)
ORIENTATIONS = ("portrait", "landscape")

FONT_STACKS = {
    "Serif (DejaVu)": "DejaVu Serif, 'Noto Serif', Georgia, 'Times New Roman', serif",
    "Serif (Times)": "'Times New Roman', 'Liberation Serif', Georgia, serif",
    "Georgia": "Georgia, 'Noto Serif', 'Times New Roman', serif",
    "Sans (DejaVu)": "DejaVu Sans, 'Noto Sans', 'Segoe UI', Helvetica, Arial, sans-serif",
    "Sans (Helvetica)": "Helvetica, Arial, 'Liberation Sans', sans-serif",
    "Mono": "DejaVu Sans Mono, 'JetBrains Mono', Consolas, 'Courier New', monospace",
    "Custom": "",
}
MONO_FONT_STACKS = {
    "DejaVu Sans Mono": "DejaVu Sans Mono, 'Noto Sans Mono', monospace",
    "JetBrains Mono": "'JetBrains Mono', 'Fira Code', monospace",
    "Consolas": "Consolas, 'Liberation Mono', monospace",
    "Courier": "'Courier New', Courier, monospace",
    "Custom": "",
}

PAGE_NUMBER_STYLES = ("arabic", "lower-roman", "upper-roman", "lower-alpha", "upper-alpha")
HEADER_FOOTER_SLOTS = ("left", "center", "right")
DOC_ID_PLACEMENTS = ("header", "footer", "cover", "filename", "metadata")


@dataclass
class Margins:
    top: float = 20.0
    right: float = 18.0
    bottom: float = 20.0
    left: float = 18.0

    def css(self) -> str:
        return f"{self.top:g}mm {self.right:g}mm {self.bottom:g}mm {self.left:g}mm"


@dataclass
class PageOptions:
    size: str = "A4"
    orientation: str = "portrait"
    custom_width_mm: float = 210.0
    custom_height_mm: float = 297.0
    margins: Margins = field(default_factory=Margins)

    def dimensions_mm(self) -> tuple[float, float]:
        width, height = PAGE_SIZES_MM.get(self.size, PAGE_SIZES_MM["Custom"])
        if self.size == "Custom":
            width = float(self.custom_width_mm or 210.0)
            height = float(self.custom_height_mm or 297.0)
        if self.orientation == "landscape":
            return max(width, height), min(width, height)
        return min(width, height), max(width, height)

    def size_css(self) -> str:
        width, height = self.dimensions_mm()
        return f"{width:g}mm {height:g}mm"


@dataclass
class HeaderFooterOptions:
    enabled: bool = True
    text: str = ""
    logo: str = ""
    logo_width_mm: float = 16.0
    logo_position: str = "left"
    text_position: str = "right"
    vertical: str = "top"
    show_on_first_page: bool = True
    font_size_pt: float = 8.0
    color: str = ""
    show_rule: bool = False

    def css_class(self) -> str:
        return "header" if self.vertical == "top" else "footer"


@dataclass
class Theme:
    body_font: str = FONT_STACKS["Serif (DejaVu)"]
    heading_font: str = ""
    mono_font: str = MONO_FONT_STACKS["DejaVu Sans Mono"]
    base_font_size_pt: float = 10.5
    line_height: float = 1.5
    heading_scale: float = 1.0
    text_color: str = "#1f2937"
    heading_color: str = "#111827"
    muted_color: str = "#6b7280"
    accent: str = "#2563eb"
    link_color: str = ""
    border_color: str = "#e5e7eb"
    code_theme: str = "friendly"
    code_bg: str = "#f7f8fa"
    code_font_size_pt: float = 9.0
    quote_bg: str = "#f8fafc"
    table_header_bg: str = "#f1f5f9"
    table_zebra: bool = True
    table_zebra_bg: str = "#f8fafc"
    table_border: bool = True
    table_full_width: bool = True
    table_font_size_pt: float = 9.5


@dataclass
class CoverOptions:
    enabled: bool = False
    title: str = "{title}"
    subtitle: str = ""
    author: str = ""
    company: str = ""
    logo: str = ""
    logo_width_mm: float = 55.0
    background: str = ""
    accent_bar: bool = True
    vertical_align: str = "center"
    show_date: bool = True
    show_doc_id: bool = True
    doc_id_label: str = "Document ID"
    break_after: bool = True


@dataclass
class WatermarkOptions:
    enabled: bool = False
    text: str = "DRAFT"
    color: str = "#ef4444"
    opacity: float = 0.09
    size_pt: float = 90.0
    rotate_deg: float = -28.0


@dataclass
class MarkdownOptions:
    tables: bool = True
    fenced_code: bool = True
    codehilite: bool = True
    line_numbers: bool = False
    footnotes: bool = True
    attr_list: bool = True
    def_list: bool = True
    abbr: bool = True
    admonition: bool = True
    md_in_html: bool = True
    sane_lists: bool = True
    smarty: bool = True
    nl2br: bool = False
    toc: bool = False
    toc_depth: int = 3
    toc_title: str = "Contents"
    toc_break_after: bool = True
    numbered_sections: bool = False
    page_break_before_h1: bool = True
    page_break_before_h2: bool = False
    page_breaks: bool = True

    def extension_names(self) -> list[str]:
        names = []
        if self.tables:
            names.append("tables")
        if self.fenced_code or self.codehilite:
            names.append("fenced_code")
        if self.codehilite:
            names.append("codehilite")
        if self.footnotes:
            names.append("footnotes")
        if self.attr_list:
            names.append("attr_list")
        if self.def_list:
            names.append("def_list")
        if self.abbr:
            names.append("abbr")
        if self.admonition:
            names.append("admonition")
        if self.md_in_html:
            names.append("md_in_html")
        if self.sane_lists:
            names.append("sane_lists")
        if self.smarty:
            names.append("smarty")
        if self.nl2br:
            names.append("nl2br")
        if self.toc:
            names.append("toc")
        return names


@dataclass
class DocIdOptions:
    enabled: bool = True
    pattern: str = "DOC-{date:%Y%m%d}-{seq:3}"
    ensure_unique: bool = True
    placements: list[str] = field(default_factory=lambda: ["footer", "cover"])

    def normalized_placements(self) -> list[str]:
        values = [item for item in (self.placements or []) if item in DOC_ID_PLACEMENTS]
        return values or ["footer"]


@dataclass
class OutputOptions:
    filename_pattern: str = "[{doc_id}-]{slug}"
    save_markdown: bool = True


@dataclass
class DocumentOptions:
    title: str = ""
    subtitle: str = ""
    author: str = ""
    company: str = ""
    subject: str = ""
    keywords: str = ""
    language: str = "en"
    header: HeaderFooterOptions = field(default_factory=HeaderFooterOptions)
    footer: HeaderFooterOptions = field(default_factory=HeaderFooterOptions)
    cover: CoverOptions = field(default_factory=CoverOptions)
    watermark: WatermarkOptions = field(default_factory=WatermarkOptions)
    markdown: MarkdownOptions = field(default_factory=MarkdownOptions)
    docid: DocIdOptions = field(default_factory=DocIdOptions)
    output: OutputOptions = field(default_factory=OutputOptions)
    page_number_style: str = "arabic"
    first_page_number: int = 1
    reset_numbering_after_cover: bool = True
    hyphenate: bool = False
    justify: bool = False
    show_link_urls: bool = False
    custom_css: str = ""


@dataclass
class Template:
    name: str = "Untitled template"
    description: str = ""
    version: str = "1.0"
    page: PageOptions = field(default_factory=PageOptions)
    theme: Theme = field(default_factory=Theme)
    document: DocumentOptions = field(default_factory=DocumentOptions)

    def copy(self) -> "Template":
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        data = dataclasses.asdict(self)
        data["schema"] = SCHEMA_VERSION
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict) -> "Template":
        return _build(cls, data or {})

    @classmethod
    def from_json(cls, text: str) -> "Template":
        return cls.from_dict(json.loads(text))

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "Template":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


NESTED_TYPES = {
    cls.__name__: cls
    for cls in (
        Margins,
        PageOptions,
        HeaderFooterOptions,
        Theme,
        CoverOptions,
        WatermarkOptions,
        MarkdownOptions,
        DocIdOptions,
        OutputOptions,
        DocumentOptions,
    )
}


def _type_name(annotation) -> str:
    if isinstance(annotation, str):
        return annotation.split("[")[0].strip()
    return getattr(annotation, "__name__", str(annotation))


def _coerce(annotation, value):
    name = _type_name(annotation)
    if name == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    if name == "int":
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
    if name == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if name == "str":
        return "" if value is None else str(value)
    if name == "list":
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        if value in (None, ""):
            return []
        return [str(value)]
    return value


def _build(cls, data: dict):
    values = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        raw = data[f.name]
        nested = NESTED_TYPES.get(_type_name(f.type))
        if nested is not None and isinstance(raw, dict):
            values[f.name] = _build(nested, raw)
        else:
            values[f.name] = _coerce(f.type, raw)
    return cls(**values)


def _preset_base(name: str, description: str) -> Template:
    template = Template(name=name, description=description)
    template.document.header = HeaderFooterOptions(
        enabled=True, text="{title}", text_position="right", show_rule=True
    )
    template.document.footer = HeaderFooterOptions(
        enabled=True,
        text="[{doc_id}  ·  ]Page {page} of {pages}",
        text_position="right",
        vertical="bottom",
    )
    return template


def preset_modern_brief() -> Template:
    template = _preset_base("Modern brief", "Sans-serif brief with cover, contents page and blue accents.")
    sans = FONT_STACKS["Sans (DejaVu)"]
    template.theme.body_font = sans
    template.theme.heading_font = sans
    template.theme.accent = "#2563eb"
    template.theme.text_color = "#334155"
    template.theme.table_header_bg = "#e8efff"
    template.document.cover.enabled = True
    template.document.cover.background = "#f8fafc"
    template.document.cover.subtitle = "{subtitle}"
    template.document.cover.company = "{company}"
    template.document.markdown.toc = True
    template.document.markdown.page_break_before_h1 = False
    return template


def preset_classic_report() -> Template:
    template = _preset_base("Classic report", "Serif report with numbered sections, contents and a bordered table style.")
    template.theme.accent = "#7c2d12"
    template.theme.text_color = "#1f2937"
    template.theme.table_zebra = False
    template.theme.table_header_bg = "#f3f4f6"
    template.document.cover.enabled = True
    template.document.cover.accent_bar = False
    template.document.cover.show_doc_id = True
    template.document.markdown.toc = True
    template.document.markdown.toc_depth = 3
    template.document.markdown.numbered_sections = True
    template.document.footer.text = "[{doc_id}  ·  ]{page}"
    template.document.footer.text_position = "center"
    return template


def preset_code_handbook() -> Template:
    template = _preset_base("Code handbook", "Portrait handbook tuned for long code blocks and deep tables of contents.")
    template.page.margins = Margins(top=18.0, right=16.0, bottom=18.0, left=16.0)
    template.theme.body_font = FONT_STACKS["Sans (DejaVu)"]
    template.theme.heading_font = FONT_STACKS["Sans (DejaVu)"]
    template.theme.accent = "#0f766e"
    template.theme.code_theme = "friendly"
    template.theme.code_bg = "#f5f7f7"
    template.theme.code_font_size_pt = 8.5
    template.document.markdown.toc = True
    template.document.markdown.toc_depth = 4
    template.document.markdown.numbered_sections = True
    template.document.markdown.line_numbers = False
    template.document.header.text = "{title}"
    template.document.footer.text = "{chapter}  ·  {page}/{pages}"
    return template


def preset_minimal_letter() -> Template:
    template = _preset_base("Minimal letter", "US Letter, generous margins, no header, quiet footer numbering.")
    template.page.size = "Letter"
    template.page.margins = Margins(top=25.4, right=25.4, bottom=25.4, left=25.4)
    template.document.header.enabled = False
    template.document.footer.text = "{page}"
    template.document.footer.text_position = "center"
    template.document.footer.font_size_pt = 9.0
    template.document.docid.enabled = False
    template.document.markdown.page_break_before_h1 = False
    return template


def preset_manual_with_cover() -> Template:
    template = _preset_base("Manual with cover", "Cover page, running chapter headers, watermark support and a sticky document id.")
    template.theme.accent = "#1d4ed8"
    template.document.cover.enabled = True
    template.document.cover.subtitle = "{subtitle}"
    template.document.cover.author = "{author}"
    template.document.cover.company = "{company}"
    template.document.cover.logo_width_mm = 60.0
    template.document.markdown.toc = True
    template.document.markdown.toc_depth = 3
    template.document.markdown.numbered_sections = True
    template.document.header.text = "[{doc_id}  ·  ]{chapter}"
    template.document.header.text_position = "left"
    template.document.footer.text = "Page {page} of {pages}"
    template.document.footer.text_position = "center"
    template.document.watermark.text = "DRAFT"
    template.document.docid.pattern = "MAN-{year}-{seq:4}"
    template.document.docid.placements = ["header", "footer", "cover", "filename"]
    return template


PRESET_BUILDERS = {
    "Modern brief": preset_modern_brief,
    "Classic report": preset_classic_report,
    "Code handbook": preset_code_handbook,
    "Minimal letter": preset_minimal_letter,
    "Manual with cover": preset_manual_with_cover,
}
PRESET_NAMES = list(PRESET_BUILDERS)


def preset(name: str) -> Template:
    builder = PRESET_BUILDERS.get(name)
    if builder is None:
        raise KeyError(name)
    return builder()


def default_template() -> Template:
    return preset("Modern brief")
