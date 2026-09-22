from __future__ import annotations

import pytest

from md2pdf import __version__
from md2pdf.cli import StateCounter, apply_overrides, build_parser, main
from md2pdf.templates import default_template


def test_parser_accepts_input_and_output():
    args = build_parser().parse_args(["convert", "doc.md", "-o", "doc.pdf"])
    assert args.input == "doc.md"
    assert args.output == "doc.pdf"
    assert args.command == "convert"


def test_package_exposes_a_version():
    assert __version__


def test_bare_file_argument_is_treated_as_convert(capsys):
    assert main(["missing.md"]) == 1
    assert "no such file" in capsys.readouterr().err


def test_no_arguments_prints_help(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_templates_command_lists_presets_and_tokens(capsys):
    assert main(["templates"]) == 0
    output = capsys.readouterr().out
    assert "Modern brief" in output
    assert "{seq}" in output
    assert "{doc_id}" in output


def test_project_init_and_list(tmp_path, capsys):
    assert main(["project", "init", "Reports", "--dir", str(tmp_path), "--preset", "Classic report"]) == 0
    root = tmp_path / "Reports"
    assert (root / "project.json").is_file()
    assert (root / "templates" / "Default.json").is_file()
    assert main(["project", "init", "Reports", "--dir", str(tmp_path)]) == 1
    assert main(["project", "list", str(tmp_path)]) == 0
    assert "Reports" in capsys.readouterr().out


def test_apply_overrides_sets_page_size_ids_and_toggles():
    args = build_parser().parse_args(
        ["convert", "a.md", "--page-size", "letter", "--landscape", "--doc-id", "INV-{seq:2}", "--toc"]
    )
    template = apply_overrides(default_template(), args)
    assert template.page.size == "Letter"
    assert template.page.orientation == "landscape"
    assert template.document.docid.pattern == "INV-{seq:2}"
    assert template.document.docid.enabled is True
    assert template.document.markdown.toc is True
    args = build_parser().parse_args(["convert", "a.md", "--page-size", "100x150", "--no-header", "--no-footer"])
    template = apply_overrides(default_template(), args)
    assert template.page.size == "Custom"
    assert template.page.dimensions_mm() == (100.0, 150.0)
    assert template.document.header.enabled is False
    assert template.document.footer.enabled is False
    args = build_parser().parse_args(["convert", "a.md", "--no-doc-id"])
    assert apply_overrides(default_template(), args).document.docid.enabled is False


def test_unknown_page_size_is_rejected():
    args = build_parser().parse_args(["convert", "a.md", "--page-size", "A9"])
    with pytest.raises(ValueError):
        apply_overrides(default_template(), args)


def test_unknown_template_is_rejected():
    assert main(["convert", "missing.md", "--template", "nope"]) == 1


def test_state_counter_persists_the_sequence(tmp_path):
    counter = StateCounter(tmp_path / ".state.json")
    assert counter.next_sequence() == 1
    assert counter.bump() == 2
    assert StateCounter(tmp_path / ".state.json").next_sequence() == 2


def test_convert_end_to_end(tmp_path):
    pytest.importorskip("markdown")
    pytest.importorskip("weasyprint")
    source = tmp_path / "note.md"
    source.write_text("# Title\n\nBody text.", encoding="utf-8")
    output = tmp_path / "out" / "note.pdf"
    assert main([str(source), "-o", str(output)]) == 0
    assert output.read_bytes().startswith(b"%PDF")


def test_convert_inside_a_project_records_history(tmp_path, capsys):
    pytest.importorskip("markdown")
    pytest.importorskip("weasyprint")
    assert main(["project", "init", "Reports", "--dir", str(tmp_path)]) == 0
    source = tmp_path / "note.md"
    source.write_text("# Title\n\nBody text.", encoding="utf-8")
    project_root = tmp_path / "Reports"
    assert main([str(source), "--project", str(project_root), "--quiet"]) == 0
    capsys.readouterr()
    from md2pdf import projects

    project = projects.Project.open(project_root)
    assert len(project.manifest) == 1
    assert project.history()[0]["doc_id"]
    assert project.outputs()
