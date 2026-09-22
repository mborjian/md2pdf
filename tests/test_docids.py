from __future__ import annotations

import datetime

import pytest

from md2pdf import docids

NOW = datetime.datetime(2026, 9, 22, 13, 14, 15)


def test_slugify_keeps_ascii_words():
    assert docids.slugify("Héllo, Wörld!") == "hello-world"
    assert docids.slugify("Release notes") == "release-notes"
    assert docids.slugify("   ") == "untitled"


def test_number_formatting_helpers():
    assert docids.format_number(7, "4") == "0007"
    assert docids.format_number(7, "04d") == "0007"
    assert docids.format_number(7, "2") == "07"
    assert docids.format_number(7) == "7"
    assert docids.format_number(26, "hex") == "1a"
    assert docids.format_number(28, "letter") == "AB"
    assert docids.format_number(4, "roman") == "iv"
    assert docids.roman(1984) == "MCMLXXXIV"
    assert docids.alpha(27) == "AA"


def test_counter_token_specs():
    assert docids.expand("{letter}", sequence=1) == "A"
    assert docids.expand("{letter}", sequence=28) == "AB"
    assert docids.expand("{letter:lower}", sequence=28) == "ab"
    assert docids.expand("{letter:3}", sequence=28) == "028"
    assert docids.expand("{roman}", sequence=4) == "iv"
    assert docids.expand("{roman:upper}", sequence=4) == "IV"
    assert docids.expand("{seq:3}", sequence=4) == "004"


def test_sequence_date_and_random_tokens():
    value = docids.expand("DOC-{year}-{seq:3}-{randhex:4}", sequence=12, now=NOW)
    prefix, _, suffix = value.rpartition("-")
    assert prefix == "DOC-2026-012"
    assert len(suffix) == 4
    assert all(character in "0123456789abcdef" for character in suffix)


def test_optional_groups_disappear_with_empty_tokens():
    assert docids.expand("[{project} · ]{title}", docids.DocIdContext(title="Notes")) == "Notes"
    assert (
        docids.expand("[{project} · ]{title}", docids.DocIdContext(title="Notes", project="Acme"))
        == "Acme · Notes"
    )


def test_value_fallbacks_and_unknown_tokens():
    assert docids.expand("{title:Untitled}", docids.DocIdContext()) == "Untitled"
    assert docids.expand("{nope}", docids.DocIdContext()) == "{nope}"
    assert docids.unknown_tokens("{nope}-{seq}-{other}") == ["nope", "other"]
    assert docids.unknown_tokens("{seq:4}") == []


def test_counter_and_random_detection():
    assert docids.uses_counter("DOC-{seq:3}") is True
    assert docids.uses_counter("DOC-{rand:6}") is False
    assert docids.uses_random("DOC-{uuid}") is True
    assert docids.uses_random("DOC-{seq:3}") is False


def test_safe_filename_strips_path_characters():
    assert docids.safe_filename("a/b:c*d.pdf") == "a-b-c-d.pdf"
    assert docids.safe_filename("   ") == "document"
    assert docids.safe_filename("x" * 200, max_length=20) == "x" * 20


@pytest.mark.parametrize("label,pattern", sorted(docids.PRESETS.items()))
def test_every_preset_pattern_resolves(label, pattern):
    assert docids.unknown_tokens(pattern) == []
    value = docids.expand(
        pattern,
        docids.DocIdContext(title="Release notes", filename="notes.md", project="Acme"),
        sequence=42,
        now=NOW,
    )
    assert value
    assert "{" not in value
    assert "}" not in value
