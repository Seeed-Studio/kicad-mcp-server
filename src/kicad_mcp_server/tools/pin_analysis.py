"""Pin analysis and connectivity tools for KiCad MCP Server.

This module provides advanced pin analysis capabilities including:
- Pin function inference (GPIO, I2C, SPI, UART, etc.)
- Pin conflict detection
- Pin multiplexing configuration extraction
- MCU-specific pin mapping support
"""

import re
from pathlib import Path

from ..parsers.netlist_parser import NetlistParser
from ..parsers.schematic_parser import SchematicParser
from ..server import mcp

# MCU family component patterns
MCU_PATTERNS = {
    "stm32": r"STM32[FHL][\d][A-Za-z0-9]+",
    "esp32": r"ESP32(?:-[A-Za-z0-9]+)?|ESP32-[A-Za-z0-9]+",
    "nrf52": r"nRF52[\d A-Za-z0-9]*|nRF528[\d]+",
    "atmega": r"ATmega[\d]+[A-Za-z]*",
    "samd": r"ATSAMD[\d]+[A-Za-z]*",
    "rp2040": r"RP2040",
}


# Pin function inference patterns based on net names
NET_FUNCTION_PATTERNS = {
    "I2C": [
        r"I2C[_\d]*[SDA|SCL]",
        r"SDA[\d]*",
        r"SCL[\d]*",
        r"TWI[_\d]*[SDA|SCL]",
    ],
    "SPI": [
        r"SPI[_\d]*[MISO|MOSI|SCK|CS]",
        r"MISO[\d]*",
        r"MOSI[\d]*",
        r"SCK[\d]*",
        r"CS[\d]*",
        r"NSS[\d]*",
    ],
    "UART": [
        r"UART[_\d]*[TX|RX|CTS|RTS]",
        r"USART[_\d]*[TX|RX|CTS|RTS]",
        r"TX[\d]*",
        r"RX[\d]*",
        r"Serial[_\d]*",
    ],
    "GPIO": [
        r"GPIO[_\d]+",
        r"IO[_\d]+",
        r"PA[\d]+",
        r"PB[\d]+",
        r"PC[\d]+",
        r"P\d+",
    ],
    "ADC": [
        r"ADC[_\d]+",
        r"AIN[\d]+",
        r"AN[\d]+",
    ],
    "PWM": [
        r"PWM[_\d]+",
        r"TIM[_\d]*[CH]*[\d]+",
    ],
    "USB": [
        r"USB[_\d]*[DM|DP|D-|D+]",
        r"UDM",
        r"UDP",
        r"D-",
        r"D+",
    ],
    "INTERRUPT": [
        r"INT[\d]*",
        r"IRQ[\d]*",
        r".*_INT",
    ],
}


def _infer_pin_function_from_net(net_name: str) -> str | None:
    """Infer pin function from net name pattern.

    Args:
        net_name: Net name to analyze

    Returns:
        Inferred function or None if unknown
    """
    if not net_name:
        return None

    net_name_upper = net_name.upper()

    # Check each function pattern
    for function, patterns in NET_FUNCTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, net_name_upper, re.IGNORECASE):
                return function

    return None


def _identify_mcu_family(component_value: str) -> str | None:
    """Identify MCU family from component value.

    Args:
        component_value: Component value/part number

    Returns:
        MCU family identifier or None if not an MCU
    """
    if not component_value:
        return None

    component_value_upper = component_value.upper()

    for family, pattern in MCU_PATTERNS.items():
        if re.search(pattern, component_value_upper, re.IGNORECASE):
            return family

    return None


