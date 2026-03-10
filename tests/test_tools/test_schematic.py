"""Tests for schematic tools."""

import pytest
from pathlib import Path

from kicad_mcp_server.parsers.schematic_parser import SchematicParser
from kicad_mcp_server.tools import schematic


@pytest.fixture
def example_schematic():
    """Path to example schematic file."""
    return Path(__file__).parent.parent / "fixtures" / "example_schematic.kicad_sch"


class TestSchematicParser:
    """Test schematic parser functionality."""

    def test_parse_file(self, example_schematic):
        """Test parsing a schematic file."""
        parser = SchematicParser(str(example_schematic))
        components = parser.get_components()

        assert len(components) >= 5
        assert any(c.reference == "R1" for c in components)
        assert any(c.reference == "R2" for c in components)
        assert any(c.reference == "R3" for c in components)
        assert any(c.reference == "C1" for c in components)
        assert any(c.reference == "U1" for c in components)
        assert any(c.reference == "J1" for c in components)

    def test_component_flags_default(self, example_schematic):
        """Test that normal components have default flags."""
        parser = SchematicParser(str(example_schematic))
        r1 = parser.get_component_by_reference("R1")
        assert r1 is not None
        assert r1.flags["dnp"] is False
        assert r1.flags["in_bom"] is True
        assert r1.flags["on_board"] is True
        assert r1.flags["exclude_from_sim"] is False

    def test_component_flags_dnp(self, example_schematic):
        """Test that DNP component has correct flags."""
        parser = SchematicParser(str(example_schematic))
        r3 = parser.get_component_by_reference("R3")
        assert r3 is not None
        assert r3.flags["dnp"] is True
        assert r3.flags["in_bom"] is False

    def test_get_nets(self, example_schematic):
        """Test getting nets from schematic."""
        parser = SchematicParser(str(example_schematic))
        nets = parser.get_nets()

        assert len(nets) >= 3
        net_names = [n.name for n in nets]
        assert "GND" in net_names
        assert "+3V3" in net_names
        assert "SPI_CLK" in net_names

    def test_hierarchical_labels_in_nets(self, example_schematic):
        """Test that hierarchical labels appear in nets."""
        parser = SchematicParser(str(example_schematic))
        nets = parser.get_nets()

        net_by_name = {n.name: n for n in nets}
        assert "SDA" in net_by_name
        assert "SCL" in net_by_name
        assert net_by_name["SDA"].type == "hierarchical"
        assert net_by_name["SCL"].type == "hierarchical"

    def test_get_component_by_reference(self, example_schematic):
        """Test getting component by reference."""
        parser = SchematicParser(str(example_schematic))
        r1 = parser.get_component_by_reference("R1")

        assert r1 is not None
        assert r1.value == "10k"
        assert r1.footprint == "Resistor_SMD:R_0805_2012Metric"

    def test_search_components(self, example_schematic):
        """Test searching components by pattern."""
        parser = SchematicParser(str(example_schematic))
        results = parser.search_components("10k")

        assert len(results) > 0
        assert any(c.value == "10k" for c in results)


class TestSchematicTools:
    """Test schematic tool functions."""

    @pytest.mark.asyncio
    async def test_list_schematic_components(self, example_schematic):
        """Test list_schematic_components tool."""
        result = await schematic.list_schematic_components(str(example_schematic))

        assert "R1" in result
        assert "10k" in result
        assert "Total:" in result
        # DNP component present, so DNP/BOM columns should appear
        assert "DNP" in result
        assert "In BOM" in result

    @pytest.mark.asyncio
    async def test_filter_dnp_true(self, example_schematic):
        """Test filtering for DNP-only components."""
        result = await schematic.list_schematic_components(str(example_schematic), filter_dnp=True)
        assert "R3" in result
        assert "R1" not in result

    @pytest.mark.asyncio
    async def test_filter_dnp_false(self, example_schematic):
        """Test filtering for non-DNP components."""
        result = await schematic.list_schematic_components(str(example_schematic), filter_dnp=False)
        assert "R1" in result
        assert "R3" not in result

    @pytest.mark.asyncio
    async def test_get_symbol_details(self, example_schematic):
        """Test get_symbol_details tool."""
        result = await schematic.get_symbol_details(str(example_schematic), "R1")

        assert "R1" in result
        assert "10k" in result
        assert "Footprint" in result

    @pytest.mark.asyncio
    async def test_search_symbols(self, example_schematic):
        """Test search_symbols tool."""
        result = await schematic.search_symbols(str(example_schematic), "ESP32")

        assert "U1" in result

    @pytest.mark.asyncio
    async def test_list_schematic_nets_hierarchical(self, example_schematic):
        """Test list_schematic_nets includes hierarchical labels with type."""
        result = await schematic.list_schematic_nets(str(example_schematic))

        assert "SDA" in result
        assert "SCL" in result
        assert "hierarchical" in result
        assert "| Type |" in result

    @pytest.mark.asyncio
    async def test_get_schematic_info(self, example_schematic):
        """Test get_schematic_info tool."""
        result = await schematic.get_schematic_info(str(example_schematic))

        assert "Example Project" in result
        assert "Components by Type" in result
