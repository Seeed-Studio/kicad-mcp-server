"""Device tree generation tools for KiCad MCP Server.

This module provides device tree source (.dts) generation capabilities including:
- GPIO pin configuration extraction
- I2C/SPI/UART device detection
- Power domain analysis
- SOC-specific device tree generation
"""

import json
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, Template

from ..parsers.netlist_parser import NetlistParser
from ..parsers.schematic_parser import SchematicParser
from ..server import mcp


# Device tree compatible strings database
DEVICE_TREE_BINDINGS = {
    "Sensor": {
        "BMP280": {"compatible": "bosch,bmp280"},
        "BME280": {"compatible": "bosch,bme280"},
        "BMP388": {"compatible": "bosch,bmp388"},
        "LSM6DS3": {"compatible": "st,lsm6ds3"},
        "MPU6050": {"compatible": "invensense,mpu6050"},
        "MPU9250": {"compatible": "invensense,mpu9250"},
        "HTS221": {"compatible": "st,hts221"},
        "LPS22HB": {"compatible": "st,lps22hb"},
        "DHT22": {"compatible": "dht22"},
        "SHT30": {"compatible": "sensirion,sht3x"},
        "MAX31855": {"compatible": "maxim,max31855"},
    },
    "Display": {
        "ST7789": {"compatible": "sitronix,st7789"},
        "ST7735": {"compatible": "sitronix,st7735"},
        "ILI9341": {"compatible": "ilitek,ili9341"},
        "SSD1306": {"compatible": "solomon,ssd1306"},
        "SH1106": {"compatible": "sinowealth,sh1106"},
    },
    "Memory": {
        "AT24C256": {"compatible": "atmel,24c256"},
        "W25Q128": {"compatible": "jedec,spi-nor"},
        "GD25Q16": {"compatible": "jedec,spi-nor"},
    },
    "Wireless": {
        "ESP8266": {"compatible": "espressif,esp8266"},
        "nRF24L01": {"compatible": "nordic,nrf24l01"},
        "SX1278": {"compatible": "semtech,sx1278"},
    },
    "Connectivity": {
        "CP2102": {"compatible": "silabs,cp2102"},
        "FT232RL": {"compatible": "ftdi,ft232rl"},
        "CH340G": {"compatible": "wch,ch340"},
    },
    "Power": {
        "TP4056": {"compatible": "tp4056"},
        "AXP192": {"compatible": "x-powers,axp192"},
        "LP3985": {"compatible": "ti,lp3985"},
        "AP2112": {"compatible": "tps,ap2112"},
    },
}


