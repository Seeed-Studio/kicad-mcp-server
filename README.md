# KiCad MCP Server

A Model Context Protocol (MCP) server for KiCad 9.0+ that lets AI assistants analyze schematics, inspect PCBs, trace connections, validate designs, and generate embedded code.

## Features

- **Schematic Analysis** - Components, nets, symbols, hierarchical sheets
- **PCB Analysis** - Footprints, tracks, routing quality, signal/power integrity via pcbnew API
- **Netlist Tracing** - 100% accurate pin-level connection tracking
- **Design Validation** - ERC/DRC via kicad-cli (headless, CI friendly)
- **Pin Analysis** - Pin function detection, conflict analysis, pinmux config
- **Code Generation** - Device tree (.dts) and hardware test code generation
- **Project Management** - Create KiCad projects from templates
- **Parts Registry** - Search 21,000+ verified parts on an open, no-login registry ([PartReel](https://partreel.com) by default, `PARTS_REGISTRY_URL` to change) and download footprints/symbols/3D into the project; downloads are host-allowlisted, extension-checked and size-capped

## Requirements

- KiCad 8.0+ (9.0 or 10.0 recommended)
- `kicad-cli` in PATH (included with KiCad)

## Installation

### Recommended: Install into KiCad Python (Full PCB Analysis)

KiCad ships with its own Python that includes the `pcbnew` module. Installing into this Python gives you full PCB analysis capabilities (precise track lengths, via statistics, signal integrity, power integrity).

**Step 1**: Find your KiCad Python path:

| Platform | Path |
|----------|------|
| Windows | `C:\Program Files\KiCad\<version>\bin\python.exe` |
| macOS | `/Applications/KiCad/KiCad.app/Contents/Frameworks/python3` |
| Linux | `/usr/bin/python3` (if kicad python bindings installed) |

**Step 2**: Install the package into KiCad Python:

```bash
# Windows example (KiCad 10.0)
"C:\Program Files\KiCad\10.0\bin\python.exe" -m pip install fastmcp
"C:\Program Files\KiCad\10.0\bin\python.exe" -m pip install -e .

# macOS example
/Applications/KiCad/KiCad.app/Contents/Frameworks/python3 -m pip install fastmcp
/Applications/KiCad/KiCad.app/Contents/Frameworks/python3 -m pip install -e .
```

**Step 3**: Configure MCP to use KiCad Python (see Configuration section below).

### Fallback: Install into System Python (Limited PCB Analysis)

If you skip KiCad Python setup, the server still works but falls back to text-based PCB parsing. You get basic data (track counts, net names, widths) but lose precise lengths, design rules, and signal integrity analysis.

```bash
pip install -e .
```

## Configuration

### Claude Desktop

Edit your config file:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

**With KiCad Python (recommended):**

```json
{
  "mcpServers": {
    "kicad": {
      "type": "stdio",
      "command": "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe",
      "args": ["-m", "kicad_mcp_server"],
      "cwd": "C:\\Users\\YourName\\Desktop\\kicad-mcp-server"
    }
  }
}
```

**With system Python (fallback):**

```json
{
  "mcpServers": {
    "kicad": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "kicad_mcp_server"],
      "cwd": "C:\\Users\\YourName\\Desktop\\kicad-mcp-server"
    }
  }
}
```

### Claude Code CLI

```bash
# With KiCad Python (recommended)
claude mcp add kicad -s user -- "C:\Program Files\KiCad\10.0\bin\python.exe" -m kicad_mcp_server

# With system Python (fallback)
claude mcp add kicad -s user -- python -m kicad_mcp_server
```

### Cursor / Windsurf / Other MCP Clients

Use the same config structure with your client's MCP settings. Point `command` to KiCad Python for full analysis, or `python` for fallback mode.

### Verify Installation

After restarting your AI client, ask it:

> "What tools are available for KiCad?"

You should see a list of KiCad MCP tools. To verify pcbnew is working:

> "Get PCB statistics for MyBoard.kicad_pcb"

If the response shows **Design Rules** section with clearance/width values, pcbnew is active. If it shows **board dimensions as approximation**, you're in text-only mode.

Common issues:
1. KiCad is installed and `kicad-cli` is accessible
2. The `cwd` path in your config points to the correct directory
3. Python can import the package (`python -c "import kicad_mcp_server"`)

## Usage

Once configured, you can interact with your KiCad projects through natural language in your AI assistant. Below are common workflows.

### 1. Analyze a Schematic

Point the AI to your `.kicad_sch` file and ask questions:

> "List all components in C:\Projects\MyBoard\MyBoard.kicad_sch"

> "Show me all the power nets in MyBoard.kicad_sch"

> "Find all resistors with value 10k"

The AI will call tools like `list_schematic_components`, `list_schematic_nets`, `search_symbols` behind the scenes.

### 2. Trace Connections (Netlist-based)

First export a netlist, then trace connections with pin-level accuracy:

> "Generate a netlist from MyBoard.kicad_sch"

> "Trace all connections from U1"

> "What pins are connected to the I2C_SDA net?"

This uses `generate_netlist` and `trace_netlist_connection` for 100% accurate results.

### 3. Validate Your Design

Run electrical and design rule checks:

> "Run ERC on MyBoard.kicad_sch and show me any errors"

> "Run DRC on MyBoard.kicad_pcb"

> "Are there any unconnected pins?"

Uses `run_erc`, `run_drc`, and `detect_pin_conflicts`.

### 4. Analyze PCB

> "Get statistics for MyBoard.kicad_pcb"

> "List all footprints on the top layer"

> "Find all tracks on the VDD_nRF net"

> "Analyze PCB routing quality"

> "Check signal integrity - are USB differential pairs length-matched?"

> "Analyze power integrity - how's the GND coverage?"

### 5. Create a New Project

> "Create a new KiCad project called LED_Blinker in C:\Projects"

> "Add a 1k resistor called R1 to the schematic"

> "Add an LED called D1"

> "Add a wire from R1 pin 2 to D1 pin 1"

### 6. Pin Analysis and Code Generation

> "Analyze pin functions for U1 in MyBoard.kicad_sch"

> "Detect any pin conflicts in the design"

> "Generate a device tree file for the STM32 on this board"

> "Generate pytest hardware tests for all I2C devices"

## Available Tools Reference

### Schematic Analysis

| Tool | Description |
|------|-------------|
| `list_schematic_components` | List components with filtering by type, value, or DNP status |
| `list_schematic_nets` | List all nets, optionally filter power nets |
| `get_schematic_info` | Project metadata and statistics |
| `search_symbols` | Search components by pattern (regex) |
| `get_symbol_details` | Detailed info for a specific component |

### PCB Analysis

| Tool | Description |
|------|-------------|
| `list_pcb_footprints` | List footprints with optional layer filter |
| `get_pcb_statistics` | Board dimensions, layer count, design rules |
| `find_tracks_by_net` | Track segments, lengths, widths, vias for a specific net |
| `analyze_pcb_nets` | Routing analysis: width/via distribution, net length ranking |
| `analyze_pcb_signal_integrity` | Diff pair matching, RF traces, longest signal nets |
| `analyze_pcb_power_integrity` | Power zones, GND coverage, power routing analysis |

### Netlist Analysis

| Tool | Description |
|------|-------------|
| `generate_netlist` | Export netlist from schematic via kicad-cli |
| `trace_netlist_connection` | Trace all connections from a component/pin |
| `get_netlist_nets` | List all nets with pin connections |
| `get_netlist_components` | List components with their net connections |

### Validation

| Tool | Description |
|------|-------------|
| `run_erc` | Electrical Rules Check on schematic |
| `run_drc` | Design Rules Check on PCB |
| `detect_pin_conflicts` | Find conflicting pin connections |

### Editing

| Tool | Description |
|------|-------------|
| `create_kicad_project` | Create project from KiCad template |
| `add_component_from_library` | Add component with symbol from library |
| `add_wire` | Add wire connection |
| `add_label` | Add local label |
| `setup_pcb_layout` | Initialize PCB with dimensions |
| `export_gerber` | Export Gerber files |

## Editing Limitations

Schematic editing is **experimental**. KiCad has no Python API for schematic editing, so tools use manual S-expression manipulation. When adding components via `add_component_from_library`, the tool automatically reads the symbol definition from KiCad's library files and inserts it into the schematic — this ensures proper rendering.

Known limitations:
- Wire connections may not form perfect electrical connections
- Visual alignment is basic
- KiCad must be closed and reopened to see file changes (no hot-reload)

**Recommendation**: Use KiCad GUI for design work. Use this MCP server for analysis, validation, and code generation.

## Troubleshooting

### "KiCad template not found"

Make sure KiCad is installed at the standard path:
- **Windows**: `C:\Program Files\KiCad\<version>\`
- **macOS**: `/Applications/KiCad/`
- **Linux**: `/usr/share/kicad/`

### "kicad-cli not found"

Add KiCad's bin directory to your PATH:
```bash
# Windows example
set PATH=%PATH%;C:\Program Files\KiCad\10.0\bin

# Linux/macOS example
export PATH="/usr/bin:$PATH"
```

### "pcbnew module not found" / PCB analysis is limited

pcbnew is only available in KiCad's bundled Python. Two options:

**Option A (recommended)**: Configure MCP to use KiCad Python — see [Installation](#recommended-install-into-kicad-python-full-pcb-analysis).

**Option B**: Accept text-only mode. You'll still get basic PCB data (footprints, track counts, net names) but without precise lengths or design rules.

### Python 3.14 install fails

Make sure you have `pip >= 26.0`:
```bash
pip install --upgrade pip
pip install -e .
```

## Resources

- [KiCad Documentation](https://docs.kicad.org/)
- [KiCad File Format Spec](https://dev-docs.kicad.org/en/file-formats/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [kicad-cli Documentation](https://docs.kicad.org/en/cli/)

## Acknowledgments

Thanks to all contributors and community feedback:
- [@raffaeler](https://github.com/raffaeler) for KiCad 10 compatibility testing and feedback (#9)
- [@shivam5594](https://github.com/shivam5594) for Python 3.14 install issue report (#11)
- [@derekc00](https://github.com/derekc00) for lint fixes (#10)
- [@befedo](https://github.com/befedo) for SchematicComponent dataclass access bug report and patch (#13)

## License

MIT
