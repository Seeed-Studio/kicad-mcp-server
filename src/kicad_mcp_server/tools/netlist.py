"""Netlist generation and analysis tools for KiCad MCP Server."""

import subprocess
from pathlib import Path
from typing import Optional
from ..server import mcp
from ..parsers.netlist_parser import NetlistParser


def _find_root_schematic(sch_path: Path) -> Optional[Path]:
    """If sch_path is a sub-sheet, return the root schematic instead.

    KiCad convention: root schematic has the same stem as the .kicad_pro file.
    Sub-sheets lack the hierarchy context needed to resolve unnamed wire-only
    nets, so we redirect to the root schematic for complete netlist export.
    """
    pro_files = list(sch_path.parent.glob("*.kicad_pro"))
    if len(pro_files) != 1:
        return None
    root_sch = pro_files[0].with_suffix(".kicad_sch")
    if root_sch.exists() and root_sch.resolve() != sch_path.resolve():
        return root_sch
    return None


@mcp.tool()
async def generate_netlist(
    schematic_path: str,
) -> str:
    """Generate KiCad netlist from schematic file.

    Args:
        schematic_path: Path to .kicad_sch file

    Returns:
        Path to generated .xml netlist file
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ Schematic file not found: {schematic_path}"

        # Detect sub-sheet and redirect to root schematic.
        # Sub-sheets lack hierarchy context to resolve unnamed wire-only nets.
        subsheet_note = ""
        root_sch = _find_root_schematic(sch_path)
        if root_sch:
            subsheet_note = (
                f"\n\n⚠️ **Note:** `{sch_path.name}` is a hierarchical sub-sheet. "
                f"Switched to root schematic `{root_sch.name}` for complete netlist "
                f"(unnamed wire-only nets require full hierarchy context to resolve)."
            )
            sch_path = root_sch

        # KiCad 7+ uses kicad-cli for headless netlist export
        # Output to /tmp to avoid read-only volume issues
        netlist_path = Path("/tmp") / (sch_path.stem + ".xml")

        # Try to use KiCad's netlist export
        # Note: This requires KiCad to be installed and in PATH
        try:
            # Use kicad-cli for headless export (no display required)
            cmd = [
                "kicad-cli",
                "sch",
                "export",
                "netlist",
                "--format",
                "kicadxml",
                "--output",
                str(netlist_path),
                str(sch_path),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and netlist_path.exists():
                return f"""✅ Netlist generated successfully

**Output:** {netlist_path}

You can now use netlist-based tools:
- `trace_netlist_connection()` - Trace component connections via netlist
- `get_netlist_nets()` - List all nets
- `get_netlist_components()` - List all components with their nets
{subsheet_note}"""
            else:
                # Fallback: return instructions
                return f"""⚠️ Automatic netlist generation failed.

KiCad command line tools may not be available.

**Manual export steps:**
1. Open schematic in KiCad: {sch_path}
2. Go to: Tools → Generate Netlist
3. Select: "KiCad XML" format
4. Save to: {netlist_path}

**Alternative:**
Use KiCad Schematic Editor GUI to export netlist.
"""

        except FileNotFoundError:
            return """⚠️ kicad-cli not found in PATH.