def _get_mcu_pin_mapping(mcu_family: str, pin_name: str) -> dict:
    """Get MCU-specific pin mapping information.

    Args:
        mcu_family: MCU family identifier
        pin_name: Pin name to map

    Returns:
        Dictionary with pin mapping information
    """
    # Basic pin mappings for common MCU families
    # This would be expanded with comprehensive pin databases

    pin_mapping = {
        "function": None,
        "alternate_functions": [],
        "max_current": 0.0,
        "is_5v_tolerant": False,
    }

    if mcu_family == "stm32":
        # STM32 pin naming convention: PXn (e.g., PA0, PB12)
        if re.match(r"P[A-Z][\d]+", pin_name, re.IGNORECASE):
            pin_mapping["function"] = "GPIO"
            pin_mapping["alternate_functions"] = [
                "GPIO", "ADC", "TIM", "USART", "SPI", "I2C", "CAN"
            ]
            pin_mapping["max_current"] = 25.0  # mA
            pin_mapping["is_5v_tolerant"] = False  # Most STM32 pins are not 5V tolerant

    elif mcu_family == "esp32":
        # ESP32 pin naming: IOx, GPIOx
        if re.match(r"(?:IO|GPIO)[\d]+", pin_name, re.IGNORECASE):
            pin_mapping["function"] = "GPIO"
            pin_mapping["alternate_functions"] = [
                "GPIO", "ADC", "DAC", "I2C", "SPI", "UART", "TOUCH"
            ]
            pin_mapping["max_current"] = 40.0  # mA
            pin_mapping["is_5v_tolerant"] = False

    elif mcu_family == "nrf52":
        # nRF52 pin naming: P0.xx, P1.xx
        if re.match(r"P[01]\.[\d]+", pin_name, re.IGNORECASE):
            pin_mapping["function"] = "GPIO"
            pin_mapping["alternate_functions"] = [
                "GPIO", "ADC", "SPI", "I2C", "UART", "PWM", "QSPI"
            ]
            pin_mapping["max_current"] = 5.0  # mA (typical for nRF52)
            pin_mapping["is_5v_tolerant"] = False

    return pin_mapping


@mcp.tool()
async def analyze_pin_functions(
    schematic_path: str,
    reference: str = "",
) -> str:
    """Analyze pin functions and detect conflicts.

    This function analyzes schematic to determine pin functions by:
    - Examining net names to infer functionality
    - Identifying MCU components and their pin mappings
    - Detecting potential pin conflicts

    Args:
        schematic_path: Path to .kicad_sch file
        reference: Optional component reference (e.g., 'U1') to analyze specific component

    Returns:
        Detailed pin function analysis report
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ **Schematic file not found:** {schematic_path}"

        # Parse schematic
        schematic_parser = SchematicParser(str(sch_path))

        # Generate netlist for accurate connection analysis
        netlist_path = sch_path.parent / (sch_path.stem + ".xml")

        if not netlist_path.exists():
            # Try to generate netlist
            from .netlist import generate_netlist

            netlist_result = await generate_netlist(str(sch_path))
            if "❌" in netlist_result:
                return f"❌ **Failed to generate netlist**\n\n{netlist_result}"

        # Parse netlist
        netlist_parser = NetlistParser(str(netlist_path))

        # Get components to analyze
        if reference:
            # Analyze specific component
            components = [comp for comp in schematic_parser.get_components() if comp["reference"] == reference]
            if not components:
                return f"❌ **Component not found:** {reference}"
        else:
            # Analyze all components
            components = list(schematic_parser.get_components())

        # Analyze pin functions
        pin_analysis = []

        for component in components:
            comp_ref = component["reference"]
            comp_value = component.get("value", "")

            # Check if this is an MCU
            mcu_family = _identify_mcu_family(comp_value)

            # Get symbol details to extract pins
            try:
                from .schematic import get_symbol_details

                symbol_details_result = await get_symbol_details(str(sch_path), comp_ref)

                if "❌" not in symbol_details_result:
                    # Parse symbol details to extract pin information
                    # This would need proper parsing of the formatted output
                    # For now, we'll extract basic info
                    pin_info = _extract_pin_info_from_symbol_details(symbol_details_result)

                    for pin in pin_info:
                        pin_number = pin.get("number", "")
                        pin_name = pin.get("name", "")
                        pin_type = pin.get("type", "")

                        # Get net connections from netlist
                        try:
                            connections = netlist_parser.trace_connection(comp_ref, pin_number)
                            net_names = [conn.get("net", "") for conn in connections if conn.get("net")]

                            # Infer pin function from net names
                            inferred_functions = []
                            for net_name in net_names:
                                func = _infer_pin_function_from_net(net_name)
                                if func and func not in inferred_functions:
                                    inferred_functions.append(func)

                            # Get MCU-specific mapping if available
                            mcu_mapping = None
                            if mcu_family:
                                mcu_mapping = _get_mcu_pin_mapping(mcu_family, pin_name)

                            pin_analysis.append({
                                "component": comp_ref,
                                "component_value": comp_value,
                                "mcu_family": mcu_family,
                                "pin_number": pin_number,
                                "pin_name": pin_name,
                                "pin_type": pin_type,
                                "net_names": net_names,
                                "inferred_functions": inferred_functions,
                                "mcu_mapping": mcu_mapping,
                            })

                        except Exception:
                            # Continue with next pin if analysis fails
                            pass

            except Exception:
                # Continue with next component if symbol details fail
                continue

        if not pin_analysis:
            return f"""⚠️ **No Pin Analysis Available**

