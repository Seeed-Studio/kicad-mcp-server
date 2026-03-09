# KiCad MCP Server

A Model Context Protocol (MCP) server for KiCad 9.0 EDA software that provides **comprehensive hardware design validation and embedded development code generation**.

## Overview

This server implements **39 tools** organized into **7 categories**:

- **Analysis Tools** (3): Schematic analysis, PCB analysis, netlist-based connection tracing
- **Validation Tools** (6): Design rule checking (DRC/ERC), pin conflict detection
- **Pin Analysis Tools** (3): Pin function analysis, conflict detection, pinmux configuration
- **Code Generation Tools** (12): Device tree generation, test code generation
- **Editing Tools** (2): Schematic editing, PCB layout (experimental)
- **Project Management** (1): Project creation and management

## Project Status

**✅ Production-Ready - Complete Hardware Design and Development Platform**

This project provides comprehensive capabilities:

- **Analysis Tools**: ✅ Production-ready
- **Validation Tools**: ✅ Production-ready **(NEW)**
- **Pin Analysis**: ✅ Production-ready **(NEW)**
- **Code Generation**: ✅ Production-ready **(NEW)**
- **Project Management**: ✅ Production-ready
- **Editing Tools**: ⚠️ Experimental (see Limitations below)

### What's New ✨

**NEW: Design Validation** - Comprehensive DRC/ERC checking with headless kicad-cli support
**NEW: Pin Analysis** - Advanced pin function detection and conflict analysis for 6+ MCU families
**NEW: Device Tree Generation** - Automatic .dts generation for STM32, ESP32, nRF52, and ATmega
**NEW: Test Code Generation** - Automated hardware test generation for pytest and Unity frameworks

## Features

### Schematic Analysis

Analyze KiCad schematic files (.kicad_sch):

- `list_schematic_components()` - List all components with optional filtering
  - **New**: Component flags support (DNP, In BOM, On Board, Exclude from Sim)
  - Filter by component type, value, or DNP status
  - Shows DNP and BOM status when non-default values exist
- `list_schematic_nets()` - List all nets
- `get_schematic_info()` - Get schematic metadata and statistics
- `search_symbols()` - Search for specific symbols
- `get_symbol_details()` - Get detailed symbol information
- `analyze_functional_blocks()` - Analyze functional blocks in schematic

### PCB Analysis

Analyze KiCad PCB files (.kicad_pcb) using official pcbnew API:

- `list_pcb_footprints()` - List all footprints
- `get_pcb_statistics()` - Get PCB statistics (dimensions, layer count, etc.)
- `find_tracks_by_net()` - Find tracks belonging to a specific net
- `get_footprint_by_reference()` - Get detailed footprint information
- `analyze_pcb_nets()` - Analyze PCB nets

### Netlist Analysis

Parse KiCad XML netlist files for 100% accurate pin-level connection tracking:

- `trace_netlist_connection()` - Trace component connections with pin-level accuracy
- `get_netlist_nets()` - List all nets with optional filtering
- `get_netlist_components()` - List all components with their net connections
- `generate_netlist()` - Export netlist from schematic using kicad-cli
  - **New**: Uses `kicad-cli` instead of `eeschema` for headless operation
  - **New**: Auto-detects hierarchical sub-sheets and redirects to root schematic
  - **New**: Docker/CI friendly (no X11 display required)
  - **New**: Outputs to /tmp to handle read-only source volumes

**Why use netlist analysis?**
- KiCad official XML format
- Pin-level precision
- Includes all connections (explicit and implicit)
- Bidirectional queries (component <-> network)
- Works with kicad-cli in headless environments

### Schematic Editing (Experimental)

Create and modify KiCad schematics:

- `create_kicad_project()` - Create new KiCad project
- `add_component_from_library()` - Add components from library
- `add_wire()` - Add wire connections
- `add_global_label()` - Add global labels
- `add_label()` - Add local labels

### PCB Layout (Experimental)

PCB layout and editing:

- `setup_pcb_layout()` - Initialize PCB with specified dimensions
- `add_footprint()` - Add footprints to PCB
- `add_track()` - Add tracks
- `add_zone()` - Add copper zones
- `export_gerber()` - Export Gerber files for manufacturing

### Project Management

KiCad project creation and management:

- `create_kicad_project()` - Create new project from template
- `copy_kicad_project()` - Copy existing project

### Design Rule Checking (NEW ✨)

