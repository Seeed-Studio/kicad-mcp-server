"""Tests for agent-driven schematic drawing (schematic_net tools).

These pin down the hard-won geometry and format knowledge:

- lib_symbols pin offsets are Y-UP while sheets are Y-DOWN (the Y flip)
- sub-symbol blocks may be named "R_0_1" or "Device:R_0_1"
- KiCad 8/9 instances require (instances ...) with path "/<root uuid>"

The end-to-end test requires kicad-cli and validates that connect_pins
really connects what it claims (via a netlist round-trip).
"""

import asyncio
import re
import uuid as uuidlib
from pathlib import Path

import pytest

from kicad_mcp_server.tools.schematic_net import (
    _rotate_offset,
    get_pin_geometry,
)

SCH_TEMPLATE = """(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "9.0")
\t(uuid "%(root_uuid)s")
\t(paper "A4")
\t(lib_symbols
%(lib)s\t)
\t(sheet_instances
\t\t(path "/"
\t\t\t(page "1")
\t\t)
\t)
\t(embedded_fonts no)
%(body)s)
"""

# A Device:R-shaped embedded symbol: pin 1 UP in lib space, pin 2 DOWN.
LIB_R = """\t\t(symbol "Device:R"
\t\t\t(symbol "R_0_1"
\t\t\t\t(rectangle (start -1.016 -2.54) (end 1.016 2.54))
\t\t\t)
\t\t\t(symbol "R_1_1"
\t\t\t\t(pin passive line (at 0 3.81 270) (length 1.27)
\t\t\t\t\t(name "" (effects (font (size 1.27 1.27))))
\t\t\t\t\t(number "1" (effects (font (size 1.27 1.27))))
\t\t\t\t)
\t\t\t\t(pin passive line (at 0 -3.81 90) (length 1.27)
\t\t\t\t\t(name "" (effects (font (size 1.27 1.27))))
\t\t\t\t\t(number "2" (effects (font (size 1.27 1.27))))
\t\t\t\t)
\t\t\t)
\t\t)
"""

INSTANCE_R1 = """\t(symbol (lib_id "Device:R") (at 100 100 0) (unit 1)
\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
\t\t(uuid "11111111-1111-1111-1111-111111111111")
\t\t(property "Reference" "R1" (at 100 95 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Value" "10k" (at 100 102 0)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(pin "1" (uuid "21111111-1111-1111-1111-111111111111"))
\t\t(pin "2" (uuid "22111111-1111-1111-1111-111111111111"))
\t\t(instances
\t\t\t(project "t"
\t\t\t\t(path "/%(root_uuid)s" (reference "R1") (unit 1))
\t\t\t)
\t\t)
\t)
"""


def _schematic(lib: str = "", body: str = "") -> str:
    return SCH_TEMPLATE % {
        "root_uuid": str(uuidlib.uuid4()),
        "lib": lib,
        "body": body,
    }


def _schematic_with_r1() -> str:
    """Template with an embedded Device:R and one placed R1 instance."""
    root_uuid = str(uuidlib.uuid4())
    return SCH_TEMPLATE % {
        "root_uuid": root_uuid,
        "lib": LIB_R,
        "body": INSTANCE_R1 % {"root_uuid": root_uuid},
    }


class TestRotateOffset:
    def test_y_flip_at_zero_degrees(self):
        # lib pin UP (dy=+3.81) must land ABOVE the origin on the sheet
        dx, dy = _rotate_offset(0.0, 3.81, 0)
        assert (dx, dy) == (0.0, -3.81)

    def test_quarter_turns(self):
        # rotate (1, 0) by 90 CCW in lib space -> sheet offset (0, -1)
        assert _rotate_offset(1.0, 0.0, 90) == (0.0, -1.0)
        assert _rotate_offset(1.0, 0.0, 180) == (-1.0, 0.0)
        assert _rotate_offset(1.0, 0.0, 270) == (0.0, 1.0)


class TestGetPinGeometry:
    def test_absolute_positions_with_y_flip(self):
        content = _schematic_with_r1()
        pins = get_pin_geometry(content, "R1")
        by_num = {p["number"]: p for p in pins}
        # lib pin 1 at (0, +3.81) -> sheet (100, 100 - 3.81)
        assert (by_num["1"]["x"], by_num["1"]["y"]) == (100.0, 96.19)
        assert (by_num["2"]["x"], by_num["2"]["y"]) == (100.0, 103.81)

    def test_missing_reference_returns_none(self):
        content = _schematic(lib=LIB_R)
        assert get_pin_geometry(content, "R99") is None

    def test_unit_filter_excludes_other_units(self):
        # sub-symbols named with unit != instance unit are ignored
        lib = LIB_R.replace('"R_1_1"', '"R_2_1"')
        content = _schematic_with_r1().replace(LIB_R, lib)
        assert get_pin_geometry(content, "R1") == []

    def test_prefixed_subsymbol_names_also_accepted(self):
        lib = (
            LIB_R.replace('"R_0_1"', '"Device:R_0_1"')
            .replace('"R_1_1"', '"Device:R_1_1"')
        )
        content = _schematic_with_r1().replace(LIB_R, lib)
        pins = get_pin_geometry(content, "R1")
        assert {p["number"] for p in pins} == {"1", "2"}