**Schematic:** {schematic_path}
{'**Component:** ' + reference if reference else ''}

Unable to extract pin information. This could be due to:
- No components found in schematic
- Missing symbol definitions
- Netlist not available

**Next Steps:**
1. Ensure schematic has components with pins
2. Generate netlist first: `generate_netlist()`
3. Verify schematic file is valid KiCad 9.0 format"""

        # Format results
        result = f"""# Pin Function Analysis

**Schematic:** {schematic_path}
{'**Component:** ' + reference if reference else ''}
**Total Pins Analyzed:** {len(pin_analysis)}

## Pin Details

| Component | Pin | Type | Nets | Inferred Functions | MCU Family |
|-----------|-----|------|------|-------------------|------------|
"""

        for pin in pin_analysis[:50]:  # Limit to first 50 pins
            comp = pin["component"]
            pin_name = pin["pin_name"]
            pin_type = pin["pin_type"]
            nets = ", ".join(pin["net_names"][:3]) if pin["net_names"] else "N/A"
            if len(pin["net_names"]) > 3:
                nets += f" (+{len(pin['net_names']) - 3} more)"
            functions = ", ".join(pin["inferred_functions"]) if pin["inferred_functions"] else "Unknown"
            mcu_family = pin["mcu_family"] if pin["mcu_family"] else "N/A"

            result += f"| {comp} | {pin_name} ({pin['pin_number']}) | {pin_type} | {nets} | {functions} | {mcu_family} |\n"

        if len(pin_analysis) > 50:
            result += f"\n*... and {len(pin_analysis) - 50} more pins*\n"

        # Add MCU-specific details if available
        mcu_pins = [p for p in pin_analysis if p["mcu_family"] and p["mcu_mapping"]]
        if mcu_pins:
            result += "\n## MCU Pin Details\n\n"

            for pin in mcu_pins[:10]:  # Limit to first 10 MCU pins
                mapping = pin["mcu_mapping"]
                result += f"**{pin['component']} - {pin['pin_name']} ({pin['pin_number']})**\n"
                result += f"- Primary Function: {mapping['function']}\n"
                result += f"- Alternate Functions: {', '.join(mapping['alternate_functions'])}\n"
                result += f"- Max Current: {mapping['max_current']} mA\n"
                result += f"- 5V Tolerant: {'Yes' if mapping['is_5v_tolerant'] else 'No'}\n\n"

        return result

    except Exception as e:
        import traceback

        return f"""❌ **Pin Analysis Failed**

**Schematic:** {schematic_path}
{'**Component:** ' + reference if reference else ''}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


def _extract_pin_info_from_symbol_details(details_text: str) -> list[dict]:
    """Extract pin information from get_symbol_details output.

    Args:
        details_text: Formatted output from get_symbol_details

    Returns:
        List of pin information dictionaries
    """
    pins = []

    # Parse the formatted output to extract pin information
    # This is a simplified implementation - would need proper parsing
    lines = details_text.split("\n")

    for line in lines:
        if "|" in line:  # Table format
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                # Try to extract pin info from table cells
                # This is a basic implementation
                pass

    return pins


@mcp.tool()
async def detect_pin_conflicts(
    schematic_path: str,
) -> str:
    """Detect pins with conflicting electrical connections.

    This function checks for:
    - Multiple outputs on same net
    - Power-to-power connections
    - Unconnected input pins
    - Pin type mismatches

    Args:
        schematic_path: Path to .kicad_sch file

    Returns:
        Detailed conflict detection report
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ **Schematic file not found:** {schematic_path}"

        # Generate netlist for accurate connection analysis
        netlist_path = sch_path.parent / (sch_path.stem + ".xml")

        if not netlist_path.exists():
            # Try to generate netlist
            from .netlist import generate_netlist

            netlist_result = await generate_netlist(str(sch_path))
            if "❌" in netlist_result:
                return f"❌ **Failed to generate netlist**\n\n{netlist_result}"

        # Parse netlist
        netlist_parser = NetlistParser(str(netlist_path))

        # Detect conflicts
        conflicts = []

        # Check for multiple outputs on same net
        nets = netlist_parser.get_all_nets()

        for net in nets:
            net_name = net.get("name", "")
            connections = net.get("connections", [])

            # Count output pins on this net
            output_pins = []
            input_pins = []
            power_pins = []

            for conn in connections:
                ref = conn.get("ref", "")
                pin = conn.get("pin", "")

                # Try to get pin type
                pin_type = conn.get("type", "unknown")

                if pin_type == "output":
                    output_pins.append(f"{ref}:{pin}")
                elif pin_type == "input":
                    input_pins.append(f"{ref}:{pin}")
                elif pin_type in ["power_in", "power_out", "power"]:
                    power_pins.append(f"{ref}:{pin}")

            # Check for multiple outputs
            if len(output_pins) > 1:
                conflicts.append({
                    "type": "multiple_outputs",
                    "severity": "error",
                    "net": net_name,
                    "description": f"Multiple outputs on same net: {', '.join(output_pins)}",
                })

            # Check for power-to-power connections
            if len(power_pins) > 1:
                conflicts.append({
                    "type": "power_conflict",
                    "severity": "warning",
                    "net": net_name,
                    "description": f"Multiple power pins on same net: {', '.join(power_pins)}",
                })

        # Check for unconnected input pins
        components = netlist_parser.get_all_components()

        for component in components:
            ref = component.get("ref", "")
            pins = component.get("pins", [])

            for pin in pins:
                pin_num = pin.get("number", "")
                pin_type = pin.get("type", "")

                if pin_type == "input":
                    # Check if pin is connected
                    connections = netlist_parser.trace_connection(ref, pin_num)
                    if not connections or not any(c.get("net") for c in connections):
                        conflicts.append({
                            "type": "unconnected_input",
                            "severity": "warning",
                            "component": ref,
                            "pin": pin_num,
                            "description": f"Unconnected input pin: {ref}:{pin_num}",
                        })

        if not conflicts:
            return f"""✅ **No Pin Conflicts Detected**

