"""Tests for the ERC/DRC JSON report parsers and the validation tools."""

import json
import os
import shutil
from pathlib import Path

import pytest

from kicad_mcp_server.parsers.check_report_parser import (
    erc_position_scale,
    parse_drc_report,
    parse_erc_item,
    parse_erc_report,
    top_level_positions,
)
from kicad_mcp_server.tools import validation
from kicad_mcp_server.utils.kicad_cli import find_kicad_cli

FIXTURES = Path(__file__).parent.parent / "fixtures"
REPORTS = FIXTURES / "reports"
LABEL_SCH = REPORTS / "dangling_label.kicad_sch"


def _load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


class TestErcItem:
    def test_pin_with_name(self):
        item = parse_erc_item({"description": "Symbol U1 Pin 3 [SDA, Bidirectional, Line]"})
        assert (item.reference, item.pin_number, item.pin_name, item.pin_type) == (
            "U1",
            "3",
            "SDA",
            "Bidirectional",
        )

    def test_pin_without_name(self):
        item = parse_erc_item({"description": "Symbol #PWR01 Pin 1 [Power input, Line]"})
        assert (item.reference, item.pin_number, item.pin_name, item.pin_type) == (
            "#PWR01",
            "1",
            "",
            "Power input",
        )

    def test_pin_name_with_comma(self):
        item = parse_erc_item({"description": "Symbol U2 Pin A1 [IN, OUT, Bidirectional, Line]"})
        assert item.pin_name == "IN, OUT"
        assert item.pin_type == "Bidirectional"

    def test_pin_of_missing_library_symbol(self):
        item = parse_erc_item({"description": "Pin 1 [???, ?]"})
        assert (item.reference, item.pin_number) == ("", "1")

    def test_symbol(self):
        item = parse_erc_item({"description": "Symbol U3 [ABC-123]"})
        assert (item.reference, item.value, item.pin_number) == ("U3", "ABC-123", "")

    def test_label(self):
        item = parse_erc_item({"description": "Global Label 'NET_A'"})
        assert (item.label, item.reference) == ("NET_A", "")

    def test_localized_pin_keeps_structure(self):
        item = parse_erc_item({"description": "Symbol U1 Vývod 3 [SDA, Obousměrný, Čára]"})
        assert (item.reference, item.pin_number, item.pin_name) == ("U1", "3", "SDA")
        # The localized pin type is not given as an English type.
        assert item.pin_type == ""

    def test_position_scale(self):
        item = parse_erc_item(
            {"description": "Global Label 'X'", "pos": {"x": 0.508, "y": -0.635}}, 100.0
        )
        assert (item.x_mm, item.y_mm) == (50.8, -63.5)

    def test_no_position(self):
        item = parse_erc_item({"description": "Global Label 'X'"})
        assert item.x_mm is None and item.y_mm is None


class TestErcReport:
    def test_reads_all_sheets(self):
        errors = parse_erc_report(_load("erc_kicad10_en.json"))
        assert len(errors) == 8
        assert {e.sheet for e in errors} == {"/", "/Power/"}

    def test_top_level_violations_are_accepted(self):
        data = _load("erc_kicad10_en.json")
        flat = {"violations": data["sheets"][0]["violations"]}
        assert len(parse_erc_report(flat)) == 7

    def test_exclusion(self):
        errors = parse_erc_report(_load("erc_kicad10_en.json"))
        excluded = [e for e in errors if e.excluded]
        assert len(excluded) == 1
        assert excluded[0].comment == "Not used in this variant"
        assert excluded[0].severity == "error"

    def test_components_and_items(self):
        errors = parse_erc_report(_load("erc_kicad10_en.json"))
        pin_to_pin = next(e for e in errors if e.type == "pin_to_pin")
        assert pin_to_pin.components == ["U4", "U5"]
        assert [i.pin_number for i in pin_to_pin.items] == ["5", "2"]

    def test_localized_report(self):
        errors = parse_erc_report(_load("erc_kicad10_cs.json"), 100.0)
        assert [e.components for e in errors] == [["U1"], ["U3"], []]
        assert errors[0].items[0].pin_number == "3"
        assert errors[2].items[0].label == "NET_A"
        assert (errors[2].items[0].x_mm, errors[2].items[0].y_mm) == (50.8, 63.5)


class TestErcPositionScale:
    def test_calibrated_from_schematic(self):
        scale, source = erc_position_scale(_load("erc_kicad10_en.json"), [LABEL_SCH])
        assert (scale, source) == (100.0, "calibrated")

    def test_calibration_detects_report_in_mm(self):
        # A future KiCad version can write correct positions. The calibration
        # must then select 1, not the version fallback.
        data = _load("erc_kicad10_en.json")
        for sheet in data["sheets"]:
            for v in sheet["violations"]:
                for item in v["items"]:
                    item["pos"] = {k: val * 100 for k, val in item["pos"].items()}
        assert erc_position_scale(data, [LABEL_SCH]) == (1.0, "calibrated")

    def test_version_fallback(self):
        assert erc_position_scale(_load("erc_kicad10_en.json"), []) == (100.0, "version")

    def test_unknown_version_uses_report_units(self):
        data = _load("erc_kicad10_en.json")
        data["kicad_version"] = "9.0.0"
        assert erc_position_scale(data, []) == (1.0, "report")


