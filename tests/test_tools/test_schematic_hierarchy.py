"""Regression tests for hierarchical (multi-sheet) schematic parsing.

Real designs keep most components in sub-sheets while the netlist is exported
from the root with full hierarchy — the parser must offer a recursive view
that matches, otherwise netlist-cross-referencing tools see zero components.
"""

from pathlib import Path

from kicad_mcp_server.parsers.schematic_parser import (
    SchematicComponent,
    SchematicParser,
    _merge_duplicate_references,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "hier"


def make_root_parser() -> SchematicParser:
    return SchematicParser(str(FIXTURES / "root.kicad_sch"))


class TestHierarchicalParsing:
    def test_flat_root_returns_only_local_components(self):
        refs = [c.reference for c in make_root_parser().get_components()]
        assert refs == ["R1"]

    def test_recursive_includes_subsheet_components(self):
        refs = {c.reference for c in make_root_parser().get_components(recursive=True)}
        assert refs == {"R1", "C9"}

    def test_missing_subsheet_is_tolerated(self):
        # root.kicad_sch also references missing.kicad_sch; the parse must
        # still return the real components, not raise or return nothing.
        refs = {c.reference for c in make_root_parser().get_components(recursive=True)}
        assert "R1" in refs and "C9" in refs

    def test_subsheet_component_metadata_is_preserved(self):
        comps = {c.reference: c for c in make_root_parser().get_components(recursive=True)}
        assert comps["C9"].value == "100nF"
        assert comps["C9"].footprint == "Capacitor_SMD:C_0603_1608Metric"

    def test_get_sheets_exposes_hierarchy(self):
        sheets = {s["name"]: s["file"] for s in make_root_parser().get_sheets()}
        assert sheets["Power"] == "child.kicad_sch"
        assert sheets["Ghost"] == "missing.kicad_sch"


class TestMergeDuplicateReferences:
    def _comp(self, ref: str, pins: list[dict]) -> SchematicComponent:
        return SchematicComponent(
            reference=ref, value="V", library_id="Lib:X", pins=list(pins)
        )

    def test_multi_unit_instances_merge_with_pin_union(self):
        u1a = self._comp("U1", [{"number": "1", "name": "VDD"}])
        u1b = self._comp("U1", [{"number": "2", "name": "GND"}, {"number": "1", "name": "VDD"}])
        merged = _merge_duplicate_references([u1a, u1b])
        assert len(merged) == 1
        numbers = [p["number"] for p in merged[0].pins]
        assert numbers == ["1", "2"]  # union, no duplicates

    def test_distinct_references_preserved(self):
        comps = [self._comp("R1", []), self._comp("C9", [])]
        assert len(_merge_duplicate_references(comps)) == 2

    def test_empty_references_are_not_collapsed(self):
        comps = [self._comp("", []), self._comp("", [])]
        assert len(_merge_duplicate_references(comps)) == 2
