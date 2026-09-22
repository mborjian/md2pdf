from __future__ import annotations

import datetime as _datetime
import re
import secrets
import string
import unicodedata
import uuid as _uuid
from dataclasses import dataclass
from typing import Callable

TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([^{}]*))?\}")
OPTIONAL_RE = re.compile(r"\[([^\[\]]*)\]")
NUMBER_SPEC_RE = re.compile(r"^(\d+)d?$")

COUNTER_TOKENS = frozenset(
    {"seq", "n", "no", "num", "number", "counter", "letter", "letters", "alpha", "roman"}
)
RANDOM_TOKENS = frozenset(
    {"rand", "random", "randhex", "hex", "randnum", "randdigits", "randalpha", "randletter"}
)
VALUE_TOKENS = frozenset(
    {
        "title",
        "subtitle",
        "author",
        "company",
        "project",
        "template",
        "filename",
        "stem",
        "version",
        "slug",
        "projectslug",
        "templateslug",
        "fileslug",
        "doc_id",
    }
)
DATE_TOKENS = frozenset({"date", "time", "datetime", "timestamp", "year", "month", "day", "week"})
EXTRA_TOKENS = frozenset({"uuid"})

PRESETS = {
    "Sequential — DOC-00042": "DOC-{seq:5}",
    "Year + sequence — 2026-0007": "{year}-{seq:4}",
    "Year and month + sequence — 202609-014": "{date:%Y%m}-{seq:3}",
    "Random — DOC-K7F3M9QP": "DOC-{rand:8}",
    "Random hex — 9f2c4a7b13": "{randhex:10}",
    "UUID — 3f1a…": "{uuid}",
    "Timestamp — DOC-20260922T131415": "DOC-{timestamp:%Y%m%dT%H%M%S}",
    "Title slug + sequence — release-notes-004": "{slug}-{seq:3}",
    "Project prefix + sequence — ACME-2026-015": "{project:ACME}-{year}-{seq:3}",
    "Alphabetic counter — DOC-AK": "DOC-{letter}",
}

TOKEN_REFERENCE = (
    ("seq", "Counter that increments per document in a project. Width pads with zeros: {seq:5}."),
    ("letter", "Counter as letters: 1 -> A, 27 -> AA. {letter:lower} gives lower case."),
    ("roman", "Counter as roman numerals: {roman} gives iv, {roman:upper} gives IV."),
    ("rand", "Random upper-case letters and digits, default 8: {rand:10}."),
    ("randhex", "Random hex string, default 8: {randhex:12}."),
    ("randnum", "Random digits, default 6: {randnum:4}."),
    ("randalpha", "Random upper-case letters, default 6: {randalpha:3}."),
    ("uuid", "Random UUID. {uuid:short} gives 8 hex characters, {uuid:hex} gives 32."),
    ("date", "Today. Default %Y-%m-%d, any strftime spec works: {date:%Y%m%d}."),
    ("time", "Current time, default %H%M%S."),
    ("datetime", "Date and time, default %Y-%m-%d %H:%M."),
    ("timestamp", "Unix seconds, or strftime when the spec starts with %: {timestamp:%s}."),
    ("year", "Current year, or strftime spec: {year:%y}."),
    ("month", "Current month, default %m."),
    ("day", "Current day, default %d."),
    ("week", "ISO week number."),
    ("title", "Document title from settings; the spec is a fallback: {title:Untitled}."),
    ("subtitle", "Subtitle from document settings."),
    ("author", "Author from document settings."),
    ("company", "Company from document settings."),
    ("project", "Project name; the spec is a fallback: {project:ACME}."),
    ("template", "Template name."),
    ("filename", "Source file name including extension."),
    ("stem", "Source file name without extension."),
    ("version", "Template version."),
    ("slug", "Slugified title, lower case with dashes."),
    ("projectslug", "Slugified project name."),
    ("doc_id", "The document id itself, useful in file name patterns."),
)

_ROMAN_TABLE = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


@dataclass(frozen=True)
class DocIdContext:
    title: str = ""
    project: str = ""
    template: str = ""
    filename: str = ""
    version: str = ""


