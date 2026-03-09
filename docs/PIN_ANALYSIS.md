# Pin Analysis Guide

Comprehensive guide for using KiCad MCP Server's pin analysis and configuration tools.

## Overview

Pin analysis tools provide detailed information about pin functions, detect conflicts, and extract pin multiplexing configurations for embedded systems development.

## Tools

### `analyze_pin_functions(schematic_path: str, reference: str = "") -> str`

Analyze pin functions and detect peripheral assignments.

**What it does:**
- Identifies MCU components and their families
- Infers pin functions from net names (I2C, SPI, UART, GPIO)
- Provides MCU-specific pin mapping information
- Shows alternate functions for each pin

**Example:**
```python
# Analyze all components in schematic
result = analyze_pin_functions("board.kicad_sch")

# Analyze specific MCU
result = analyze_pin_functions("board.kicad_sch", reference="U1")
print(result)
```

**Output includes:**
- Component reference and value
- MCU family identification
- Pin names and numbers
- Net connections
- Inferred peripheral functions
- MCU-specific alternate functions
- Maximum current ratings
- 5V tolerance information

### `detect_pin_conflicts(schematic_path: str) -> str`

Detect conflicting electrical connections in your design.

**What it detects:**
- Multiple outputs on same net
- Power-to-power connections
- Unconnected input pins
- Pin type mismatches

**Example:**
```python
conflicts = detect_pin_conflicts("board.kicad_sch")
if "❌" in conflicts:
    print("Pin conflicts found:")
    print(conflicts)
else:
    print("No pin conflicts detected")
```

**Severity levels:**
- ❌ **Error**: Must fix before manufacturing (e.g., multiple outputs)
- ⚠️ **Warning**: Review but may be acceptable (e.g., unconnected inputs)

### `extract_pinmux_config(schematic_path: str, component_type: str = "") -> str`

Extract pin multiplexing configuration for MCUs.

**What it provides:**
- Pin-to-peripheral mappings
- Alternate function assignments
- GPIO configuration details
- MCU-specific information

**Example:**
```python
# Extract pinmux for all MCUs
pinmux = extract_pinmux_config("board.kicad_sch")

# Extract for specific MCU family
stm32_pinmux = extract_pinmux_config("board.kicad_sch", component_type="stm32")
print(stm32_pinmux)
```

**Output includes:**
- Pin names and numbers
- Peripheral assignments (I2C, SPI, UART, etc.)
- Alternate function options
- Code generation suggestions
- MCU-specific configuration details

## Supported MCU Families

### STM32 (STM32F, STM32H, STM32L)
- Pin naming: PA0, PB12, etc.
- Alternate functions: GPIO, ADC, TIM, USART, SPI, I2C, CAN
- Max current: 25mA per pin
- 5V tolerance: No (most pins)

### ESP32 (ESP32, ESP32-S2, ESP32-S3)
- Pin naming: IO0, GPIO2, etc.
- Alternate functions: GPIO, ADC, DAC, I2C, SPI, UART, TOUCH
- Max current: 40mA per pin
- 5V tolerance: No

### nRF52 (nRF52832, nRF52840)
- Pin naming: P0.00, P0.01, etc.
- Alternate functions: GPIO, ADC, SPI, I2C, UART, PWM, QSPI
- Max current: 5mA per pin (typical)
- 5V tolerance: No

### ATmega (ATmega328P, ATmega2560)
- Pin naming: PD0, PD1, etc. (port + number)
- Alternate functions: GPIO, UART, SPI, I2C, ADC
- Max current: 40mA per pin
- 5V tolerance: Yes

### SAMD (ATSAMD21, ATSAMD51)
- Pin naming: PA00, PA12, etc.
- Alternate functions: GPIO, ADC, DAC, I2C, SPI, UART
- Max current: Varies by series
- 5V tolerance: No

### RP2040
- Pin naming: GPIO0, GPIO1, etc.
- Alternate functions: GPIO, SPI, UART, I2C, PWM, ADC
- Max current: 16mA per pin
- 5V tolerance: No

## Peripheral Function Detection

### I2C Detection
Net names containing:
- `I2C`, `TWI`
- `SDA`, `SCL`
- `I2C_SDA`, `I2C_SCL`

### SPI Detection
Net names containing:
- `SPI`
- `MISO`, `MOSI`, `SCK`, `CS`, `NSS`
- `SPI_MOSI`, `SPI_MISO`

### UART Detection
Net names containing:
- `UART`, `USART`, `SERIAL`
- `TX`, `RX`, `CTS`, `RTS`
- `UART_TX`, `UART_RX`

### GPIO Detection
Net names containing:
- `GPIO`, `IO`
- `PA0`, `PB12` (STM32 style)
- `P0.00` (nRF52 style)

## Usage Patterns

### Complete Pin Analysis Workflow