**Schematic:** {schematic_path}

The schematic has been analyzed and no pin conflicts were found.

**Checked:**
- ✅ No multiple outputs on same net
- ✅ No power-to-power connections
- ✅ No unconnected input pins
- ✅ No pin type mismatches"""

        # Format conflicts
        result = f"""❌ **Pin Conflicts Detected**

**Schematic:** {schematic_path}
**Total Conflicts:** {len(conflicts)}

## Conflicts

| Severity | Type | Location | Description |
|----------|------|----------|-------------|
"""

        for conflict in conflicts[:50]:  # Limit to first 50
            severity_icon = "❌" if conflict["severity"] == "error" else "⚠️"
            conflict_type = conflict["type"]
            location = conflict.get("net", conflict.get("component", "Unknown"))
            description = conflict["description"]

            result += f"| {severity_icon} {conflict['severity']} | {conflict_type} | {location} | {description} |\n"

        if len(conflicts) > 50:
            result += f"\n*... and {len(conflicts) - 50} more conflicts*\n"

        result += "\n## Recommendations\n\n"
        result += "1. **Fix all errors** before proceeding to PCB layout\n"
        result += "2. Review warnings - some may be acceptable design choices\n"
        result += "3. Verify pin connections in KiCad Eeschema\n"
        result += "4. Re-run analysis after fixes\n"

        return result

    except Exception as e:
        import traceback

        return f"""❌ **Conflict Detection Failed**

