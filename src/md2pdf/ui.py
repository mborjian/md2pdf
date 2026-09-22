from __future__ import annotations

import datetime
import hashlib
import re
from pathlib import Path

import streamlit as st

from . import converter, docids, native_env, picker, projects, styles
from .templates import (
    DOC_ID_PLACEMENTS,
    FONT_STACKS,
    HEADER_FOOTER_SLOTS,
    MONO_FONT_STACKS,
    PAGE_NUMBER_STYLES,
    PAGE_SIZE_NAMES,
    PRESET_NAMES,
    Template,
    default_template,
    preset,
)

MODE_ONE_TIME = "One-time convert"
MODE_PROJECT = "Project workspace"
SOURCE_PASTE = "Paste Markdown"
SOURCE_UPLOAD = "Upload files"
SOURCE_EXAMPLE = "Example document"
SOURCE_PROJECT = "Project document"
SOURCE_MODES = (SOURCE_PASTE, SOURCE_UPLOAD, SOURCE_EXAMPLE, SOURCE_PROJECT)
SESSION_SCHEMA = 1
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
MM_TO_PX = 96 / 25.4
PREVIEW_WIDTH_PX = 430.0
NEW_DOCUMENT_NAME = "draft.md"
NEW_DOCUMENT_BODY = "# Untitled document\n\n"


def hex_or(value: str, fallback: str) -> str:
    return value if isinstance(value, str) and HEX_RE.match(value.strip()) else fallback