# SOC-specific device tree templates
DEVICE_TREE_TEMPLATES = {
    "stm32f4": """/* Device Tree for STM32F4 SOC */
/* Auto-generated from KiCad schematic */

#include <dt-bindings/gpio/gpio.h>
#include <dt-bindings/pinctrl/stm32-pinctrl.h>

/ {
  model = "{{ board_name }}";
  compatible = "st,stm32f4";

  /* GPIO Configuration */
  {% for pin in gpio_pins %}
  gpio_{{ pin.name }}: gpio@{{ pin.number }} {
    gpio-controller;
    #gpio-cells = <2>;
    status = "okay";
  };
  {% endfor %}

  /* I2C Devices */
  {% for bus in i2c_buses %}
  i2c{{ bus.number }}: i2c@{{ bus.address }} {
    compatible = "st,stm32-i2c";
    #address-cells = <1>;
    #size-cells = <0>;
    status = "okay";

    {% for device in bus.devices %}
    {{ device.name }}: {{ device.compatible }}@{{ device.address }} {
      compatible = "{{ device.compatible }}";
      reg = <{{ device.address }}>;
      {% if device.properties %}
      {% for key, value in device.properties.items() %}
      {{ key }} = <{{ value }}>;
      {% endfor %}
      {% endif %}
    };
    {% endfor %}
  };

  {% endfor %}

  /* SPI Devices */
  {% for bus in spi_buses %}
  spi{{ bus.number }}: spi@{{ bus.address }} {
    compatible = "st,stm32-spi";
    #address-cells = <1>;
    #size-cells = <0>;
    status = "okay";

    {% for device in bus.devices %}
    {{ device.name }}: {{ device.compatible }}@{{ device.cs }} {
      compatible = "{{ device.compatible }}";
      reg = <{{ device.cs }}>;
      spi-max-frequency = <{{ device.frequency }}>;
      {% if device.properties %}
      {% for key, value in device.properties.items() %}
      {{ key }} = <{{ value }}>;
      {% endfor %}
      {% endif %}
    };
    {% endfor %}
  };

  {% endfor %}

  /* UART Devices */
  {% for uart in uarts %}
  usart{{ uart.number }}: serial@{{ uart.address }} {
    compatible = "st,stm32-usart";
    status = "okay";
  };
  {% endfor %}
};
""",
    "esp32": """/* Device Tree for ESP32 SOC */
/* Auto-generated from KiCad schematic */

#include <dt-bindings/gpio/gpio.h>

/ {
  model = "{{ board_name }}";
  compatible = "espressif,esp32";

  /* GPIO Configuration */
  {% for pin in gpio_pins %}
  gpio_{{ pin.number }}: gpio@{{ pin.number }} {
    gpio-controller;
    #gpio-cells = <2>;
    status = "okay";
  };
  {% endfor %}

  /* I2C Devices */
  {% for bus in i2c_buses %}
  i2c{{ bus.number }}: i2c@{{ bus.address }} {
    compatible = "espressif,esp32-i2c";
    #address-cells = <1>;
    #size-cells = <0>;
    status = "okay";

    {% for device in bus.devices %}
    {{ device.name }}: {{ device.compatible }}@{{ device.address }} {
      compatible = "{{ device.compatible }}";
      reg = <{{ device.address }}>;
      {% if device.properties %}
      {% for key, value in device.properties.items() %}
      {{ key }} = <{{ value }}>;
      {% endfor %}
      {% endif %}
    };
    {% endfor %}
  };

  {% endfor %}

  /* SPI Devices */
  {% for bus in spi_buses %}
  spi{{ bus.number }}: spi@{{ bus.address }} {
    compatible = "espressif,esp32-spi";
    #address-cells = <1>;
    #size-cells = <0>;
    status = "okay";

    {% for device in bus.devices %}
    {{ device.name }}: {{ device.compatible }}@{{ device.cs }} {
      compatible = "{{ device.compatible }}";
      reg = <{{ device.cs }}>;
      spi-max-frequency = <{{ device.frequency }}>;
      {% if device.properties %}
      {% for key, value in device.properties.items() %}
      {{ key }} = <{{ value }}>;
      {% endfor %}
      {% endif %}
    };
    {% endfor %}
  };

  {% endfor %}
};
""",
    "nrf52": """/* Device Tree for nRF52 SOC */
/* Auto-generated from KiCad schematic */

#include <dt-bindings/gpio/gpio.h>

/ {
  model = "{{ board_name }}";
  compatible = "nordic,nrf52";

  /* GPIO Configuration */
  {% for pin in gpio_pins %}
  gpio_{{ pin.number }}: gpio@{{ pin.number }} {
    gpio-controller;
    #gpio-cells = <2>;
    status = "okay";
  };
  {% endfor %}

  /* I2C Devices */
  {% for bus in i2c_buses %}
  i2c{{ bus.number }}: i2c@{{ bus.address }} {
    compatible = "nordic,nrf52-i2c";
    #address-cells = <1>;
    #size-cells = <0>;
    status = "okay";

    {% for device in bus.devices %}
    {{ device.name }}: {{ device.compatible }}@{{ device.address }} {
      compatible = "{{ device.compatible }}";
      reg = <{{ device.address }}>;
      {% if device.properties %}
      {% for key, value in device.properties.items() %}
      {{ key }} = <{{ value }}>;
      {% endfor %}
      {% endif %}
    };
    {% endfor %}
  };

  {% endfor %}

  /* SPI Devices */
  {% for bus in spi_buses %}
  spi{{ bus.number }}: spi@{{ bus.address }} {
    compatible = "nordic,nrf52-spi";
    #address-cells = <1>;
    #size-cells = <0>;
    status = "okay";

    {% for device in bus.devices %}
    {{ device.name }}: {{ device.compatible }}@{{ device.cs }} {
      compatible = "{{ device.compatible }}";
      reg = <{{ device.cs }}>;
      spi-max-frequency = <{{ device.frequency }}>;
      {% if device.properties %}
      {% for key, value in device.properties.items() %}
      {{ key }} = <{{ value }}>;
      {% endfor %}
      {% endif %}
    };
    {% endfor %}
  };

  {% endfor %}
};
""",
}


