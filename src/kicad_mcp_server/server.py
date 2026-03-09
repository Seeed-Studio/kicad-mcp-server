"""Main MCP server setup for KiCad integration."""

from fastmcp import FastMCP
from typing import Optional

from .config import config

# Create MCP server
mcp = FastMCP(
    name="kicad-mcp-server",
    instructions="""KiCad MCP Server - A server for analyzing KiCad schematics and PCBs,
    generating test code, and performing design rule checks.

    Available capabilities:
    - Schematic analysis (components, nets, symbols)
    - PCB analysis (footprints, tracks, statistics)
    - Design rule checking (ERC/DRC)
    - Schematic summarization
    - Test code generation for multiple frameworks
    """,
)


# Import and register tools
from .tools import (
    project,
    schematic,
    schematic_editor,
    pcb,
    pcb_layout,
    netlist,
    validation,
    pin_analysis,
    device_tree,
    test_generation,
)

# Resources
@mcp.resource("kicad://config")
def get_config() -> dict:
    """Get current server configuration."""
    return {
        "project_paths": config.kicad_project_paths,
        "default_summary_detail_level": config.default_summary_detail_level,
        "include_nets_in_summary": config.include_nets_in_summary,
        "include_power_in_summary": config.include_power_in_summary,
        "default_test_framework": config.default_test_framework,
        "default_test_type": config.default_test_type,
    }


def create_server() -> FastMCP:
    """Create and configure the MCP server instance.

    Returns:
        Configured FastMCP server instance
    """
    return mcp


def get_server() -> FastMCP:
    """Get the singleton MCP server instance.

    Returns:
        The FastMCP server instance
    """
    return mcp