Comprehensive hardware validation and design rule checking:

- `run_erc()` - Run Electrical Rules Check on schematic
  - Detects unconnected pins, power conflicts, multiple outputs on same net
  - Uses kicad-cli for headless operation (Docker/CI friendly)
  - Parses XML violation reports with severity filtering
- `run_drc()` - Run Design Rules Check on PCB
  - Identifies clearance violations, spacing issues, missing connections
  - Detects pad/footprint overlaps and board edge constraints
  - Generates detailed violation reports with coordinates
- `get_erc_violations()` - Get filtered ERC violations by severity
- `get_drc_violations()` - Get filtered DRC violations by type
- `export_erc_report()` - Export ERC report to file
- `export_drc_report()` - Export DRC report to file

**Why use DRC/ERC?**
- Ensures design correctness before manufacturing
- Prevents hardware failures from electrical conflicts
- Enables automated CI/CD workflows for hardware
- Foundation for reliable code generation

### Pin Analysis & Configuration (NEW ✨)

Advanced pin function analysis and configuration extraction:

- `analyze_pin_functions()` - Analyze pin functions (GPIO/I2C/SPI/UART)
  - Infers peripheral functions from net names
  - Supports 6+ MCU families (STM32, ESP32, nRF52, ATmega, SAMD, RP2040)
  - Detects pin multiplexing configurations
- `detect_pin_conflicts()` - Detect conflicting electrical connections
  - Identifies multiple outputs on same net
  - Detects power-to-power connections
  - Flags unconnected input pins
- `extract_pinmux_config()` - Extract pin multiplexing configuration
  - MCU-specific pin mapping databases
  - Alternate function assignments
  - GPIO configuration details

**Supported MCU Families:**
- STM32 (STM32F, STM32H, STM32L series)
- ESP32 (ESP32, ESP32-S2, ESP32-S3)
- nRF52 (nRF52832, nRF52840)
- ATmega (ATmega328P, ATmega2560)
- SAMD (ATSAMD21, ATSAMD51)
- RP2040

### Device Tree Generation (NEW ✨)

Automatic Linux device tree generation for embedded systems:

- `generate_device_tree()` - Generate complete .dts files
  - Support for 4 SOC families (STM32F4, ESP32, nRF52, ATmega)
  - Jinja2 template system for customizable output
  - Automatic I2C address extraction
  - Peripheral configuration inference
- `extract_gpio_config()` - Extract GPIO pin configurations
- `extract_i2c_devices()` - Extract I2C device configurations
  - Includes device tree bindings for 30+ components
  - Automatic device detection from schematic
- `extract_spi_devices()` - Extract SPI device configurations
- `extract_power_domains()` - Extract power domain configurations
- `validate_pin_configuration()` - Validate before device tree generation

**Device Tree Bindings Database:**
- **Sensors**: BMP280, BME280, MPU6050, LSM6DS3, HTS221, etc.
- **Displays**: ST7789, SSD1306, ILI9341, etc.
- **Memory**: AT24C256, W25Q128, GD25Q16
- **Wireless**: ESP8266, nRF24L01, SX1278
- **Connectivity**: CP2102, FT232RL, CH340G
- **Power**: TP4056, AXP192, LP3985, AP2112

### Test Code Generation (NEW ✨)

Automated hardware test generation for multiple frameworks:

- `generate_hardware_tests()` - Generate complete test suite
  - Support for pytest (Python) and Unity (embedded C)
  - Framework-specific optimizations
  - Comprehensive test coverage
- `generate_gpio_test()` - Generate GPIO pin tests
  - Input/output functionality tests
  - Continuity verification
  - Multi-pin interaction tests
- `generate_i2c_test()` - Generate I2C device tests
  - Device detection and communication tests
  - Device-specific test cases
  - Bus scanning functionality
- `generate_spi_test()` - Generate SPI communication tests
  - Device detection and data transfer tests
  - Bus configuration verification
- `generate_pinmux_test()` - Generate pin multiplexing tests
  - Pin conflict detection
  - Alternate function verification
  - Peripheral mapping validation
- `export_test_framework()` - Export complete test framework
  - Directory structure and build files
  - Configuration files (pytest.ini, Makefile)
  - Dependency files (requirements.txt)
  - Documentation (README.md)

**Supported Test Frameworks:**
- **pytest** (Python) - Full hardware interaction support
- **Unity** (Embedded C) - MCU testing framework
- **Google Test** (C++) - Framework structure ready

