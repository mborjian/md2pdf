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


def test_app_converts_the_example_and_shows_both_views():
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
    assert at.radio(key="preview_layout").value == "PDF and preview"
    if pdf_component_available():
        messages = [str(element.value) for element in at.warning]
        assert not [text for text in messages if "inline PDF viewer needs" in text]


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


def test_reopening_a_project_restores_the_preview_layout(tmp_path, monkeypatch):
    skip_without_renderer()
    root = make_project(tmp_path)
    stub_dialog(monkeypatch, root)
    at = open_app()
    at.radio(key="mode_radio").set_value("Project workspace").run()
    open_via_dialog(at, root)
    at.radio(key="source_mode").set_value("Example document").run()
    at.button(key="convert_button").click().run()
    assert len(at.session_state["results"]) == 1
    next(item for item in at.radio if item.label == "Layout").set_value("PDF only").run()
    at.button(key="close_project_button").click().run()
    assert at.session_state["project"] is None
    open_via_dialog(at, root)
    assert at.session_state["layout_pref"] == "PDF only"
    assert projects.Project.open(root).load_session()["preview_layout"] == "PDF only"
    at.button(key="convert_button").click().run()
    assert next(item for item in at.radio if item.label == "Layout").value == "PDF only"


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
