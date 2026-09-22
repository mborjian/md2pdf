from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, docids, native_env, projects
from .templates import PAGE_SIZE_NAMES, PRESET_NAMES, Template, default_template, preset

COMMANDS = ("convert", "project", "templates", "ui")
STATE_FILENAME = ".md2pdf-state.json"


class StateCounter:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def next_sequence(self) -> int:
        try:
            return max(int(self._load().get("next_sequence", 1)), 1)
        except (TypeError, ValueError):
            return 1

    def bump(self) -> int:
        value = self.next_sequence() + 1
        payload = self._load()
        payload["next_sequence"] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md2pdf",
        description="Convert Markdown to PDF with templates, projects and a Streamlit UI.",
    )
    parser.add_argument("--version", action="version", version=f"md2pdf {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    convert = subparsers.add_parser("convert", help="convert a Markdown file to PDF")
    convert.add_argument("input", help="Markdown file to convert")
    convert.add_argument("-o", "--output", help="PDF file or directory to write into")
    convert.add_argument("-t", "--template", help="preset name, project template name or JSON path")
    convert.add_argument("-p", "--project", help="project directory for templates, ids and history")
    convert.add_argument("--title", help="document title used by headers, covers and the file name")
    convert.add_argument("--subtitle", help="subtitle available to covers and tokens")
    convert.add_argument("--author", help="author written to PDF metadata and available as {author}")
    convert.add_argument("--company", help="company available to covers and tokens")
    convert.add_argument("--doc-id", dest="doc_id", help="override the document id pattern")
    convert.add_argument("--no-doc-id", dest="no_doc_id", action="store_true", help="disable document ids")
    convert.add_argument("--page-size", help="page size such as A4, Letter or 210x297")
    convert.add_argument("--landscape", action="store_true", help="rotate the page")
    convert.add_argument("--toc", action="store_true", help="include a table of contents")
    convert.add_argument("--no-toc", dest="no_toc", action="store_true", help="drop the table of contents")
    convert.add_argument("--no-header", dest="no_header", action="store_true", help="drop the running header")
    convert.add_argument("--no-footer", dest="no_footer", action="store_true", help="drop the running footer")
    convert.add_argument("--state-file", dest="state_file", help="counter file for {seq} outside projects")
    convert.add_argument("--save-html", dest="save_html", help="also write the intermediate HTML")
    convert.add_argument("--save-css", dest="save_css", help="also write the generated stylesheet")
    convert.add_argument("-q", "--quiet", action="store_true", help="only print the PDF path")

    project = subparsers.add_parser("project", help="create or inspect project directories")
    project_sub = project.add_subparsers(dest="project_command")
    init = project_sub.add_parser("init", help="create a project directory")
    init.add_argument("name", help="project name, also the directory name")
    init.add_argument("--dir", dest="parent", help="parent directory for the new project")
    init.add_argument("--preset", default="Modern brief", help="starting template preset")
    init.add_argument("--description", default="", help="free-form project description")
    listing = project_sub.add_parser("list", help="find existing project directories")
    listing.add_argument("root", nargs="?", help="directory to search in")

    templates = subparsers.add_parser("templates", help="list template presets and project templates")
    templates.add_argument("-p", "--project", help="project directory to list templates from")

    ui = subparsers.add_parser("ui", help="launch the Streamlit interface")
    ui.add_argument("--port", type=int, default=8501, help="port for the Streamlit server")
    ui.add_argument("--address", default="localhost", help="address for the Streamlit server")

    return parser


def resolve_template(spec: str | None, project: projects.Project | None) -> Template:
    if spec:
        if spec in PRESET_NAMES:
            return preset(spec)
        candidate = Path(spec).expanduser()
        if candidate.is_file():
            return Template.load(candidate)
        if project and spec in project.template_names():
            return project.load_template(spec)
        raise ValueError(f"unknown template: {spec}")
    if project:
        return project.load_first_template()
    return default_template()


def apply_overrides(template: Template, args: argparse.Namespace) -> Template:
    if args.page_size:
        value = args.page_size.strip()
        lowered = value.lower()
        if "x" in lowered:
            width, _, height = lowered.partition("x")
            template.page.size = "Custom"
            template.page.custom_width_mm = float(width)
            template.page.custom_height_mm = float(height)
        else:
            match = next((name for name in PAGE_SIZE_NAMES if name.lower() == lowered), None)
            if not match:
                raise ValueError(f"unknown page size: {value}")
            template.page.size = match
    if args.landscape:
        template.page.orientation = "landscape"
    if getattr(args, "subtitle", None):
        template.document.subtitle = args.subtitle
    if getattr(args, "author", None):
        template.document.author = args.author
    if getattr(args, "company", None):
        template.document.company = args.company
    if args.doc_id:
        template.document.docid.enabled = True
        template.document.docid.pattern = args.doc_id
    if args.no_doc_id:
        template.document.docid.enabled = False
    if args.toc:
        template.document.markdown.toc = True
    if args.no_toc:
        template.document.markdown.toc = False
    if args.no_header:
        template.document.header.enabled = False
    if args.no_footer:
        template.document.footer.enabled = False
    return template


def _resolve_output(output: str | None, input_path: Path, default_name: str) -> Path:
    if not output:
        return input_path.parent / default_name
    target = Path(output).expanduser()
    if output.endswith(("/", "\\")) or target.is_dir():
        return target / default_name
    return target


def _is_directory_target(output: str | None) -> bool:
    if not output:
        return True
    if output.endswith(("/", "\\")):
        return True
    return Path(output).expanduser().is_dir()


def _output_directory(output: str | None, input_path: Path) -> Path:
    if not output:
        return input_path.parent
    target = Path(output).expanduser()
    if _is_directory_target(output):
        return target
    return target.parent


def command_convert(args: argparse.Namespace) -> int:
    from . import converter

    input_path = Path(args.input).expanduser()
    if not input_path.is_file():
        print(f"md2pdf: no such file: {input_path}", file=sys.stderr)
        return 1
    project = None
    if args.project:
        try:
            project = projects.Project.open(args.project)
        except FileNotFoundError as exc:
            print(f"md2pdf: {exc}", file=sys.stderr)
            return 1
    try:
        template = apply_overrides(resolve_template(args.template, project), args)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"md2pdf: {exc}", file=sys.stderr)
        return 1
    text = input_path.read_text(encoding="utf-8")
    context = docids.DocIdContext(
        title=args.title
        or template.document.title
        or converter.first_heading(text)
        or input_path.stem,
        project=project.meta.name if project else "",
        filename=input_path.name,
    )
    output_dir = _output_directory(args.output, input_path)
    counter = StateCounter(args.state_file or (output_dir / STATE_FILENAME))
    doc_id = ""
    if template.document.docid.enabled and template.document.docid.pattern.strip():
        if project:
            doc_id = project.allocate_doc_id(template, context)
        else:
            doc_id = docids.expand(
                template.document.docid.pattern,
                context,
                sequence=counter.next_sequence(),
                optional_groups=True,
            ).strip()
            if docids.uses_counter(template.document.docid.pattern):
                counter.bump()
    try:
        result = converter.convert(
            text, template, doc_id=doc_id, context=context, base_dir=input_path.parent
        )
    except RuntimeError as exc:
        print(f"md2pdf: {exc}", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"md2pdf: warning: {warning}", file=sys.stderr)
    if args.save_html:
        Path(args.save_html).expanduser().write_text(result.html, encoding="utf-8")
    if args.save_css:
        Path(args.save_css).expanduser().write_text(result.css, encoding="utf-8")
    if project is not None:
        entry = project.save_conversion(
            text,
            pdf_bytes=result.pdf_bytes,
            output_name=result.output_name,
            doc_id=doc_id,
            title=context.title,
            template_name=template.name,
            source_name=input_path.name,
            page_count=result.page_count,
            save_markdown=template.document.output.save_markdown,
        )
        target = project.absolute(entry["pdf"])
        if args.output:
            copy = _resolve_output(args.output, input_path, target.name)
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(result.pdf_bytes)
            target = copy
    else:
        target = _resolve_output(args.output, input_path, result.output_name)
        if _is_directory_target(args.output):
            target = docids.unique_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.pdf_bytes)
    if args.quiet:
        print(target)
    else:
        pages = f", {result.page_count} pages" if result.page_count else ""
        identifier = f", id {doc_id}" if doc_id else ""
        print(f"wrote {target}{pages}{identifier}")
    return 0


