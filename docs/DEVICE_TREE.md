# Device Tree Generation Guide

Comprehensive guide for using KiCad MCP Server's device tree generation capabilities.

## Overview

Device tree generation tools automatically create Linux device tree source (.dts) files from KiCad schematics, supporting multiple SOC families and peripheral types.

## Tools

### `generate_device_tree(schematic_path: str, target_soc: str = "stm32f4", output_path: str = "") -> str`

Generate complete device tree source file from schematic.

**Supported SOC Families:**
- `stm32f4` - STM32F4 series (STM32F407, STM32F411, etc.)
- `esp32` - ESP32 series (ESP32, ESP32-S2, ESP32-S3)
- `nrf52` - nRF52 series (nRF52832, nRF52840)
- `atmega` - ATmega series (ATmega328P, ATmega2560)

**Example:**
```python
# Generate device tree for STM32F4
result = generate_device_tree(
    schematic_path="board.kicad_sch",
    target_soc="stm32f4",
    output_path="board.dts"
)
print(result)
```

**Output includes:**
- GPIO pin configurations
- I2C buses and devices
- SPI buses and devices
- UART/USART configurations
- Power domains and regulators
- SOC-specific configurations

### `extract_gpio_config(schematic_path: str, soc_family: str = "") -> str`

Extract GPIO pin configurations from schematic.

**Example:**
```python
# Extract all GPIO configurations
gpio = extract_gpio_config("board.kicad_sch")

# Extract for specific SOC
stm32_gpio = extract_gpio_config("board.kicad_sch", soc_family="stm32")
```

**Output includes:**
- Pin numbers and names
- Net connections
- SOC family identification
- Code generation suggestions

### `extract_i2c_devices(schematic_path: str) -> str`

Extract I2C bus and device configurations.

**Example:**
```python
i2c_devices = extract_i2c_devices("board.kicad_sch")
print(i2c_devices)
```

**Output includes:**
- I2C bus configuration
- Device addresses (extracted from net names)
- Device tree compatible strings
- Device tree node configurations

### `extract_spi_devices(schematic_path: str) -> str`

Extract SPI bus and device configurations.

**Example:**
```python
spi_devices = extract_spi_devices("board.kicad_sch")
print(spi_devices)
```

**Output includes:**
- SPI bus configuration
- Chip select assignments
- Device tree compatible strings
- SPI frequency settings

### `extract_power_domains(schematic_path: str) -> str`

Extract power domain and regulator configurations.

**Example:**
```python
power = extract_power_domains("board.kicad_sch")
print(power)
```

**Output includes:**
- Regulator components
- Power domain assignments
- Voltage configurations
- Device tree regulator nodes

### `validate_pin_configuration(schematic_path: str) -> str`

Validate pin configuration before device tree generation.

**Example:**
```python
validation = validate_pin_configuration("board.kicad_sch")
if "✅" in validation:
    # Safe to generate device tree
    generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")
else:
    print("Fix validation issues first")
```

## Device Tree Bindings Database

### Supported Components

**Sensors:**
- BMP280, BME280, BMP388 (bosch,bmp280)
- LSM6DS3, MPU6050, MPU9250 (motion sensors)
- HTS221, LPS22HB (environmental sensors)
- DHT22, SHT30 (temperature/humidity)
- MAX31855 (thermocouple)

**Displays:**
- ST7789, ST7735, ILI9341 (TFT displays)
- SSD1306, SH1106 (OLED displays)

**Memory:**
- AT24C256 (I2C EEPROM)
- W25Q128, GD25Q16 (SPI Flash)

**Wireless:**
- ESP8266 (WiFi module)
- nRF24L01 (2.4GHz radio)
- SX1278 (LoRa radio)

**Connectivity:**
- CP2102, FT232RL, CH340G (USB-serial)

**Power:**
- TP4056 (battery charger)
- AXP192 (power management)
- LP3985, AP2112 (voltage regulators)

## Usage Patterns

### Basic Device Tree Generation

```python
# 1. Validate pin configuration
validation = validate_pin_configuration("board.kicad_sch")
assert "✅" in validation, "Fix validation issues first"

# 2. Generate device tree
result = generate_device_tree(
    schematic_path="board.kicad_sch",
    target_soc="stm32f4",
    output_path="board.dts"
)

print(result)
```

### Multi-SOC Support

```python
# Generate device trees for different SOCs
for soc in ["stm32f4", "esp32", "nrf52"]:
    result = generate_device_tree(
        schematic_path="board.kicad_sch",
        target_soc=soc,
        output_path=f"board_{soc}.dts"
    )
    print(f"Generated {soc} device tree")
```

### Peripheral-Specific Extraction

```python
# Extract specific peripheral configurations
gpio = extract_gpio_config("board.kicad_sch", "stm32")
i2c = extract_i2c_devices("board.kicad_sch")
spi = extract_spi_devices("board.kicad_sch")
power = extract_power_domains("board.kicad_sch")

# Use extracted data for custom device tree
# (integrate into your build system)
```