def slugify(value: str, max_length: int = 48, separator: str = "-") -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", separator, text).strip("-_ ")
    text = re.sub(re.escape(separator) + r"{2,}", separator, text).lower()
    if len(text) > max_length:
        text = text[:max_length].rstrip(separator)
    return text or "untitled"


def unique_path(path: Path, limit: int = 999) -> Path:
    if not path.exists():
        return path
    for index in range(2, limit + 1):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem}-{secrets.token_hex(3)}{path.suffix}")


def safe_filename(value: str, max_length: int = 120, fallback: str = "document") -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value or "")
    text = re.sub(r"\s+", " ", text).strip(" .-")
    text = re.sub(r"-{2,}", "-", text)
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .-")
    return text or fallback


def roman(number: int) -> str:
    if number <= 0 or number > 3999:
        return str(number)
    parts = []
    remaining = number
    for value, symbol in _ROMAN_TABLE:
        while remaining >= value:
            parts.append(symbol)
            remaining -= value
    return "".join(parts)


def alpha(number: int) -> str:
    if number <= 0:
        return str(number)
    letters = []
    remaining = number
    while remaining > 0:
        remaining, index = divmod(remaining - 1, 26)
        letters.append(string.ascii_uppercase[index])
    return "".join(reversed(letters))


def format_number(value: int, spec: str = "") -> str:
    key = (spec or "").strip().lower()
    if key in {"roman", "romanlower", "lowerroman"}:
        return roman(value).lower()
    if key in {"romanupper", "upperroman"}:
        return roman(value)
    if key in {"letter", "alpha", "letters"}:
        return alpha(value)
    if key in {"letterlower", "alphalower"}:
        return alpha(value).lower()
    if key == "hex":
        return format(value, "x")
    if key in {"hexupper", "upperhex"}:
        return format(value, "X")
    match = NUMBER_SPEC_RE.match(key)
    if match:
        return str(value).zfill(int(match.group(1)))
    return str(value)


def random_token(spec: str = "", kind: str = "rand") -> str:
    width = int(spec) if spec.strip().isdigit() else 0
    width = max(1, min(width or 8, 64))
    if kind in {"randhex", "hex"}:
        return secrets.token_hex((width + 1) // 2)[:width]
    if kind in {"randnum", "randdigits"}:
        alphabet = string.digits
    elif kind in {"randalpha", "randletter"}:
        alphabet = string.ascii_uppercase
    else:
        alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(width))


def _value_map(context: DocIdContext, extra: dict[str, str] | None) -> dict[str, str]:
    filename = re.split(r"[\\/]", context.filename or "")[-1]
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    title = context.title or stem
    values = {
        "title": context.title,
        "subtitle": "",
        "author": "",
        "company": "",
        "project": context.project,
        "template": context.template,
        "filename": filename,
        "stem": stem,
        "version": context.version,
        "slug": slugify(title),
        "projectslug": slugify(context.project) if context.project else "",
        "templateslug": slugify(context.template) if context.template else "",
        "fileslug": slugify(stem) if stem else "",
        "doc_id": "",
    }
    for key, value in (extra or {}).items():
        values[str(key).lower()] = "" if value is None else str(value)
    return values


