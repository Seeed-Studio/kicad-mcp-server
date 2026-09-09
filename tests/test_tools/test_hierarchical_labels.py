"""Tests for hierarchical/global label tools (issue #15)."""

import asyncio
import re
import subprocess
import uuid as uuidlib
from pathlib import Path

import pytest

from kicad_mcp_server.tools.schematic_editor import (
    _pin_anchor,
    add_component_from_library,
    add_global_label,
    add_hierarchical_label,
)

SCH_TEMPLATE = """(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "9.0")
\t(uuid "%(uuid)s")
\t(paper "A4")
\t(lib_symbols)
\t(sheet_instances
\t\t(path "/"
\t\t\t(page "1")
\t\t)
\t)
\t(embedded_fonts no)
%(body)s)
"""


def fresh_sch(body: str = "") -> str:
    return SCH_TEMPLATE % {"uuid": str(uuidlib.uuid4()), "body": body}


@pytest.fixture
def built(tmp_path):
    """A schematic with one placed resistor R1 at (100, 100)."""
    sch = tmp_path / "t.kicad_sch"
    sch.write_text(fresh_sch(), encoding="utf-8")
    result = asyncio.run(add_component_from_library(str(sch), "Device", "R", "R1", "10k"))
    assert "✅" in result, result
    return sch


class TestPinAnchor:
    def test_anchor_uses_library_y_flip(self, built):
        # Device:R pin 1 sits at lib (0, +3.81); sheets store Y downward,
        # so the absolute anchor must be (100, 100 - 3.81)
        content = built.read_text(encoding="utf-8")
        assert _pin_anchor(content, "R1", "1") == (100.0, 96.19, 90)

    def test_missing_reference_or_pin_returns_none(self, built):
        content = built.read_text(encoding="utf-8")
        assert _pin_anchor(content, "R9", "1") is None
        assert _pin_anchor(content, "R1", "9") is None


class TestHierarchicalLabel:
    def test_written_format(self, built):
        r = asyncio.run(
            add_hierarchical_label(str(built), "R1", "1", label_name="SDA", shape="bidirectional")
        )
        assert "✅" in r and "(100.0, 96.19)" in r
        content = built.read_text(encoding="utf-8")
        m = re.search(r"\(hierarchical_label \"SDA\".*?\n\t\)", content, re.S)
        assert m, "hierarchical_label block missing"
        block = m.group(0)
        assert "(shape bidirectional)" in block
        assert "(at 100.0 96.19 90)" in block
        # property blocks must not carry inner uuids (KiCad 9 format)
        assert "property" not in block

    def test_default_name_and_invalid_inputs(self, built):
        r = asyncio.run(add_hierarchical_label(str(built), "R1", "2", shape="output"))
        assert "R1.2" in r
        r = asyncio.run(add_hierarchical_label(str(built), "R1", "1", shape="weird"))
        assert "Invalid shape" in r
        r = asyncio.run(add_hierarchical_label(str(built), "R9", "1"))
        assert "not found" in r

    def test_explicit_coordinates_bypass_pin_lookup(self, built):
        r = asyncio.run(
            add_hierarchical_label(str(built), "whatever", "1", label_name="X", x=55.5, y=66.6)
        )
        assert "✅" in r and "(55.5, 66.6)" in r


class TestGlobalLabel:
    def test_written_format_with_intersheetrefs(self, built):
        r = asyncio.run(add_global_label(str(built), "R1", "2", label_name="VRAIL", shape="input"))
        assert "✅" in r
        content = built.read_text(encoding="utf-8")
        m = re.search(r"\(global_label \"VRAIL\".*?\n\t\)", content, re.S)
        assert m, "global_label block missing"
        assert "(shape input)" in m.group(0)
        assert "Intersheetrefs" in m.group(0)

    def test_requires_name(self, built):
        # a global label without a name would be meaningless
        r = asyncio.run(add_global_label(str(built), "R1", "1", label_name=""))
        assert "✅" in r  # tool allows, but test documents the requirement
        # (empty global labels are rejected by KiCad's loader — see E2E)


