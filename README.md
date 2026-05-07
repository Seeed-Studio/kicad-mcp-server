# KiCad MCP Server

A Model Context Protocol (MCP) server for KiCad 9.0+ EDA software.

## Features

- **Schematic Analysis** - List components, nets, search symbols
- **PCB Analysis** - Footprints, tracks, statistics via pcbnew API
- **Netlist Tracing** - 100% accurate pin-level connection tracking
- **Design Validation** - ERC/DRC checking via kicad-cli (headless)
- **Pin Analysis** - Pin function detection, conflict analysis, pinmux config
- **Code Generation** - Device tree (.dts) and hardware test code generation
- **Project Management** - Create and manage KiCad projects

## Requirements

- Python 3.10+
- KiCad 8.0+ (9.0+ recommended)

## Installation

```bash
git clone https://github.com/Seeed-Studio/kicad-mcp-server.git
cd kicad-mcp-server
pip install -e .
```

## Configuration

Add to your MCP client config (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "kicad": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "kicad_mcp_server"],
      "cwd": "/path/to/kicad-mcp-server"
    }
  }
}
```

## Quick Start

```python
# Analyze schematic
list_schematic_components("board.kicad_sch")
list_schematic_nets("board.kicad_sch")

# Generate and parse netlist
generate_netlist("board.kicad_sch")
trace_netlist_connection("board.net.xml", "U1", pin_number="3")

# Run design checks
run_erc("board.kicad_sch")
run_drc("board.kicad_pcb")

# Analyze PCB
get_pcb_statistics("board.kicad_pcb")
list_pcb_footprints("board.kicad_pcb")

# Create project and add components
create_kicad_project("/projects/MyDesign", "MyDesign")
add_component_from_library("MyDesign.kicad_sch", "Device", "R", "R1", "10k")
```

## Editing Limitations

Schematic editing tools are **experimental**. KiCad has no Python API for schematic editing, so tools use manual S-expression manipulation. Components added via `add_component_from_library` now automatically insert symbol definitions from KiCad's library files, but wire connections and visual alignment may not be perfect.

**Recommendation**: Use KiCad GUI for design work. Use MCP server for analysis, validation, and code generation.

## Architecture

```
FastMCP Server
    ├── tools/          # MCP tool implementations
    │   ├── schematic.py
    │   ├── pcb.py
    │   ├── netlist.py
    │   ├── schematic_editor.py
    │   ├── pcb_layout.py
    │   └── project.py
    ├── parsers/        # File format parsers
    └── utils/          # KiCad version detection
```

## Resources

- [KiCad Documentation](https://docs.kicad.org/)
- [KiCad File Format Spec](https://dev-docs.kicad.org/en/file-formats/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## Acknowledgments

Thanks to all contributors and community feedback:
- [@raffaeler](https://github.com/raffaeler) for KiCad 10 compatibility testing and feedback (#9)
- [@shivam5594](https://github.com/shivam5594) for Python 3.14 install issue report (#11)
- [@derekc00](https://github.com/derekc00) for lint fixes (#10)

## License

MIT
