"""Intelligent component search tools for KiCad MCP Server."""

from ..server import mcp
from ..parsers.schematic_parser import SchematicParser


@mcp.tool()
async def search_components_by_type(
    file_path: str,
    component_type: str,
    search_in_subsheets: bool = True
) -> str:
    """Search for components by type (OLED, sensor, display, etc.).

    This tool intelligently searches for components by their type, value,
    footprint, or network connections to identify specific component categories.

    Args:
        file_path: Path to .kicad_sch file
        component_type: Type of component to search for (e.g., 'OLED', 'sensor', 'display', 'SPI', 'I2C')
        search_in_subsheets: Whether to search in hierarchical subsheets (default: True)

    Returns:
        Formatted list of matching components with their connections and details
    """
    try:
        import os
        from pathlib import Path

        parser = SchematicParser(file_path)
        components = parser.get_components()
        nets = parser.get_nets()

        # Smart component type detection patterns
        type_patterns = {
            'OLED': ['oled', 'ssd', 'display', 'lcd', 'tft'],
            'sensor': ['sensor', 'temp', 'humidity', 'pressure', 'motion', 'accel', 'gyro'],
            'display': ['display', 'oled', 'lcd', 'tft', 'screen'],
            'SPI': ['spi', 'mosi', 'miso', 'sck', 'cs'],
            'I2C': ['i2c', 'sda', 'scl', 'twi'],
            'UART': ['uart', 'serial', 'tx', 'rx'],
            'power': ['regulator', 'ldo', 'buck', 'boost', 'pmic'],
            'memory': ['flash', 'eeprom', 'ram', 'sdram'],
            'wireless': ['wifi', 'bluetooth', 'nrf', 'esp'],
        }

        # Get search patterns for the requested type
        search_type = component_type.upper()
        patterns = type_patterns.get(search_type, [component_type.lower()])

        # Search for matching components
        matching_components = []

        for component in components:
            # Check value field
            if any(pattern in component.value.lower() for pattern in patterns):
                matching_components.append(component)
                continue

            # Check footprint
            if hasattr(component, 'footprint') and component.footprint:
                if any(pattern in component.footprint.lower() for pattern in patterns):
                    matching_components.append(component)
                    continue

            # Check network connections
            if nets:
                for net in nets:
                    if any(pattern in net.name.lower() for pattern in patterns):
                        # Check if this component is connected to this net
                        for pin in net.pins:
                            if pin.reference == component.reference:
                                matching_components.append(component)
                                break
                        if component in matching_components:
                            break

        if not matching_components:
            return f"# No {component_type} components found\n\nSearched for patterns: {', '.join(patterns)}\n\nFound 0 matching components in {len(components)} total components."

        # Format results
        lines = [
            f"# {component_type} Components Found",
            f"",
            f"**File:** {file_path}",
            f"**Total {component_type} components:** {len(matching_components)}",
            f"**Searched patterns:** {', '.join(patterns)}",
            f"",
            f"## Matching Components",
            f""
        ]

        for i, component in enumerate(matching_components, 1):
            lines.append(f"### {i}. {component.reference} - {component.value}")

            if hasattr(component, 'footprint') and component.footprint:
                lines.append(f"**Footprint:** {component.footprint}")

            # Find network connections for this component
            component_nets = []
            if nets:
                for net in nets:
                    for pin in net.pins:
                        if pin.reference == component.reference:
                            component_nets.append({
                                'net': net.name,
                                'pin': pin.pin
                            })

            if component_nets:
                lines.append(f"**Connections ({len(component_nets)}):**")
                for conn in component_nets[:10]:  # Show first 10 connections
                    lines.append(f"  - Pin {conn['pin']}: {conn['net']}")
                if len(component_nets) > 10:
                    lines.append(f"  - ... and {len(component_nets) - 10} more connections")

            lines.append("")

        # Search in subsheets if requested
        if search_in_subsheets:
            sheets = parser.get_sheets()
            if sheets:
                lines.extend([
                    f"## Sub-Sheet Search",
                    f""
                ])

                project_dir = Path(file_path).parent

                for sheet in sheets:
                    sheet_path = project_dir / sheet['file']
                    if sheet_path.exists():
                        try:
                            sheet_parser = SchematicParser(str(sheet_path))
                            sheet_components = sheet_parser.get_components()

                            # Search for matching components in subsheet
                            sheet_matches = []
                            for component in sheet_components:
                                if any(pattern in component.value.lower() for pattern in patterns):
                                    sheet_matches.append(component)

                            if sheet_matches:
                                lines.append(f"### {sheet['name']}")
                                lines.append(f"Found {len(sheet_matches)} {component_type} components:")
                                for component in sheet_matches:
                                    lines.append(f"  - {component.reference}: {component.value}")
                                lines.append("")

                        except Exception as e:
                            lines.append(f"### {sheet['name']}")
                            lines.append(f"Error: {e}")
                            lines.append("")

        return "\n".join(lines)

    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except Exception as e:
        return f"Error: {e}"