# Test Code Generation Guide

Comprehensive guide for using KiCad MCP Server's automated test code generation capabilities.

## Overview

Test generation tools automatically create hardware test suites for connectivity testing, peripheral communication, and pin configuration validation across multiple testing frameworks.

## Tools

### `generate_hardware_tests(schematic_path: str, framework: str = "pytest", output_dir: str = "") -> str`

Generate complete hardware test suite covering all testable connections.

**Supported Frameworks:**
- `pytest` - Python testing framework (recommended for hardware interaction)
- `unity` - Embedded C testing framework
- `googletest` - C++ testing framework (basic support)

**Example:**
```python
# Generate pytest test suite
result = generate_hardware_tests(
    schematic_path="board.kicad_sch",
    framework="pytest",
    output_dir="tests/"
)
print(result)
```

**Generated test categories:**
- GPIO pin tests (input/output/continuity)
- I2C device tests (detection/communication)
- SPI device tests (detection/communication)
- Pin multiplexing tests (configuration validation)

### `generate_gpio_test(schematic_path: str, test_type: str = "connectivity") -> str`

Generate GPIO pin-specific tests.

**Test types:**
- `connectivity` - Verify connections exist
- `voltage` - Test voltage levels
- `functionality` - Test input/output behavior

**Example:**
```python
gpio_test = generate_gpio_test("board.kicad_sch", test_type="connectivity")
print(gpio_test)
```

**Generated tests include:**
- Pin initialization tests
- Input/output functionality tests
- State verification tests
- Multi-pin interaction tests

### `generate_i2c_test(schematic_path: str) -> str`

Generate I2C device detection and communication tests.

**Example:**
```python
i2c_test = generate_i2c_test("board.kicad_sch")
print(i2c_test)
```

**Generated tests include:**
- I2C bus scanning
- Device detection at expected addresses
- Basic communication tests
- Device-specific functionality tests

### `generate_spi_test(schematic_path: str) -> str`

Generate SPI communication tests.

**Example:**
```python
spi_test = generate_spi_test("board.kicad_sch")
print(spi_test)
```

**Generated tests include:**
- SPI device detection
- Data transfer tests
- Bus configuration verification
- Device-specific tests

### `generate_pinmux_test(schematic_path: str) -> str`

Generate pin multiplexing configuration tests.

**Example:**
```python
pinmux_test = generate_pinmux_test("board.kicad_sch")
print(pinmux_test)
```

**Generated tests include:**
- Pin conflict detection
- Alternate function verification
- Peripheral mapping validation

### `export_test_framework(schematic_path: str, framework: str = "pytest", output_dir: str = "") -> str`

Export complete test framework with directory structure and build files.

**Example:**
```python
framework = export_test_framework(
    schematic_path="board.kicad_sch",
    framework="pytest",
    output_dir="test_framework/"
)
print(framework)
```

**Generated structure:**
```
test_framework/
├── test_gpio.py          # GPIO tests
├── test_i2c.py           # I2C tests
├── test_spi.py           # SPI tests
├── test_pinmux.py        # Pin multiplexing tests
├── pytest.ini            # Pytest configuration (pytest)
├── requirements.txt      # Python dependencies (pytest)
├── Makefile              # Build configuration (unity)
└── README.md             # Documentation
```

## Framework-Specific Features

### Pytest (Python)

**Advantages:**
- Full hardware interaction support
- Easy to read and modify
- Rich ecosystem of plugins
- Excellent for integration testing

**Hardware Interaction:**
```python
# Enable hardware interaction
import RPi.GPIO as GPIO
from smbus2 import SMBus

# Tests can directly access hardware
def test_gpio_output():
    GPIO.setup(17, GPIO.OUT)
    GPIO.output(17, GPIO.HIGH)
    assert GPIO.input(17) == GPIO.HIGH
```

**Dependencies:**
```txt
pytest>=7.0.0
pytest-cov>=4.0.0
smbus2>=0.4.0  # I2C
spidev>=3.5    # SPI
RPi.GPIO>=0.7.0  # Raspberry Pi GPIO
```

### Unity (Embedded C)

**Advantages:**
- Designed for embedded systems
- Minimal memory footprint
- Works on MCUs without OS
- Easy to integrate with build systems

**Hardware Abstraction:**
```c
// Implement hardware abstraction layer
void gpio_init(uint32_t pin, uint32_t direction) {
    // MCU-specific GPIO initialization
}

uint32_t gpio_read(uint32_t pin) {
    // MCU-specific GPIO read
    return GPIO_Read(pin);
}
```

**Build Integration:**
```makefile
CC = gcc
CFLAGS = -Wall -Wextra -I.
LDFLAGS = -lunity

# Compile and run tests
test: $(TARGET)
	./$(TARGET)
```

## Schematic Requirements

### Net Naming for Test Generation

Use descriptive net names for better test generation:

```python
# GPIO nets
"GPIO_LED_STATUS"
"GPIO_BUTTON_RESET"
"IO0"  # ESP32 style
"PA0"  # STM32 style

# I2C nets with addresses
"I2C_SDA_0x76"  # BMP280 at 0x76
"I2C_SCL_0x5A"  # Device at 0x5A

# SPI nets with chip selects
"SPI1_MOSI"
"SPI1_CS0"  # Chip select 0
```