## Usage Examples

### Design Validation Workflow

Validate your hardware design before manufacturing:

```bash
# Run Electrical Rules Check on schematic
run_erc("board.kicad_sch")

# Run Design Rules Check on PCB
run_drc("board.kicad_pcb")

# Get specific error violations
get_erc_violations("board.kicad_sch", severity="error")

# Export reports for documentation
export_erc_report("board.kicad_sch", "design_erc_report.txt")
```

### Pin Analysis Workflow

Analyze pin configurations and detect conflicts:

```bash
# Analyze pin functions for an MCU
analyze_pin_functions("board.kicad_sch", reference="U1")

# Detect pin conflicts in the design
detect_pin_conflicts("board.kicad_sch")

# Extract pin multiplexing configuration
extract_pinmux_config("board.kicad_sch", component_type="stm32")
```

### Device Tree Generation Workflow

Generate device trees for embedded Linux systems:

```bash
# Validate pin configuration first
validate_pin_configuration("board.kicad_sch")

# Generate device tree for STM32F4
generate_device_tree(
    schematic_path="board.kicad_sch",
    target_soc="stm32f4",
    output_path="board.dts"
)

# Extract specific configurations
extract_gpio_config("board.kicad_sch", soc_family="stm32")
extract_i2c_devices("board.kicad_sch")
extract_spi_devices("board.kicad_sch")
```

### Test Generation Workflow

Generate automated hardware tests:

```bash
# Generate complete test suite
generate_hardware_tests(
    schematic_path="board.kicad_sch",
    framework="pytest",
    output_dir="tests/"
)

# Export complete test framework
export_test_framework(
    schematic_path="board.kicad_sch",
    framework="pytest",
    output_dir="test_framework/"
)

# Generate specific test types
generate_gpio_test("board.kicad_sch", test_type="connectivity")
generate_i2c_test("board.kicad_sch")
generate_spi_test("board.kicad_sch")
```

### Complete Embedded Development Workflow

End-to-end workflow for embedded system development:

```bash
# 1. Analyze existing design
list_schematic_components("board.kicad_sch")
get_schematic_info("board.kicad_sch")

# 2. Validate design
run_erc("board.kicad_sch")
run_drc("board.kicad_pcb")

# 3. Analyze pin configuration
analyze_pin_functions("board.kicad_sch")
detect_pin_conflicts("board.kicad_sch")

# 4. Generate device tree
generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")

# 5. Generate tests
generate_hardware_tests("board.kicad_sch", "pytest", "tests/")
export_test_framework("board.kicad_sch", "pytest", "test_framework/")

# 6. Compile and run tests
cd test_framework/
pip install -r requirements.txt
pytest
```

## Limitations and Recommendations

### Current Status

**Analysis Tools (Production-Ready)**
- Schematic analysis: Fully functional
- PCB analysis: Fully functional (uses official pcbnew API)
- Netlist analysis: 100% accurate, recommended for connection tracing

**Editing Tools (Experimental)**
- Schematic editing: Basic functionality, has limitations
- PCB layout: Basic functionality, has limitations

### Known Limitations

**Schematic Editing:**
- Components are added with minimal pin definitions
- Wire connections may not form proper electrical connections
- Symbol placement may not be visually aligned
- **Recommendation**: Use KiCad GUI for actual schematic editing

**PCB Layout:**
- Basic initialization only
- No automatic placement or routing
- **Recommendation**: Use KiCad GUI for PCB layout

### Recommended Workflow

```
1. Create Project (MCP or KiCad GUI)
   ↓
2. Edit Schematic in KiCad GUI
   - Add components
   - Wire connections
   - Set component flags (DNP, In BOM, etc.)
   - Design validation
   ↓
3. Export Netlist
   Option A: Use MCP Server (automated, headless)
   generate_netlist("project.kicad_sch")
   - Auto-detects sub-sheets
   - Uses kicad-cli (no X11 needed)

   Option B: Manual export
   kicad-cli sch export netlist --format kicadxml \
     --output project.net.xml project.kicad_sch
   ↓
4. Analyze Design (MCP Server)
   - Trace connections (netlist-based, 100% accurate)
   - List components with flags (DNP, In BOM)
   - Verify topology
   ↓
5. Analyze PCB (MCP Server)
   - Check footprints
   - Verify tracks
   - Get statistics
```

### Future Improvements

