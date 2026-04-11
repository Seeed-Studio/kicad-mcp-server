"""Hierarchical schematic analysis tools for KiCad MCP Server."""

from pathlib import Path

from ..parsers.schematic_parser import SchematicParser
from ..server import mcp


@mcp.tool()
async def trace_hierarchical_connection(
    file_path: str,
    reference: str,
    pin_number: str = ""
) -> str:
    """Trace component connections across hierarchical schematics.

    This tool traces connections through the entire schematic hierarchy,
    including sub-sheets, to show complete signal paths.

    Args:
        file_path: Path to main .kicad_sch file
        reference: Component reference designator (e.g., 'U1', 'R5')
        pin_number: Optional pin number to trace (if empty, trace all pins)

    Returns:
        Complete connection trace through hierarchy
    """
    try:
        parser = SchematicParser(file_path)
        components = parser.get_components()
        nets = parser.get_nets()
        sheets = parser.get_sheets()

        # Find the target component
        target_component = None
        for component in components:
            if component.reference == reference:
                target_component = component
                break

        if not target_component:
            return f"# Component Not Found\n\nComponent '{reference}' not found in schematic.\n\nAvailable components: {', '.join([c.reference for c in components[:10]])}..."

        lines = [
            f"# Connection Trace for {target_component.reference}",
            "",
            f"**Component:** {target_component.reference}",
            f"**Value:** {target_component.value}",
            f"**File:** {file_path}",
            ""
        ]

        # Trace connections for specific pin or all pins
        if pin_number:
            # Trace specific pin
            pin_nets = []
            for net in nets:
                for pin in net.pins:
                    if pin.reference == reference and pin.pin == pin_number:
                        pin_nets.append({
                            'pin': pin.pin,
                            'net': net.name,
                            'connections': [(p.reference, p.pin) for p in net.pins if p.reference != reference]
                        })
                        break

            if not pin_nets:
                lines.append(f"## Pin {pin_number} Not Found")
                lines.append(f"No connections found for pin {pin_number} on component {reference}.")
            else:
                lines.append(f"## Pin {pin_number} Connections")
                for pin_net in pin_nets:
                    lines.append(f"**Net:** {pin_net['net']}")
                    lines.append("**Connected to:**")
                    for ref, pin in pin_net['connections']:
                        lines.append(f"  - {ref}:{pin}")
        else:
            # Trace all pins
            all_pin_nets = {}
            for net in nets:
                for pin in net.pins:
                    if pin.reference == reference:
                        if pin.pin not in all_pin_nets:
                            all_pin_nets[pin.pin] = []

                        all_pin_nets[pin.pin].append({
                            'net': net.name,
                            'connections': [(p.reference, p.pin) for p in net.pins if p.reference != reference]
                        })

            if not all_pin_nets:
                lines.append("## No Connections Found")
                lines.append(f"No network connections found for component {reference}.")
            else:
                lines.append(f"## All Pin Connections ({len(all_pin_nets)} pins)")
                for pin_num in sorted(all_pin_nets.keys()):
                    lines.append("")
                    lines.append(f"### Pin {pin_num}")
                    for pin_net in all_pin_nets[pin_num]:
                        lines.append(f"**Net:** {pin_net['net']}")
                        if pin_net['connections']:
                            lines.append(f"**Connected to ({len(pin_net['connections'])} pins):**")
                            for ref, pin in pin_net['connections'][:15]:
                                lines.append(f"  - {ref}:{pin}")
                            if len(pin_net['connections']) > 15:
                                lines.append(f"  - ... and {len(pin_net['connections']) - 15} more")
                        else:
                            lines.append("**No external connections**")

        # Search in sub-sheets
        if sheets:
            lines.extend([
                "",
                "## Sub-Sheet Search",
                ""
            ])

            project_dir = Path(file_path).parent

            for sheet in sheets:
                sheet_path = project_dir / sheet['file']
                if sheet_path.exists():
                    try:
                        sheet_parser = SchematicParser(str(sheet_path))
                        sheet_components = sheet_parser.get_components()
                        sheet_nets = sheet_parser.get_nets()

                        # Search for component in subsheet
                        sheet_target = None
                        for component in sheet_components:
                            if component.reference == reference:
                                sheet_target = component
                                break

                        if sheet_target:
                            lines.append(f"### Found in {sheet['name']}")
                            lines.append(f"**Value:** {sheet_target.value}")
                            lines.append(f"**Location:** {sheet['file']}")

                            # Find connections in subsheet
                            if pin_number:
                                for net in sheet_nets:
                                    for pin in net.pins:
                                        if pin.reference == reference and pin.pin == pin_number:
                                            lines.append(f"**Pin {pin_number} Net:** {net.name}")
                                            connections = [(p.reference, p.pin) for p in net.pins if p.reference != reference]
                                            if connections:
                                                lines.append("**Connections:**")
                                                for ref, pin in connections[:10]:
                                                    lines.append(f"  - {ref}:{pin}")
                                            break

                    except Exception as e:
                        lines.append(f"### {sheet['name']}")
                        lines.append(f"Error analyzing sheet: {e}")

        return "\n".join(lines)

    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def analyze_hierarchical_nets(
    file_path: str,
    filter_pattern: str = "",
    show_hierarchy: bool = True
) -> str:
    """Analyze all nets in hierarchical schematic design.

    This tool analyzes network connections across the entire hierarchy,
    showing how signals flow between main schematic and sub-sheets.

    Args:
        file_path: Path to main .kicad_sch file
        filter_pattern: Optional regex pattern to filter net names
        show_hierarchy: Whether to show hierarchical structure (default: True)

    Returns:
        Complete hierarchical net analysis
    """
    try:
        parser = SchematicParser(file_path)
        nets = parser.get_nets()
        sheets = parser.get_sheets()

        # Collect all nets from hierarchy
        hierarchical_nets = {}

        # Add main schematic nets
        for net in nets:
            net_name = net.name
            if filter_pattern and filter_pattern not in net_name:
                continue

            hierarchical_nets[net_name] = {
                'location': 'Main Schematic',
                'pins': list(net.pins),
                'sub_nets': []
            }

        # Add sub-sheet nets
        if sheets:
            project_dir = Path(file_path).parent

            for sheet in sheets:
                sheet_path = project_dir / sheet['file']
                if sheet_path.exists():
                    try:
                        sheet_parser = SchematicParser(str(sheet_path))
                        sheet_nets = sheet_parser.get_nets()

                        for net in sheet_nets:
                            net_name = net.name
                            if filter_pattern and filter_pattern not in net_name:
                                continue

                            # Check if this net already exists in main schematic
                            if net_name in hierarchical_nets:
                                hierarchical_nets[net_name]['sub_nets'].append({
                                    'location': sheet['name'],
                                    'pins': list(net.pins)
                                })
                            else:
                                hierarchical_nets[net_name] = {
                                    'location': sheet['name'],
                                    'pins': list(net.pins),
                                    'sub_nets': []
                                }

                    except Exception:
                        # Skip sheets that can't be parsed
                        continue

        if not hierarchical_nets:
            return f"# No Nets Found\n\nNo nets found matching pattern: {filter_pattern if filter_pattern else 'all'}"

        # Format results
        lines = [
            "# Hierarchical Net Analysis",
            "",
            f"**File:** {file_path}",
            f"**Total nets:** {len(hierarchical_nets)}",
            f"**Filter:** {filter_pattern if filter_pattern else 'none'}",
            f"**Hierarchical sheets:** {len(sheets)}",
            "",
            "## Network Summary",
            ""
        ]

        # Group nets by type
        power_nets = []
        signal_nets = []
        interface_nets = []

        for net_name, net_info in hierarchical_nets.items():
            net_upper = net_name.upper()
            if any(p in net_upper for p in ['VDD', 'VSS', 'GND', 'VCC', 'VBAT', 'VPP', '+3V', '+5V']):
                power_nets.append((net_name, net_info))
            elif any(i in net_upper for i in ['I2C', 'SPI', 'UART', 'SDA', 'SCL', 'MOSI', 'MISO', 'TX', 'RX']):
                interface_nets.append((net_name, net_info))
            else:
                signal_nets.append((net_name, net_info))

        # Display power nets
        if power_nets:
            lines.append("### Power Nets")
            for net_name, net_info in sorted(power_nets)[:20]:
                lines.append(f"**{net_name}** ({net_info['location']})")
                lines.append(f"  Connections: {len(net_info['pins'])} pins")
                if show_hierarchy and net_info['sub_nets']:
                    lines.append(f"  Sub-sheets: {len(net_info['sub_nets'])}")
                lines.append("")

        # Display interface nets
        if interface_nets:
            lines.append("### Interface Nets")
            for net_name, net_info in sorted(interface_nets)[:30]:
                lines.append(f"**{net_name}** ({net_info['location']})")
                lines.append(f"  Connections: {len(net_info['pins'])} pins")
                if show_hierarchy and net_info['sub_nets']:
                    lines.append(f"  Sub-sheets: {len(net_info['sub_nets'])}")
                lines.append("")

        # Display signal nets (limited)
        if signal_nets:
            lines.append(f"### Signal Nets (showing first 20 of {len(signal_nets)})")
            for net_name, net_info in sorted(signal_nets)[:20]:
                lines.append(f"**{net_name}** ({net_info['location']})")
                lines.append(f"  Connections: {len(net_info['pins'])} pins")
                if show_hierarchy and net_info['sub_nets']:
                    lines.append(f"  Sub-sheets: {len(net_info['sub_nets'])}")
                lines.append("")

            if len(signal_nets) > 20:
                lines.append(f"*... and {len(signal_nets) - 20} more signal nets*")

        return "\n".join(lines)

    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except Exception as e:
        return f"Error: {e}"
