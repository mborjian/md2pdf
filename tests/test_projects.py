from __future__ import annotations

import json

import pytest

from md2pdf import docids, projects
from md2pdf.templates import preset


def test_create_project_lays_out_the_expected_directories(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports", description="demo")
    for directory in projects.DIRECTORIES:
        assert (project.root / directory).is_dir()
    assert (project.root / projects.PROJECT_FILE).is_file()
    assert (project.root / projects.STATE_FILE).is_file()
    assert json.loads((project.root / projects.MANIFEST_FILE).read_text(encoding="utf-8")) == []
    assert project.template_names() == ["Default"]
    assert project.load_first_template().name == "Default"
    assert project.meta.description == "demo"
    assert project.meta.created


def test_open_round_trip_and_summary(tmp_path):
    projects.Project.create(tmp_path / "Reports", name="Reports")
    reopened = projects.Project.open(tmp_path / "Reports")
    assert reopened.meta.name == "Reports"
    summary = reopened.summary()
    assert summary["templates"] == 1
    assert summary["next_sequence"] == 1
    assert summary["pdfs"] == 0


def test_open_without_project_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        projects.Project.open(tmp_path / "nope")


def test_template_save_load_rename_and_delete(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    template = preset("Classic report")
    template.name = "Reports"
    project.save_template(template)
    assert project.template_names() == ["Default", "Reports"]
    loaded = project.load_template("Reports")
    assert loaded.theme.accent == template.theme.accent
    assert loaded.document.markdown.numbered_sections is True
    project.rename_template("Reports", "Client report")
    assert "Client report" in project.template_names()
    assert project.delete_template("Client report") is True
    assert project.delete_template("Client report") is False


def test_doc_ids_are_sequential_and_never_reused(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    template = project.load_first_template()
    template.document.docid.pattern = "DOC-{seq:3}"
    assert project.allocate_doc_id(template, docids.DocIdContext(title="One")) == "DOC-001"
    assert project.next_sequence() == 2
    project.manifest.append({"id": "x", "doc_id": "DOC-002"})
    assert project.allocate_doc_id(template, docids.DocIdContext(title="Two")) == "DOC-003"
    assert projects.Project.open(project.root).next_sequence() == 4


def test_random_doc_ids_do_not_consume_the_counter(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    template = project.load_first_template()
    template.document.docid.pattern = "DOC-{rand:8}"
    first = project.allocate_doc_id(template, docids.DocIdContext())
    assert len(first) == 12
    assert project.next_sequence() == 1


def test_disabled_doc_ids_return_empty(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    template = project.load_first_template()
    template.document.docid.enabled = False
    assert project.allocate_doc_id(template, docids.DocIdContext()) == ""


def test_save_conversion_writes_pdf_markdown_and_history(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    entry = project.save_conversion(
        "# Hello",
        pdf_bytes=b"%PDF-1.4",
        output_name="DOC-001-note.pdf",
        doc_id="DOC-001",
        title="Note",
        template_name="Default",
        source_name="note.md",
        page_count=2,
    )
    assert (project.root / entry["pdf"]).read_bytes() == b"%PDF-1.4"
    assert (project.root / entry["markdown"]).read_text(encoding="utf-8") == "# Hello"
    assert entry["pages"] == 2
    assert project.history()[0]["doc_id"] == "DOC-001"
    assert project.read_entry_markdown(entry) == "# Hello"
    assert project.entry_pdf_bytes(entry) == b"%PDF-1.4"
    assert project.summary()["pdfs"] == 1
    assert project.summary()["documents"] == 1


def test_save_conversion_can_skip_the_markdown_copy(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    entry = project.save_conversion(
        "body", pdf_bytes=b"%PDF", output_name="one.pdf", save_markdown=False
    )
    assert entry["markdown"] == ""
    assert project.documents() == []


def test_repeating_an_output_name_adds_a_suffix(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    for _ in range(2):
        project.save_conversion("body", pdf_bytes=b"%PDF", output_name="same.pdf")
    assert sorted(path.name for path in project.outputs()) == ["same-2.pdf", "same.pdf"]


def test_assets_are_stored_and_deduplicated(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    assert project.add_asset("logo.png", b"one").name == "logo.png"
    assert project.add_asset("logo.png", b"two").name == "logo-2.png"
    assert project.add_asset("../escape.png", b"three").name == "escape.png"
    assert project.delete_asset("logo.png") is True
    assert [path.name for path in project.assets()] == ["escape.png", "logo-2.png"]


def test_rescan_picks_up_untracked_pdfs(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    (project.root / projects.OUTPUT_DIR / "dropped.pdf").write_bytes(b"%PDF")
    assert project.rescan() == 1
    assert project.rescan() == 0
    assert project.history()[0]["imported"] is True


def test_forget_entry_keeps_or_deletes_files(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    entry = project.save_conversion("body", pdf_bytes=b"%PDF", output_name="one.pdf")
    assert project.forget_entry(entry["id"]) is True
    assert project.history() == []
    assert (project.root / entry["pdf"]).is_file()
    assert project.forget_entry(entry["id"]) is False
    second = project.save_conversion("body", pdf_bytes=b"%PDF", output_name="two.pdf")
    assert project.forget_entry(second["id"], delete_files=True) is True
    assert not (project.root / second["pdf"]).exists()


def test_find_projects_walks_nested_folders(tmp_path):
    projects.Project.create(tmp_path / "a" / "One", name="One")
    projects.Project.create(tmp_path / "b" / "c" / "Two", name="Two")
    projects.Project.create(tmp_path / ".hidden" / "Skip", name="Skip")
    found = projects.find_projects(tmp_path)
    assert [path.name for path in found] == ["One", "Two"]


def test_relative_and_absolute_helpers(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    target = project.directory(projects.OUTPUT_DIR) / "doc.pdf"
    target.write_bytes(b"%PDF")
    assert project.relative(target) == "output/doc.pdf"
    assert project.absolute("output/doc.pdf") == target
