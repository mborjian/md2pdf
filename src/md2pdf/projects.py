from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import docids
from .templates import SCHEMA_VERSION, Template, default_template

PROJECT_FILE = "project.json"
MANIFEST_FILE = "manifest.json"
STATE_FILE = "state.json"
SESSION_FILE = "session.json"
RECENTS_FILE = "recents.json"
RECENTS_LIMIT = 8
NESTED_PROJECT_LEVELS = 8
TEMPLATES_DIR = "templates"
DOCUMENTS_DIR = "documents"
OUTPUT_DIR = "output"
ASSETS_DIR = "assets"
DIRECTORIES = (TEMPLATES_DIR, DOCUMENTS_DIR, OUTPUT_DIR, ASSETS_DIR)


@dataclass
class ProjectMeta:
    name: str = ""
    description: str = ""
    created: str = ""
    schema: int = SCHEMA_VERSION


@dataclass
class Project:
    root: Path
    meta: ProjectMeta = field(default_factory=ProjectMeta)
    state: dict = field(default_factory=dict)
    manifest: list[dict] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        root: str | Path,
        name: str = "",
        template: Template | None = None,
        description: str = "",
        extra_templates: list[Template] | None = None,
    ) -> "Project":
        target = Path(root).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        for directory in DIRECTORIES:
            (target / directory).mkdir(parents=True, exist_ok=True)
        project = cls(
            root=target,
            meta=ProjectMeta(
                name=(name or target.name).strip(),
                description=description,
                created=datetime.datetime.now().isoformat(timespec="seconds"),
            ),
            state={"schema": SCHEMA_VERSION, "next_sequence": 1, "counters": {}, "last_doc_id": ""},
            manifest=[],
        )
        if template is None:
            chosen = default_template()
            chosen.name = "Default"
        else:
            chosen = template
            if not chosen.name:
                chosen.name = "Default"
        project.save_template(chosen)
        for extra in extra_templates or []:
            if extra.name and extra.name != chosen.name:
                project.save_template(extra)
        project.save_meta()
        project.save_state()
        project.save_manifest()
        return project

    @classmethod
    def open(cls, root: str | Path) -> "Project":
        target = Path(root).expanduser()
        meta_path = target / PROJECT_FILE
        if not meta_path.is_file():
            raise FileNotFoundError(f"no {PROJECT_FILE} in {target}")
        meta_data = _read_json(meta_path, {})
        project = cls(
            root=target.resolve(),
            meta=ProjectMeta(
                name=meta_data.get("name") or target.name,
                description=meta_data.get("description", ""),
                created=meta_data.get("created", ""),
                schema=int(meta_data.get("schema", SCHEMA_VERSION) or SCHEMA_VERSION),
            ),
            state=_read_json(target / STATE_FILE, {}),
            manifest=_read_json(target / MANIFEST_FILE, []),
        )
        project.state.setdefault("schema", SCHEMA_VERSION)
        project.state.setdefault("next_sequence", 1)
        project.state.setdefault("counters", {})
        project.state.setdefault("last_doc_id", "")
        if not isinstance(project.manifest, list):
            project.manifest = []
        for directory in DIRECTORIES:
            (project.root / directory).mkdir(parents=True, exist_ok=True)
        return project

    def directory(self, name: str) -> Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_meta(self) -> Path:
        return _write_json(self.root / PROJECT_FILE, asdict(self.meta))

    def save_state(self) -> Path:
        return _write_json(self.root / STATE_FILE, self.state)

    def save_manifest(self) -> Path:
        return _write_json(self.root / MANIFEST_FILE, self.manifest)

    def session_path(self) -> Path:
        return self.root / SESSION_FILE

    def load_session(self) -> dict:
        data = _read_json(self.session_path(), {})
        return data if isinstance(data, dict) else {}

    def save_session(self, data: dict) -> Path:
        return _write_json(self.session_path(), data if isinstance(data, dict) else {})

    def save(self) -> None:
        self.save_meta()
        self.save_state()
        self.save_manifest()

    def template_paths(self) -> list[Path]:
        directory = self.directory(TEMPLATES_DIR)
        return sorted(directory.glob("*.json"), key=lambda item: item.name.lower())

    def template_names(self) -> list[str]:
        return [path.stem for path in self.template_paths()]

    def template_path(self, name: str) -> Path:
        return self.directory(TEMPLATES_DIR) / f"{docids.safe_filename(name, fallback='template')}.json"

    def load_template(self, name: str) -> Template:
        path = self.template_path(name)
        if not path.is_file():
            raise FileNotFoundError(f"template not found: {name}")
        template = Template.load(path)
        if not template.name:
            template.name = name
        return template

    def template_digest(self, name: str) -> str:
        path = self.template_path(name)
        if not path.is_file():
            return ""
        return hashlib.sha1(path.read_bytes()).hexdigest()

    def load_first_template(self) -> Template:
        names = self.template_names()
        if not names:
            template = default_template()
            template.name = "Default"
            self.save_template(template)
            return template
        return self.load_template(names[0])

    def save_template(self, template: Template) -> Path:
        name = template.name or "Default"
        return template.save(self.template_path(name))

    def rename_template(self, old_name: str, new_name: str) -> Path:
        template = self.load_template(old_name)
        template.name = new_name
        path = self.save_template(template)
        if old_name.lower() != new_name.lower():
            self.template_path(old_name).unlink(missing_ok=True)
        return path

    def delete_template(self, name: str) -> bool:
        path = self.template_path(name)
        if path.is_file():
            path.unlink()
            return True
        return False

    def assets(self) -> list[Path]:
        directory = self.directory(ASSETS_DIR)
        return sorted((item for item in directory.iterdir() if item.is_file()), key=lambda item: item.name.lower())

    def asset_path(self, filename: str) -> Path:
        return self.directory(ASSETS_DIR) / docids.safe_filename(filename, fallback="asset")

    def add_asset(self, filename: str, data: bytes) -> Path:
        target = self.asset_path(filename)
        if target.exists():
            target = _unique_path(target)
        target.write_bytes(data)
        return target

    def delete_asset(self, filename: str) -> bool:
        path = self.directory(ASSETS_DIR) / Path(filename).name
        if path.is_file():
            path.unlink()
            return True
        return False

    def documents(self) -> list[Path]:
        directory = self.directory(DOCUMENTS_DIR)
        return sorted(directory.glob("*.md"), key=lambda item: item.name.lower())

    def outputs(self) -> list[Path]:
        directory = self.directory(OUTPUT_DIR)
        return sorted(directory.glob("*.pdf"), key=lambda item: item.name.lower())

    def next_sequence(self) -> int:
        try:
            value = int(self.state.get("next_sequence", 1))
        except (TypeError, ValueError):
            value = 1
        return max(value, 1)

    def bump_sequence(self, amount: int = 1) -> int:
        value = self.next_sequence() + amount
        self.state["next_sequence"] = value
        self.save_state()
        return value

    def existing_doc_ids(self) -> set[str]:
        ids: set[str] = set()
        for entry in self.manifest:
            value = str(entry.get("doc_id") or "").strip()
            if value:
                ids.add(value)
        return ids

    def preview_doc_id(self, template: Template, context: docids.DocIdContext) -> str:
        pattern = template.document.docid.pattern
        value = docids.expand(
            pattern,
            context,
            sequence=self.next_sequence(),
            optional_groups=True,
        )
        return value.strip()

    def allocate_doc_id(self, template: Template, context: docids.DocIdContext) -> str:
        options = template.document.docid
        pattern = options.pattern
        if not options.enabled or not pattern.strip():
            return ""
        known = self.existing_doc_ids()
        candidate = ""
        for _ in range(128):
            candidate = docids.expand(
                pattern,
                context,
                sequence=self.next_sequence(),
                optional_groups=True,
            ).strip()
            if docids.uses_counter(pattern):
                self.bump_sequence()
            if not options.ensure_unique or candidate not in known:
                break
        self.state["last_doc_id"] = candidate
        self.save_state()
        return candidate

    def unique_target(self, directory: str, filename: str) -> Path:
        return _unique_path(self.directory(directory) / Path(filename).name)

    def save_conversion(
        self,
        markdown_text: str,
        *,
        pdf_bytes: bytes,
        output_name: str,
        doc_id: str = "",
        title: str = "",
        template_name: str = "",
        source_name: str = "",
        page_count: int = 0,
        save_markdown: bool = True,
        created: str | None = None,
    ) -> dict:
        stem = Path(output_name).stem or "document"
        pdf_path = self.unique_target(OUTPUT_DIR, f"{stem}.pdf")
        pdf_path.write_bytes(pdf_bytes)
        markdown_path = ""
        if save_markdown:
            md_target = self.unique_target(DOCUMENTS_DIR, f"{stem}.md")
            md_target.write_text(markdown_text or "", encoding="utf-8")
            markdown_path = self.relative(md_target)
        entry = {
            "id": uuid.uuid4().hex[:12],
            "doc_id": doc_id,
            "title": title,
            "template": template_name,
            "source": source_name,
            "markdown": markdown_path,
            "pdf": self.relative(pdf_path),
            "pages": int(page_count or 0),
            "bytes": pdf_path.stat().st_size,
            "created": created or datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self.manifest.append(entry)
        self.save_manifest()
        return entry

    def entry(self, entry_id: str) -> dict | None:
        for item in self.manifest:
            if item.get("id") == entry_id:
                return item
        return None

    def entry_for_markdown(self, relative_path: str | Path) -> dict | None:
        target = str(relative_path).replace("\\", "/")
        for item in self.manifest:
            stored = str(item.get("markdown") or "").replace("\\", "/")
            if stored and stored == target:
                return item
        return None

    def update_conversion(
        self,
        entry_id: str,
        markdown_text: str,
        *,
        pdf_bytes: bytes,
        output_name: str,
        doc_id: str = "",
        title: str = "",
        template_name: str = "",
        source_name: str = "",
        page_count: int = 0,
        save_markdown: bool = True,
        updated: str | None = None,
    ) -> dict | None:
        entry = self.entry(entry_id)
        if entry is None:
            return None
        stem = Path(output_name).stem or "document"
        previous_pdf = str(entry.get("pdf") or "")
        pdf_target = self.directory(OUTPUT_DIR) / f"{stem}.pdf"
        if previous_pdf and self.relative(pdf_target) != previous_pdf:
            pdf_target = self.unique_target(OUTPUT_DIR, f"{stem}.pdf")
        pdf_target.write_bytes(pdf_bytes)
        current_pdf = self.relative(pdf_target)
        if previous_pdf and previous_pdf != current_pdf:
            self.absolute(previous_pdf).unlink(missing_ok=True)
        previous_md = str(entry.get("markdown") or "")
        markdown_path = previous_md
        if save_markdown:
            md_target = self.directory(DOCUMENTS_DIR) / f"{stem}.md"
            if previous_md and self.relative(md_target) != previous_md:
                md_target = self.unique_target(DOCUMENTS_DIR, f"{stem}.md")
            md_target.write_text(markdown_text or "", encoding="utf-8")
            markdown_path = self.relative(md_target)
            if previous_md and previous_md != markdown_path:
                self.absolute(previous_md).unlink(missing_ok=True)
        entry.update(
            {
                "doc_id": doc_id or entry.get("doc_id", ""),
                "title": title or entry.get("title", ""),
                "template": template_name or entry.get("template", ""),
                "source": source_name or entry.get("source", ""),
                "markdown": markdown_path,
                "pdf": current_pdf,
                "pages": int(page_count or 0),
                "bytes": pdf_target.stat().st_size,
                "updated": updated or datetime.datetime.now().isoformat(timespec="seconds"),
            }
        )
        self.save_manifest()
        return entry

    def history(self) -> list[dict]:
        return list(reversed(self.manifest))

    def relative(self, path: str | Path) -> str:
        candidate = Path(path)
        root = self.root.resolve()
        for value in (candidate.resolve(), candidate):
            try:
                return str(value.relative_to(root))
            except ValueError:
                continue
        return str(candidate)

    def absolute(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        return candidate if candidate.is_absolute() else self.root / candidate

    def read_entry_markdown(self, entry: dict) -> str:
        relative_path = entry.get("markdown") or ""
        if not relative_path:
            return ""
        path = self.absolute(relative_path)
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return ""

    def entry_pdf_bytes(self, entry: dict) -> bytes:
        relative_path = entry.get("pdf") or ""
        path = self.absolute(relative_path)
        return path.read_bytes() if path.is_file() else b""

    def forget_entry(self, entry_id: str, delete_files: bool = False) -> bool:
        remaining = []
        removed = None
        for entry in self.manifest:
            if entry.get("id") == entry_id:
                removed = entry
                continue
            remaining.append(entry)
        if removed is None:
            return False
        self.manifest = remaining
        self.save_manifest()
        if delete_files:
            for key in ("pdf", "markdown"):
                value = removed.get(key) or ""
                if value:
                    self.absolute(value).unlink(missing_ok=True)
        return True

    def rescan(self) -> int:
        known = {entry.get("pdf") for entry in self.manifest}
        added = 0
        for path in self.outputs():
            relative_path = self.relative(path)
            if relative_path in known:
                continue
            self.manifest.append(
                {
                    "id": uuid.uuid4().hex[:12],
                    "doc_id": "",
                    "title": path.stem,
                    "template": "",
                    "source": "",
                    "markdown": "",
                    "pdf": relative_path,
                    "pages": 0,
                    "bytes": path.stat().st_size,
                    "created": datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat(
                        timespec="seconds"
                    ),
                    "imported": True,
                }
            )
            added += 1
        if added:
            self.save_manifest()
        return added

    def summary(self) -> dict:
        return {
            "name": self.meta.name,
            "root": str(self.root),
            "templates": len(self.template_names()),
            "documents": len(self.documents()),
            "pdfs": len(self.outputs()),
            "assets": len(self.assets()),
            "next_sequence": self.next_sequence(),
        }

    def delete(self, everything: bool = False) -> None:
        if everything:
            shutil.rmtree(self.root, ignore_errors=True)


def _read_json(path: Path, fallback):
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _unique_path(path: Path) -> Path:
    return docids.unique_path(path)


def find_projects(root: str | Path, max_depth: int = 3) -> list[Path]:
    base = Path(root).expanduser()
    if not base.is_dir():
        return []
    found: list[Path] = []
    base_depth = len(base.parts)
    for path in sorted(base.rglob(PROJECT_FILE)):
        if len(path.parts) - base_depth > max_depth + 1:
            continue
        if any(part.startswith(".") for part in path.parts[base_depth:-1]):
            continue
        found.append(path.parent)
    return found


def default_projects_root() -> Path:
    home = Path.home()
    documents = home / "Documents"
    return (documents if documents.is_dir() else home) / "md2pdf-projects"


def is_project(root: str | Path) -> bool:
    return (Path(root).expanduser() / PROJECT_FILE).is_file()


def list_subdirectories(root: str | Path) -> list[Path]:
    base = Path(root).expanduser()
    if not base.is_dir():
        return []
    try:
        entries = list(base.iterdir())
    except OSError:
        return []
    return sorted(
        (item for item in entries if item.is_dir() and not item.name.startswith(".")),
        key=lambda item: item.name.lower(),
    )


def nearest_project_root(root: str | Path, max_levels: int = NESTED_PROJECT_LEVELS) -> Path | None:
    current = Path(root).expanduser()
    try:
        current = current.resolve()
    except OSError:
        return None
    if current.is_file():
        current = current.parent
    for _ in range(max_levels + 1):
        if is_project(current):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def app_home() -> Path:
    override = os.environ.get("MD2PDF_HOME", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".md2pdf"


def recents_file() -> Path:
    return app_home() / RECENTS_FILE


def load_recents() -> list[Path]:
    data = _read_json(recents_file(), [])
    if not isinstance(data, list):
        return []
    values: list[Path] = []
    for item in data:
        candidate = Path(str(item)).expanduser()
        if candidate not in values:
            values.append(candidate)
    return values


def remember_recent(root: str | Path) -> list[Path]:
    path = Path(root).expanduser()
    try:
        path = path.resolve()
    except OSError:
        pass
    entries = [item for item in load_recents() if item != path]
    entries.insert(0, path)
    entries = entries[:RECENTS_LIMIT]
    _write_json(recents_file(), [str(item) for item in entries])
    return entries
