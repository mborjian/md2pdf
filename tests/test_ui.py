from __future__ import annotations

from pathlib import Path

import pytest

from md2pdf import native_env, picker, projects
from md2pdf.cli import main

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_APP = ROOT / "app.py"
MODULE_APP = ROOT / "src" / "md2pdf" / "streamlit_app.py"


@pytest.fixture(autouse=True)
def isolated_app_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MD2PDF_HOME", str(tmp_path / "md2pdf-home"))


def app_test_class():
    return pytest.importorskip("streamlit.testing.v1").AppTest


def weasyprint_is_usable() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def skip_without_renderer() -> None:
    if weasyprint_is_usable():
        return
    hint = native_env.library_path_hint()
    pytest.skip("weasyprint cannot load its system libraries (Pango)" + (f": {hint}" if hint else ""))


def pdf_component_available() -> bool:
    try:
        import streamlit_pdf  # noqa: F401
    except Exception:
        return False
    return True


def open_app(entry: Path = MODULE_APP):
    at = app_test_class().from_file(str(entry), default_timeout=180)
    at.run()
    return at


@pytest.mark.parametrize("entry", [MODULE_APP, SCRIPT_APP], ids=["packaged", "checkout"])
def test_app_starts_without_errors(entry):
    at = open_app(entry)
    assert not at.exception
    assert at.radio(key="mode_radio").value == "One-time convert"
    assert not at.session_state["results"]


def test_app_converts_the_example_and_shows_the_preview_beside_the_editor():
    skip_without_renderer()
    at = open_app()
    at.radio(key="source_mode").set_value("Example document").run()
    assert not at.exception
    at.button(key="convert_button").click().run()
    assert not at.exception
    results = at.session_state["results"]
    assert len(results) == 1
    item = results[0]
    assert item["pdf"].startswith(b"%PDF")
    assert item["pages"] >= 1
    assert item["name"].endswith(".pdf")
    assert item["html"].startswith("<!DOCTYPE html>")
    assert '<main class="document">' in item["html"]
    assert at.session_state["preview_pdf"]["pages"] == item["pages"]
    assert not [element for element in at.main if element.type == "iframe"]
    assert not [element for element in at.radio if element.label == "Layout"]
    if pdf_component_available():
        messages = [str(element.value) for element in at.warning]
        assert not [text for text in messages if "inline PDF viewer needs" in text]
    at.button(key="edit_example_button").click().run()
    assert not at.exception
    assert at.session_state["source_mode"] == "Paste Markdown"
    assert markdown_editor(at).value.startswith("# ")
    assert at.session_state["preview_pdf"]["pages"] >= 1


def test_app_stays_quiet_when_the_library_path_is_already_set():
    if native_env.missing_library_paths():
        pytest.skip("this process does not have the Homebrew library path set")
    at = open_app()
    messages = [str(element.value) for element in at.warning]
    assert not [text for text in messages if "WeasyPrint's native libraries" in text]


def make_project(tmp_path, name="Reports", preset_name="Classic report") -> Path:
    assert main(["project", "init", name, "--dir", str(tmp_path), "--preset", preset_name]) == 0
    return tmp_path / name


def stub_dialog(monkeypatch, path, error=""):
    monkeypatch.setattr(
        picker,
        "choose_directory",
        lambda *args, **kwargs: (Path(path) if path else None, error),
    )


def preview_html(at) -> str:
    return str((at.session_state.get("preview_pdf") or {}).get("html") or "")


def markdown_editor(at):
    return next(item for item in at.text_area if item.label == "Markdown")


def app_blocks(block):
    try:
        children = list(block.children.values())
    except AttributeError:
        return []
    found = []
    for child in children:
        found.append(child)
        found.extend(app_blocks(child))
    return found


