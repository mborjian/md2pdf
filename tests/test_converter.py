from __future__ import annotations

import pytest

from md2pdf import converter
from md2pdf.templates import MarkdownOptions, default_template


def test_output_filename_follows_the_pattern():
    template = default_template()
    context = converter.make_context(template, title="Release Notes", filename="notes.md")
    template.document.output.filename_pattern = "{doc_id}-{slug}"
    assert converter.output_filename(template, context, "DOC-001") == "DOC-001-release-notes.pdf"
    template.document.output.filename_pattern = "[{doc_id}-]{slug}"
    assert converter.output_filename(template, context, "") == "release-notes.pdf"
    assert converter.output_filename(template, converter.make_context(template), "") == "untitled.pdf"


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


def test_full_conversion_produces_a_pdf(tmp_path):
    pytest.importorskip("markdown")
    pytest.importorskip("weasyprint")
    result = converter.convert("# Title\n\nHello.", default_template(), doc_id="DOC-1")
    assert result.pdf_bytes.startswith(b"%PDF")
    assert result.page_count >= 1
    assert result.output_name.endswith(".pdf")
    assert result.warnings == []