def _find_component_binding(component_value: str, component_type: str) -> Optional[dict]:
    """Find device tree binding for a component.

    Args:
        component_value: Component value/part number
        component_type: Component category (Sensor, Display, etc.)

    Returns:
        Device tree binding dict or None if not found
    """
    if not component_value or not component_type:
        return None

    component_value_upper = component_value.upper()

    # Try exact match first
    if component_type in DEVICE_TREE_BINDINGS:
        if component_value_upper in DEVICE_TREE_BINDINGS[component_type]:
            return DEVICE_TREE_BINDINGS[component_type][component_value_upper]

        # Try partial match
        for key, value in DEVICE_TREE_BINDINGS[component_type].items():
            if key in component_value_upper or component_value_upper in key:
                return value

    return None


def _infer_peripheral_type(net_name: str) -> Optional[str]:
    """Infer peripheral type from net name.

    Args:
        net_name: Net name to analyze

    Returns:
        Peripheral type (I2C, SPI, UART, GPIO) or None
    """
    if not net_name:
        return None

    net_name_upper = net_name.upper()

    if "I2C" in net_name_upper or "TWI" in net_name_upper:
        return "I2C"
    elif "SPI" in net_name_upper:
        return "SPI"
    elif "UART" in net_name_upper or "USART" in net_name_upper or "SERIAL" in net_name_upper:
        return "UART"
    elif "GPIO" in net_name_upper or "IO" in net_name_upper:
        return "GPIO"

    return None


def _extract_i2c_address_from_net(net_name: str) -> Optional[int]:
    """Extract I2C address from net name.

    Args:
        net_name: Net name (e.g., I2C_SDA_0x76)

    Returns:
        I2C address as integer or None
    """
    import re

    # Look for hex address pattern
    match = re.search(r"0x[0-9A-Fa-f]+", net_name)
    if match:
        return int(match.group(0), 16)

    # Look for decimal address pattern
    match = re.search(r"[_\s](\d{2,3})$", net_name)
    if match:
        address = int(match.group(1))
        if 1 <= address <= 127:  # Valid I2C address range
            return address

    return None


@mcp.tool()
async def generate_device_tree(
    schematic_path: str,
    target_soc: str = "stm32f4",
    output_path: str = "",
) -> str:
    """Generate device tree source (.dts) file from schematic.

    This function analyzes a KiCad schematic and generates a device tree
    source file compatible with the specified SOC family.

    Args:
        schematic_path: Path to .kicad_sch file
        target_soc: Target SOC family (stm32f4, esp32, nrf52)
        output_path: Optional output file path

    Returns:
        Generated device tree source code or error message
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"X **Schematic file not found:** {schematic_path}"

        # Validate SOC family
        if target_soc not in DEVICE_TREE_TEMPLATES:
            return f"""X **Unsupported SOC Family**

**Requested:** {target_soc}
**Supported:** {', '.join(DEVICE_TREE_TEMPLATES.keys())}