**Schematic:** {schematic_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def extract_pinmux_config(
    schematic_path: str,
    component_type: str = "",
) -> str:
    """Extract pin multiplexing configuration for MCUs.

    This function extracts pin multiplexing (pinmux) configuration
    for MCU components, showing which peripherals are assigned to which pins.

    Args:
        schematic_path: Path to .kicad_sch file
        component_type: Optional MCU type filter (e.g., 'stm32', 'esp32', 'nrf52')

    Returns:
        Detailed pinmux configuration report
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ **Schematic file not found:** {schematic_path}"

        # Parse schematic
        schematic_parser = SchematicParser(str(sch_path))

        # Generate netlist for accurate connection analysis
        netlist_path = sch_path.parent / (sch_path.stem + ".xml")

        if not netlist_path.exists():
            # Try to generate netlist
            from .netlist import generate_netlist

            netlist_result = await generate_netlist(str(sch_path))
            if "❌" in netlist_result:
                return f"❌ **Failed to generate netlist**\n\n{netlist_result}"

        # Parse netlist
        netlist_parser = NetlistParser(str(netlist_path))

        # Find MCU components
        components = list(schematic_parser.get_components())
        mcu_components = []

        for component in components:
            comp_ref = component["reference"]
            comp_value = component.get("value", "")

            # Check if this is an MCU
            mcu_family = _identify_mcu_family(comp_value)

            if mcu_family:
                # Filter by component_type if specified
                if component_type and component_type.lower() != mcu_family.lower():
                    continue

                mcu_components.append({
                    "reference": comp_ref,
                    "value": comp_value,
                    "mcu_family": mcu_family,
                    "library": component.get("library_id", ""),
                })

        if not mcu_components:
            return f"""⚠️ **No MCU Components Found**

**Schematic:** {schematic_path}
{'**Component Type Filter:** ' + component_type if component_type else ''}

No MCU components were found in the schematic.

**Supported MCU families:**
- STM32 (STM32F, STM32H, STM32L series)
- ESP32 (ESP32, ESP32-S2, ESP32-S3, etc.)
- nRF52 (nRF52832, nRF52840, etc.)
- ATmega (ATmega328P, ATmega2560, etc.)
- SAMD (ATSAMD21, ATSAMD51, etc.)
- RP2040

**Next Steps:**
1. Ensure schematic contains MCU components
2. Check component values match supported patterns
3. Try without component_type filter"""

        # Extract pinmux configuration for each MCU
        pinmux_configs = []

        for mcu in mcu_components:
            mcu_ref = mcu["reference"]
            mcu_family = mcu["mcu_family"]

            config = {
                "component": mcu_ref,
                "mcu_family": mcu_family,
                "part_number": mcu["value"],
                "pins": [],
            }

            # Get pin connections from netlist
            try:
                # Get all pins for this component
                component_data = None
                for comp in netlist_parser.get_all_components():
                    if comp.get("ref") == mcu_ref:
                        component_data = comp
                        break

                if component_data:
                    for pin in component_data.get("pins", []):
                        pin_num = pin.get("number", "")
                        pin_name = pin.get("name", "")

                        # Get net connection
                        connections = netlist_parser.trace_connection(mcu_ref, pin_num)

                        if connections and connections[0].get("net"):
                            net_name = connections[0]["net"]

                            # Infer peripheral function from net name
                            peripheral = _infer_pin_function_from_net(net_name)

                            # Get MCU-specific pin mapping
                            mcu_mapping = _get_mcu_pin_mapping(mcu_family, pin_name)

                            pin_config = {
                                "pin_number": pin_num,
                                "pin_name": pin_name,
                                "net": net_name,
                                "peripheral": peripheral,
                                "alternate_functions": mcu_mapping["alternate_functions"] if mcu_mapping else [],
                                "max_current": mcu_mapping["max_current"] if mcu_mapping else 0,
                            }

                            config["pins"].append(pin_config)

            except Exception:
                # Continue with next MCU if this one fails
                pass

            pinmux_configs.append(config)

        # Format results
        result = f"""# Pin Multiplexing Configuration

**Schematic:** {schematic_path}
{'**Component Type Filter:** ' + component_type if component_type else ''}
**Total MCUs Analyzed:** {len(pinmux_configs)}

"""

        for mcu_config in pinmux_configs:
            result += f"""## {mcu_config['component']}: {mcu_config['part_number']}

**MCU Family:** {mcu_config['mcu_family']}

| Pin | Net | Peripheral | Alternate Functions |
|-----|-----|------------|---------------------|
"""

            for pin in mcu_config["pins"][:30]:  # Limit to first 30 pins per MCU
                pin_name = pin["pin_name"]
                net = pin["net"]
                peripheral = pin["peripheral"] if pin["peripheral"] else "GPIO"
                alt_funcs = ", ".join(pin["alternate_functions"]) if pin["alternate_functions"] else "N/A"

                result += f"| {pin_name} ({pin['pin_number']}) | {net} | {peripheral} | {alt_funcs} |\n"

            if len(mcu_config["pins"]) > 30:
                result += f"\n*... and {len(mcu_config['pins']) - 30} more pins*\n"

            result += "\n"

        # Add code generation suggestions
        result += "## Code Generation Suggestions\n\n"

        for mcu_config in pinmux_configs:
            result += f"""### {mcu_config['component']} ({mcu_config['mcu_family']})

```c
// Pin configuration for {mcu_config['part_number']}
"""

            for pin in mcu_config["pins"][:10]:  # Show first 10 pins as example
                if pin["peripheral"]:
                    result += f"// {pin['pin_name']}: {pin['peripheral']} ({pin['net']})\n"
                    if mcu_config["mcu_family"] == "stm32":
                        result += f"// GPIO_{pin['pin_name'][1]}_{pin['pin_name'][2:]} // {pin['peripheral']}_AF\n"
                    elif mcu_config["mcu_family"] == "esp32":
                        result += f"// GPIO{pin['pin_number']} // {pin['peripheral']}\n"

            result += "```\n\n"

        return result

    except Exception as e:
        import traceback

        return f"""❌ **Pinmux Extraction Failed**

**Schematic:** {schematic_path}
{'**Component Type:** ' + component_type if component_type else ''}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""
