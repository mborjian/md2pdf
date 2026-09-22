from __future__ import annotations

from md2pdf import styles
from md2pdf.templates import PRESET_NAMES, default_template, preset


def test_default_css_balances_braces_and_sets_the_page():
    css = styles.build_css(default_template(), doc_id="DOC-001")
    assert css.count("{") == css.count("}")
    assert "size: 210mm 297mm;" in css
    assert "margin: 20mm 18mm 20mm 18mm;" in css
    assert "@top-" in css
    assert "@bottom-" in css


def test_header_and_footer_use_page_counters_and_the_doc_id():
    css = styles.build_css(default_template(), doc_id="DOC-001")
    assert "counter(page)" in css
    assert "counter(pages)" in css
    assert '"DOC-001' in css


def test_optional_footer_group_drops_the_separator_without_a_doc_id():
    with_id = styles.build_css(default_template(), doc_id="DOC-001")
    without_id = styles.build_css(default_template(), doc_id="")
    assert "\u00b7" in with_id
    assert "\u00b7" not in without_id
    assert "Page" in without_id


def test_page_number_style_switches_the_counter():
    template = default_template()
    template.document.page_number_style = "upper-roman"
    css = styles.build_css(template, doc_id="X")
    assert "counter(page, upper-roman)" in css


def test_running_headings_use_string_set():
    template = default_template()
    template.document.header.text = "{chapter}"
    css = styles.build_css(template, doc_id="")
    assert "string-set: chapter content();" in css
    assert "string(chapter)" in css


def test_content_expression_handles_counters_and_optional_groups():
    context = styles.docids.DocIdContext(title="Report", project="Acme")
    expression = styles.content_expression("Page {page} of {pages}", context=context)
    assert expression == '"Page " counter(page) " of " counter(pages)'
    expression = styles.content_expression("[{project} \u00b7 ]{title}", context=context)
    assert expression == '"Acme \u00b7 Report"'
    assert styles.content_expression("   ", context=context) == "none"


def test_logo_assets_are_linked_and_missing_ones_warn(tmp_path):
    image = tmp_path / "logo.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    template = default_template()
    template.document.header.logo = "logo.png"
    warnings: list[str] = []
    css = styles.build_css(template, base_dir=tmp_path, warnings=warnings)
    assert image.as_uri() in css
    assert "background-size: contain;" in css
    assert warnings == []
    template.document.header.logo = "missing.png"
    warnings = []
    css = styles.build_css(template, base_dir=tmp_path, warnings=warnings)
    assert "background-image" not in css
    assert warnings and "missing.png" in warnings[0]


def test_cover_and_watermark_css_only_when_enabled():
    template = default_template()
    template.document.cover.enabled = False
    template.document.watermark.enabled = False
    plain = styles.build_css(template, doc_id="")
    assert "@page cover" not in plain
    assert ".watermark" not in plain
    template.document.cover.enabled = True
    template.document.watermark.enabled = True
    rich = styles.build_css(template, doc_id="")
    assert "@page cover" in rich
    assert ".cover-title" in rich
    assert ".watermark" in rich
    assert "break-after: page;" in rich


def test_cover_suppresses_margin_boxes():
    css = styles.build_css(default_template(), doc_id="")
    assert "@page cover {" in css
    assert "content: none;" in css


def test_table_and_code_options_are_reflected():
    template = default_template()
    template.theme.table_zebra = False
    template.theme.code_theme = "monokai"
    css = styles.build_css(template, doc_id="")
    assert "nth-child(even)" not in css
    assert ".codehilite" in css
    template.document.markdown.numbered_sections = True
    assert "counter(section)" in styles.build_css(template, doc_id="")


def test_custom_css_is_appended_last():
    template = default_template()
    template.document.custom_css = ".document h1 { color: red }"
    css = styles.build_css(template, doc_id="")
    assert css.rstrip().endswith(".document h1 { color: red }")


def test_every_preset_produces_balanced_css():
    for name in PRESET_NAMES:
        css = styles.build_css(preset(name), doc_id="DOC-9")
        assert css.count("{") == css.count("}")
        assert "size:" in css


def test_invalid_code_theme_falls_back():
    template = default_template()
    template.theme.code_theme = "not-a-real-theme"
    css = styles.build_css(template, doc_id="")
    assert ".codehilite" in css