Please:
1. Install KiCad 7+ (https://www.kicad.org/)
2. Ensure kicad-cli is in system PATH
3. Or use KiCad GUI to export netlist manually

**Manual export:**
Open schematic → Tools → Generate Netlist → KiCad XML format
"""

    except Exception as e:
        return f"❌ Error generating netlist: {e}"


@mcp.tool()
async def trace_netlist_connection(
    netlist_path: str,
    reference: str,
    pin_number: str = "",
) -> str:
    """Trace component connections using netlist file (most accurate).

    Args:
        netlist_path: Path to .xml netlist file
        reference: Component reference (e.g., 'R16')
        pin_number: Optional pin number (e.g., '1'). If empty, trace all pins.

    Returns:
        Detailed connection information from netlist
    """
    try:
        parser = NetlistParser(netlist_path)

        if pin_number:
            result = parser.trace_connection(reference, pin_number)

            if "error" in result:
                return f"❌ {result['error']}"

            lines = [
                f"## Netlist Connection Trace: {reference}",
                "",
                f"**Pin:** {result['pin']}",
                f"**Net:** {result['net']}",
                "",
                "### Connected Components:",
                "",
            ]

            if result['connected_to']:
                lines.append("| Reference | Pin |")
                lines.append("|-----------|-----|")
                for ref, pin in result['connected_to']:
                    lines.append(f"| {ref} | {pin} |")
            else:
                lines.append("No other components on this net.")

            return "\n".join(lines)

        else:
            result = parser.trace_connection(reference)

            if "error" in result:
                return f"❌ {result['error']}"

            lines = [
                f"## Netlist Connection Trace: {reference}",
                "",
                f"**Total Nets:** {len(result['nets'])}",
                "",
            ]

            for net_name, net_info in result['nets'].items():
                lines.append(f"### Net: {net_name}")
                lines.append(f"**Pin:** {net_info['pin']}")
                lines.append("")

                if net_info['connected_to']:
                    lines.append("| Reference | Pin |")
                    lines.append("|-----------|-----|")
                    for ref, pin in net_info['connected_to']:
                        lines.append(f"| {ref} | {pin} |")
                else:
                    lines.append("No other components on this net.")

                lines.append("")

            return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ File not found: {e}"
    except Exception as e:
        return f"❌ Error tracing netlist: {e}"


@mcp.tool()
async def get_netlist_nets(
    netlist_path: str,
    filter_pattern: str = "",
) -> str:
    """Get all nets from netlist file.

    Args:
        netlist_path: Path to .xml netlist file
        filter_pattern: Optional regex pattern to filter net names

    Returns:
        List of all nets with their connections
    """
    try:
        parser = NetlistParser(netlist_path)
        nets = parser.get_nets()

        lines = [
            f"## Nets from Netlist: {netlist_path}",
            "",
            f"**Total Nets:** {len(nets)}",
            "",
        ]

        for net_name, net in sorted(nets.items()):
            if filter_pattern:
                import re
                if not re.search(filter_pattern, net_name, re.IGNORECASE):
                    continue

            lines.append(f"### {net_name}")
            lines.append(f"**Code:** {net.code}")
            lines.append(f"**Connections:** {len(net.pins)} pins")

            if net.pins:
                lines.append("")
                lines.append("| Reference | Pin |")
                lines.append("|-----------|-----|")
                for ref, pin in net.pins[:10]:  # Show first 10
                    lines.append(f"| {ref} | {pin} |")
                if len(net.pins) > 10:
                    lines.append(f"| ... | ({len(net.pins) - 10} more) |")

            lines.append("")

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ File not found: {e}"
    except Exception as e:
        return f"❌ Error reading netlist: {e}"


@mcp.tool()
async def get_netlist_components(
    netlist_path: str,
    filter_ref: str = "",
) -> str:
    """Get all components from netlist with their network connections.

    Args:
        netlist_path: Path to .xml netlist file
        filter_ref: Optional reference filter (e.g., 'R', 'U', 'C')

    Returns:
        List of components with their net connections
    """
    try:
        parser = NetlistParser(netlist_path)
        components = parser.get_components()

        lines = [
            f"## Components from Netlist: {netlist_path}",
            "",
            f"**Total Components:** {len(components)}",
            "",
        ]

        for ref, comp in sorted(components.items()):
            if filter_ref and not ref.startswith(filter_ref):
                continue

            lines.append(f"### {ref}")
            lines.append(f"**Value:** {comp.value}")
            lines.append(f"**Library:** {comp.library}")
            if comp.footprint:
                lines.append(f"**Footprint:** {comp.footprint}")

            if comp.pins:
                lines.append("")
                lines.append("**Pin Connections:**")
                lines.append("")
                lines.append("| Pin | Net |")
                lines.append("|-----|-----|")
                for pin_num, net_name in sorted(comp.pins.items()):
                    lines.append(f"| {pin_num} | {net_name} |")

            lines.append("")

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ File not found: {e}"
    except Exception as e:
        return f"❌ Error reading netlist: {e}"
