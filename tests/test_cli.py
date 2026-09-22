from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from md2pdf import __version__, native_env
from md2pdf.cli import StateCounter, apply_overrides, build_parser, main
from md2pdf.templates import default_template

UNAVAILABLE_MARKERS = ("WeasyPrint cannot load", "package is not installed")


def weasyprint_skip_reason() -> str:
    hint = native_env.library_path_hint()
    return "weasyprint cannot load its system libraries (Pango)" + (f": {hint}" if hint else "")


def run_cli(*arguments: str) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "md2pdf", *arguments],
        capture_output=True,
        text=True,
        env=environment,
    )
    for marker in UNAVAILABLE_MARKERS:
        if marker in completed.stderr:
            pytest.skip(f"this environment cannot render PDFs yet ({marker})")
    return completed


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


def test_apply_overrides_sets_document_metadata():
    args = build_parser().parse_args(
        ["convert", "a.md", "--title", "Report", "--subtitle", "Q3", "--author", "Ada", "--company", "Acme"]
    )
    template = apply_overrides(default_template(), args)
    assert template.document.subtitle == "Q3"
    assert template.document.author == "Ada"
    assert template.document.company == "Acme"


def test_unknown_page_size_is_rejected():
    args = build_parser().parse_args(["convert", "a.md", "--page-size", "A9"])
    with pytest.raises(ValueError):
        apply_overrides(default_template(), args)


def test_unknown_template_is_rejected():
    assert main(["convert", "missing.md", "--template", "nope"]) == 1


def test_ui_command_launches_the_packaged_app_file(monkeypatch):
    streamlit_cli = pytest.importorskip("streamlit.web.cli")
    captured: dict[str, list[str]] = {}
    def fake_main() -> int:
        captured["argv"] = list(sys.argv)
        return 0

    monkeypatch.setattr(streamlit_cli, "main", fake_main)
    before = os.environ.get(native_env.LIBRARY_PATH_VARIABLE)
    try:
        assert main(["ui", "--port", "8901"]) == 0
    finally:
        if before is None:
            os.environ.pop(native_env.LIBRARY_PATH_VARIABLE, None)
        else:
            os.environ[native_env.LIBRARY_PATH_VARIABLE] = before
    assert captured["argv"][:2] == ["streamlit", "run"]
    app_file = Path(captured["argv"][2])
    assert app_file.is_file()
    assert app_file.name == "streamlit_app.py"
    assert captured["argv"][3:] == ["--server.port", "8901", "--server.address", "localhost"]


def test_state_counter_persists_the_sequence(tmp_path):
    counter = StateCounter(tmp_path / ".state.json")
    assert counter.next_sequence() == 1
    assert counter.bump() == 2
    assert StateCounter(tmp_path / ".state.json").next_sequence() == 2


def test_convert_end_to_end(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Title\n\nBody text.", encoding="utf-8")
    output = tmp_path / "out" / "note.pdf"
    completed = run_cli(str(source), "-o", str(output))
    assert completed.returncode == 0, completed.stderr
    assert output.read_bytes().startswith(b"%PDF")


def test_derived_output_names_come_from_the_heading_and_do_not_overwrite(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Quarterly report\n\nBody.", encoding="utf-8")
    assert run_cli(str(source), "--no-doc-id", "--quiet").returncode == 0
    assert run_cli(str(source), "--no-doc-id", "--quiet").returncode == 0
    assert sorted(path.name for path in tmp_path.glob("*.pdf")) == [
        "quarterly-report-2.pdf",
        "quarterly-report.pdf",
    ]


def test_explicit_output_path_overwrites(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Title\n\nBody.", encoding="utf-8")
    target = tmp_path / "fixed.pdf"
    assert run_cli(str(source), "--no-doc-id", "-o", str(target)).returncode == 0
    assert run_cli(str(source), "--no-doc-id", "-o", str(target)).returncode == 0
    assert target.is_file()
    assert sorted(path.name for path in tmp_path.glob("*.pdf")) == ["fixed.pdf"]


def test_convert_inside_a_project_records_history(tmp_path):
    from md2pdf import projects

    assert main(["project", "init", "Reports", "--dir", str(tmp_path)]) == 0
    source = tmp_path / "note.md"
    source.write_text("# Title\n\nBody text.", encoding="utf-8")
    project_root = tmp_path / "Reports"
    completed = run_cli(str(source), "--project", str(project_root), "--quiet", "--title", "Note")
    assert completed.returncode == 0, completed.stderr
    project = projects.Project.open(project_root)
    assert len(project.manifest) == 1
    assert project.history()[0]["doc_id"]
    assert len(project.outputs()) == 1
    assert len(project.documents()) == 1
    assert not list(tmp_path.glob("*.pdf"))
