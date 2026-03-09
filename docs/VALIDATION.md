# Design Rule Checking Guide

Comprehensive guide for using KiCad MCP Server's design rule checking capabilities.

## Overview

The validation tools provide automated design rule checking (DRC) and electrical rules check (ERC) to ensure your hardware designs are correct before manufacturing.

## Tools

### ERC Tools

#### `run_erc(schematic_path: str) -> str`

Run Electrical Rules Check on a schematic file.

**What it checks:**
- Unconnected pins
- Power conflicts (VCC to VCC, GND to GND)
- Multiple outputs on same net
- Pin type mismatches

**Example:**
```python
result = run_erc("board.kicad_sch")
if "X" in result:
    print("ERC violations found")
else:
    print("No ERC violations")
```

**Returns:**
- ✅ Pass: No violations detected
- ❌ Fail: List of violations with severity and descriptions

#### `get_erc_violations(schematic_path: str, severity: str = "") -> str`

Get filtered ERC violations by severity.

**Parameters:**
- `severity`: "error", "warning", or "" for all

**Example:**
```python
# Get only errors
errors = get_erc_violations("board.kicad_sch", severity="error")

# Get all violations
all_violations = get_erc_violations("board.kicad_sch")
```

### DRC Tools

#### `run_drc(pcb_path: str) -> str`

Run Design Rules Check on a PCB file.

**What it checks:**
- Clearance violations (< 0.15mm default)
- Track spacing violations
- Missing connections (unrouted nets)
- Pad/footprint overlaps
- Board edge constraints

**Example:**
```python
result = run_drc("board.kicad_pcb")
if "X" in result:
    print("DRC violations found")
    # Parse violations and fix in KiCad
else:
    print("No DRC violations - ready for manufacturing")
```

#### `get_drc_violations(pcb_path: str, violation_type: str = "") -> str`

Get filtered DRC violations by type.

**Parameters:**
- `violation_type`: "clearance", "spacing", "missing_connection", or "" for all

**Example:**
```python
# Get only clearance violations
clearance_issues = get_drc_violations("board.kicad_pcb", violation_type="clearance")

# Get all violations
all_violations = get_drc_violations("board.kicad_pcb")
```

### Export Tools

#### `export_erc_report(schematic_path: str, output_path: str = "") -> str`
#### `export_drc_report(pcb_path: str, output_path: str = "") -> str`

Export validation reports to files for documentation.

**Example:**
```python
export_erc_report("board.kicad_sch", "reports/erc_report.txt")
export_drc_report("board.kicad_pcb", "reports/drc_report.txt")
```

## Usage Patterns

### Pre-Manufacturing Checklist

Before sending your design to manufacturing:

```python
# 1. Run ERC on schematic
erc_result = run_erc("board.kicad_sch")
assert "X" not in erc_result, "Fix ERC violations first"

# 2. Run DRC on PCB
drc_result = run_drc("board.kicad_pcb")
assert "X" not in drc_result, "Fix DRC violations first"

# 3. Export reports for documentation
export_erc_report("board.kicad_sch", "manufacturing/erc.txt")
export_drc_report("board.kicad_pcb", "manufacturing/drc.txt")

print("OK Design ready for manufacturing")
```

### CI/CD Integration

Automated validation in continuous integration:

```bash
# In your CI pipeline
python -c "
from kicad_mcp_server.tools import validation
import sys

# Run checks
erc = validation.run_erc('board.kicad_sch')
drc = validation.run_drc('board.kicad_pcb')

# Fail if violations found
if 'X' in erc or 'X' in drc:
    sys.exit(1)
"
```

### Iterative Design Process

During design iteration:

```python
while True:
    # Make design changes in KiCad
    input("Make changes in KiCad, then press Enter...")

    # Run validation
    erc = run_erc("board.kicad_sch")
    drc = run_drc("board.kicad_pcb")

    # Check for violations
    if "X" not in erc and "X" not in drc:
        print("OK Design is clean!")
        break

    # Show violations to fix
    print(erc)
    print(drc)
```

## Common Violations

### ERC Violations

**Unconnected Input Pin**
```
X ERC violation detected
Type: unconnected_input
Component: U1
Pin: 3 (RESET)
Description: Unconnected input pin may cause undefined behavior
```
**Fix:** Connect the pin to appropriate signal or add pull-up/pull-down resistor.

**Multiple Outputs on Same Net**
```
X ERC violation detected
Type: multiple_outputs
Components: U1:8, U2:3
Description: Multiple outputs on same net can cause damage
```
**Fix:** Remove one output or add proper isolation (diode, buffer).

**Power Conflict**
```
X ERC violation detected
Type: power_conflict
Components: U1:1, U2:1
Description: Multiple power outputs on same net
```
**Fix:** Ensure only one power source per net or use proper power distribution.

### DRC Violations

**Clearance Violation**
```
X DRC violation detected
Type: clearance
Location: (45.2, 23.1)
Description: Insufficient clearance (0.12mm < 0.15mm required)
```
**Fix:** Increase spacing between tracks/pads to meet clearance requirements.

**Missing Connection**
```
X DRC violation detected
Type: missing_connection
Net: I2C_SDA
Description: Unrouted net detected
```
**Fix:** Route the connection in KiCad or mark as no-route if intentional.

## Best Practices

1. **Run ERC Early:** Check schematic frequently during design
2. **Run DRC After Layout:** Check PCB after routing is complete
3. **Fix Errors First:** Always fix error-level violations before warnings
4. **Document Exceptions:** Some warnings may be acceptable design choices
5. **Version Control:** Commit validation reports with design files

## Troubleshooting

**Issue:** kicad-cli not found
```bash
# Install KiCad or add to PATH
export PATH=$PATH:/path/to/kicad/bin
```

**Issue:** False positives in ERC
- Some warnings may be intentional design choices
- Use `get_erc_violations()` with severity filters to focus on errors
- Document design exceptions in your project notes

**Issue:** DRC takes too long
- Check design rules in KiCad (Board Setup → Design Rules)
- Simplify rules if too strict for your application
- Use `get_drc_violations()` to check specific violation types

## Integration with Other Tools

### Before Device Tree Generation
```python
# Always validate before generating code
validate_pin_configuration("board.kicad_sch")  # Run ERC/DRC first
generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")
```

### Before Test Generation
```python
# Ensure design is valid before generating tests
run_erc("board.kicad_sch")
run_drc("board.kicad_pcb")
generate_hardware_tests("board.kicad_sch", "pytest")
```

## Resources

- [KiCad Design Rules](https://docs.kicad.org/doxygen/latest/)
- [IPC Standards](https://www.ipc.org/)
- [Project-specific design rules](board.kicad_pcb setup)