def the_editor_and_the_pdf_preview_share_a_row(at) -> list[str]:
    rows: list[list[str]] = []
    for node in app_blocks(at.main):
        if node.type != "flex_container":
            continue
        inner = app_blocks(node)
        has_editor = any(item.type == "text_area" and item.proto.label == "Markdown" for item in inner)
        has_preview = any(
            item.type == "markdown" and str(item.value) == "**PDF preview**" for item in inner
        )
        if has_editor and has_preview:
            rows.append([child.type for child in node.children.values()])
    return rows[-1] if rows else []


def open_project_in_app(at, root: Path):
    at.session_state["project"] = projects.Project.open(root)
    at.run()


def test_the_preview_follows_the_markdown_and_the_page_breaks(tmp_path):
    skip_without_renderer()
    root = make_project(tmp_path)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    open_project_in_app(at, root)
    body = "# Survey\n\nIntro.\n\n" + "\n".join(f"| row {index} | {index} |" for index in range(30)) + "\n"
    markdown_editor(at).set_value(body).run()
    pages_before = at.session_state["preview_pdf"]["pages"]
    assert pages_before >= 1
    assert "Survey" in preview_html(at)
    assert 'class="page-break"' not in preview_html(at)
    at.button(key="insert_break_button").click().run()
    assert not at.exception
    assert "\\newpage" in at.session_state["source_text"]
    assert 'class="page-break"' in preview_html(at)
    assert at.session_state["preview_pdf"]["pages"] == pages_before + 1


def test_converting_twice_updates_the_same_project_document(tmp_path):
    skip_without_renderer()
    root = make_project(tmp_path)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    open_project_in_app(at, root)
    markdown_editor(at).set_value("# Survey\n\nFirst pass.\n").run()
    at.button(key="convert_button").click().run()
    project = projects.Project.open(root)
    assert len(project.manifest) == 1
    first = project.manifest[0]
    assert at.session_state["editing_id"] == first["id"]
    assert any("Editing" in str(element.value) for element in at.info)
    markdown_editor(at).set_value("# Survey\n\nSecond pass, with more text.\n").run()
    at.button(key="convert_button").click().run()
    assert not at.exception
    project = projects.Project.open(root)
    assert len(project.manifest) == 1
    assert len(project.outputs()) == 1
    assert len(project.documents()) == 1
    stored = project.manifest[0]
    assert stored["doc_id"] == first["doc_id"]
    assert stored["pdf"] == first["pdf"]
    assert stored["updated"]
    assert stored["pages"] >= 1
    assert at.session_state["results"][0]["updated"] is True


def test_stopping_the_edit_saves_a_new_copy_instead(tmp_path):
    skip_without_renderer()
    root = make_project(tmp_path)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    open_project_in_app(at, root)
    markdown_editor(at).set_value("# Survey\n\nFirst pass.\n").run()
    at.button(key="convert_button").click().run()
    at.button(key="stop_editing_button").click().run()
    assert at.session_state["editing_id"] == ""
    assert not any("Editing" in str(element.value) for element in at.info)
    at.button(key="convert_button").click().run()
    project = projects.Project.open(root)
    assert len(project.manifest) == 2
    assert len(project.outputs()) == 2


def test_the_library_reopens_a_document_for_editing(tmp_path):
    skip_without_renderer()
    root = make_project(tmp_path)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    open_project_in_app(at, root)
    markdown_editor(at).set_value("# Survey\n\nFirst pass.\n").run()
    at.button(key="convert_button").click().run()
    at.button(key="stop_editing_button").click().run()
    entry = projects.Project.open(root).manifest[0]
    at.button(key=f"library_open_0_{entry['id']}").click().run()
    assert not at.exception
    assert at.session_state["editing_id"] == entry["id"]
    assert at.session_state["source_text"].startswith("# Survey")
    at.button(key="convert_button").click().run()
    project = projects.Project.open(root)
    assert len(project.manifest) == 1
    assert project.manifest[0]["updated"]