def _resolver(
    context: DocIdContext,
    sequence: int,
    stamp: _datetime.datetime,
    extra: dict[str, str] | None,
) -> Callable[[str, str], str]:
    values = _value_map(context, extra)

    def resolve(name: str, spec: str) -> str:
        key = name.lower()
        if key in COUNTER_TOKENS:
            lowered = spec.strip().lower()
            if key in {"letter", "letters", "alpha"}:
                if lowered in {"lower", "lowercase", "letterlower"}:
                    return alpha(sequence).lower()
                if lowered.isdigit():
                    return str(sequence).zfill(int(lowered))
                return alpha(sequence)
            if key == "roman":
                if lowered in {"upper", "uppercase"}:
                    return roman(sequence)
                if lowered.isdigit():
                    return str(sequence).zfill(int(lowered))
                return roman(sequence).lower()
            return format_number(sequence, spec)
        if key in RANDOM_TOKENS:
            return random_token(spec, key)
        if key == "uuid":
            lowered = spec.lower()
            if lowered in {"hex", "hex32"}:
                return _uuid.uuid4().hex
            if lowered in {"short", "s"}:
                return _uuid.uuid4().hex[:8]
            if spec.isdigit():
                return _uuid.uuid4().hex[: int(spec)]
            return str(_uuid.uuid4())
        if key == "timestamp":
            if spec.startswith("%"):
                return stamp.strftime(spec)
            if spec.isdigit():
                return str(int(stamp.timestamp()))[-int(spec) :]
            return str(int(stamp.timestamp()))
        if key == "date":
            return stamp.strftime(spec or "%Y-%m-%d")
        if key == "time":
            return stamp.strftime(spec or "%H%M%S")
        if key == "datetime":
            return stamp.strftime(spec or "%Y-%m-%d %H:%M")
        if key == "year":
            return stamp.strftime(spec or "%Y")
        if key == "month":
            return stamp.strftime(spec or "%m")
        if key == "day":
            return stamp.strftime(spec or "%d")
        if key == "week":
            return stamp.strftime(spec or "%V")
        if key in values:
            value = values[key]
            return value if value else spec
        return "{" + name + (":" + spec if spec else "") + "}"

    return resolve


def resolver(
    context: DocIdContext | None = None,
    *,
    sequence: int = 1,
    now: _datetime.datetime | None = None,
    extra: dict[str, str] | None = None,
) -> Callable[[str, str], str]:
    stamp = now or _datetime.datetime.now()
    return _resolver(context or DocIdContext(), sequence, stamp, extra)


def expand_with(pattern: str, resolve: Callable[[str, str], str], optional_groups: bool = True) -> str:
    text = pattern or ""

    def run(source: str) -> tuple[str, bool]:
        had_empty = False

        def replace(match: re.Match) -> str:
            nonlocal had_empty
            value = resolve(match.group(1), match.group(2) or "")
            if value == "":
                had_empty = True
            return value

        return TOKEN_RE.sub(replace, source), had_empty

    if optional_groups and "[" in text:
        stash: list[str] = []

        def replace_group(match: re.Match) -> str:
            inner, had_empty = run(match.group(1))
            if had_empty:
                return ""
            stash.append(inner)
            return "\x00" + str(len(stash) - 1) + "\x00"

        text = OPTIONAL_RE.sub(replace_group, text)
        text, _ = run(text)
        for index, value in enumerate(stash):
            text = text.replace("\x00" + str(index) + "\x00", value)
        return text

    result, _ = run(text)
    return result


def expand(
    pattern: str,
    context: DocIdContext | None = None,
    *,
    sequence: int = 1,
    now: _datetime.datetime | None = None,
    extra: dict[str, str] | None = None,
    optional_groups: bool = True,
) -> str:
    stamp = now or _datetime.datetime.now()
    resolve = _resolver(context or DocIdContext(), sequence, stamp, extra)
    return expand_with(pattern, resolve, optional_groups=optional_groups)


def tokens(pattern: str) -> list[str]:
    found = []
    for match in TOKEN_RE.finditer(pattern or ""):
        found.append(match.group(1).lower())
    return found


def unknown_tokens(pattern: str) -> list[str]:
    known = COUNTER_TOKENS | RANDOM_TOKENS | DATE_TOKENS | VALUE_TOKENS | EXTRA_TOKENS
    seen: list[str] = []
    for name in tokens(pattern):
        if name not in known and name not in seen:
            seen.append(name)
    return seen


def uses_counter(pattern: str) -> bool:
    return any(name in COUNTER_TOKENS for name in tokens(pattern))


def uses_random(pattern: str) -> bool:
    return any(name in RANDOM_TOKENS or name == "uuid" for name in tokens(pattern))


def preview(
    pattern: str,
    context: DocIdContext | None = None,
    *,
    sequence: int = 1,
    extra: dict[str, str] | None = None,
) -> str:
    return expand(pattern, context, sequence=sequence, extra=extra, optional_groups=True)