### Component Recognition

Use standard component values:

```python
# Recognizable sensors
"BMP280"
"LSM6DS3"
"SSD1306"

# Avoid generic names
# "SENSOR1"  # Poor - be specific
```

## Usage Patterns

### Basic Test Generation

```python
# Generate complete test suite
result = generate_hardware_tests(
    schematic_path="board.kicad_sch",
    framework="pytest",
    output_dir="tests/"
)

print(result)
```

### Export Complete Framework

```python
# Export framework with build files
framework = export_test_framework(
    schematic_path="board.kicad_sch",
    framework="pytest",
    output_dir="test_framework/"
)

# Navigate and run
import os
os.chdir("test_framework/")
os.system("pytest")
```

### Peripheral-Specific Tests

```python
# Generate only I2C tests
i2c_test = generate_i2c_test("board.kicad_sch")
with open("test_i2c.py", "w") as f:
    f.write(i2c_test)

# Generate only GPIO tests
gpio_test = generate_gpio_test("board.kicad_sch")
with open("test_gpio.py", "w") as f:
    f.write(gpio_test)
```

## Running Tests

### Pytest (Python)

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run specific test file
pytest test_gpio.py

# Run with coverage
pytest --cov=. --cov-report=html

# Run in verbose mode
pytest -v

# Run specific test
pytest test_gpio.py::TestGPIO17::test_gpio_output
```

### Unity (Embedded C)

```bash
# Compile tests
make

# Run tests
make test

# Clean build
make clean
```

## Test Customization

### Modifying Generated Tests

```python
# Generate tests
generate_hardware_tests("board.kicad_sch", "pytest", "tests/")

# Edit test_gpio.py to add custom tests
# Add device-specific test cases
# Modify hardware interaction code
# Add custom assertions
```

### Adding Device-Specific Tests

```python
# After generation, add custom tests
def test_bmp280_specific():
    """Test BMP280-specific functionality"""
    # Read chip ID
    chip_id = bus.read_byte_data(0x76, 0xD0)
    assert chip_id == 0x58, "Invalid chip ID"

    # Read calibration data
    # Test pressure reading
    # Test temperature reading
```

### Hardware Interaction Setup

```python
# In test files, enable hardware interaction
hardware_interaction = True

# Or set via environment variable
import os
os.environ['HARDWARE_TEST'] = '1'
```

## Best Practices

1. **Start with Mock Mode**: Test without hardware first
2. **Validate Design**: Run DRC/ERC before generating tests
3. **Review Generated Tests**: Inspect and customize as needed
4. **Incremental Testing**: Test peripherals one at a time
5. **Hardware Safety**: Ensure tests won't damage hardware
6. **Continuous Integration**: Run tests in CI/CD pipeline

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Hardware Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r test_framework/requirements.txt
      - name: Run tests
        run: |
          cd test_framework
          pytest
```

### GitLab CI Example

```yaml
test:
  script:
    - pip install -r test_framework/requirements.txt
    - cd test_framework
    - pytest
  artifacts:
    when: always
    reports:
      junit: test-results.xml
```

## Troubleshooting

**Issue:** No tests generated
- **Solution:** Check schematic has testable components
- **Solution:** Verify net naming conventions
- **Solution:** Ensure netlist is up to date

**Issue:** Hardware tests fail
- **Solution:** Check hardware connections
- **Solution:** Verify I2C/SPI addresses in schematic
- **Solution:** Test with mock mode first (hardware_interaction=False)

**Issue:** Pytest not found
- **Solution:** Install pytest: `pip install pytest`
- **Solution:** Check Python version (requires 3.7+)
- **Solution:** Use virtual environment

**Issue:** Unity tests won't compile
- **Solution:** Install Unity framework
- **Solution:** Check Makefile configuration
- **Solution:** Verify hardware abstraction layer

## Advanced Usage

### Custom Test Templates

Create custom test templates:

```python
# Save template as custom_test.py.j2
# In templates/tests/ directory

# Use custom template
# (integrate into your test generation workflow)
```

### Test Data Generation

```python
# Generate test data files
import json

test_data = {
    "gpio_pins": gpio_data,
    "i2c_devices": i2c_data,
    "spi_devices": spi_data
}

with open("test_data.json", "w") as f:
    json.dump(test_data, f)
```

### Integration with Build System

```makefile
# Generate tests from schematic
generate_tests:
	python -c "
from kicad_mcp_server.tools import test_generation
test_generation.export_test_framework('board.kicad_sch', 'pytest', 'tests/')
"

# Run tests
test: generate_tests
	cd tests && pytest

.PHONY: generate_tests test
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Unity Test Framework](https://github.com/ThrowTheSwitch/Unity)
- [Python GPIO Libraries](https://pypi.org/project/RPi.GPIO/)
- [Hardware Testing Best Practices](https://www.embedded.com/hardware-testing-techniques/)
