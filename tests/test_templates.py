from __future__ import annotations

from md2pdf.templates import Margins, PRESET_NAMES, Template, default_template, preset


def test_every_preset_builds():
    for name in PRESET_NAMES:
        template = preset(name)
        assert template.name == name
        assert template.theme.body_font
        assert template.page.dimensions_mm()[0] > 0


def test_dict_round_trip_preserves_values():
    original = preset("Manual with cover")
    restored = Template.from_dict(original.to_dict())
    assert restored.to_dict() == original.to_dict()


def test_json_round_trip_through_disk(tmp_path):
    original = default_template()
    path = original.save(tmp_path / "templates" / "modern.json")
    assert path.is_file()
    assert Template.load(path).to_dict() == original.to_dict()


def test_from_dict_tolerates_partial_and_stringy_data():
    template = Template.from_dict(
        {
            "name": "Partial",
            "page": {"size": "Letter", "margins": {"top": "25.4"}},
            "theme": {"base_font_size_pt": "11.5", "table_zebra": "yes"},
            "unknown_key": {"nested": True},
        }
    )
    assert template.page.size == "Letter"
    assert template.page.margins.top == 25.4
    assert template.page.margins.right == Margins().right
    assert template.theme.base_font_size_pt == 11.5
    assert template.theme.table_zebra is True
    assert template.document.title == ""


def test_page_dimensions_follow_orientation_and_custom_size():
    template = default_template()
    assert template.page.dimensions_mm() == (210.0, 297.0)
    template.page.orientation = "landscape"
    assert template.page.dimensions_mm()[0] == 297.0
    template.page.size = "Custom"
    template.page.orientation = "portrait"
    template.page.custom_width_mm = 100.0
    template.page.custom_height_mm = 150.0
    assert template.page.size_css() == "100mm 150mm"


def test_extension_names_reflect_toggles():
    options = default_template().document.markdown
    options.toc = False
    options.codehilite = False
    names = options.extension_names()
    assert "toc" not in names
    assert "codehilite" not in names
    assert "fenced_code" in names
    options.toc = True
    assert "toc" in options.extension_names()


def test_doc_id_placements_are_filtered():
    template = default_template()
    template.document.docid.placements = ["nonsense"]
    assert template.document.docid.normalized_placements() == ["footer"]