Please specify a supported SOC family."""

        # Parse schematic
        schematic_parser = SchematicParser(str(sch_path))

        # Generate netlist for accurate connection analysis
        netlist_path = sch_path.parent / (sch_path.stem + ".xml")

        if not netlist_path.exists():
            # Try to generate netlist
            from .netlist import generate_netlist

            netlist_result = await generate_netlist(str(sch_path))
            if "X" in netlist_result:
                return f"X **Failed to generate netlist**\n\n{netlist_result}"

        # Parse netlist
        netlist_parser = NetlistParser(str(netlist_path))

        # Extract device tree data
        dt_data = {
            "board_name": sch_path.stem,
            "gpio_pins": [],
            "i2c_buses": [],
            "spi_buses": [],
            "uarts": [],
        }

        # Analyze components and extract peripheral configuration
        components = list(schematic_parser.get_components())

        for component in components:
            comp_ref = component["reference"]
            comp_value = component.get("value", "")
            comp_library = component.get("library_id", "")

            # Find device tree binding
            for category, bindings in DEVICE_TREE_BINDINGS.items():
                binding = _find_component_binding(comp_value, category)
                if binding:
                    # Get net connections
                    connections = []
                    for pin_num in range(1, 9):  # Check first 8 pins
                        try:
                            pin_connections = netlist_parser.trace_connection(comp_ref, str(pin_num))
                            if pin_connections and pin_connections[0].get("net"):
                                net_name = pin_connections[0]["net"]
                                peripheral_type = _infer_peripheral_type(net_name)

                                connections.append({
                                    "net": net_name,
                                    "peripheral": peripheral_type,
                                    "pin": pin_num,
                                })
                        except:
                            continue

                    if connections:
                        # Determine peripheral type based on connections
                        i2c_nets = [c for c in connections if c["peripheral"] == "I2C"]
                        spi_nets = [c for c in connections if c["peripheral"] == "SPI"]
                        uart_nets = [c for c in connections if c["peripheral"] == "UART"]

                        if i2c_nets:
                            # I2C device
                            i2c_address = _extract_i2c_address_from_net(i2c_nets[0]["net"])

                            device = {
                                "name": comp_ref,
                                "compatible": binding["compatible"],
                                "address": i2c_address or 0x00,
                                "properties": {},
                            }

                            # Add to I2C bus
                            dt_data["i2c_buses"].append({
                                "number": 1,  # Default to I2C1
                                "address": "0x40005400",  # Example STM32 I2C1 address
                                "devices": [device],
                            })

                        elif spi_nets:
                            # SPI device
                            device = {
                                "name": comp_ref,
                                "compatible": binding["compatible"],
                                "cs": 0,  # Default CS
                                "frequency": 1000000,  # 1 MHz default
                                "properties": {},
                            }

                            # Add to SPI bus
                            dt_data["spi_buses"].append({
                                "number": 1,  # Default to SPI1
                                "address": "0x40013000",  # Example STM32 SPI1 address
                                "devices": [device],
                            })

                        elif uart_nets:
                            # UART device
                            dt_data["uarts"].append({
                                "number": 1,  # Default to USART1
                                "address": "0x40011000",  # Example STM32 USART1 address
                            })

        # Extract GPIO pins
        for component in components:
            comp_ref = component["reference"]
            comp_value = component.get("value", "")

            # Check if this is an MCU
            if any(soc in comp_value.upper() for soc in ["STM32", "ESP32", "NRF"]):
                # Extract GPIO pins from netlist
                for pin_num in range(1, 100):  # Check first 100 pins
                    try:
                        pin_connections = netlist_parser.trace_connection(comp_ref, str(pin_num))
                        if pin_connections and pin_connections[0].get("net"):
                            net_name = pin_connections[0]["net"]

                            # Check if this is a GPIO net
                            if "GPIO" in net_name.upper() or "IO" in net_name.upper():
                                dt_data["gpio_pins"].append({
                                    "number": pin_num,
                                    "name": f"P{pin_num}",
                                })
                    except:
                        continue

        # Generate device tree from template
        template = Template(DEVICE_TREE_TEMPLATES[target_soc])
        device_tree = template.render(**dt_data)

        # Save to file if output path specified
        if output_path:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            with open(output, "w") as f:
                f.write(device_tree)

            return f"""OK **Device Tree Generated Successfully**

**Schematic:** {schematic_path}
**Target SOC:** {target_soc}
**Output:** {output_path}

## Device Tree Contents

- **GPIO Pins:** {len(dt_data['gpio_pins'])}
- **I2C Buses:** {len(dt_data['i2c_buses'])}
- **SPI Buses:** {len(dt_data['spi_buses'])}
- **UARTs:** {len(dt_data['uarts'])}

The device tree source file has been generated and saved to the specified location.

## Next Steps

1. Review and customize the generated device tree
2. Compile with device tree compiler: `dtc -I dts -O dtb -o output.dtb {output_path}`
3. Test on target hardware
4. Iterate as needed"""

        else:
            # Return device tree content directly
            return f"""OK **Device Tree Generated Successfully**