class TestInstanceFormat:
    def test_written_instances_reference_root_uuid(self, tmp_path):
        """add_component_from_library must emit (instances (path "/<root uuid>"))
        with no inner property uuids — KiCad 8/9 refuses the file otherwise."""
        from kicad_mcp_server.tools.schematic_editor import add_component_from_library

        sch = tmp_path / "t.kicad_sch"
        sch.write_text(_schematic(), encoding="utf-8")
        result = asyncio.run(
            add_component_from_library(str(sch), "Device", "R", "R1", "10k")
        )
        content = sch.read_text(encoding="utf-8")
        root_uuid = re.search(r'\(uuid\s+"([0-9a-f-]+)"', content).group(1)
        assert f'(path "/{root_uuid}" (reference "R1") (unit 1))' in content
        # property blocks must NOT contain inner uuids (KiCad 6/7 relic)
        prop = re.search(r'\(property "Reference".*?\n\s*\)', content, re.S)
        assert prop and "uuid" not in prop.group(0)
        assert "✅" in result


class TestConnectPins:
    def test_labels_written_at_both_pin_positions(self, tmp_path):
        from kicad_mcp_server.tools.schematic_net import connect_pins

        sch = tmp_path / "t.kicad_sch"
        sch.write_text(_schematic_with_r1(), encoding="utf-8")
        result = asyncio.run(connect_pins(str(sch), "R1", "1", "R1", "2", "N1"))
        content = sch.read_text(encoding="utf-8")
        assert content.count('(label "N1"') == 2
        assert "(at 100.0 96.19 0)" in content
        assert "(at 100.0 103.81 0)" in content
        assert "✅" in result

    def test_unknown_pin_reports_available(self, tmp_path):
        from kicad_mcp_server.tools.schematic_net import connect_pins

        sch = tmp_path / "t.kicad_sch"
        sch.write_text(_schematic_with_r1(), encoding="utf-8")
        result = asyncio.run(connect_pins(str(sch), "R1", "9", "R1", "1", "N1"))
        assert "Pin '9' not found" in result and "1, 2" in result


@pytest.mark.skipif(
    not Path("C:/Program Files/KiCad").is_dir(), reason="KiCad not installed"
)
class TestNetlistRoundTrip:
    def test_built_circuit_connects_as_requested(self, tmp_path):
        """The proof the whole feature works: build a divider+LED purely via
        the tools, export a netlist with kicad-cli, and assert every pin
        landed on the net the 'agent' asked for."""
        from kicad_mcp_server.parsers.netlist_parser import NetlistParser
        from kicad_mcp_server.tools.netlist import generate_netlist, netlist_cache_path
        from kicad_mcp_server.tools.schematic_editor import add_component_from_library
        from kicad_mcp_server.tools.schematic_net import add_power_net, connect_pins

        sch = tmp_path / "roundtrip.kicad_sch"
        sch.write_text(_schematic(), encoding="utf-8")

        async def build():
            for lib, sym, ref, val, x in [
                ("Device", "R", "R1", "10k", 100),
                ("Device", "R", "R2", "4.7k", 130),
                ("Device", "LED", "D1", "RED", 160),
            ]:
                r = await add_component_from_library(str(sch), lib, sym, ref, val, x=x)
                assert "✅" in r, r
            assert "✅" in await connect_pins(str(sch), "R1", "2", "R2", "1", "MID")
            assert "✅" in await connect_pins(str(sch), "R2", "2", "D1", "1", "LED_A")
            assert "✅" in await add_power_net(str(sch), "+3V3", "R1", "1")
            assert "✅" in await add_power_net(str(sch), "GND", "D1", "2")
            assert "✅" in await generate_netlist(str(sch))

        asyncio.run(build())

        np = NetlistParser(str(netlist_cache_path(sch)))
        comps = np.get_components()
        expected = {
            "R1": {"1": "+3V3", "2": "MID"},
            "R2": {"1": "MID", "2": "LED_A"},
            "D1": {"1": "LED_A", "2": "GND"},
        }
        for ref, exp in expected.items():
            got = {k: v.lstrip("/") for k, v in comps[ref].pins.items()}
            assert got == exp, f"{ref}: {got} != {exp}"
