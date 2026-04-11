"""PCB analysis tools for KiCad MCP Server."""

from ..parsers.pcb_parser import PCBParser
from ..server import mcp


@mcp.tool()
async def list_pcb_footprints(
    file_path: str,
    filter_layer: str | None = None,
) -> str:
    """List all footprints in a KiCad PCB file.

    Args:
        file_path: Path to .kicad_pcb file
        filter_layer: Optional filter by layer (e.g., 'F.Cu', 'B.Cu')

    Returns:
        Formatted list of footprints
    """
    try:
        parser = PCBParser(file_path)
        footprints = parser.get_footprints()

        # Apply layer filter
        if filter_layer:
            footprints = [f for f in footprints if f.layer == filter_layer]

        if not footprints:
            return "No footprints found."

        # Format output
        lines = [
            f"# Footprints in {file_path}",
            f"Total: {len(footprints)} footprint(s)",
            "",
            "| Reference | Value | Footprint | Layer | Position | Rotation | Pads |",
            "|-----------|-------|-----------|-------|----------|----------|------|",
        ]

        for fp in footprints:
            fp_name = fp.footprint_id.split(":")[-1] if ":" in fp.footprint_id else fp.footprint_id
            pos_str = f"({fp.position[0]:.2f}, {fp.position[1]:.2f})"
            lines.append(
                f"| {fp.reference} | {fp.value} | {fp_name} | {fp.layer} | {pos_str} | {fp.rotation:.1f}° | {fp.pad_count} |"
            )

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


@mcp.tool()
async def get_pcb_statistics(file_path: str) -> str:
    """Get statistics about a KiCad PCB design.

    Args:
        file_path: Path to .kicad_pcb file

    Returns:
        PCB statistics and metrics
    """
    try:
        parser = PCBParser(file_path)
        stats = parser.get_statistics()

        # Format output
        lines = [
            f"# PCB Statistics: {file_path}",
            "",
            "## Board Information",
            f"**Dimensions:** {stats['board_width']:.2f} x {stats['board_height']:.2f} mm",
            f"**Layers:** {stats['layers']}",
            f"**Thickness:** {stats['thickness']:.2f} mm",
            "",
            "## Elements",
            f"**Footprints:** {stats['total_footprints']}",
            f"**Total Pads:** {stats['total_pads']}",
            f"**Track Segments:** {stats['total_tracks']}",
            f"**Vias:** {stats['total_vias']}",
            f"**Copper Zones:** {stats['total_zones']}",
            "",
            "## Averages",
            f"**Pads per Footprint:** {stats['total_pads'] / max(stats['total_footprints'], 1):.1f}",
        ]

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


@mcp.tool()
async def analyze_pcb_nets(file_path: str) -> str:
    """Analyze nets in a KiCad PCB file.

    Args:
        file_path: Path to .kicad_pcb file

    Returns:
        Net information from PCB
    """
    try:
        parser = PCBParser(file_path)
        stats = parser.get_statistics()

        # Format output
        lines = [
            f"# PCB Net Analysis: {file_path}",
            "",
            "This tool provides basic net information. ",
            "For detailed net connectivity analysis, use the schematic tools.",
            "",
            "## Summary",
            f"**Copper Zones:** {stats['total_zones']} zones defined",
        ]

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


@mcp.tool()
async def find_tracks_by_net(file_path: str, net_name: str) -> str:
    """Find track segments belonging to a specific net.

    Args:
        file_path: Path to .kicad_pcb file
        net_name: Name of the net to search for

    Returns:
        Track information for the specified net
    """
    try:
        parser = PCBParser(file_path)
        data = parser._parse_file()

        # Note: This is a simplified implementation
        # In production, use kicad-skip for proper net-to-track mapping
        lines = [
            f"# Tracks for net: {net_name}",
            "",
            "Track analysis requires kicad-skip library integration.",
            f"Total track segments in design: {len(data['tracks'])}",
            "",
            "For detailed track analysis, use the KiCad PCB editor or integrate kicad-skip.",
        ]

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"
