from __future__ import annotations

import pytest

from md2pdf import converter
from md2pdf.templates import MarkdownOptions, default_template


def weasyprint_is_usable() -> bool:
    try:
        import weasyprint
    except Exception:
        return False
    return True


def weasyprint_skip_reason() -> str:
    from md2pdf import native_env

    hint = native_env.library_path_hint()
    return "weasyprint cannot load its system libraries (Pango)" + (f": {hint}" if hint else "")


def test_output_filename_follows_the_pattern():
    template = default_template()
    context = converter.make_context(template, title="Release Notes", filename="notes.md")
    template.document.output.filename_pattern = "{doc_id}-{slug}"
    assert converter.output_filename(template, context, "DOC-001") == "DOC-001-release-notes.pdf"
    template.document.output.filename_pattern = "[{doc_id}-]{slug}"
    assert converter.output_filename(template, context, "") == "release-notes.pdf"
    assert converter.output_filename(template, converter.make_context(template), "") == "untitled.pdf"


def test_first_heading_reads_the_document_title():
    assert converter.first_heading("# Quarterly engineering report\n\nBody") == (
        "Quarterly engineering report"
    )
    assert converter.first_heading("\n\n## Section only\n") == ""
    assert converter.first_heading("Text first\n\n# Later title ##\n") == "Later title"
    assert converter.first_heading("# Title#\n") == "Title"
    assert converter.first_heading("```\n# not a heading\n```\n# Real\n") == "Real"
    assert converter.first_heading("~~~python\n# no\n~~~\n") == ""
    assert converter.first_heading("#\n") == ""
    assert converter.first_heading("") == ""


def test_make_context_falls_back_to_template_fields():
    template = default_template()
    template.document.title = "Template title"
    context = converter.make_context(template, filename="notes.md")
    assert context.title == "Template title"
    assert context.template == template.name
    assert context.filename == "notes.md"
    assert context.version == template.version


def test_build_html_includes_css_cover_and_metadata():
    template = default_template()
    template.document.title = "Quarterly report"
    template.document.author = "Ada"
    template.document.docid.placements = ["footer", "cover", "metadata"]
    context = converter.make_context(template, filename="report.md")
    html, css = converter.build_html("<p>body</p>", template, doc_id="DOC-7", context=context)
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html
    assert 'meta name="author" content="Ada"' in html
    assert 'content="DOC-7"' in html
    assert '<section class="cover">' in html
    assert '<main class="document">' in html
    assert 'lang="en"' in html
    assert css.count("{") == css.count("}")


def test_build_html_respects_disabled_features():
    template = default_template()
    template.document.cover.enabled = False
    template.document.watermark.enabled = False
    template.document.markdown.toc = False
    html, css = converter.build_html("<p>x</p>", template)
    assert 'class="cover"' not in html
    assert "watermark" not in html
    assert 'class="toc"' not in html
    assert ".toc a::after" not in css
    assert ".cover-title" not in css
    assert ".watermark" not in css


def test_cover_html_expands_document_field_tokens():
    template = default_template()
    template.document.cover.subtitle = "{subtitle}"
    template.document.cover.author = "{author}"
    template.document.cover.company = "{company}"
    template.document.subtitle = "Quarterly numbers"
    template.document.author = "Ada Lovelace"
    template.document.company = "Acme"
    context = converter.make_context(template, title="Report", filename="r.md")
    fields = converter.document_fields(template, context, "DOC-9")
    html = converter.cover_html(template, context, "DOC-9", None, None, fields)
    assert "Quarterly numbers" in html
    assert "Ada Lovelace" in html
    assert "Acme" in html
    assert "{subtitle}" not in html
    assert "{author}" not in html
    assert "{company}" not in html


def test_cover_html_expands_document_tokens():
    template = default_template()
    template.document.cover.subtitle = "{project} · {doc_id}"
    context = converter.make_context(template, title="Report", project="Acme", filename="r.md")
    html = converter.cover_html(template, context, "DOC-9", None)
    assert "Acme · DOC-9" in html
    assert "Report" in html


def test_inline_assets_embeds_local_images(tmp_path):
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    html = '<img src="logo.png" /><img src="https://example.com/x.png" /><a href="#top">top</a>'
    result = converter.inline_assets(html, tmp_path)
    assert "data:image/png;base64," in result
    assert "https://example.com/x.png" in result
    assert 'href="#top"' in result


def test_render_markdown_tables_and_toc():
    pytest.importorskip("markdown")
    options = MarkdownOptions(toc=True, toc_depth=2, codehilite=False)
    body, toc = converter.render_markdown(
        "# One\n\n## Two\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n", options
    )
    assert "<table>" in body
    assert 'id="two"' in body
    assert "One" in toc
    assert "Two" in toc


def test_render_markdown_syntax_highlighting():
    pytest.importorskip("markdown")
    pytest.importorskip("pygments")
    options = MarkdownOptions(toc=False, codehilite=True)
    body, _ = converter.render_markdown("```python\nprint(1)\n```\n", options)
    assert "codehilite" in body


def page_texts(document) -> list[list[str]]:
    pages = []
    for page in document.pages:
        collected = []
        for box in page._page_box.descendants():
            value = getattr(box, "text", None)
            if isinstance(value, str) and value.strip():
                collected.append(value.strip())
        pages.append(collected)
    return pages


def test_cover_stays_on_one_page_and_keeps_the_footer_off():
    pytest.importorskip("markdown")
    if not weasyprint_is_usable():
        pytest.skip(weasyprint_skip_reason())
    from weasyprint import HTML

    from md2pdf.templates import preset

    template = preset("Manual with cover")
    template.document.title = "Quarterly report"
    template.document.subtitle = "Q3 numbers"
    context = converter.make_context(template, filename="report.md")
    body, toc = converter.render_markdown("# Head\n\nSome text.\n", template.document.markdown)
    html, _ = converter.build_html(body, template, doc_id="DOC-1", context=context, toc_html=toc)
    document = HTML(string=html).render()
    pages = page_texts(document)
    assert any("Quarterly report" in item for item in pages[0])
    assert any("Q3 numbers" in item for item in pages[0])
    assert any("DOC-1" in item for item in pages[0])
    assert not any("Page" in item for item in pages[0])
    assert any("Head" in item for item in pages[1] + pages[2])


def test_full_conversion_produces_a_pdf(tmp_path):
    pytest.importorskip("markdown")
    if not weasyprint_is_usable():
        pytest.skip(weasyprint_skip_reason())
    result = converter.convert("# Title\n\nHello.", default_template(), doc_id="DOC-1", base_dir=tmp_path)
    assert result.pdf_bytes.startswith(b"%PDF")
    assert result.page_count >= 1
    assert result.output_name.endswith(".pdf")
    assert result.warnings == []