def state(key: str, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


def revision() -> int:
    return int(state("template_rev", 0))


def wkey(name: str) -> str:
    return f"{name}::{revision()}"


def current_template() -> Template:
    return state("template", default_template())


def set_template(template: Template) -> None:
    st.session_state["template"] = template
    st.session_state["template_rev"] = revision() + 1


def load_preset(name: str) -> None:
    template = preset(name)
    set_template(template)
    st.session_state["status"] = f"Loaded preset '{name}'."


def current_project() -> projects.Project | None:
    value = st.session_state.get("project")
    return value if isinstance(value, projects.Project) else None


def current_edit_entry(project: projects.Project | None) -> dict | None:
    if project is None:
        return None
    entry_id = str(st.session_state.get("editing_id") or "")
    return project.entry(entry_id) if entry_id else None


def editing_enabled(project: projects.Project | None) -> bool:
    if current_edit_entry(project) is None:
        return False
    return bool(st.session_state.get("update_in_place", True))


def begin_editing(project: projects.Project, entry: dict | None) -> None:
    if not entry:
        stop_editing()
        return
    st.session_state["editing_id"] = entry.get("id", "")
    st.session_state["pending_update_in_place"] = True


def stop_editing() -> None:
    st.session_state["editing_id"] = ""
    st.session_state["pending_update_in_place"] = False
    st.session_state.pop("project_document", None)


def apply_pending_edit_flag() -> None:
    if "pending_update_in_place" in st.session_state:
        st.session_state["update_in_place"] = bool(st.session_state.pop("pending_update_in_place"))
    state("update_in_place", True)


def source_fingerprint(text: str, template: Template, doc_id: str) -> str:
    payload = "\n".join([text or "", template.to_json(), doc_id or ""])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def session_snapshot(template: Template, project: projects.Project) -> dict:
    names = project.template_names()
    source = template.name if template.name in names else ""
    return {
        "schema": SESSION_SCHEMA,
        "template": template.to_dict(),
        "template_source": source,
        "template_digest": project.template_digest(source) if source else "",
        "source_mode": str(st.session_state.get("source_mode", SOURCE_PASTE)),
        "source_name": str(st.session_state.get("source_name", "")),
        "source_text": str(st.session_state.get("source_text", ""))[:200000],
        "editing_id": str(st.session_state.get("editing_id") or ""),
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def without_stamp(snapshot: dict) -> dict:
    return {key: value for key, value in snapshot.items() if key != "updated"}


def remember_project_session(project: projects.Project, template: Template) -> None:
    snapshot = session_snapshot(template, project)
    cache = st.session_state.get("session_written") or {}
    if cache.get("root") == str(project.root) and cache.get("snapshot") == without_stamp(snapshot):
        return
    project.save_session(snapshot)
    st.session_state["session_written"] = {
        "root": str(project.root),
        "snapshot": without_stamp(snapshot),
    }


def apply_project_session(project: projects.Project) -> None:
    data = project.load_session()
    stored = data.get("template")
    source = str(data.get("template_source") or "")
    digest = str(data.get("template_digest") or "")
    stale = bool(source and digest) and project.template_digest(source) != digest
    template: Template | None = None
    if isinstance(stored, dict) and not stale:
        try:
            template = Template.from_dict(stored)
        except (TypeError, ValueError, KeyError, AttributeError):
            template = None
    if template is None:
        names = project.template_names()
        active = source if source in names else (names[0] if names else "")
        try:
            template = project.load_template(active) if active else project.load_first_template()
        except (FileNotFoundError, ValueError):
            template = project.load_first_template()
    set_template(template)
    mode = str(data.get("source_mode") or "")
    if mode in SOURCE_MODES:
        st.session_state["pending_source_mode"] = mode
    text = str(data.get("source_text") or "")
    name = str(data.get("source_name") or "")
    if text or name:
        set_source(text, name or "pasted.md", mode if mode in SOURCE_MODES else SOURCE_PASTE)
    entry_id = str(data.get("editing_id") or "")
    stored_entry = project.entry(entry_id) if entry_id else None
    if stored_entry is not None:
        begin_editing(project, stored_entry)
    else:
        stop_editing()
    st.session_state["results"] = []
    st.session_state["session_written"] = {
        "root": str(project.root),
        "snapshot": without_stamp(data),
    }


def open_project(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    project: projects.Project | None = None
    try:
        project = projects.Project.open(candidate)
    except (FileNotFoundError, OSError):
        project = None
    note = ""
    if project is None:
        root = projects.nearest_project_root(candidate)
        if root is None:
            st.session_state["status"] = (
                f"Cannot open '{candidate}': no {projects.PROJECT_FILE} in it or in a parent folder."
            )
            return False
        try:
            project = projects.Project.open(root)
        except (FileNotFoundError, OSError) as exc:
            st.session_state["status"] = f"Cannot open project: {exc}"
            return False
        note = f" (nearest project above {candidate})"
    st.session_state["project"] = project
    st.session_state["pending_mode"] = MODE_PROJECT
    st.session_state["last_browse_dir"] = str(project.root.parent)
    apply_project_session(project)
    projects.remember_recent(project.root)
    st.session_state["status"] = f"Opened project '{project.meta.name}' in {project.root}{note}."
    return True


def document_context(
    template: Template, source_name: str, project: projects.Project | None, text: str = ""
):
    return converter.make_context(
        template,
        title=converter.first_heading(text),
        project=project.meta.name if project else "",
        filename=source_name,
    )


def next_sequence(project: projects.Project | None, pattern: str) -> int:
    if project is not None:
        return project.next_sequence()
    counters = state("session_counters", {})
    return int(counters.get(pattern, 1))


def bump_session_sequence(pattern: str) -> None:
    counters = state("session_counters", {})
    counters[pattern] = int(counters.get(pattern, 1)) + 1
    st.session_state["session_counters"] = counters


def allocate_doc_id(
    template: Template,
    context: docids.DocIdContext,
    project: projects.Project | None,
) -> str:
    options = template.document.docid
    if not options.enabled or not options.pattern.strip():
        return ""
    if project is not None:
        return project.allocate_doc_id(template, context)
    value = docids.expand(
        options.pattern, context, sequence=next_sequence(None, options.pattern), optional_groups=True
    ).strip()
    if docids.uses_counter(options.pattern):
        bump_session_sequence(options.pattern)
    return value


def source_key(name: str) -> str:
    return f"{name}::{int(state('source_rev', 0))}"


def notify(message: str) -> None:
    st.session_state["status"] = message
    st.toast(message)


def set_source(text: str, name: str, mode: str | None = SOURCE_PASTE) -> None:
    st.session_state["source_text"] = text
    st.session_state["source_name"] = name
    st.session_state["source_rev"] = int(state("source_rev", 0)) + 1
    if mode is not None:
        st.session_state["pending_source_mode"] = mode


def new_document(project: projects.Project | None) -> None:
    stop_editing()
    st.session_state["results"] = []
    st.session_state.pop("preview_pdf", None)
    set_source(NEW_DOCUMENT_BODY, NEW_DOCUMENT_NAME, SOURCE_PASTE)
    where = f" in '{project.meta.name}'" if project is not None else ""
    note = "Convert it to add the document to this project." if project is not None else ""
    notify(" ".join(part for part in (f"New document{where}.", note) if part))
    st.rerun()


def source_mode() -> str:
    if "pending_source_mode" in st.session_state:
        st.session_state["source_mode"] = st.session_state.pop("pending_source_mode")
    if "source_mode" not in st.session_state:
        st.session_state["source_mode"] = SOURCE_PASTE
    return st.radio(
        "Source",
        list(SOURCE_MODES),
        horizontal=True,
        key="source_mode",
        label_visibility="collapsed",
    )


def text_field(
    label: str,
    value: str,
    name: str,
    help_text: str | None = None,
    placeholder: str = "",
    key: str | None = None,
) -> str:
    return st.text_input(
        label, value=value or "", key=key or wkey(name), help=help_text, placeholder=placeholder
    )


def text_area(label: str, value: str, name: str, help_text: str | None = None, rows: int = 3) -> str:
    return st.text_area(label, value=value or "", key=wkey(name), help=help_text, height=rows * 26)


def number_field(
    label: str,
    value: float,
    name: str,
    minimum: float = 0.0,
    maximum: float = 200.0,
    step: float = 1.0,
    help_text: str | None = None,
) -> float:
    return st.number_input(
        label,
        min_value=float(minimum),
        max_value=float(maximum),
        value=float(value),
        step=float(step),
        key=wkey(name),
        help=help_text,
    )


def slider_field(
    label: str,
    value: float,
    name: str,
    minimum: float,
    maximum: float,
    step: float,
    help_text: str | None = None,
) -> float:
    return st.slider(
        label,
        min_value=float(minimum),
        max_value=float(maximum),
        value=float(value),
        step=float(step),
        key=wkey(name),
        help=help_text,
    )


def checkbox_field(label: str, value: bool, name: str, help_text: str | None = None) -> bool:
    return st.checkbox(label, value=bool(value), key=wkey(name), help=help_text)


def color_field(label: str, value: str, name: str, fallback: str = "#000000", help_text: str | None = None) -> str:
    return st.color_picker(label, value=hex_or(value, fallback), key=wkey(name), help=help_text)


def select_field(label: str, options: list[str], value: str, name: str, help_text: str | None = None) -> str:
    choices = list(options)
    index = choices.index(value) if value in choices else 0
    return st.selectbox(label, choices, index=index, key=wkey(name), help=help_text)


def font_field(label: str, value: str, name: str, stacks: dict[str, str], fallback: str) -> str:
    preset_name = next((key for key, stack in stacks.items() if stack and stack == value), "Custom")
    chosen = select_field(label, list(stacks), preset_name, f"{name}_preset")
    if chosen == "Custom":
        return text_field(f"{label} (custom CSS font stack)", value, f"{name}_custom", placeholder=fallback)
    return stacks[chosen]


def logo_field(label: str, value: str, name: str, project: projects.Project | None) -> str:
    assets = [project.relative(path) for path in project.assets()] if project else []
    mode = st.radio(
        f"{label} source",
        ["None", "Project asset", "Path"],
        index=2 if (value and value not in assets) else (1 if value in assets else 0),
        key=wkey(f"{name}_mode"),
        horizontal=True,
    )
    if mode == "None":
        return ""
    if mode == "Project asset":
        if not assets:
            st.caption("No assets in this project yet. Upload files in the Project tab.")
            return ""
        return select_field(f"{label} asset", assets, value if value in assets else assets[0], f"{name}_asset")
    return text_field(f"{label} path", value, f"{name}_path", placeholder="assets/logo.png")


def template_editor(template: Template, project: projects.Project | None) -> Template:
    page = template.page
    theme = template.theme
    document = template.document
    markdown_options = document.markdown
    tabs = st.tabs(
        [
            "Page",
            "Typography",
            "Tables & code",
            "Header & footer",
            "Cover",
            "Watermark",
            "Markdown",
            "Document ID",
            "Metadata & advanced",
        ]
    )
    with tabs[0]:
        columns = st.columns(2)
        with columns[0]:
            page.size = select_field("Page size", PAGE_SIZE_NAMES, page.size, "page_size")
            page.orientation = select_field(
                "Orientation", ["portrait", "landscape"], page.orientation, "page_orientation"
            )
        with columns[1]:
            if page.size == "Custom":
                page.custom_width_mm = number_field(
                    "Width (mm)", page.custom_width_mm, "page_custom_width", 20.0, 1000.0, 1.0
                )
                page.custom_height_mm = number_field(
                    "Height (mm)", page.custom_height_mm, "page_custom_height", 20.0, 1000.0, 1.0
                )
            width, height = page.dimensions_mm()
            st.caption(f"Page is {width:g} x {height:g} mm ({page.orientation}).")
        st.markdown("**Margins (mm)**")
        margin_columns = st.columns(4)
        with margin_columns[0]:
            page.margins.top = number_field("Top", page.margins.top, "margin_top", 0.0, 80.0, 1.0)
        with margin_columns[1]:
            page.margins.right = number_field("Right", page.margins.right, "margin_right", 0.0, 80.0, 1.0)
        with margin_columns[2]:
            page.margins.bottom = number_field("Bottom", page.margins.bottom, "margin_bottom", 0.0, 80.0, 1.0)
        with margin_columns[3]:
            page.margins.left = number_field("Left", page.margins.left, "margin_left", 0.0, 80.0, 1.0)

    with tabs[1]:
        columns = st.columns(2)
        with columns[0]:
            theme.body_font = font_field(
                "Body font", theme.body_font, "body_font", FONT_STACKS, "Georgia, serif"
            )
            theme.heading_font = font_field(
                "Heading font", theme.heading_font or theme.body_font, "heading_font", FONT_STACKS, "inherit"
            )
            theme.mono_font = font_field(
                "Monospace font", theme.mono_font, "mono_font", MONO_FONT_STACKS, "monospace"
            )
        with columns[1]:
            theme.base_font_size_pt = slider_field(
                "Body size (pt)", theme.base_font_size_pt, "base_font_size", 7.0, 16.0, 0.25
            )
            theme.line_height = slider_field(
                "Line height", theme.line_height, "line_height", 0.9, 2.5, 0.05
            )
            theme.heading_scale = slider_field(
                "Heading scale", theme.heading_scale, "heading_scale", 0.7, 1.6, 0.05
            )
        color_columns = st.columns(3)
        with color_columns[0]:
            theme.accent = color_field("Accent", theme.accent, "accent", "#2563eb")
            theme.text_color = color_field("Text", theme.text_color, "text_color", "#1f2937")
        with color_columns[1]:
            theme.heading_color = color_field("Headings", theme.heading_color, "heading_color", "#111827")
            theme.muted_color = color_field("Muted", theme.muted_color, "muted_color", "#6b7280")
        with color_columns[2]:
            theme.border_color = color_field("Borders", theme.border_color, "border_color", "#e5e7eb")
            theme.quote_bg = color_field("Quote background", theme.quote_bg, "quote_bg", "#f8fafc")

    with tabs[2]:
        columns = st.columns(2)
        with columns[0]:
            theme.table_header_bg = color_field("Table header", theme.table_header_bg, "table_header_bg", "#f1f5f9")
            theme.table_zebra = checkbox_field("Zebra stripes", theme.table_zebra, "table_zebra")
            if theme.table_zebra:
                theme.table_zebra_bg = color_field("Zebra color", theme.table_zebra_bg, "table_zebra_bg", "#f8fafc")
            theme.table_border = checkbox_field("Cell borders", theme.table_border, "table_border")
            theme.table_full_width = checkbox_field("Full width tables", theme.table_full_width, "table_full_width")
            theme.table_font_size_pt = slider_field(
                "Table font size (pt)", theme.table_font_size_pt, "table_font_size", 7.0, 12.0, 0.25
            )
        with columns[1]:
            theme.code_theme = select_field(
                "Code theme", styles.available_code_themes(), theme.code_theme, "code_theme"
            )
            theme.code_bg = color_field("Code background", theme.code_bg, "code_bg", "#f7f8fa")
            theme.code_font_size_pt = slider_field(
                "Code size (pt)", theme.code_font_size_pt, "code_font_size", 6.0, 12.0, 0.25
            )

    with tabs[3]:
        for options, side, label in ((document.header, "top", "Header"), (document.footer, "bottom", "Footer")):
            st.markdown(f"**{label}**")
            options.enabled = checkbox_field(f"{label} enabled", options.enabled, f"{side}_enabled")
            if not options.enabled:
                continue
            columns = st.columns([2, 1, 1])
            with columns[0]:
                options.text = text_field(
                    f"{label} text",
                    options.text,
                    f"{side}_text",
                    help_text="Tokens: {title} {doc_id} {page} {pages} {chapter} {section} {date}. "
                    "Wrap optional parts in [brackets] to drop them when a token is empty.",
                    placeholder="{doc_id}  ·  Page {page} of {pages}",
                )
            with columns[1]:
                options.text_position = select_field(
                    f"{label} position", list(HEADER_FOOTER_SLOTS), options.text_position, f"{side}_text_position"
                )
            with columns[2]:
                options.font_size_pt = number_field(
                    f"{label} size (pt)", options.font_size_pt, f"{side}_font_size", 5.0, 16.0, 0.5
                )
            logo_columns = st.columns([2, 1, 1])
            with logo_columns[0]:
                options.logo = logo_field(f"{label} logo", options.logo, f"{side}_logo", project)
            with logo_columns[1]:
                options.logo_position = select_field(
                    f"{label} logo position", list(HEADER_FOOTER_SLOTS), options.logo_position, f"{side}_logo_position"
                )
            with logo_columns[2]:
                options.logo_width_mm = number_field(
                    f"{label} logo width (mm)", options.logo_width_mm, f"{side}_logo_width", 4.0, 80.0, 1.0
                )
            extra = st.columns(3)
            with extra[0]:
                options.show_on_first_page = checkbox_field(
                    f"Show {label.lower()} on first page", options.show_on_first_page, f"{side}_first_page"
                )
            with extra[1]:
                if side == "top":
                    options.show_rule = checkbox_field("Rule under header", options.show_rule, "header_rule")
            with extra[2]:
                options.color = text_field(f"{label} color", options.color, f"{side}_color", placeholder="#6b7280")
            st.divider()

    with tabs[4]:
        cover = document.cover
        cover.enabled = checkbox_field("Cover page", cover.enabled, "cover_enabled")
        if cover.enabled:
            columns = st.columns(2)
            with columns[0]:
                cover.title = text_field("Cover title", cover.title, "cover_title", placeholder="{title}")
                cover.subtitle = text_field("Cover subtitle", cover.subtitle, "cover_subtitle")
                cover.author = text_field("Cover author", cover.author, "cover_author")
                cover.company = text_field("Cover company", cover.company, "cover_company")
            with columns[1]:
                cover.vertical_align = select_field(
                    "Vertical align", ["top", "center", "bottom"], cover.vertical_align, "cover_valign"
                )
                cover.logo = logo_field("Cover logo", cover.logo, "cover_logo", project)
                cover.logo_width_mm = number_field(
                    "Cover logo width (mm)", cover.logo_width_mm, "cover_logo_width", 10.0, 160.0, 1.0
                )
                cover.background = text_field(
                    "Cover background", cover.background, "cover_background", placeholder="#f8fafc or assets/cover.png"
                )
            flags = st.columns(3)
            with flags[0]:
                cover.accent_bar = checkbox_field("Accent bar", cover.accent_bar, "cover_accent")
            with flags[1]:
                cover.show_date = checkbox_field("Show date", cover.show_date, "cover_date")
            with flags[2]:
                cover.show_doc_id = checkbox_field("Show document id", cover.show_doc_id, "cover_docid")
            if cover.show_doc_id:
                cover.doc_id_label = text_field("Document id label", cover.doc_id_label, "cover_docid_label")
            cover.break_after = checkbox_field("Start content on a new page", cover.break_after, "cover_break")
            st.caption("Token placeholders work in cover fields too, for example {title} or {project}.")

    with tabs[5]:
        watermark = document.watermark
        watermark.enabled = checkbox_field("Watermark", watermark.enabled, "watermark_enabled")
        if watermark.enabled:
            columns = st.columns(3)
            with columns[0]:
                watermark.text = text_field("Watermark text", watermark.text, "watermark_text")
            with columns[1]:
                watermark.color = color_field("Watermark color", watermark.color, "watermark_color", "#ef4444")
            with columns[2]:
                watermark.size_pt = number_field("Watermark size (pt)", watermark.size_pt, "watermark_size", 20.0, 300.0, 5.0)
            columns = st.columns(3)
            with columns[0]:
                watermark.opacity = slider_field("Opacity", watermark.opacity, "watermark_opacity", 0.02, 0.5, 0.01)
            with columns[1]:
                watermark.rotate_deg = slider_field("Rotation (deg)", watermark.rotate_deg, "watermark_rotation", -90.0, 90.0, 1.0)

    with tabs[6]:
        columns = st.columns(2)
        with columns[0]:
            markdown_options.toc = checkbox_field("Table of contents", markdown_options.toc, "md_toc")
            markdown_options.toc_title = text_field("Contents title", markdown_options.toc_title, "md_toc_title")
            markdown_options.toc_depth = int(
                number_field("TOC depth", markdown_options.toc_depth, "md_toc_depth", 1.0, 6.0, 1.0)
            )
            markdown_options.toc_break_after = checkbox_field(
                "Contents on its own page", markdown_options.toc_break_after, "md_toc_break"
            )
            markdown_options.numbered_sections = checkbox_field(
                "Number h2/h3 headings", markdown_options.numbered_sections, "md_numbered"
            )
        with columns[1]:
            markdown_options.tables = checkbox_field("Tables", markdown_options.tables, "md_tables")
            markdown_options.fenced_code = checkbox_field("Fenced code blocks", markdown_options.fenced_code, "md_fenced")
            markdown_options.codehilite = checkbox_field(
                "Syntax highlighting", markdown_options.codehilite, "md_codehilite"
            )
            markdown_options.line_numbers = checkbox_field("Code line numbers", markdown_options.line_numbers, "md_linenums")
            markdown_options.footnotes = checkbox_field("Footnotes", markdown_options.footnotes, "md_footnotes")
            markdown_options.admonition = checkbox_field("Admonitions", markdown_options.admonition, "md_admonition")
            markdown_options.smarty = checkbox_field("Smart quotes", markdown_options.smarty, "md_smarty")
            markdown_options.nl2br = checkbox_field("Single newline becomes <br>", markdown_options.nl2br, "md_nl2br")
            markdown_options.page_break_before_h1 = checkbox_field(
                "Page break before h1", markdown_options.page_break_before_h1, "md_break_h1"
            )
            markdown_options.page_break_before_h2 = checkbox_field(
                "Page break before h2", markdown_options.page_break_before_h2, "md_break_h2"
            )
            markdown_options.page_breaks = checkbox_field(
                "Page break markers (\newpage)", markdown_options.page_breaks, "md_page_breaks"
            )

    with tabs[7]:
        options = document.docid
        options.enabled = checkbox_field("Generate document ids", options.enabled, "docid_enabled")
        if options.enabled:
            preset_label = st.selectbox(
                "Pattern preset",
                ["(keep current)"] + list(docids.PRESETS),
                index=0,
                key=wkey("docid_preset"),
            )
            if preset_label != "(keep current)":
                st.caption(f"Preset value: {docids.PRESETS[preset_label]}")
                if st.button("Apply preset", key=wkey("docid_apply")):
                    options.pattern = docids.PRESETS[preset_label]
                    st.session_state["template_rev"] = revision() + 1
                    st.rerun()
            options.pattern = text_field("Pattern", options.pattern, "docid_pattern")
            options.ensure_unique = checkbox_field(
                "Never reuse an id inside a project", options.ensure_unique, "docid_unique"
            )
            options.placements = st.multiselect(
                "Show the id in",
                list(DOC_ID_PLACEMENTS),
                default=[item for item in options.normalized_placements() if item in DOC_ID_PLACEMENTS],
                key=wkey("docid_placements"),
                help="Header and footer need the {doc_id} token in their text.",
            )
            unknown = docids.unknown_tokens(options.pattern)
            if unknown:
                st.warning("Unknown tokens are kept literally: " + ", ".join("{" + item + "}" for item in unknown))
            sequence = next_sequence(current_project(), options.pattern)
            sample = docids.expand(
                options.pattern,
                document_context(template, "", current_project()),
                sequence=sequence,
                extra={"doc_id": ""},
                optional_groups=True,
            )
            st.info(f"Next id would be `{sample}` (sequence {sequence}).")
            if st.button("New sample", key=wkey("docid_shuffle")):
                st.rerun()
            with st.expander("Token reference"):
                st.table(
                    [{"token": "{" + token + "}", "meaning": meaning} for token, meaning in docids.TOKEN_REFERENCE]
                )

    with tabs[8]:
        columns = st.columns(2)
        with columns[0]:
            document.title = text_field("Title", document.title, "doc_title")
            document.subtitle = text_field("Subtitle", document.subtitle, "doc_subtitle")
            document.author = text_field("Author", document.author, "doc_author")
            document.company = text_field("Company", document.company, "doc_company")
        with columns[1]:
            document.subject = text_field("Subject (PDF metadata)", document.subject, "doc_subject")
            document.keywords = text_field("Keywords (PDF metadata)", document.keywords, "doc_keywords")
            document.language = text_field("Language", document.language, "doc_language", placeholder="en")
            document.output.filename_pattern = text_field(
                "File name pattern",
                document.output.filename_pattern,
                "doc_filename",
                help_text="Tokens plus {doc_id}. [brackets] drop a part when a token is empty.",
            )
        flags = st.columns(3)
        with flags[0]:
            document.first_page_number = int(
                number_field("First page number", document.first_page_number, "doc_first_page", 1.0, 500.0, 1.0)
            )
            document.reset_numbering_after_cover = checkbox_field(
                "Restart numbering after cover", document.reset_numbering_after_cover, "doc_reset_numbering"
            )
        with flags[1]:
            document.page_number_style = select_field(
                "Page number style", list(PAGE_NUMBER_STYLES), document.page_number_style, "doc_page_style"
            )
            document.hyphenate = checkbox_field("Hyphenate text", document.hyphenate, "doc_hyphenate")
        with flags[2]:
            document.justify = checkbox_field("Justified text", document.justify, "doc_justify")
            document.show_link_urls = checkbox_field("Print link URLs", document.show_link_urls, "doc_links")
            document.output.save_markdown = checkbox_field(
                "Keep Markdown copies in projects", document.output.save_markdown, "doc_save_md"
            )
        document.custom_css = text_area(
            "Custom CSS appended last",
            document.custom_css,
            "doc_custom_css",
            help_text="Overrides everything above. Example: .document h1 { border-bottom: 1pt solid #ddd }",
            rows=6,
        )
    return template


def render_results(results: list[dict]) -> None:
    if not results:
        return
    st.markdown("#### Results")
    for index, item in enumerate(results):
        label = item["name"]
        if item.get("doc_id"):
            label += f"  ·  {item['doc_id']}"
        if item.get("updated"):
            label += "  ·  updated in place"
        with st.container(border=True):
            columns = st.columns([3, 1, 1])
            with columns[0]:
                st.markdown(f"**{label}**")
                if item.get("saved_path"):
                    st.caption(f"Saved to {item['saved_path']}")
            with columns[1]:
                st.metric("Pages", item.get("pages") or 0)
            with columns[2]:
                st.metric("Size", f"{len(item['pdf']) / 1024:.0f} KB")
            for warning in item.get("warnings") or []:
                st.warning(warning)
            actions = st.columns([1, 1, 2])
            with actions[0]:
                st.download_button(
                    "Download PDF",
                    data=item["pdf"],
                    file_name=item["name"],
                    mime="application/pdf",
                    key=f"download_pdf_{index}_{item['id']}",
                )
            with actions[1]:
                st.download_button(
                    "Download HTML",
                    data=item["html"].encode("utf-8"),
                    file_name=item["name"].replace(".pdf", ".html"),
                    mime="text/html",
                    key=f"download_html_{index}_{item['id']}",
                )
            if item.get("markdown"):
                with st.expander("Markdown source"):
                    st.code(item["markdown"], language="markdown")


def convert_sources(
    sources: list[tuple[str, str]],
    template: Template,
    project: projects.Project | None,
    base_dir: Path,
    save_to_disk: bool = False,
    output_dir: Path | None = None,
    edit: dict | None = None,
) -> list[dict]:
    results: list[dict] = []
    for name, text in sources:
        context = document_context(template, name, project, text)
        try:
            doc_id = ""
            if edit is not None:
                doc_id = str(edit.get("doc_id") or "")
            if not doc_id:
                doc_id = allocate_doc_id(template, context, project)
            result = converter.convert(
                text, template, doc_id=doc_id, context=context, base_dir=base_dir
            )
        except (RuntimeError, ValueError, OSError) as exc:
            st.error(f"{name}: {exc}")
            continue
        saved_path = ""
        entry: dict | None = None
        if project is not None and edit is not None:
            entry = project.update_conversion(
                str(edit.get("id") or ""),
                text,
                pdf_bytes=result.pdf_bytes,
                output_name=result.output_name,
                doc_id=doc_id,
                title=context.title,
                template_name=template.name,
                source_name=name,
                page_count=result.page_count,
                save_markdown=template.document.output.save_markdown,
            )
        if entry is not None:
            saved_path = str(project.absolute(entry["pdf"]))
        elif project is not None:
            entry = project.save_conversion(
                text,
                pdf_bytes=result.pdf_bytes,
                output_name=result.output_name,
                doc_id=doc_id,
                title=context.title,
                template_name=template.name,
                source_name=name,
                page_count=result.page_count,
                save_markdown=template.document.output.save_markdown,
            )
            saved_path = str(project.absolute(entry["pdf"]))
        elif save_to_disk and output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            target = docids.unique_path(output_dir / result.output_name)
            target.write_bytes(result.pdf_bytes)
            saved_path = str(target)
        results.append(
            {
                "id": docids.safe_filename(f"{name}-{len(results)}", fallback="doc"),
                "name": result.output_name,
                "doc_id": doc_id,
                "pdf": result.pdf_bytes,
                "html": result.html,
                "markdown": text,
                "pages": result.page_count,
                "warnings": result.warnings,
                "saved_path": saved_path,
                "entry_id": str(entry.get("id") or "") if entry else "",
                "updated": bool(entry and edit is not None),
            }
        )
    return results


def source_editor(text: str, name: str, key: str, height: int = 430) -> str:
    value = st.text_area(
        "Markdown",
        value=text or "",
        height=height,
        key=source_key(key),
        placeholder="# Title\n\nWrite, paste or drop Markdown here.",
    )
    st.session_state["source_text"] = value
    st.session_state["source_name"] = name
    return value


def source_stats(name: str, text: str) -> None:
    label = name or NEW_DOCUMENT_NAME
    lines = len([line for line in (text or "").splitlines() if line.strip()])
    if not lines:
        st.caption(f"{label}  ·  empty")
        return
    words = len((text or "").split())
    st.caption(f"{label}  ·  {lines} lines  ·  {words} words")


def source_panel(
    project: projects.Project | None, mode: str
) -> tuple[list[tuple[str, str]], Path]:
    base_dir = project.root if project is not None else Path.cwd()
    if mode == SOURCE_PASTE:
        text = source_editor(state("source_text", ""), state("source_name", NEW_DOCUMENT_NAME), "paste_area")
        name = text_field(
            "Source file name",
            state("source_name", NEW_DOCUMENT_NAME),
            "source_name_field",
            key=source_key("source_name_field"),
            help_text="Used for the file name when the document has no heading and no document id.",
        )
        st.session_state["source_name"] = name
        source_stats(name, text)
        return [(name, text)] if text.strip() else [], base_dir
    if mode == SOURCE_UPLOAD:
        uploads = st.file_uploader(
            "Drop Markdown files here",
            type=["md", "markdown", "mdown", "mkd", "txt"],
            accept_multiple_files=True,
            key="uploader",
        )
        sources: list[tuple[str, str]] = []
        for upload in uploads or []:
            try:
                sources.append((upload.name, upload.getvalue().decode("utf-8", errors="replace")))
            except Exception as exc:
                st.warning(f"{upload.name}: {exc}")
        if not sources:
            st.caption("Drop one or more .md files, then convert them together.")
            return [], base_dir
        for name, text in sources:
            source_stats(name, text)
        if st.button("Edit the text in the editor", key="edit_upload_button"):
            set_source(sources[0][1], sources[0][0])
            st.rerun()
        return sources, base_dir
    if mode == SOURCE_PROJECT:
        if project is None:
            st.info("Open a project to edit one of its Markdown documents.")
            return [], base_dir
        documents = project.documents()
        if not documents:
            st.info("No Markdown documents in this project yet. Convert something first.")
            return [], project.root
        choices = [project.relative(path) for path in documents]
        picker_row = st.columns([3, 1])
        with picker_row[0]:
            choice = st.selectbox("Document", choices, key=f"project_document_choice::{len(choices)}")
        with picker_row[1]:
            if st.button("Reload from file", key="reload_document_button"):
                st.session_state["project_document"] = ""
                st.rerun()
        if str(state("project_document", "")) != choice:
            try:
                loaded = project.absolute(choice).read_text(encoding="utf-8")
            except OSError as exc:
                st.error(str(exc))
                return [], project.root
            begin_editing(project, project.entry_for_markdown(choice))
            st.session_state["source_text"] = loaded
            st.session_state["source_name"] = Path(choice).name
            st.session_state["source_rev"] = int(state("source_rev", 0)) + 1
            st.session_state["project_document"] = choice
        name = Path(choice).name
        text = source_editor(str(state("source_text", "")), name, "project_area")
        source_stats(name, text)
        entry = current_edit_entry(project)
        if entry is not None:
            st.caption(
                f"Editing {entry.get('doc_id') or entry.get('title') or 'this document'} in place: "
                "converting updates this document instead of adding a copy."
            )
        else:
            st.caption("Not in the project history yet, so converting adds a new document.")
        return [(name, text)] if text.strip() else [], project.root
    text = converter.example_markdown_text()
    st.caption("A small sample document that exercises tables, code blocks, quotes and footnotes.")
    if st.button("Edit the text in the editor", key="edit_example_button"):
        set_source(text, "sample.md")
        st.rerun()
    with st.expander("Preview the sample", expanded=False):
        st.code(text, language="markdown")
    return [("sample.md", text)], base_dir


def page_break_tools(text: str, name: str, mode: str) -> None:
    blocks = [block for block in converter.markdown_blocks(text) if block.start > 0]
    with st.expander("Page breaks", expanded=False):
        st.caption(
            "A line with `\newpage` or `<!-- pagebreak -->` starts a new page. Put one above a table or a "
            "section that should not be split, and the PDF preview shows the pages move."
        )
        if not blocks:
            st.caption("More Markdown, and the places you can break before, show up here.")
            return
        labels = [f"{'✓ ' if block.has_break else ''}{block.label()}" for block in blocks]
        choice = st.selectbox("Insert a page break above", labels, key=f"break_choice::{len(labels)}")
        columns = st.columns([1, 2])
        with columns[0]:
            if st.button("Insert page break", key="insert_break_button"):
                block = blocks[labels.index(choice)]
                set_source(converter.insert_page_break(text, block.start), name, mode=mode)
                notify("Page break inserted.")
                st.rerun()
        with columns[1]:
            st.caption("The marker is plain text, so it survives a round trip through any editor.")


def pdf_panel(item: dict, height: int) -> None:
    viewer = getattr(st, "pdf", None)
    if viewer is not None:
        try:
            viewer(item["pdf"], height=height, key=f"pdf_viewer::{item['id']}")
            return
        except TypeError:
            try:
                viewer(item["pdf"])
                return
            except Exception:
                pass
        except Exception:
            pass
    st.download_button(
        "Download the PDF",
        data=item["pdf"],
        file_name=item["name"],
        mime="application/pdf",
        key=f"pdf_download::{item['id']}",
    )
    st.warning(
        "The inline PDF viewer needs Streamlit's pdf component. Install it with "
        '`pip install "streamlit[pdf]"` to see the pages here.'
    )


def preview_height(template: Template) -> int:
    page_width, page_height = template.page.dimensions_mm()
    width_scale = min(1.0, PREVIEW_WIDTH_PX / (page_width * MM_TO_PX))
    return int(min(page_height * MM_TO_PX * width_scale, 900.0))


def render_preview_pdf(
    text: str,
    template: Template,
    context: docids.DocIdContext,
    base_dir: Path,
    doc_id: str,
    fingerprint: str,
) -> dict:
    try:
        result = converter.convert(text, template, doc_id=doc_id, context=context, base_dir=base_dir)
    except (RuntimeError, ValueError, OSError) as exc:
        return {
            "id": "preview",
            "fingerprint": fingerprint,
            "pdf": b"",
            "pages": 0,
            "name": "",
            "doc_id": doc_id,
            "error": str(exc),
        }
    return {
        "id": "preview",
        "fingerprint": fingerprint,
        "pdf": result.pdf_bytes,
        "pages": result.page_count,
        "name": result.output_name,
        "doc_id": doc_id,
        "html": result.html,
        "warnings": result.warnings,
        "rendered": datetime.datetime.now().strftime("%H:%M:%S"),
    }


def preview_item_from_result(item: dict, text: str, template: Template, doc_id: str) -> dict:
    return {
        "id": "preview",
        "fingerprint": source_fingerprint(text, template, doc_id),
        "pdf": item["pdf"],
        "pages": item.get("pages") or 0,
        "name": item["name"],
        "doc_id": item.get("doc_id", doc_id),
        "html": item.get("html", ""),
        "warnings": item.get("warnings") or [],
        "saved": True,
    }


def preview_panel(
    sources: list[tuple[str, str]],
    template: Template,
    base_dir: Path,
    context: docids.DocIdContext,
    doc_id: str,
) -> int:
    st.markdown("**PDF preview**")
    if not sources:
        st.caption("Paste, drop or load Markdown and the rendered pages appear here.")
        return 0
    text = sources[0][1]
    fingerprint = source_fingerprint(text, template, doc_id)
    preview = st.session_state.get("preview_pdf") or {}
    results = st.session_state.get("results") or []
    controls = st.columns([1, 1])
    with controls[0]:
        refresh = st.button("Update PDF preview", key="refresh_preview_button")
    with controls[1]:
        auto = st.checkbox("Keep it current", value=True, key="auto_preview")
    if refresh or (auto and preview.get("fingerprint") != fingerprint):
        with st.spinner("Rendering the PDF preview…"):
            preview = render_preview_pdf(text, template, context, base_dir, doc_id, fingerprint)
        st.session_state["preview_pdf"] = preview
    pages = int(preview.get("pages") or 0)
    if preview.get("error"):
        st.warning(f"PDF preview: {preview['error']}")
    fallback = dict(results[0]) if results else None
    item = dict(preview) if preview.get("pdf") else fallback
    if item is not None:
        item["pages"] = int(preview.get("pages") or item.get("pages") or 0)
        pages = int(item["pages"]) or pages
    if item is None:
        st.caption("Nothing rendered yet. Write a line or two of Markdown.")
    elif preview.get("pdf"):
        stamp = f"  ·  rendered {preview['rendered']}" if preview.get("rendered") else ""
        st.caption(f"{pages} page(s){stamp}")
    else:
        st.caption(f"Showing the last saved PDF ({item['name']}); the live render failed.")
    if item is not None:
        pdf_panel(item, preview_height(template))
    return pages


def convert_tab(template: Template, project: projects.Project | None) -> None:
    st.caption(
        "Write Markdown on the left and the pages update on the right. Convert to PDF saves the file."
    )
    st.caption("Source")
    toolbar = st.columns([3, 1])
    with toolbar[0]:
        mode = source_mode()
    with toolbar[1]:
        if st.button("New document", key="new_document_button", help="Start from an empty page."):
            new_document(project)
    left, right = st.columns([1, 1], gap="large")
    with left:
        sources, base_dir = source_panel(project, mode)
        name, text = sources[0] if sources else ("", "")
        if text.strip() and mode in (SOURCE_PASTE, SOURCE_PROJECT):
            page_break_tools(text, name, mode)
        if project is not None:
            apply_pending_edit_flag()
        edit_entry = current_edit_entry(project)
    options = template.document.docid
    context = document_context(template, name, project, text)
    doc_id_preview = ""
    if options.enabled and options.pattern.strip():
        doc_id_preview = docids.expand(
            options.pattern,
            context,
            sequence=next_sequence(project, options.pattern),
            extra={"doc_id": ""},
            optional_groups=True,
        ).strip()
    if edit_entry is not None and str(edit_entry.get("doc_id") or ""):
        doc_id_preview = str(edit_entry["doc_id"])
    with right:
        pages = preview_panel(sources, template, base_dir, context, doc_id_preview)
    with st.container(border=True):
        meta = st.columns([2, 2, 3, 1])
        with meta[0]:
            st.caption("Template")
            st.markdown(f"`{template.name}`")
        with meta[1]:
            st.caption("Document id")
            st.markdown(f"`{doc_id_preview or 'disabled'}`")
        with meta[2]:
            st.caption("Output file")
            st.markdown(f"`{converter.output_filename(template, context, doc_id_preview)}`")
        with meta[3]:
            st.caption("Pages")
            st.markdown(f"`{pages or '—'}`")
        st.divider()
        if project is None:
            if "pending_one_time_output" in st.session_state:
                st.session_state["one_time_output"] = st.session_state.pop("pending_one_time_output")
                st.session_state["output_rev"] = int(state("output_rev", 0)) + 1
            columns = st.columns([4, 1, 1])
            with columns[0]:
                output_value = text_field(
                    "Save a copy to this folder",
                    str(state("one_time_output", str(Path.cwd() / "output"))),
                    "one_time_output_field",
                    key=f"one_time_output_field::{int(state('output_rev', 0))}",
                )
                st.session_state["one_time_output"] = output_value
            with columns[1]:
                if st.button("Browse…", key="browse_output_button"):
                    chosen, reason = picker.choose_directory(
                        "Choose the folder for the PDF copy", output_value
                    )
                    if reason:
                        st.session_state["picker_error"] = reason
                    elif chosen is not None:
                        st.session_state["pending_one_time_output"] = str(chosen)
                    st.rerun()
            with columns[2]:
                save_to_disk = st.checkbox("Save copy", value=True, key="one_time_save")
            output_dir = Path(output_value).expanduser()
        else:
            save_to_disk = False
            output_dir = None
            st.caption(f"PDFs and Markdown copies are written inside {project.root}.")
            if edit_entry is not None:
                st.info(
                    f"Editing {edit_entry.get('doc_id') or edit_entry.get('title') or 'this document'}: "
                    f"converting overwrites {edit_entry.get('pdf')} instead of adding a second copy."
                )
                row = st.columns([2, 2, 3])
                with row[0]:
                    st.checkbox("Update that document in place", key="update_in_place")
                with row[1]:
                    if st.button("Stop editing and save new copies", key="stop_editing_button"):
                        stop_editing()
                        st.rerun()
    disabled = not sources
    actions = st.columns([1, 3])
    with actions[0]:
        convert_clicked = st.button(
            "Convert to PDF", type="primary", disabled=disabled, key="convert_button"
        )
    with actions[1]:
        if disabled:
            st.caption("Add Markdown first: paste text, drop a file, or load the example.")
        elif project is not None:
            st.caption("Saves the PDF and a Markdown copy inside the project.")
        else:
            st.caption("Nothing is written to disk unless Save copy is ticked.")
    if convert_clicked:
        edit = edit_entry if editing_enabled(project) else None
        with st.spinner("Rendering PDF..."):
            results = convert_sources(
                sources, template, project, base_dir, bool(save_to_disk), output_dir, edit
            )
        st.session_state["results"] = results
        if results:
            message = (
                f"Updated {results[0]['name']} in place."
                if results[0].get("updated")
                else f"Converted {len(results)} document(s)."
            )
            st.session_state["preview_pdf"] = preview_item_from_result(
                results[0], text, template, doc_id_preview
            )
            adopted = None
            if project is not None and not results[0].get("updated"):
                adopted = project.entry(str(results[0].get("entry_id") or ""))
                if adopted is not None:
                    begin_editing(project, adopted)
                    label = adopted.get("doc_id") or adopted.get("pdf")
                    message += (
                        f" Editing {label} from now on: the next conversion updates it instead of adding "
                        "a copy."
                    )
            st.session_state["status"] = message
            if adopted is not None:
                st.rerun()
            st.toast(message)
    render_results(st.session_state.get("results") or [])


def template_tab(template: Template, project: projects.Project | None) -> None:
    st.caption(
        "Everything about how the PDF looks: page, fonts, colors, tables, code, header and footer, cover "
        "and watermark. Changes show up in the PDF preview on the Write tab."
    )
    with st.container(border=True):
        columns = st.columns([2, 1, 1, 1])
        with columns[0]:
            template.name = text_field("Template name", template.name, "template_name")
        with columns[1]:
            if st.button("Save to project", disabled=project is None, key="save_template_button"):
                assert project is not None
                project.save_template(template)
                st.session_state["status"] = f"Saved template '{template.name}'."
                st.rerun()
        with columns[2]:
            st.download_button(
                "Export JSON",
                data=template.to_json().encode("utf-8"),
                file_name=f"{docids.safe_filename(template.name, fallback='template')}.json",
                mime="application/json",
                key="export_template",
            )
        with columns[3]:
            if st.button("Reset to preset", key="reset_template_button"):
                load_preset("Modern brief")
                st.rerun()
        columns = st.columns(2)
        with columns[0]:
            description = text_field("Description", template.description, "template_description")
            template.description = description
        with columns[1]:
            template.version = text_field("Version", template.version, "template_version")
        upload = st.file_uploader("Import template JSON", type=["json"], key="template_import")
        if upload is not None:
            try:
                imported = Template.from_json(upload.getvalue().decode("utf-8"))
                set_template(imported)
                st.session_state["status"] = f"Imported template '{imported.name}'."
                st.rerun()
            except (ValueError, UnicodeDecodeError) as exc:
                st.error(f"Could not read that template: {exc}")
        st.caption(
            "The template is stored as JSON: save it into a project to reuse it, export it, or drop it "
            "into another project."
        )
    template_editor(template, project)


def recent_projects() -> list[Path]:
    return [item for item in projects.load_recents() if projects.is_project(item)]


def known_projects() -> list[Path]:
    found: list[Path] = []
    candidates = (
        recent_projects()
        + projects.find_projects(projects.default_projects_root())
        + projects.find_projects(Path.cwd())
    )
    for item in candidates:
        resolved = item.expanduser()
        if resolved in found or not projects.is_project(resolved):
            continue
        found.append(resolved)
    return found


def browse_start() -> Path:
    candidate = Path(str(state("last_browse_dir", "")) or ".").expanduser()
    return candidate if candidate.is_dir() else Path.cwd()


def open_project_from_dialog() -> None:
    chosen, reason = picker.choose_directory("Open a project folder", browse_start())
    if reason:
        st.session_state["picker_error"] = reason
        st.rerun()
        return
    if chosen is not None and open_project(chosen):
        st.rerun()


def choose_parent_folder() -> None:
    current = Path(str(state("new_project_parent", "")) or ".").expanduser()
    chosen, reason = picker.choose_directory(
        "Choose the folder that will hold the project",
        current if current.is_dir() else browse_start(),
    )
    if reason:
        st.session_state["picker_error"] = reason
    elif chosen is not None:
        st.session_state["pending_new_project_parent"] = str(chosen)
    st.rerun()


def create_project_panel() -> None:
    st.markdown("**Create a project**")
    if "pending_new_project_parent" in st.session_state:
        st.session_state["new_project_parent"] = st.session_state.pop("pending_new_project_parent")
    state("new_project_name", "Reports")
    state("new_project_parent", str(projects.default_projects_root()))
    state("new_project_preset", PRESET_NAMES[0])
    state("new_project_description", "")
    name = st.text_input("Project name", key="new_project_name")
    parent_columns = st.columns([3, 1])
    with parent_columns[0]:
        parent = st.text_input("Parent folder", key="new_project_parent")
    with parent_columns[1]:
        if st.button("Browse…", key="browse_parent_button"):
            choose_parent_folder()
    chosen = st.selectbox("Starting template", PRESET_NAMES, key="new_project_preset")
    description = st.text_input("Description", key="new_project_description")
    if st.button("Create project", key="create_project_button"):
        root = Path(parent).expanduser() / docids.safe_filename(name, fallback="project")
        template = preset(chosen)
        template.name = "Default"
        new_project = projects.Project.create(root, name=name, template=template, description=description)
        st.session_state["project"] = new_project
        st.session_state["pending_mode"] = MODE_PROJECT
        st.session_state["results"] = []
        set_template(new_project.load_first_template())
        projects.remember_recent(new_project.root)
        notify(f"Created project '{new_project.meta.name}' in {new_project.root}.")
        st.rerun()


def open_project_panel() -> None:
    st.markdown("**Open a project**")
    path = st.text_input("Project folder", key="open_project_path", placeholder=str(Path.cwd()))
    columns = st.columns(2)
    with columns[0]:
        if st.button("Open project", type="primary", key="open_project_button"):
            if open_project(path):
                st.rerun()
    with columns[1]:
        if st.button("Browse…", key="browse_project_button"):
            open_project_from_dialog()
    found = known_projects()
    if found:
        labels = [f"{item.name}  ·  {item}" for item in found]
        choice = st.selectbox("Projects on this machine", labels, key=f"known_project::{len(found)}")
        if st.button("Open selected project", key="open_known_button"):
            if open_project(found[labels.index(choice)]):
                st.rerun()
    st.caption(
        f"Any folder with a {projects.PROJECT_FILE} can be opened, even after you move it. Type a path, "
        "browse for one, or pick from the list: the template you were editing, its colors and logos, the "
        "Markdown and the document you were editing all come back."
    )


def project_tab(project: projects.Project | None) -> None:
    if project is None:
        st.caption(
            "A project keeps templates, assets, Markdown and PDFs together in one folder you can move, "
            "copy or put in version control."
        )
        columns = st.columns(2)
        with columns[0]:
            with st.container(border=True):
                create_project_panel()
        with columns[1]:
            with st.container(border=True):
                open_project_panel()
        st.info(
            "No project is open. Create or open one to keep templates, assets, Markdown and PDFs together."
        )
        return
    summary = project.summary()
    metrics = st.columns(5)
    for column, key in zip(metrics, ("templates", "documents", "pdfs", "assets", "next_sequence")):
        column.metric(key.replace("_", " ").title(), summary[key])
    with st.container(border=True):
        st.markdown(f"**{project.meta.name}**")
        st.caption(str(project.root))
        actions = st.columns([1, 1, 1, 2])
        with actions[0]:
            if st.button("Rescan output folder", key="rescan_button"):
                added = project.rescan()
                notify(f"Found {added} new PDF(s).")
                st.rerun()
        with actions[1]:
            if st.button("Switch project…", key="switch_project_button"):
                open_project_from_dialog()
        with actions[2]:
            if st.button("Close project", key="close_project_button"):
                st.session_state["project"] = None
                st.session_state["results"] = []
                stop_editing()
                st.rerun()
        with actions[3]:
            st.caption(f"Next document sequence: {project.next_sequence()}")
        st.caption(
            f"Editing template '{current_template().name}'. The template, the Markdown you are working on "
            f"and the document you are editing are kept in {projects.SESSION_FILE} and come back the next "
            "time you open this project."
        )
    columns = st.columns(2)
    with columns[0]:
        with st.container(border=True):
            st.markdown("**Templates in this project**")
            names = project.template_names()
            if names:
                selected = st.selectbox("Template", names, key=f"project_template_select::{len(names)}")
                actions = st.columns(3)
                with actions[0]:
                    if st.button("Load", key="project_template_load"):
                        set_template(project.load_template(selected))
                        st.rerun()
                with actions[1]:
                    rename = st.text_input("Rename to", value=selected, key="project_template_rename_value")
                    if st.button("Rename", key="project_template_rename") and rename.strip():
                        project.rename_template(selected, rename.strip())
                        st.session_state["status"] = f"Renamed to '{rename.strip()}'."
                        st.rerun()
                with actions[2]:
                    confirm = st.checkbox("Confirm", key="project_template_delete_confirm")
                    if st.button("Delete", key="project_template_delete", disabled=not confirm):
                        project.delete_template(selected)
                        st.session_state["status"] = f"Deleted template '{selected}'."
                        st.rerun()
                st.caption("Save with Save to project on the Design tab, or from the sidebar.")
            else:
                st.caption("No templates yet.")
    with columns[1]:
        with st.container(border=True):
            st.markdown("**Assets**")
            uploads = st.file_uploader(
                "Upload logos and images", accept_multiple_files=True, key="asset_uploader"
            )
            if uploads and st.button("Add uploaded files to assets", key="asset_add_button"):
                added = [project.add_asset(upload.name, upload.getvalue()).name for upload in uploads]
                notify("Added: " + ", ".join(added))
            assets = project.assets()
            if assets:
                for path in assets:
                    row = st.columns([3, 1])
                    with row[0]:
                        st.caption(f"{project.relative(path)}  ·  {path.stat().st_size / 1024:.0f} KB")
                    with row[1]:
                        if st.button("Remove", key=f"asset_remove_{path.name}"):
                            project.delete_asset(path.name)
                            st.rerun()
            else:
                st.caption("No assets yet. Logos referenced by templates live here.")
    with st.expander("Project folder layout"):
        st.code(
            "\n".join(
                [
                    f"{project.root.name}/",
                    f"  {projects.PROJECT_FILE}      project name, description, schema",
                    f"  {projects.TEMPLATES_DIR}/       one JSON file per template",
                    f"  {projects.DOCUMENTS_DIR}/       Markdown copies of everything converted",
                    f"  {projects.OUTPUT_DIR}/          generated PDFs",
                    f"  {projects.ASSETS_DIR}/          logos, images, any external file",
                    f"  {projects.MANIFEST_FILE}     history of every conversion",
                    f"  {projects.STATE_FILE}        document id counters",
                    f"  {projects.SESSION_FILE}      where you left off in the app",
                ]
            ),
            language=None,
        )


def library_tab(project: projects.Project | None) -> None:
    if project is None:
        st.caption("Open a project to browse its history. One-time conversions live only in this session.")
        return
    history = project.history()
    if not history:
        st.caption("Nothing converted in this project yet. The first conversion shows up here.")
        return
    st.caption(f"{len(history)} document(s) in {project.root.name}, newest first.")
    st.dataframe(
        [
            {
                "document id": entry.get("doc_id", ""),
                "title": entry.get("title", ""),
                "template": entry.get("template", ""),
                "pages": entry.get("pages", 0),
                "created": entry.get("created", ""),
                "pdf": entry.get("pdf", ""),
            }
            for entry in history
        ],
        hide_index=True,
    )
    for index, entry in enumerate(history[:25]):
        label = entry.get("doc_id") or entry.get("title") or entry.get("pdf", "document")
        with st.container(border=True):
            columns = st.columns([3, 1, 1, 1])
            with columns[0]:
                st.markdown(f"**{label}**")
                st.caption(
                    f"{entry.get('title', '')}  ·  {entry.get('created', '')}  ·  {entry.get('pdf', '')}"
                )
            with columns[1]:
                st.download_button(
                    "Download",
                    data=project.entry_pdf_bytes(entry),
                    file_name=Path(entry.get("pdf", "document.pdf")).name,
                    mime="application/pdf",
                    key=f"library_download_{index}_{entry.get('id')}",
                )
            with columns[2]:
                if st.button("Edit", key=f"library_open_{index}_{entry.get('id')}"):
                    text = project.read_entry_markdown(entry)
                    if text:
                        begin_editing(project, entry)
                        st.session_state["project_document"] = entry.get("markdown", "")
                        set_source(text, Path(entry.get("markdown", "document.md")).name)
                        notify("Opened for editing: converting updates this document.")
                        st.rerun()
                    else:
                        st.warning("No Markdown copy for that entry.")
            with columns[3]:
                confirm = st.checkbox("Confirm", key=f"library_forget_confirm_{index}_{entry.get('id')}")
                if st.button("Forget", key=f"library_forget_{index}_{entry.get('id')}", disabled=not confirm):
                    project.forget_entry(entry.get("id", ""), delete_files=False)
                    st.rerun()


def help_tab() -> None:
    st.caption("How the two modes work, and what every token and setting does.")
    st.markdown(
        """
**One-time convert** is for a single document: paste Markdown, load the example, or drop a file.
**Project workspace** keeps templates, assets, Markdown and PDFs in one folder that you can move, copy
or put in version control. Any folder with a `project.json` is a project, so it can live anywhere, even
on a drive you move around.
**Write tab**: the Markdown editor sits beside the rendered PDF, so an edit, a page break or a style
change is judged on the page right away. **New document** clears the editor and starts a fresh one.
**Browse** opens your operating system's own folder dialog, the same panel your file manager shows.
Picking a folder inside a project opens the project above it, and the next dialog starts beside the
last project you used. Recent projects are also listed next to the path box.
**Continue where you left off**: reopening a project reloads the template you were editing, including
its colors, fonts and logos, plus the Markdown, the source mode and the document you were editing, from
`session.json`. The next document id keeps counting where it stopped.
**Page breaks**: a line with `\newpage` (or `<!-- pagebreak -->`) starts a new page. The **Page breaks**
panel in the Write tab inserts one above any heading, table, list or code block you pick, and the PDF
preview shows the pages move.
**Editing an old document**: open it from the Library or from the project documents in the source panel,
edit it, and converting updates that document in place — same id, same file names, no duplicate.
"""
    )
    with st.expander("Setup"):
        st.code(
            "python3 -m venv .venv\n"
            "source .venv/bin/activate\n"
            "python -m pip install --upgrade pip\n"
            'python -m pip install -e ".[dev]"\n'
            "md2pdf ui",
            language="bash",
        )
        st.caption("WeasyPrint needs Pango: brew install pango libffi on macOS, apt install libpango-1.0-0 on Debian.")
    with st.expander("Document id tokens"):
        st.table([{"token": "{" + token + "}", "meaning": meaning} for token, meaning in docids.TOKEN_REFERENCE])
    with st.expander("Header, footer and file name tokens"):
        st.markdown(
            "- `{title}`, `{doc_id}`, `{project}`, `{template}`, `{author}`, `{company}`, `{date}`, `{datetime}`\n"
            "- `{page}` and `{pages}` for page numbers, `{chapter}` for the running h1, `{section}` for the running h2\n"
            "- `[optional text]` disappears when it contains an empty token, so "
            "`[{doc_id} · ]Page {page}` prints only `Page 3` when no id is set"
        )
    with st.expander("Markdown support"):
        st.markdown(
            "- Tables, fenced code with syntax highlighting, footnotes, definition lists, attribute lists, "
            "abbreviations and admonitions come from python-markdown extensions\n"
            "- A table of contents is generated with clickable entries and PDF page numbers\n"
            "- Long tables repeat their header row on every page, rows and code blocks avoid awkward breaks"
        )
    with st.expander("Command line"):
        st.code(
            "md2pdf report.md\n"
            "md2pdf report.md -o out/ --template 'Classic report'\n"
            "md2pdf report.md --project ~/Documents/md2pdf-projects/Reports\n"
            "md2pdf project init Reports\n"
            "md2pdf project list\n"
            "md2pdf templates --project Reports",
            language="bash",
        )


def sidebar() -> None:
    template = current_template()
    project = current_project()
    st.sidebar.title("md2pdf")
    st.sidebar.caption("Markdown to PDF with templates and project workspaces.")
    if "pending_mode" in st.session_state:
        st.session_state["mode_radio"] = st.session_state.pop("pending_mode")
    if "mode_radio" not in st.session_state:
        st.session_state["mode_radio"] = state("mode", MODE_ONE_TIME)
    st.session_state["mode"] = st.sidebar.radio(
        "Mode", [MODE_ONE_TIME, MODE_PROJECT], key="mode_radio", label_visibility="collapsed"
    )
    st.sidebar.caption(f"Project: {project.meta.name}" if project else "Project: none open")
    st.sidebar.divider()
    with st.sidebar:
        with st.container(border=True):
            st.markdown("**Project**")
            if project is None:
                if st.button("Open a project…", key="sidebar_browse_project"):
                    st.session_state["pending_mode"] = MODE_PROJECT
                    open_project_from_dialog()
                recent = recent_projects()
                if recent:
                    if st.button(f"Resume '{recent[0].name}'", key="sidebar_resume_project"):
                        if open_project(recent[0]):
                            st.rerun()
            else:
                st.caption(str(project.root))
                if st.button("New document", key="sidebar_new_document"):
                    new_document(project)
                if st.button("Switch project…", key="sidebar_switch_project"):
                    open_project_from_dialog()
        with st.container(border=True):
            st.markdown("**Template**")
            choices: list[str] = []
            if project is not None:
                choices.extend(project.template_names())
            choices.extend(f"preset: {name}" for name in PRESET_NAMES)
            selected = st.selectbox(
                "Load", ["(current)"] + choices, key=f"sidebar_template_choice::{len(choices)}"
            )
            if selected != "(current)" and st.button("Load template", key="sidebar_load_template"):
                if selected.startswith("preset: "):
                    load_preset(selected.replace("preset: ", "", 1))
                elif project is not None:
                    set_template(project.load_template(selected))
                    st.session_state["status"] = f"Loaded template '{selected}'."
                st.rerun()
            st.caption(f"Editing: {template.name} v{template.version}")
            if st.button("Save template", disabled=project is None, key="sidebar_save_template"):
                assert project is not None
                project.save_template(template)
                st.session_state["status"] = f"Saved template '{template.name}'."
                st.rerun()
    picker_error = st.session_state.pop("picker_error", "")
    if picker_error:
        st.sidebar.warning(picker_error)
    status = st.session_state.pop("status", "")
    if status:
        st.sidebar.success(status)
    st.sidebar.caption(
        "Generated files stay inside the project. A one-time convert writes to disk only when you ask."
    )


def main() -> None:
    st.set_page_config(page_title="md2pdf", page_icon="📄", layout="wide")
    if native_env.missing_library_paths():
        hint = native_env.library_path_hint()
        st.warning(
            "This process cannot find WeasyPrint's native libraries, so conversion will fail. "
            f"Relaunch with `{hint}`, or start the app with `md2pdf ui`, which sets it for you."
        )
    state("mode", MODE_ONE_TIME)
    state("template", default_template())
    state("template_rev", 0)
    state("session_counters", {})
    state("results", [])
    state("source_text", "")
    state("source_name", NEW_DOCUMENT_NAME)
    sidebar()
    mode = state("mode", MODE_ONE_TIME)
    project = current_project()
    template = current_template()
    if mode == MODE_PROJECT and project is None:
        project_tab(project)
        return
    tabs = st.tabs(["Write", "Design", "Project", "Library", "Help"])
    with tabs[0]:
        convert_tab(template, project)
    with tabs[1]:
        template_tab(template, project)
    with tabs[2]:
        project_tab(project)
    with tabs[3]:
        library_tab(project)
    with tabs[4]:
        help_tab()
    if project is not None:
        remember_project_session(project, template)


if __name__ == "__main__":
    main()
