"""Tests for setup_pcb_layout."""

import asyncio

import pytest

from kicad_mcp_server.tools.pcb_layout import setup_pcb_layout

ROUTED_BOARD = '(kicad_pcb (version 20241229)\n  (footprint "R_0603" (layer "F.Cu"))\n)\n'


@pytest.fixture
def schematic(tmp_path):
    sch = tmp_path / "board.kicad_sch"
    sch.write_text('(kicad_sch (version 20250114) (generator "eeschema"))\n', encoding="utf-8")
    return sch


class TestSetupPcbLayout:
    def test_new_board(self, schematic):
        result = asyncio.run(setup_pcb_layout(str(schematic), width=50, height=40))
        assert result.startswith("✅"), result
        assert "50.000 × 40.000 mm" in result
        assert "Edge.Cuts" in schematic.with_suffix(".kicad_pcb").read_text(encoding="utf-8")

    def test_existing_board_is_not_replaced(self, schematic):
        pcb = schematic.with_suffix(".kicad_pcb")
        pcb.write_text(ROUTED_BOARD, encoding="utf-8")
        result = asyncio.run(setup_pcb_layout(str(schematic), width=50, height=40))
        assert result.startswith("Error: The board file"), result
        assert "overwrite=True" in result
        assert pcb.read_text(encoding="utf-8") == ROUTED_BOARD

    def test_existing_board_is_replaced_with_overwrite(self, schematic):
        pcb = schematic.with_suffix(".kicad_pcb")
        pcb.write_text(ROUTED_BOARD, encoding="utf-8")
        result = asyncio.run(setup_pcb_layout(str(schematic), width=50, height=40, overwrite=True))
        assert result.startswith("✅"), result
        content = pcb.read_text(encoding="utf-8")
        assert "R_0603" not in content
        assert "Edge.Cuts" in content