def command_project_init(args: argparse.Namespace) -> int:
    parent = Path(args.parent).expanduser() if args.parent else projects.default_projects_root()
    name = args.name.strip()
    root = parent / docids.safe_filename(name, fallback="project")
    if (root / projects.PROJECT_FILE).is_file():
        print(f"md2pdf: project already exists: {root}", file=sys.stderr)
        return 1
    try:
        template = preset(args.preset)
    except KeyError:
        print(f"md2pdf: unknown preset: {args.preset}", file=sys.stderr)
        return 1
    template.name = "Default"
    project = projects.Project.create(
        root, name=name, template=template, description=args.description
    )
    print(f"created project {project.meta.name}")
    print(f"  root       {project.root}")
    print(f"  templates  {project.root / projects.TEMPLATES_DIR}")
    print(f"  output     {project.root / projects.OUTPUT_DIR}")
    print(f"  assets     {project.root / projects.ASSETS_DIR}")
    print("next: md2pdf ui   then open this directory from the Projects tab")
    return 0


def command_project_list(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser() if args.root else projects.default_projects_root()
    found = projects.find_projects(root)
    if not found:
        print(f"no projects under {root}")
        return 0
    for path in found:
        try:
            project = projects.Project.open(path)
            summary = project.summary()
            print(
                f"{path}  templates={summary['templates']} "
                f"documents={summary['documents']} pdfs={summary['pdfs']} "
                f"next_id={summary['next_sequence']}"
            )
        except FileNotFoundError:
            print(f"{path}  (unreadable)")
    return 0


def command_templates(args: argparse.Namespace) -> int:
    print("presets")
    for name in PRESET_NAMES:
        print(f"  {name}")
    if args.project:
        try:
            project = projects.Project.open(args.project)
        except FileNotFoundError as exc:
            print(f"md2pdf: {exc}", file=sys.stderr)
            return 1
        print(f"project templates in {project.root}")
        names = project.template_names()
        if not names:
            print("  (none)")
        for name in names:
            print(f"  {name}")
    print("doc id tokens")
    for token, description in docids.TOKEN_REFERENCE:
        print(f"  {{{token}}}  {description}")
    return 0


def command_ui(args: argparse.Namespace) -> int:
    app_file = Path(__file__).resolve().parent / "streamlit_app.py"
    if not app_file.is_file():
        app_file = Path(__file__).resolve().parents[2] / "app.py"
    if not app_file.is_file():
        print("md2pdf: cannot locate the Streamlit app file", file=sys.stderr)
        return 1
    try:
        from streamlit.web import cli as streamlit_cli
    except Exception as exc:
        print(f"md2pdf: Streamlit is not installed: {exc}", file=sys.stderr)
        return 1
    os.environ.update(native_env.environment_with_library_path())
    sys.argv = [
        "streamlit",
        "run",
        str(app_file),
        "--server.port",
        str(args.port),
        "--server.address",
        args.address,
    ]
    return int(streamlit_cli.main() or 0)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if native_env.cli_relaunch_needed():
        native_env.relaunch_with_library_path(arguments)
    if arguments and arguments[0] not in COMMANDS and not arguments[0].startswith("-"):
        arguments.insert(0, "convert")
    parser = build_parser()
    args = parser.parse_args(arguments)
    if args.command == "convert":
        return command_convert(args)
    if args.command == "project":
        if args.project_command == "init":
            return command_project_init(args)
        if args.project_command == "list":
            return command_project_list(args)
        print("usage: md2pdf project {init,list}", file=sys.stderr)
        return 2
    if args.command == "templates":
        return command_templates(args)
    if args.command == "ui":
        return command_ui(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