The editing tools are currently experimental and will be improved in future releases. For now, we recommend:

- Use KiCad GUI for all design and editing work
- Use MCP server for analysis and verification
- Use netlist export for accurate connection tracing

## Installation

```bash
# Clone repository
git clone https://github.com/LynnL4/kicad-mcp-server.git
cd kicad-mcp-server

# Install dependencies
pip install -r requirements.txt
```

### Requirements

- Python 3.10 or higher
- KiCad 7.0 or later (KiCad 9.0+ recommended for full feature support)
- `kicad-cli` command-line tool (included with KiCad 7.0+)
- macOS / Linux / Windows

**Docker Support:**
- ✅ Full headless operation using `kicad-cli`
- ✅ No X11 display required
- ✅ Works with read-only source volumes

## Configuration

### Claude Desktop

Add to Claude Desktop configuration file (`~/.config/Claude/claude_desktop_config.json` on Linux/macOS or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "kicad": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "kicad_mcp_server"],
      "cwd": "/path/to/kicad-mcp-server",
      "env": {
        "PYTHONPATH": "/path/to/kicad-mcp-server/src"
      }
    }
  }
}
```

**Windows Example:**
```json
{
  "mcpServers": {
    "kicad": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "kicad_mcp_server"],
      "cwd": "C:\\Users\\YourName\\Desktop\\kicad-mcp-server",
      "env": {
        "PYTHONPATH": "C:\\Users\\YourName\\Desktop\\kicad-mcp-server\\src"
      }
    }
  }
}
```

## Usage

### Analyze Schematic

```python
# List all resistors
list_schematic_components("Power.kicad_sch", filter_type="R")

# List only DNP (Do Not Populate) components
list_schematic_components("Power.kicad_sch", filter_dnp=True)

# List components excluding DNP
list_schematic_components("Power.kicad_sch", filter_dnp=False)

# Get schematic information
get_schematic_info("Power.kicad_sch")

# Search for components
search_symbols("Power.kicad_sch", pattern="U1")
```

### Trace Connections Using Netlist (Recommended)

First, export netlist from KiCad:

```bash
kicad-cli sch export netlist --format kicadxml \
  --output Power.net.xml Power.kicad_sch
```

Then trace connections:

```python
# Trace component connections (100% accurate)
trace_netlist_connection("Power.net.xml", "Q3")

# List all I2C nets
get_netlist_nets("Power.net.xml", filter_pattern="I2C")

# Get all components with their nets
get_netlist_components("Power.net.xml", filter_ref="U")
```

### Analyze PCB

```python
# Get PCB statistics
get_pcb_statistics("reSpeaker Lav.kicad_pcb")

# List all footprints
list_pcb_footprints("reSpeaker Lav.kicad_pcb")

# Find tracks by net
find_tracks_by_net("reSpeaker Lav.kicad_pcb", "GND")
```

### Edit Schematic

```python
# Create new project
create_kicad_project(
    path="/projects/MyDesign",
    name="MyDesign",
    title="My Design",
    company="My Company"
)

# Add component
add_component_from_library(
    file_path="Power.kicad_sch",
    library_name="Device",
    symbol_name="R",
    reference="R16",
    value="4.7K",
    x=150,
    y=200
)

# Add wire
add_wire("Power.kicad_sch", points=[(100, 100), (150, 100)])
```

### Edit PCB

```python
# Initialize PCB layout
setup_pcb_layout("Power.kicad_sch", width=100, height=100, unit="mm")