```python
# 1. Analyze all pins in schematic
pin_analysis = analyze_pin_functions("board.kicad_sch")
print(pin_analysis)

# 2. Check for conflicts
conflicts = detect_pin_conflicts("board.kicad_sch")
if "❌" in conflicts:
    print("WARNING: Pin conflicts detected!")
    print(conflicts)

# 3. Extract pinmux configuration
pinmux = extract_pinmux_config("board.kicad_sch", "stm32")
print(pinmux)
```

### Device Tree Generation Preparation

```python
# Before generating device tree, validate pin configuration
from kicad_mcp_server.tools.device_tree import validate_pin_configuration

validation = validate_pin_configuration("board.kicad_sch")
if "✅" in validation:
    # Safe to generate device tree
    generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")
```

### Code Generation Workflow

```python
# Analyze pins for code generation
pinmux = extract_pinmux_config("board.kicad_sch", "esp32")

# Use pinmux info for code generation
# (This can be integrated into your code generator)
for pin_config in pinmux:
    if pin_config['peripheral'] == 'I2C':
        # Generate I2C initialization code
        pass
    elif pin_config['peripheral'] == 'SPI':
        # Generate SPI initialization code
        pass
```

## Common Scenarios

### Scenario 1: I2C Bus Analysis

```python
# Analyze I2C pins
result = analyze_pin_functions("board.kicad_sch")

# Look for I2C functionality
# Output will show:
# - SDA and SCL pins
# - I2C bus number
# - Connected devices
# - Alternate functions

# Extract specific I2C configuration
i2c_devices = extract_i2c_devices("board.kicad_sch")
```

### Scenario 2: SPI Peripheral Setup

```python
# Analyze SPI pins
result = analyze_pin_functions("board.kicad_sch", reference="U1")

# Look for SPI functionality
# Output will show:
# - MOSI, MISO, SCK pins
# - CS pins
# - SPI bus number
# - Maximum frequency

# Extract SPI configuration
spi_devices = extract_spi_devices("board.kicad_sch")
```

### Scenario 3: GPIO Configuration

```python
# Get all GPIO pins
pinmux = extract_pinmux_config("board.kicad_sch", "stm32")

# Generate GPIO initialization code
for pin in pinmux['gpio_pins']:
    print(f"GPIO: {pin['name']}")
    print(f"  Function: {pin.get('function', 'GPIO')}")
    print(f"  Max Current: {pin.get('max_current', 0)} mA")
    print(f"  5V Tolerant: {pin.get('is_5v_tolerant', False)}")
```

## Conflict Resolution

### Multiple Outputs on Same Net

```python
# Detect conflicts
conflicts = detect_pin_conflicts("board.kicad_sch")

# If multiple outputs found:
# 1. Identify the conflicting pins
# 2. Remove one output or add isolation
# 3. Re-run conflict detection
```

### Unconnected Input Pins

```python
# Find unconnected inputs
conflicts = detect_pin_conflicts("board.kicad_sch")

# For each unconnected input:
# - Add pull-up/pull-down resistor if needed
# - Connect to appropriate signal
# - Or explicitly mark as unused (if design intent)
```

## Best Practices

1. **Name Your Nets**: Use descriptive net names (I2C_SDA, SPI_MOSI)
2. **Run Pin Analysis Early**: Check pin functions during schematic design
3. **Document Design Decisions**: Note why certain pins are configured
4. **Check for Conflicts**: Run conflict detection before PCB layout
5. **Verify Pinmux**: Ensure pinmux matches your firmware configuration

## Troubleshooting

**Issue:** Pin functions not detected
- **Solution:** Use descriptive net names (I2C_SDA, not Net-123)
- **Solution:** Check component value matches supported patterns
- **Solution:** Verify component is recognized as MCU

**Issue:** MCU family not detected
- **Solution:** Check component value field (e.g., "STM32F407")
- **Solution:** Ensure component library is properly configured
- **Solution:** Try specifying component_type parameter

**Issue:** False positive conflicts
- **Solution:** Review actual circuit design
- **Solution:** Some warnings may be acceptable (document them)
- **Solution:** Use pin-specific analysis instead of global detection

## Integration with Code Generation

```python
# Complete workflow for embedded development
from kicad_mcp_server.tools import pin_analysis, device_tree, test_generation

# 1. Analyze pins
pin_info = pin_analysis.analyze_pin_functions("board.kicad_sch")
pinmux = pin_analysis.extract_pinmux_config("board.kicad_sch", "stm32")

# 2. Check for conflicts
conflicts = pin_analysis.detect_pin_conflicts("board.kicad_sch")
assert "✅" in conflicts, "Fix pin conflicts first"

# 3. Generate device tree
device_tree.generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")

# 4. Generate tests
test_generation.generate_pinmux_test("board.kicad_sch")
```

## Resources

- [STM32 Pin Multiplexing](https://www.st.com/resource/en/datasheet/)
- [ESP32 Pin Reference](https://docs.espressif.com/projects/esp-idf/en/latest/)
- [nRF52 Reference Manual](https://infocenter.nordicsemi.com/)
- [Device Tree Specification](https://www.devicetree.org/)