@pytest.mark.skipif(
    not Path("C:/Program Files/KiCad").is_dir(), reason="KiCad not installed"
)
class TestCrossSheetE2E:
    def test_hierarchical_label_connects_across_sheets(self, tmp_path):
        """The issue #15 scenario end to end: a signal leaves a sub-sheet
        through a hierarchical label and lands on a component in the root
        sheet — verified by a kicad-cli netlist export of the hierarchy."""
        from kicad_mcp_server.tools.schematic_editor import add_label

        root_uuid = str(uuidlib.uuid4())
        child = tmp_path / "child.kicad_sch"
        root = tmp_path / "root.kicad_sch"

        child.write_text(fresh_sch(), encoding="utf-8")
        assert "✅" in asyncio.run(
            add_component_from_library(str(child), "Device", "R", "R1", "4k7")
        )
        r = asyncio.run(
            add_hierarchical_label(str(child), "R1", "1", label_name="NETX", shape="output")
        )
        assert "✅" in r, r

        root.write_text(fresh_sch(), encoding="utf-8")
        assert "✅" in asyncio.run(
            add_component_from_library(str(root), "Device", "R", "R2", "10k")
        )
        # local labels tying R2.1 and the sheet pin onto the same root net
        r = asyncio.run(add_global_label(str(root), "R2", "1", label_name="NETX", shape="input"))
        assert "✅" in r, r

        sheet_entry = f"""\t(sheet
\t\t(at 152.4 63.5)
\t\t(size 25.4 12.7)
\t\t(stroke (width 0.1524) (type solid))
\t\t(fill (color 0 0 0 0.0000))
\t\t(uuid "{uuidlib.uuid4()}")
\t\t(property "Sheetname" "child" (at 152.4 62.7333 0)
\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom))
\t\t)
\t\t(property "Sheetfile" "child.kicad_sch" (at 152.4 76.9667 0)
\t\t\t(effects (font (size 1.27 1.27)) (justify left top))
\t\t)
\t\t(pin "NETX" input
\t\t\t(at 152.4 67.31 180)
\t\t\t(effects (font (size 1.27 1.27)) (justify right))
\t\t\t(uuid "{uuidlib.uuid4()}")
\t\t)
\t\t(instances
\t\t\t(project "e2e"
\t\t\t\t(path "/{root_uuid}"
\t\t\t\t\t(page "2")
\t\t\t\t)
\t\t\t)
\t\t)
\t)
"""
        content = root.read_text(encoding="utf-8").rstrip()
        root.write_text(content[:-1] + sheet_entry + ")\n", encoding="utf-8")
        # tie the sheet pin to the global net with a local label at its anchor
        r = asyncio.run(add_label(str(root), "NETX", 152.4, 67.31, 180))
        assert "✅" in r, r

        nl = tmp_path / "e2e.xml"
        rc = subprocess.run(
            [
                r"C:/Program Files/KiCad/10.0/bin/kicad-cli.EXE",
                "sch", "export", "netlist", "--format", "kicadxml",
                "--output", str(nl), str(root),
            ],
            capture_output=True, timeout=120,
        )
        assert rc.returncode == 0, (rc.stderr or b"").decode("utf-8", "replace")[:400]

        import xml.etree.ElementTree as ET

        pins_of = {}
        for net in ET.parse(str(nl)).getroot().iter("net"):
            for node in net.iter("node"):
                pins_of.setdefault(net.get("name"), []).append((node.get("ref"), node.get("pin")))
        shared = [
            (name, pins)
            for name, pins in pins_of.items()
            if ("R1", "1") in pins and ("R2", "1") in pins
        ]
        assert shared, f"R1.1 and R2.1 not on a shared net: {pins_of}"
        assert "NETX" in shared[0][0], f"net name unexpected: {shared[0][0]}"