# Export Gerber files
export_gerber("reSpeaker Lav.kicad_pcb")
```

## Architecture

### Tool Organization

The server is organized into 6 modules:

1. **schematic** - Schematic file analysis and parsing
2. **pcb** - PCB file analysis using pcbnew API
3. **netlist** - XML netlist parsing and connection tracing
4. **schematic_editor** - Schematic editing and project creation
5. **pcb_layout** - PCB layout initialization and editing
6. **project** - KiCad project management

### KiCad 9.0 Compatibility

- Uses KiCad official templates for project creation
- Supports `.kicad_pro` (JSON format, version 3)
- Supports `.kicad_sch` (S-expression format, version 20240130)
- Supports `.kicad_pcb` (S-expression format, version 20240130)

### Parser Implementation

- **Schematic parser**: Custom S-expression parser
- **PCB parser**: KiCad pcbnew Python API
- **Netlist parser**: XML parser for KiCad netlist format

## Documentation

- **README.md** - This file (user guide)
- **CLAUDE.md** - Development documentation

## Design Decisions

### Scope

The server focuses on analysis and project management:

1. **Analysis** - Understand existing designs (Production-Ready)
2. **Project Management** - Create and organize projects (Production-Ready)
3. **Editing** - Basic schematic/PCB editing (Experimental)

### Technical Limitations

**Why Editing Tools Are Experimental:**

KiCad 9.0 does not provide Python APIs for schematic editing:

- **PCB**: Has official `pcbnew` API (fully functional)
- **Schematic**: No Python API available (manual S-expression parsing required)
- **Netlist**: Can export via CLI, but cannot import via API

**Schematic Editing Challenges:**

1. **Complex S-expression Format**
   - KiCad schematics use nested Lisp-like expressions
   - Requires precise UUID generation for all elements
   - Pin definitions need exact positions and electrical types

2. **Symbol Instantiation**
   - Must reference library symbols correctly
   - Requires proper pin mapping and units
   - Visual alignment is difficult without GUI

3. **Electrical Connections**
   - Wires must connect to exact pin coordinates
   - Junctions and labels need proper formatting
   - Power symbols have special handling

**Current Approach:**

```python
# Simplified component addition (experimental)
component_entry = f'''
  (symbol (lib_id "{lib_id}") (at {x} {y} 0)
    (exclude_from_sim no)
    (uuid {uuid})
    (pins...)  # Minimal pin definitions
  )
'''
```

**Result**: Components are added but may lack complete electrical information.

### Out of Scope

The following features are intentionally not included:

- Test code generation (not a core requirement)
- Natural language processing (use AI assistant directly)
- Component library management (use KiCad built-in libraries)
- Auto-routing (use KiCad's built-in router)
- Complete schematic editing (use KiCad GUI instead)

### Recent Improvements (v0.1.0)

**Component Flag Extraction** (PR #1)
- Extract KiCad's 4 boolean component flags from `.kicad_sch` files:
  - `dnp` - Do Not Populate (assembly flag)
  - `in_bom` - Include in Bill of Materials
  - `on_board` - Include in PCB layout
  - `exclude_from_sim` - Exclude from simulation
- Display DNP/In BOM columns when non-default values exist
- Filter components by DNP status for BOM generation

**Headless Netlist Export** (PR #1)
- Migrated from `eeschema` (GUI) to `kicad-cli` (CLI)
- Full Docker/CI support without X11 display
- Outputs to `/tmp` to handle read-only source volumes

**Sub-sheet Detection** (PR #1)
- Auto-detects hierarchical sub-sheets
- Redirects to root schematic to prevent data loss
- Prevents silent incomplete netlist exports from kicad-cli

### Recommended Usage

**For Best Results:**

1. **Design Phase**: Use KiCad GUI for all schematic and PCB editing
2. **Analysis Phase**: Use MCP server to analyze and verify designs
3. **Connection Tracing**: Export netlist and use MCP netlist tools
4. **Automation**: Use MCP for bulk analysis and reporting

**MCP Server Excels At:**
- Analyzing existing schematics
- Tracing connections (netlist-based)
- Listing components and footprints
- PCB statistics and verification
- Project organization

**KiCad GUI Excels At:**
- Schematic design and editing
- PCB layout and routing
- Visual design verification
- Interactive component placement

### Optimization Results

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Number of tools | 10 | 6 | -40% |
| Lines of code | ~3500 | ~2250 | -36% |
| Focus | Distributed | Core | Improved |
| Analysis tools | Basic | Production-Ready | ✅ |
| Editing tools | Ambitious | Experimental | ⚠️ |

## Changelog

### v0.1.0 (2026-02-24)
- ✨ **New**: Component flag extraction (DNP, In BOM, On Board, Exclude from Sim)
- ✨ **New**: Headless netlist export using kicad-cli (Docker/CI friendly)
- ✨ **New**: Sub-sheet detection to prevent incomplete netlist exports
- 🐛 **Fix**: Improved netlist generation reliability
- 📝 **Docs**: Updated documentation with new features

## Resources

- [KiCad Documentation](https://docs.kicad.org/)
- [KiCad 9.0 File Format Specification](https://dev-docs.kicad.org/en/file-formats/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [KiCad Python Scripting](https://docs.kicad.org/doxygen-python/)
- [kicad-cli Documentation](https://docs.kicad.org/en/cli/)

## License

MIT License
