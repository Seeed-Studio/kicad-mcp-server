# KiCad MCP Server Documentation

Comprehensive documentation for the KiCad MCP Server - a complete hardware design validation and embedded development platform.

## Quick Start

1. **[Installation Guide](../README.md#installation)** - Get started with the server
2. **[Configuration](../README.md#configuration)** - Set up Claude Desktop integration
3. **[Basic Usage](../README.md#usage-examples)** - Common workflows and examples

## Core Documentation

### Design Validation
**[VALIDATION.md](./VALIDATION.md)** - Design Rule Checking Guide
- Electrical Rules Check (ERC)
- Design Rules Check (DRC)
- Violation detection and filtering
- Pre-manufacturing validation workflows
- CI/CD integration

### Pin Analysis
**[PIN_ANALYSIS.md](./PIN_ANALYSIS.md)** - Pin Analysis and Configuration Guide
- Pin function detection (GPIO/I2C/SPI/UART)
- MCU family support (STM32, ESP32, nRF52, ATmega, SAMD, RP2040)
- Pin conflict detection
- Pin multiplexing configuration extraction
- Code generation integration

### Device Tree Generation
**[DEVICE_TREE.md](./DEVICE_TREE.md)** - Device Tree Generation Guide
- Automatic .dts generation from schematics
- SOC family support (STM32F4, ESP32, nRF52, ATmega)
- Peripheral configuration extraction
- Device tree bindings database
- Customization and integration

### Test Code Generation
**[TEST_GENERATION.md](./TEST_GENERATION.md)** - Automated Test Generation Guide
- Hardware test generation (pytest, Unity, Google Test)
- GPIO, I2C, SPI, pinmux testing
- Framework-specific features
- CI/CD integration
- Test customization

## Usage Guides

### Complete Embedded Development Workflow

```python
# 1. Design Validation
run_erc("board.kicad_sch")
run_drc("board.kicad_pcb")

# 2. Pin Analysis
analyze_pin_functions("board.kicad_sch")
detect_pin_conflicts("board.kicad_sch")

# 3. Device Tree Generation
validate_pin_configuration("board.kicad_sch")
generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")

# 4. Test Generation
generate_hardware_tests("board.kicad_sch", "pytest", "tests/")
export_test_framework("board.kicad_sch", "pytest", "test_framework/")
```

### Common Tasks

**Validate Hardware Design**
```bash
# Check schematic for electrical issues
run_erc("design.kicad_sch")

# Check PCB for manufacturing issues
run_drc("design.kicad_pcb")

# Export reports
export_erc_report("design.kicad_sch", "erc_report.txt")
export_drc_report("design.kicad_pcb", "drc_report.txt")
```

**Generate Device Tree**
```bash
# Validate pin configuration
validate_pin_configuration("board.kicad_sch")

# Generate device tree
generate_device_tree("board.kicad_sch", "stm32f4", "board.dts")

# Compile device tree
dtc -I dts -O dtb -o board.dtb board.dts
```

**Generate Hardware Tests**
```bash
# Generate test suite
generate_hardware_tests("board.kicad_sch", "pytest", "tests/")

# Export complete framework
export_test_framework("board.kicad_sch", "pytest", "test_framework/")

# Run tests
cd test_framework/
pytest
```

## Tool Reference

### Analysis Tools (3 tools)
- `list_schematic_components()` - List schematic components
- `get_schematic_info()` - Get schematic metadata
- `trace_netlist_connection()` - Trace component connections

### Validation Tools (6 tools) ✨ NEW
- `run_erc()` - Run Electrical Rules Check
- `run_drc()` - Run Design Rules Check
- `get_erc_violations()` - Get filtered ERC violations
- `get_drc_violations()` - Get filtered DRC violations
- `export_erc_report()` - Export ERC report
- `export_drc_report()` - Export DRC report

### Pin Analysis Tools (3 tools) ✨ NEW
- `analyze_pin_functions()` - Analyze pin functions
- `detect_pin_conflicts()` - Detect pin conflicts
- `extract_pinmux_config()` - Extract pinmux configuration

### Device Tree Tools (6 tools) ✨ NEW
- `generate_device_tree()` - Generate .dts files
- `extract_gpio_config()` - Extract GPIO configuration
- `extract_i2c_devices()` - Extract I2C devices
- `extract_spi_devices()` - Extract SPI devices
- `extract_power_domains()` - Extract power domains
- `validate_pin_configuration()` - Validate configuration

### Test Generation Tools (6 tools) ✨ NEW
- `generate_hardware_tests()` - Generate complete test suite
- `generate_gpio_test()` - Generate GPIO tests
- `generate_i2c_test()` - Generate I2C tests
- `generate_spi_test()` - Generate SPI tests
- `generate_pinmux_test()` - Generate pinmux tests
- `export_test_framework()` - Export test framework

## Supported Hardware

### MCU Families
- **STM32** (STM32F, STM32H, STM32L series)
- **ESP32** (ESP32, ESP32-S2, ESP32-S3)
- **nRF52** (nRF52832, nRF52840)
- **ATmega** (ATmega328P, ATmega2560)
- **SAMD** (ATSAMD21, ATSAMD51)
- **RP2040**

### Peripherals
- **Sensors**: BMP280, MPU6050, LSM6DS3, HTS221, etc.
- **Displays**: ST7789, SSD1306, ILI9341, etc.
- **Memory**: AT24C256, W25Q128, GD25Q16
- **Wireless**: ESP8266, nRF24L01, SX1278
- **Connectivity**: CP2102, FT232RL, CH340G
- **Power**: TP4056, AXP192, LP3985, AP2112

### Test Frameworks
- **pytest** (Python) - Full hardware interaction
- **Unity** (Embedded C) - MCU testing
- **Google Test** (C++) - Framework structure ready

## Best Practices

### Schematic Design
1. **Use descriptive net names** (I2C_SDA, SPI_MOSI, GPIO_LED)
2. **Include I2C addresses** in net names (I2C_SDA_0x76)
3. **Use standard component values** (STM32F407, BMP280)
4. **Run ERC frequently** during design

### PCB Layout
1. **Run DRC after routing** to catch manufacturing issues
2. **Check clearance violations** before production
3. **Verify all connections** are routed
4. **Export DRC reports** for documentation

### Device Tree Generation
1. **Validate pin configuration** before generation
2. **Review generated .dts** file
3. **Test compilation** with device tree compiler
4. **Keep schematic and DT in sync**

### Test Generation
1. **Start with mock mode** for initial testing
2. **Enable hardware interaction** after validation
3. **Customize tests** for your specific hardware
4. **Integrate with CI/CD** for automated testing

## Troubleshooting

### Common Issues

**kicad-cli not found**
```bash
# Add KiCad to PATH
export PATH=$PATH:/path/to/kicad/bin

# Or install KiCad
sudo apt install kicad  # Linux
brew install kicad      # macOS
```

**Device tree won't compile**
```bash
# Check syntax
dtc -I dts -O dts -o verify.dts board.dts

# Look for missing includes or undefined nodes
# Verify all referenced devices exist in schematic
```

**Tests not detecting hardware**
```python
# Check hardware interaction is enabled
hardware_interaction = True

# Verify I2C addresses in net names
# Use format: I2C_SDA_0x76

# Check component values are recognizable
# Use specific names: "BMP280", not "SENSOR1"
```

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## License

See [LICENSE](../LICENSE) for license information.

## Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
- **Documentation**: This directory
- **Examples**: [examples/](../examples/) directory

## Changelog

See [CHANGELOG.md](../CHANGELOG.md) for version history and changes.

---

**Last Updated**: 2025-01-09
**Version**: 2.0.0 - Complete Hardware Design and Development Platform