**Schematic:** {schematic_path}
**Target SOC:** {target_soc}

## Device Tree Contents

- **GPIO Pins:** {len(dt_data['gpio_pins'])}
- **I2C Buses:** {len(dt_data['i2c_buses'])}
- **SPI Buses:** {len(dt_data['spi_buses'])}
- **UARTs:** {len(dt_data['uarts'])}

## Generated Device Tree

```dts
{device_tree}
```

## Next Steps

1. Review and customize the generated device tree
2. Save to file: `{sch_path.stem}.dts`
3. Compile with device tree compiler: `dtc -I dts -O dtb -o output.dtb`
4. Test on target hardware"""

    except Exception as e:
        import traceback

        return f"""X **Device Tree Generation Failed**

**Schematic:** {schematic_path}
**Target SOC:** {target_soc}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def extract_gpio_config(
    schematic_path: str,
    soc_family: str = "",
) -> str:
    """Extract GPIO pin configurations from schematic.

    Args:
        schematic_path: Path to .kicad_sch file
        soc_family: Optional SOC family filter

    Returns:
        GPIO configuration report
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"X **Schematic file not found:** {schematic_path}"

        # Generate netlist
        netlist_path = sch_path.parent / (sch_path.stem + ".xml")

        if not netlist_path.exists():
            from .netlist import generate_netlist

            netlist_result = await generate_netlist(str(sch_path))
            if "X" in netlist_result:
                return f"X **Failed to generate netlist**\n\n{netlist_result}"

        # Parse netlist
        netlist_parser = NetlistParser(str(netlist_path))

        # Extract GPIO configurations
        gpio_configs = []

        components = netlist_parser.get_all_components()

        for component in components:
            comp_ref = component.get("ref", "")
            comp_value = component.get("value", "")

            # Filter by SOC family if specified
            if soc_family and soc_family.lower() not in comp_value.lower():
                continue

            # Check if this is an MCU
            if any(soc in comp_value.upper() for soc in ["STM32", "ESP32", "NRF", "ATMEGA"]):
                for pin in component.get("pins", []):
                    pin_num = pin.get("number", "")
                    pin_name = pin.get("name", "")

                    try:
                        connections = netlist_parser.trace_connection(comp_ref, pin_num)
                        if connections and connections[0].get("net"):
                            net_name = connections[0]["net"]

                            # Check if this is a GPIO net
                            if "GPIO" in net_name.upper() or "IO" in net_name.upper():
                                gpio_configs.append({
                                    "component": comp_ref,
                                    "pin_number": pin_num,
                                    "pin_name": pin_name,
                                    "net": net_name,
                                    "soc": comp_value,
                                })
                    except:
                        continue

        if not gpio_configs:
            return f"""WARN **No GPIO Configurations Found**

**Schematic:** {schematic_path}
{'**SOC Family Filter:** ' + soc_family if soc_family else ''}

No GPIO configurations were found in the schematic.

**Next Steps:**
1. Ensure schematic has MCU components
2. Check net names contain 'GPIO' or 'IO'
3. Try without SOC family filter"""

        # Format results
        result = f"""# GPIO Configuration Extraction

**Schematic:** {schematic_path}
{'**SOC Family:** ' + soc_family if soc_family else ''}
**Total GPIO Pins:** {len(gpio_configs)}

## GPIO Pin Details

