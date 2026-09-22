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


def test_session_round_trip(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    assert project.load_session() == {}
    project.save_session({"template": {"name": "Default"}, "source_text": "# Hi\n"})
    assert project.load_session()["source_text"] == "# Hi\n"
    assert (project.root / projects.SESSION_FILE).is_file()
    (project.root / projects.SESSION_FILE).write_text("not json", encoding="utf-8")
    assert project.load_session() == {}


def test_update_conversion_keeps_one_document(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    first = project.save_conversion(
        "# One\n",
        pdf_bytes=b"first draft",
        output_name="DOC-1-one.pdf",
        doc_id="DOC-1",
        title="One",
        page_count=2,
    )
    assert [path.name for path in project.outputs()] == ["DOC-1-one.pdf"]
    updated = project.update_conversion(
        first["id"],
        "# One\n\nmore text\n",
        pdf_bytes=b"second draft",
        output_name="DOC-1-one.pdf",
        doc_id="DOC-1",
        title="One",
        page_count=3,
    )
    assert updated is not None
    assert len(project.manifest) == 1
    assert [path.name for path in project.outputs()] == ["DOC-1-one.pdf"]
    assert [path.name for path in project.documents()] == ["DOC-1-one.md"]
    stored = project.entry(first["id"])
    assert stored is not None
    assert stored["pages"] == 3
    assert stored["bytes"] == len(b"second draft")
    assert stored["updated"]
    assert project.entry_pdf_bytes(stored) == b"second draft"
    assert project.read_entry_markdown(stored) == "# One\n\nmore text\n"
    assert projects.Project.open(project.root).entry(first["id"])["pages"] == 3


def test_update_conversion_renames_without_leaving_files_behind(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    first = project.save_conversion(
        "# One\n", pdf_bytes=b"a", output_name="DOC-1-one.pdf", doc_id="DOC-1"
    )
    project.save_conversion("# Two\n", pdf_bytes=b"b", output_name="DOC-2-two.pdf", doc_id="DOC-2")
    project.update_conversion(
        first["id"],
        "# One renamed\n",
        pdf_bytes=b"c",
        output_name="DOC-1-renamed.pdf",
        doc_id="DOC-1",
    )
    assert sorted(path.name for path in project.outputs()) == ["DOC-1-renamed.pdf", "DOC-2-two.pdf"]
    assert sorted(path.name for path in project.documents()) == ["DOC-1-renamed.md", "DOC-2-two.md"]
    assert project.entry(first["id"])["pdf"].endswith("DOC-1-renamed.pdf")
    assert project.update_conversion("missing", "# x\n", pdf_bytes=b"x", output_name="x.pdf") is None


def test_entries_can_be_found_by_id_and_by_markdown_path(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    entry = project.save_conversion("# One\n", pdf_bytes=b"a", output_name="one.pdf")
    assert project.entry(entry["id"]) is entry
    assert project.entry("missing") is None
    assert project.entry_for_markdown(entry["markdown"]) is entry
    assert project.entry_for_markdown("documents/nope.md") is None


def test_template_digest_follows_the_file(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    original = project.template_digest("Default")
    assert len(original) == 40
    assert project.template_digest("Missing") == ""
    template = project.load_template("Default")
    template.theme.accent = "#010203"
    project.save_template(template)
    assert project.template_digest("Default") != original


def test_browsing_helpers_see_projects_and_skip_hidden_folders(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    (project.root / ".hidden").mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert [item.name for item in projects.list_subdirectories(tmp_path)] == ["Reports"]
    assert [item.name for item in projects.list_subdirectories(project.root)] == [
        projects.ASSETS_DIR,
        projects.DOCUMENTS_DIR,
        projects.OUTPUT_DIR,
        projects.TEMPLATES_DIR,
    ]
    assert projects.list_subdirectories(tmp_path / "missing") == []
    assert projects.is_project(project.root)
    assert not projects.is_project(tmp_path)


def test_nearest_project_root_walks_up_from_anywhere(tmp_path):
    project = projects.Project.create(tmp_path / "Reports", name="Reports")
    nested = project.root / projects.OUTPUT_DIR / "2026"
    nested.mkdir(parents=True, exist_ok=True)
    assert projects.nearest_project_root(nested) == project.root
    assert projects.nearest_project_root(nested / "report.pdf") == project.root
    assert projects.nearest_project_root(project.root) == project.root
    assert projects.nearest_project_root(tmp_path) is None


def test_recent_projects_are_remembered_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("MD2PDF_HOME", str(tmp_path / "home"))
    first = projects.Project.create(tmp_path / "One", name="One")
    second = projects.Project.create(tmp_path / "Two", name="Two")
    assert projects.load_recents() == []
    projects.remember_recent(first.root)
    projects.remember_recent(second.root)
    assert projects.load_recents() == [second.root, first.root]
    projects.remember_recent(first.root)
    assert projects.load_recents() == [first.root, second.root]
    assert (tmp_path / "home" / projects.RECENTS_FILE).is_file()
    for index in range(projects.RECENTS_LIMIT + 3):
        projects.remember_recent(tmp_path / f"P{index}")
    assert len(projects.load_recents()) == projects.RECENTS_LIMIT


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
