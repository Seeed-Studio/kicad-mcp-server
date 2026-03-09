# Test Fixtures for KiCad MCP Server

This directory contains test fixture files for testing the MCP server tools.

## Fixture Categories

### Validation Test Fixtures
- `erc_violations.kicad_sch` - Schematic with intentional ERC violations
- `drc_violations.kicad_pcb` - PCB with intentional DRC violations
- `clean_design.kicad_sch` - Clean schematic with no violations
- `clean_design.kicad_pcb` - Clean PCB with no violations

### Pin Analysis Test Fixtures
- `stm32_board.kicad_sch` - STM32-based board for pin analysis
- `esp32_board.kicad_sch` - ESP32-based board for pin analysis
- `pin_conflicts.kicad_sch` - Schematic with pin conflicts

### Device Tree Test Fixtures
- `stm32f4_project/` - Complete STM32F4 project for device tree generation
- `esp32_project/` - Complete ESP32 project for device tree generation
- `complex_peripherals.kicad_sch` - Schematic with multiple I2C/SPI devices

### Test Generation Test Fixtures
- `gpio_test_board.kicad_sch` - Board for GPIO test generation
- `i2c_sensors.kicad_sch` - Board with multiple I2C sensors
- `spi_devices.kicad_sch` - Board with multiple SPI devices

## Fixture Creation Guidelines

### ERC Violation Fixture
Create schematic with:
- Unconnected input pins
- Multiple outputs on same net
- Power-to-power connections
- Pin type mismatches

### DRC Violation Fixture
Create PCB with:
- Clearance violations (< 0.15mm)
- Missing connections
- Pad/footprint overlaps
- Board edge constraints

### Device Tree Fixture
Create project with:
- MCU component (STM32/ESP32/etc.)
- I2C devices with proper naming
- SPI devices with chip selects
- GPIO pins with named nets
- Power management components

## Usage

```python
# Example test using fixtures
def test_run_erc_with_violations():
    result = await run_erc("tests/fixtures/erc_violations.kicad_sch")
    assert "❌ ERC violation detected" in result
    assert "unconnected pin" in result.lower()
```

## Note

These fixtures should be created using actual KiCad 9.0 to ensure compatibility.
For now, this directory serves as a placeholder for future fixture creation.