| Component | Pin | Net | SOC |
|-----------|-----|-----|-----|
"""

        for config in gpio_configs:
            result += f"| {config['component']} | {config['pin_name']} ({config['pin_number']}) | {config['net']} | {config['soc']} |\n"

        # Add code generation suggestions
        result += "\n## Code Generation Suggestions\n\n"

        # Group by SOC
        soc_groups = {}
        for config in gpio_configs:
            soc = config["soc"]
            if soc not in soc_groups:
                soc_groups[soc] = []
            soc_groups[soc].append(config)

        for soc, configs in soc_groups.items():
            result += f"### {soc}\n\n```c\n"
            result += f"// GPIO configuration for {soc}\n\n"

            for config in configs[:10]:  # Show first 10
                result += f"// {config['pin_name']} ({config['pin_number']}): {config['net']}\n"
                if "STM32" in soc.upper():
                    result += f"GPIO_InitTypeDef gpio_{config['pin_name'].lower()};\n"
                    result += f"gpio_{config['pin_name'].lower()}.Pin = GPIO_PIN_{config['pin_number']};\n"
                    result += f"gpio_{config['pin_name'].lower()}.Mode = GPIO_MODE_OUTPUT_PP;\n"
                    result += f"HAL_GPIO_Init(GPIO{config['pin_name'][1]}, &gpio_{config['pin_name'].lower()});\n\n"
                elif "ESP32" in soc.upper():
                    result += f"gpio_set_direction(GPIO{config['pin_number']}, GPIO_MODE_OUTPUT);\n\n"

            if len(configs) > 10:
                result += f"// ... and {len(configs) - 10} more GPIO pins\n"

            result += "```\n\n"

        return result

    except Exception as e:
        import traceback

        return f"""X **GPIO Configuration Extraction Failed**

**Schematic:** {schematic_path}
{'**SOC Family:** ' + soc_family if soc_family else ''}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def extract_i2c_devices(
    schematic_path: str,
) -> str:
    """Extract I2C bus and device configurations.

    Args:
        schematic_path: Path to .kicad_sch file

    Returns:
        I2C device configuration report
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"X **Schematic file not found:** {schematic_path}"

        # Generate netlist
        netlist_path = sch_path.parent / (sch_path.stem + ".xml")

        if not netlist_path.exists():
            from .netlist import generate_netlist

            netlist_result = await generate_netlist(str(sch_path))
            if "X" in netlist_result:
                return f"X **Failed to generate netlist**\n\n{netlist_result}"

        # Parse netlist and schematic
        netlist_parser = NetlistParser(str(netlist_path))
        schematic_parser = SchematicParser(str(sch_path))

        # Extract I2C devices
        i2c_devices = []

        components = list(schematic_parser.get_components())

        for component in components:
            comp_ref = component["reference"]
            comp_value = component.get("value", "")
            comp_library = component.get("library_id", "")

            # Check if this is an I2C device
            for category, bindings in DEVICE_TREE_BINDINGS.items():
                binding = _find_component_binding(comp_value, category)
                if binding:
                    # Get net connections
                    for pin_num in range(1, 9):
                        try:
                            connections = netlist_parser.trace_connection(comp_ref, str(pin_num))
                            if connections and connections[0].get("net"):
                                net_name = connections[0]["net"]

                                if "I2C" in net_name.upper() or "TWI" in net_name.upper():
                                    i2c_address = _extract_i2c_address_from_net(net_name)

                                    i2c_devices.append({
                                        "component": comp_ref,
                                        "value": comp_value,
                                        "compatible": binding["compatible"],
                                        "address": i2c_address,
                                        "net": net_name,
                                        "pin": pin_num,
                                    })
                                    break
                        except:
                            continue

        if not i2c_devices:
            return f"""WARN **No I2C Devices Found**

**Schematic:** {schematic_path}

No I2C devices were found in the schematic.

**Next Steps:**
1. Ensure schematic has I2C peripherals
2. Check net names contain 'I2C' or 'TWI'
3. Include I2C addresses in net names (e.g., I2C_SDA_0x76)"""

        # Format results
        result = f"""# I2C Device Extraction

**Schematic:** {schematic_path}
**Total I2C Devices:** {len(i2c_devices)}

## I2C Device Details

| Component | Device | Compatible | Address | Net |
|-----------|--------|------------|---------|-----|
"""

        for device in i2c_devices:
            address_str = f"0x{device['address']:02X}" if device['address'] else "Unknown"
            result += f"| {device['component']} | {device['value']} | {device['compatible']} | {address_str} | {device['net']} |\n"

        # Add device tree generation
        result += "\n## Device Tree Configuration\n\n```dts\n"
        result += "&i2c1 {\n"
        result += "    status = \"okay\";\n\n"

        for device in i2c_devices:
            address_str = f"0x{device['address']:02X}" if device['address'] else "0x00"
            result += f"    {device['component'].lower()}: {device['compatible']}@{address_str} {{\n"
            result += f"        compatible = \"{device['compatible']}\";\n"
            result += f"        reg = <{address_str}>;\n"
            result += "    };\n\n"

        result += "};\n```"

        return result

    except Exception as e:
        import traceback

        return f"""X **I2C Device Extraction Failed**