class TestTopLevelPositions:
    def test_kicad10_format(self):
        positions = top_level_positions(LABEL_SCH.read_text(encoding="utf-8"))
        assert positions == {"00000000-0000-4000-8000-000000000106": (50.8, 63.5)}

    def test_compact_format_and_nested_uuids(self):
        positions = top_level_positions((FIXTURES / "hier" / "root.kicad_sch").read_text())
        # The symbol position, not the position of a property or a pin.
        assert positions["aaaaaaaa-0000-0000-0000-000000000001"] == (100.0, 100.0)
        assert "11111111-0000-0000-0000-111111111111" not in positions


class TestDrcReport:
    def test_reads_all_lists(self):
        errors = parse_drc_report(_load("drc_kicad10_en.json"))
        assert len(errors) == 6
        assert [e.category for e in errors].count("unconnected") == 1
        assert [e.category for e in errors].count("schematic_parity") == 1

    def test_references(self):
        errors = {e.type: e for e in parse_drc_report(_load("drc_kicad10_en.json"))}
        assert errors["unconnected_items"].components == ["U1", "J1"]
        assert errors["shorting_items"].components == ["U1"]
        assert errors["courtyards_overlap"].components == ["L4", "C18"]
        # A net name with brackets and " of " is not read as a reference.
        assert errors["clearance"].components == ["L6"]
        assert errors["text_height"].components == ["L4"]

    def test_location_and_exclusion(self):
        errors = {e.type: e for e in parse_drc_report(_load("drc_kicad10_en.json"))}
        assert errors["shorting_items"].location == (97.18, 65.3)
        assert errors["text_height"].excluded
        assert errors["text_height"].comment == "Accepted for the prototype"


class TestValidationFormatting:
    def test_erc_row_has_pin_data(self):
        errors = parse_erc_report(_load("erc_kicad10_en.json"), 100.0)
        row = validation._erc_row(errors[0])
        assert "U1.3 SDA (Bidirectional)" in row
        assert "(101.60, 76.20)" in row

    def test_excluded_is_marked_and_not_counted(self):
        errors = parse_erc_report(_load("erc_kicad10_en.json"))
        excluded = next(e for e in errors if e.excluded)
        assert "(excluded)" in validation._erc_row(excluded)
        counts = validation._count_text(errors)
        assert "- Errors: 5" in counts
        assert "- Excluded: 1" in counts

    def test_markdown_cell_is_escaped(self):
        assert validation._md("A|B\nC") == "A\\|B C"

    def test_report_path_is_keyed_by_path(self, tmp_path):
        a = validation._report_path(tmp_path / "a" / "main.kicad_sch", "erc")
        b = validation._report_path(tmp_path / "b" / "main.kicad_sch", "erc")
        assert a != b
        assert a.name.startswith("main_") and a.name.endswith("_erc.json")

    def test_stale_report(self, tmp_path):
        src = tmp_path / "main.kicad_sch"
        report = tmp_path / "report.json"
        assert validation._report_is_stale(report, [src])
        report.write_text("{}")
        src.write_text("")
        src_mtime = report.stat().st_mtime + 10
        os.utime(src, (src_mtime, src_mtime))
        assert validation._report_is_stale(report, [src])
        os.utime(src, (src_mtime - 20, src_mtime - 20))
        assert not validation._report_is_stale(report, [src])


@pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli is not installed")
class TestKicadCliIntegration:
    async def test_run_erc_gives_label_position_in_mm(self, tmp_path):
        sch = tmp_path / "dangling_label.kicad_sch"
        shutil.copy(LABEL_SCH, sch)
        out = await validation.run_erc(str(sch))
        assert "label_dangling" in out
        assert "Global Label 'NET_A'" in out
        assert "(50.80, 63.50)" in out

    async def test_get_erc_violations_gives_table_not_run_summary(self, tmp_path):
        sch = tmp_path / "dangling_label.kicad_sch"
        shutil.copy(LABEL_SCH, sch)
        out = await validation.get_erc_violations(str(sch))
        assert out.startswith("# ERC Violations")
        assert "**Count:** 1" in out

    async def test_export_erc_report_with_violations(self, tmp_path):
        sch = tmp_path / "dangling_label.kicad_sch"
        shutil.copy(LABEL_SCH, sch)
        out = await validation.export_erc_report(str(sch))
        assert "Exported" in out
        exported = tmp_path / "dangling_label_erc_report.json"
        assert json.loads(exported.read_text(encoding="utf-8"))["sheets"]