def test_project_documents_load_into_the_editor_with_a_reload(tmp_path):
    skip_without_renderer()
    root = make_project(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal body.\n", encoding="utf-8")
    assert main(["convert", str(source), "--project", str(root)]) == 0
    entry = projects.Project.open(root).manifest[0]
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    open_project_in_app(at, root)
    at.radio(key="source_mode").set_value("Project document").run()
    assert not at.exception
    assert at.session_state["editing_id"] == entry["id"]
    assert at.session_state["source_text"] == "# Brief\n\nOriginal body.\n"
    markdown_editor(at).set_value("# Brief\n\nEdited in the app.\n").run()
    assert "Edited in the app" in at.session_state["source_text"]
    at.button(key="reload_document_button").click().run()
    assert at.session_state["source_text"] == "# Brief\n\nOriginal body.\n"
    markdown_editor(at).set_value("# Brief\n\nEdited again.\n").run()
    at.button(key="convert_button").click().run()
    project = projects.Project.open(root)
    assert len(project.manifest) == 1
    assert len(project.outputs()) == 1
    assert project.read_entry_markdown(project.manifest[0]) == "# Brief\n\nEdited again.\n"


def open_via_dialog(at, root: Path):
    at.button(key="browse_project_button").click().run()
    assert not at.exception
    assert Path(at.session_state["project"].root) == Path(root).resolve()


def test_browse_opens_the_project_picked_in_the_system_dialog(tmp_path, monkeypatch):
    root = make_project(tmp_path)
    stub_dialog(monkeypatch, root)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    at.button(key="browse_project_button").click().run()
    assert not at.exception
    assert at.session_state["mode"] == "Project workspace"
    assert Path(at.session_state["project"].root) == root.resolve()
    assert at.session_state["last_browse_dir"] == str(root.parent)
    assert "Project: Reports" in [str(element.value) for element in at.caption]
    assert any("Opened project 'Reports'" in str(element.value) for element in at.success)


def test_browse_opens_the_project_that_contains_the_chosen_folder(tmp_path, monkeypatch):
    root = make_project(tmp_path)
    stub_dialog(monkeypatch, root / "output")
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    at.button(key="browse_project_button").click().run()
    assert not at.exception
    assert Path(at.session_state["project"].root) == root.resolve()


def test_browse_reports_a_missing_system_dialog(monkeypatch):
    stub_dialog(monkeypatch, None, "this Python has no tkinter")
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    at.button(key="browse_project_button").click().run()
    assert not at.exception
    assert any("has no tkinter" in str(element.value) for element in at.warning)


def test_browse_can_pick_the_new_project_parent(tmp_path, monkeypatch):
    target = tmp_path / "MyReports"
    target.mkdir()
    stub_dialog(monkeypatch, target)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    at.button(key="browse_parent_button").click().run()
    assert not at.exception
    assert at.session_state["new_project_parent"] == str(target)
    at.button(key="create_project_button").click().run()
    assert not at.exception
    created = target / "Reports"
    assert (created / projects.PROJECT_FILE).is_file()
    assert Path(at.session_state["project"].root) == created


def test_browse_can_pick_the_one_time_output_folder(tmp_path, monkeypatch):
    stub_dialog(monkeypatch, tmp_path / "pdfs")
    at = open_app()
    at.button(key="browse_output_button").click().run()
    assert not at.exception
    field = next(item for item in at.text_input if item.label == "Save a copy to this folder")
    assert field.value.endswith("pdfs")
    field.set_value(str(tmp_path / "elsewhere")).run()
    assert at.session_state["one_time_output"].endswith("elsewhere")


def test_sidebar_browse_and_resume(tmp_path, monkeypatch):
    root = make_project(tmp_path)
    stub_dialog(monkeypatch, root)
    at = open_app()
    at.button(key="sidebar_browse_project").click().run()
    assert not at.exception
    assert at.session_state["mode"] == "Project workspace"
    assert Path(at.session_state["project"].root) == root.resolve()
    at.button(key="close_project_button").click().run()
    assert at.session_state["project"] is None
    at.button(key="sidebar_resume_project").click().run()
    assert not at.exception
    assert Path(at.session_state["project"].root) == root.resolve()


def test_reopening_a_project_restores_the_last_session(tmp_path, monkeypatch):
    skip_without_renderer()
    root = make_project(tmp_path)
    stub_dialog(monkeypatch, root)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    at.session_state["project"] = projects.Project.open(root)
    at.run()
    next(item for item in at.color_picker if item.label == "Accent").set_value("#123456").run()
    assert at.session_state["template"].theme.accent == "#123456"
    next(item for item in at.text_area if item.label == "Markdown").set_value(
        "# Restored heading\n\nBody line.\n"
    ).run()
    assert at.session_state["source_text"].startswith("# Restored heading")
    assert (root / projects.SESSION_FILE).is_file()
    at.button(key="close_project_button").click().run()
    assert at.session_state["project"] is None
    open_via_dialog(at, root)
    assert at.session_state["template"].theme.accent == "#123456"
    assert at.session_state["source_text"].startswith("# Restored heading")
    assert at.session_state["source_name"].endswith(".md")


def test_the_markdown_editor_sits_beside_the_pdf_preview():
    skip_without_renderer()
    at = open_app()
    markdown_editor(at).set_value("# Layout\n\nBody.\n").run()
    assert not at.exception
    assert the_editor_and_the_pdf_preview_share_a_row(at) == ["column", "column"]
    assert at.session_state["preview_pdf"]["pages"] >= 1
    assert not [element for element in at.main if element.type == "iframe"]


def test_new_document_starts_a_second_document_without_touching_the_first(tmp_path):
    skip_without_renderer()
    root = make_project(tmp_path)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    open_project_in_app(at, root)
    markdown_editor(at).set_value("# Survey\n\nFirst document.\n").run()
    at.button(key="convert_button").click().run()
    assert len(projects.Project.open(root).manifest) == 1
    assert at.session_state["editing_id"]
    at.button(key="new_document_button").click().run()
    assert not at.exception
    assert at.session_state["editing_id"] == ""
    assert at.session_state["results"] == []
    assert at.session_state["source_name"] == "draft.md"
    assert at.session_state["source_text"].startswith("# Untitled document")
    assert markdown_editor(at).value.startswith("# Untitled document")
    markdown_editor(at).set_value("# Second survey\n\nA fresh document.\n").run()
    at.button(key="convert_button").click().run()
    project = projects.Project.open(root)
    assert len(project.manifest) == 2
    assert len(project.outputs()) == 2
    assert len(project.documents()) == 2


def test_new_document_resets_a_one_time_session():
    skip_without_renderer()
    at = open_app()
    at.radio(key="source_mode").set_value("Example document").run()
    at.button(key="convert_button").click().run()
    assert len(at.session_state["results"]) == 1
    at.button(key="new_document_button").click().run()
    assert not at.exception
    assert at.session_state["results"] == []
    assert at.session_state["source_mode"] == "Paste Markdown"
    assert at.session_state["source_name"] == "draft.md"
    assert at.session_state["source_text"].startswith("# Untitled document")
    assert at.session_state["preview_pdf"]["pages"] >= 1
    assert "project" not in at.session_state
    assert "Project: none open" in [str(element.value) for element in at.caption]


def test_editing_a_template_file_on_disk_beats_the_stored_session(tmp_path, monkeypatch):
    skip_without_renderer()
    root = make_project(tmp_path)
    stub_dialog(monkeypatch, root)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    open_via_dialog(at, root)
    next(item for item in at.color_picker if item.label == "Accent").set_value("#123456").run()
    on_disk = projects.Project.open(root)
    external = on_disk.load_template("Default")
    external.theme.accent = "#abcdef"
    on_disk.save_template(external)
    at.button(key="close_project_button").click().run()
    open_via_dialog(at, root)
    assert at.session_state["template"].theme.accent == "#abcdef"


def test_app_opens_a_project_directory(tmp_path):
    skip_without_renderer()
    root = make_project(tmp_path)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    assert not at.exception
    at.session_state["project"] = projects.Project.open(root)
    at.run()
    assert not at.exception
    assert "Project: Reports" in [str(element.value) for element in at.caption]
    assert [element.value for element in at.selectbox if "Default" in element.options]