## Schematic Requirements

### Component Naming

For best results, use standard component values:

```python
# Good - Recognizable components
"STM32F407VGT6"
"ESP32-WROOM-32"
"BMP280"
"SSD1306"

# Avoid - Generic names
"U1"  # Use proper component value
"SENSOR"  # Be specific
```

### Net Naming

Use descriptive net names for automatic detection:

```python
# I2C nets
"I2C1_SDA"
"I2C1_SCL"
"I2C_SENSOR_SDA_0x76"  # Include I2C address

# SPI nets
"SPI1_MOSI"
"SPI1_MISO"
"SPI1_SCK"
"SPI1_CS0"

# UART nets
"UART1_TX"
"UART1_RX"

# GPIO nets
"GPIO_LED_STATUS"
"GPIO_BUTTON_RESET"
"PA0"  # STM32 style
"IO0"  # ESP32 style
```

### I2C Address Detection

Include I2C addresses in net names:

```python
# Format: I2C_<name>_<address>
"I2C_SDA_0x76"  # BMP280 at 0x76
"I2C_SCL_0x5A"  # Device at 0x5A
```

## Device Tree Compilation

### Compile Generated Device Tree

```bash
# Install device tree compiler
sudo apt-get install device-tree-compiler

# Compile .dts to .dtb
dtc -I dts -O dtb -o board.dtb board.dts

# Verify compiled device tree
dtc -I dtb -O dts -o verify.dts board.dtb
```

### Integration with Build System

```makefile
# Makefile
BOARD_DTS = board.dts
BOARD_DTB = board.dtb

all: $(BOARD_DTB)

$(BOARD_DTB): $(BOARD_DTS)
	dtc -I dts -O dtb -o $@ $<

generate:
	python -c "
from kicad_mcp_server.tools import device_tree
device_tree.generate_device_tree('board.kicad_sch', 'stm32f4', '$(BOARD_DTS)')
"

clean:
	rm -f $(BOARD_DTB)
```

## Customization

### Custom Templates

Create custom device tree templates:

```python
# Save template as custom_soc.dts.j2
# In templates/device_tree/ directory

# Use custom template
result = generate_device_tree(
    schematic_path="board.kicad_sch",
    target_soc="custom_soc",
    output_path="board.dts"
)
```

### Custom Bindings

Add device tree bindings for new components:

```python
# In device_tree.py, add to DEVICE_TREE_BINDINGS
DEVICE_TREE_BINDINGS = {
    "MyCategory": {
        "MY_PART": {"compatible": "vendor,my-part"},
    },
    # ... existing bindings
}
```

### Post-Processing

Process generated device tree:

```python
# Generate device tree
result = generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")

# Read and modify
with open("board.dts", "r") as f:
    dts = f.read()

# Add custom modifications
dts += """
/* Custom additions */
&i2c1 {
    my_custom_device: custom@50 {
        compatible = "vendor,custom";
        reg = <0x50>;
    };
};
"""

# Write modified version
with open("board_custom.dts", "w") as f:
    f.write(dts)
```

## Best Practices

1. **Validate First**: Always run validation before generation
2. **Use Standard Names**: Use recognizable component values and net names
3. **Include Addresses**: Put I2C addresses in net names
4. **Review Output**: Inspect generated .dts file
5. **Test Compilation**: Compile .dts to .dtb to verify syntax
6. **Version Control**: Keep both schematic and device tree in sync

## Troubleshooting

**Issue:** MCU not detected
- **Solution:** Check component value (e.g., "STM32F407")
- **Solution:** Verify component library is properly configured

**Issue:** I2C addresses not detected
- **Solution:** Include address in net name (e.g., "I2C_SDA_0x76")
- **Solution:** Use hex format (0x76, not 118)

**Issue:** Device tree won't compile
- **Solution:** Check for syntax errors in generated .dts
- **Solution:** Verify all referenced nodes exist
- **Solution:** Check for missing include files

**Issue:** Generated device tree missing peripherals
- **Solution:** Check net naming conventions
- **Solution:** Verify component is in bindings database
- **Solution:** Ensure schematic netlist is up to date

## Integration with Embedded Linux

### Complete Workflow

```python
# 1. Validate design
validate_pin_configuration("board.kicad_sch")

# 2. Generate device tree
generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")

# 3. Compile device tree
import subprocess
subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", "board.dtb", "board.dts"])

# 4. Deploy to target
# (copy board.dtb to target system)
```

### Kernel Integration

```bash
# Copy device tree to boot partition
cp board.dtb /boot/

# Update boot loader to use new device tree
# (varies by platform)

# Reboot and test
reboot
```

## Resources

- [Device Tree Specification](https://www.devicetree.org/)
- [Linux Device Tree Usage](https://www.kernel.org/doc/Documentation/devicetree/usage-model.txt)
- [Device Tree Compiler](https://github.com/dgibson/dtc)
- [STM32 Device Tree](https://wiki.st.com/stm32mpu/wiki/Device_tree)