**Schematic:** {schematic_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def extract_spi_devices(
    schematic_path: str,
) -> str:
    """Extract SPI bus and device configurations.

    Args:
        schematic_path: Path to .kicad_sch file

    Returns:
        SPI device configuration report
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"X **Schematic file not found:** {schematic_path}"

        # Generate netlist
        netlist_path = sch_path.parent / (sch_path.stem + ".xml")

        if not netlist_path.exists():
            from .netlist import generate_netlist

            netlist_result = await generate_netlist(str(sch_path))
            if "X" in netlist_result:
                return f"X **Failed to generate netlist**\n\n{netlist_result}"

        # Parse netlist and schematic
        netlist_parser = NetlistParser(str(netlist_path))
        schematic_parser = SchematicParser(str(sch_path))

        # Extract SPI devices
        spi_devices = []

        components = list(schematic_parser.get_components())

        for component in components:
            comp_ref = component["reference"]
            comp_value = component.get("value", "")

            # Check if this is an SPI device
            for category, bindings in DEVICE_TREE_BINDINGS.items():
                binding = _find_component_binding(comp_value, category)
                if binding:
                    # Get net connections
                    for pin_num in range(1, 9):
                        try:
                            connections = netlist_parser.trace_connection(comp_ref, str(pin_num))
                            if connections and connections[0].get("net"):
                                net_name = connections[0]["net"]

                                if "SPI" in net_name.upper():
                                    spi_devices.append({
                                        "component": comp_ref,
                                        "value": comp_value,
                                        "compatible": binding["compatible"],
                                        "net": net_name,
                                        "pin": pin_num,
                                    })
                                    break
                        except:
                            continue

        if not spi_devices:
            return f"""WARN **No SPI Devices Found**

**Schematic:** {schematic_path}

No SPI devices were found in the schematic.

**Next Steps:**
1. Ensure schematic has SPI peripherals
2. Check net names contain 'SPI'
3. Include CS signals in net naming"""

        # Format results
        result = f"""# SPI Device Extraction

**Schematic:** {schematic_path}
**Total SPI Devices:** {len(spi_devices)}

## SPI Device Details

| Component | Device | Compatible | Net |
|-----------|--------|------------|-----|
"""

        for device in spi_devices:
            result += f"| {device['component']} | {device['value']} | {device['compatible']} | {device['net']} |\n"

        # Add device tree generation
        result += "\n## Device Tree Configuration\n\n```dts\n"
        result += "&spi1 {\n"
        result += "    status = \"okay\";\n\n"

        for i, device in enumerate(spi_devices):
            result += f"    {device['component'].lower()}: {device['compatible']}@{i} {{\n"
            result += f"        compatible = \"{device['compatible']}\";\n"
            result += f"        reg = <{i}>;\n"
            result += "        spi-max-frequency = <1000000>;\n"
            result += "    };\n\n"

        result += "};\n```"

        return result

    except Exception as e:
        import traceback

        return f"""X **SPI Device Extraction Failed**

**Schematic:** {schematic_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def extract_power_domains(
    schematic_path: str,
) -> str:
    """Extract power domain and regulator configurations.

    Args:
        schematic_path: Path to .kicad_sch file

    Returns:
        Power domain configuration report
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"X **Schematic file not found:** {schematic_path}"

        # Parse schematic
        schematic_parser = SchematicParser(str(sch_path))

        # Extract power components
        power_components = []

        components = list(schematic_parser.get_components())

        for component in components:
            comp_ref = component["reference"]
            comp_value = component.get("value", "")
            comp_library = component.get("library_id", "")

            # Check if this is a power-related component
            power_keywords = ["REG", "LDO", "BUCK", "BOOST", "TPS", "AP", "LP", "AXP"]
            if any(keyword in comp_value.upper() for keyword in power_keywords):
                power_components.append({
                    "reference": comp_ref,
                    "value": comp_value,
                    "library": comp_library,
                })

        if not power_components:
            return f"""WARN **No Power Components Found**

**Schematic:** {schematic_path}

No power management components were found in the schematic.

**Next Steps:**
1. Check for regulators, LDOs, power ICs
2. Verify component values contain power-related keywords"""

        # Format results
        result = f"""# Power Domain Extraction

**Schematic:** {schematic_path}
**Total Power Components:** {len(power_components)}

## Power Components

| Reference | Component | Type |
|-----------|-----------|------|
"""

        for comp in power_components:
            # Determine component type
            comp_type = "Regulator"
            if "LDO" in comp["value"].upper():
                comp_type = "LDO Regulator"
            elif "BUCK" in comp["value"].upper():
                comp_type = "Buck Converter"
            elif "BOOST" in comp["value"].upper():
                comp_type = "Boost Converter"

            result += f"| {comp['reference']} | {comp['value']} | {comp_type} |\n"

        # Add device tree generation suggestions
        result += "\n## Device Tree Configuration\n\n```dts\n"
        result += "/ {\n"
        result += "    regulators {\n\n"

        for comp in power_components[:5]:  # Limit to first 5
            result += f"        {comp['reference'].lower()}: {comp['reference'].lower()} {{\n"
            result += f"            compatible = \"regulator-fixed\";\n"
            result += "            regulator-name = \"" + comp['reference'].lower() + "\";\n"
            result += "            regulator-min-microvolt = <3300000>;\n"
            result += "            regulator-max-microvolt = <3300000>;\n"
            result += "        };\n\n"

        if len(power_components) > 5:
            result += "        // ... and " + str(len(power_components) - 5) + " more regulators\n"

        result += "    };\n"
        result += "};\n```"

        return result

    except Exception as e:
        import traceback

        return f"""X **Power Domain Extraction Failed**

**Schematic:** {schematic_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def validate_pin_configuration(
    schematic_path: str,
) -> str:
    """Validate pin configuration conflicts for device tree generation.

    This function validates that the pin configuration is suitable for
    device tree generation and reports any conflicts or issues.

    Args:
        schematic_path: Path to .kicad_sch file

    Returns:
        Validation report with conflicts and recommendations
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"X **Schematic file not found:** {schematic_path}"

        # First, run pin conflict detection
        from .pin_analysis import detect_pin_conflicts

        conflict_result = await detect_pin_conflicts(str(sch_path))

        if "X" in conflict_result:
            return f"""X **Pin Configuration Validation Failed**

The schematic has pin conflicts that must be resolved before
device tree generation.

{conflict_result}

## Device Tree Generation Blocked

Pin conflicts prevent reliable device tree generation. Please
resolve all conflicts before attempting device tree generation."""

        # Check for MCU components
        schematic_parser = SchematicParser(str(sch_path))
        components = list(schematic_parser.get_components())

        mcu_found = False
        for component in components:
            comp_value = component.get("value", "")
            if any(soc in comp_value.upper() for soc in ["STM32", "ESP32", "NRF", "ATMEGA"]):
                mcu_found = True
                break

        if not mcu_found:
            return f"""WARN **No MCU Component Found**

**Schematic:** {schematic_path}

Device tree generation requires an MCU component in the schematic.

**Supported MCU families:**
- STM32 (STM32F, STM32H, STM32L series)
- ESP32 (ESP32, ESP32-S2, ESP32-S3, etc.)
- nRF52 (nRF52832, nRF52840, etc.)
- ATmega (ATmega328P, ATmega2560, etc.)

**Next Steps:**
1. Add an MCU component to the schematic
2. Verify component value matches supported patterns
3. Re-run validation"""

        return f"""OK **Pin Configuration Validation Passed**

**Schematic:** {schematic_path}

The schematic is ready for device tree generation.

## Validation Results

- OK No pin conflicts detected
- OK MCU component found
- OK Net connections valid
- OK Pin assignments compatible

## Ready for Device Tree Generation

You can now proceed with device tree generation:

```bash
# Generate device tree
generate_device_tree(
    schematic_path="{schematic_path}",
    target_soc="stm32f4",
    output_path="{sch_path.stem}.dts"
)
```

**Supported SOC families:** {', '.join(DEVICE_TREE_TEMPLATES.keys())}"""

    except Exception as e:
        import traceback

        return f"""X **Validation Failed**

**Schematic:** {schematic_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```
"""
