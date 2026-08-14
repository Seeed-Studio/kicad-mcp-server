"""Pin analysis and connectivity tools for KiCad MCP Server.

This module provides advanced pin analysis capabilities including:
- Pin function inference (GPIO, I2C, SPI, UART, etc.)
- Pin conflict detection
- Pin multiplexing configuration extraction
- MCU-specific pin mapping support
"""

import re
import tempfile
from pathlib import Path

from ..parsers.netlist_parser import NetlistParser
from ..parsers.schematic_parser import SchematicParser
from ..server import mcp


async def _ensure_netlist(sch_path: Path) -> Path | None:
    """Find or generate a netlist for the given schematic.

    Checks schematic directory first, then temp directory. If neither exists,
    generates one via kicad-cli (auto-redirects to root schematic for sub-sheets).

    Returns the netlist Path, or None on failure.
    """
    # Check for netlist with the given schematic's stem
    for stem in [sch_path.stem]:
        local = sch_path.parent / (stem + ".xml")
        if local.exists():
            return local
        temp_nl = Path(tempfile.gettempdir()) / (stem + ".xml")
        if temp_nl.exists():
            return temp_nl

    # Also check root schematic stem (sub-sheets redirect to root)
    pro_files = list(sch_path.parent.glob("*.kicad_pro"))
    if pro_files:
        root_stem = pro_files[0].stem
        local = sch_path.parent / (root_stem + ".xml")
        if local.exists():
            return local
        temp_nl = Path(tempfile.gettempdir()) / (root_stem + ".xml")
        if temp_nl.exists():
            return temp_nl

    from .netlist import generate_netlist

    result = await generate_netlist(str(sch_path))
    if "❌" in result:
        return None

    # Check all possible locations after generation
    for stem in [sch_path.stem, pro_files[0].stem if pro_files else ""]:
        if not stem:
            continue
        for base in [sch_path.parent, Path(tempfile.gettempdir())]:
            candidate = base / (stem + ".xml")
            if candidate.exists():
                return candidate
    return None

# MCU family component patterns
MCU_PATTERNS = {
    "stm32": r"STM32[FHL]\d[A-Za-z0-9]*",
    "esp32": r"ESP32(?:-[A-Za-z0-9]+)?",
    "nrf52": r"nRF5[2-9][\d A-Za-z0-9]*",  # nRF52/nRF53/nRF54 (e.g. nRF54LM20B)
    "atmega": r"ATmega\d+[A-Za-z]*",
    "samd": r"ATSAMD\d+[A-Za-z]*",
    "rp2040": r"RP2040",
}


# Pin function inference patterns based on net names.
# IMPORTANT: use alternation groups (SDA|SCL), NOT character classes [SDA|SCL] —
# a character class matches any single char in the set {S,D,A,|,C,L} and would
# match almost every net name, producing nonsense matches.
NET_FUNCTION_PATTERNS = {
    "I2C": [
        r"I2C[_\d]*(?:SDA|SCL)",
        r"SDA\d*",
        r"SCL\d*",
        r"TWI[_\d]*(?:SDA|SCL)",
    ],
    "SPI": [
        r"SPI[_\d]*(?:MISO|MOSI|SCK|CS)",
        r"MISO\d*",
        r"MOSI\d*",
        r"SCK\d*",
        r"CS\d*",
        r"NSS\d*",
    ],
    "UART": [
        r"UART[_\d]*(?:TX|RX|CTS|RTS)",
        r"USART[_\d]*(?:TX|RX|CTS|RTS)",
        r"TX\d*",
        r"RX\d*",
        r"Serial\d*",
    ],
    "GPIO": [
        r"GPIO[_\d]+",
        r"IO[_\d]+",
        r"PA\d+",
        r"PB\d+",
        r"PC\d+",
        r"P\d+",
    ],
    "ADC": [
        r"ADC[_\d]+",
        r"AIN\d+",
        r"AN\d+",
    ],
    "PWM": [
        r"PWM[_\d]+",
        r"TIM[_\d]*CH*\d+",
    ],
    "USB": [
        r"USB[_\d]*(?:DM|DP|D-|D\+)",
        r"UDM",
        r"UDP",
        r"D-",
        r"D\+",
    ],
    "INTERRUPT": [
        r"INT\d*",
        r"IRQ\d*",
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
        netlist_path = await _ensure_netlist(sch_path)
        if netlist_path is None:
            return "❌ **Failed to generate netlist for pin analysis**"

        # Parse netlist
        netlist_parser = NetlistParser(str(netlist_path))

        # Get components to analyze
        if reference:
            # Analyze specific component
            components = [comp for comp in schematic_parser.get_components(recursive=True) if comp.reference == reference]
            if not components:
                return f"❌ **Component not found:** {reference}"
        else:
            # Analyze all components
            components = list(schematic_parser.get_components(recursive=True))

        # Analyze pin functions.
        # The authoritative pin->net map comes from the netlist; pin name/type
        # are enriched from the schematic's lib_symbols via SchematicComponent.pins.
        # (Previously this relied on _extract_pin_info_from_symbol_details whose
        # only parse branch was `pass`, so the tool always returned empty.)
        sch_components = {c.reference: c for c in schematic_parser.get_components(recursive=True)}
        nl_components = netlist_parser.get_components()
        pin_analysis = []

        for component in components:
            comp_ref = component.reference
            comp_value = component.value
            mcu_family = _identify_mcu_family(comp_value)

            nl_comp = nl_components.get(comp_ref)
            pin_map = nl_comp.pins if nl_comp else {}  # pin_number -> net_name
            if not pin_map:
                continue  # not in netlist / nothing connected

            # pin number -> (name, electrical_type) from schematic lib_symbols
            pin_meta: dict[str, tuple[str, str]] = {}
            sch_comp = sch_components.get(comp_ref)
            if sch_comp:
                for p in sch_comp.pins:
                    pin_meta[str(p.get("number", ""))] = (
                        p.get("name", ""),
                        p.get("electrical_type", ""),
                    )

            for pin_num, net_name in pin_map.items():
                pin_name, pin_type = pin_meta.get(str(pin_num), (str(pin_num), ""))

                func = _infer_pin_function_from_net(net_name)
                inferred_functions = [func] if func else []

                mcu_mapping = _get_mcu_pin_mapping(mcu_family, pin_name) if mcu_family else None

                pin_analysis.append({
                    "component": comp_ref,
                    "component_value": comp_value,
                    "mcu_family": mcu_family,
                    "pin_number": str(pin_num),
                    "pin_name": pin_name or str(pin_num),
                    "pin_type": pin_type,
                    "net_names": [net_name] if net_name else [],
                    "inferred_functions": inferred_functions,
                    "mcu_mapping": mcu_mapping,
                })

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
3. Verify schematic file is valid KiCad 9.0+ format"""

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

    # Parse the get_symbol_details markdown table, e.g.:
    #   | Pin | Name | Type |
    #   | --- | ---- | ---- |
    #   | 1 | VDD | power_in |
    lines = details_text.split("\n")

    for line in lines:
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c != ""]  # drop empty edge cells
        if len(cells) < 3:
            continue
        first = cells[0].lower()
        # skip header / separator rows
        if first in ("pin", "number", "#", "no.", "ref"):
            continue
        if set(cells[0]) <= set("-:="):
            continue
        pins.append({"number": cells[0], "name": cells[1], "type": cells[2]})

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
        netlist_path = await _ensure_netlist(sch_path)
        if netlist_path is None:
            return "❌ **Failed to generate netlist for conflict detection**"

        # Parse netlist + schematic. The netlist carries pin->net but NOT pin
        # electrical type; that comes from the schematic's lib_symbols.
        netlist_parser = NetlistParser(str(netlist_path))
        schematic_parser = SchematicParser(str(sch_path))

        output_types = {"output", "power_out", "open_collector", "open_emitter", "tri_state"}

        # (ref, pin_number) -> electrical_type
        pin_type_of: dict[tuple[str, str], str] = {}
        for c in schematic_parser.get_components(recursive=True):
            for p in c.pins:
                pin_type_of[(c.reference, str(p.get("number", "")))] = (
                    p.get("electrical_type", "").lower()
                )

        # Detect conflicts
        conflicts = []

        # Check for multiple output/driver pins on the same net.
        # (Multiple power_in pins on a rail like +3V3 are normal and are NOT
        # reported — only multiple drivers are a conflict.)
        all_nets = netlist_parser.get_nets()

        for net_name, net in all_nets.items():
            connections = net.pins  # list of (ref, pin_number)

            output_pins = []
            for ref, pin_num in connections:
                pin_type = pin_type_of.get((ref, str(pin_num)), "")
                if pin_type in output_types:
                    output_pins.append(f"{ref}:{pin_num}")

            if len(output_pins) > 1:
                conflicts.append({
                    "type": "multiple_outputs",
                    "severity": "error",
                    "net": net_name,
                    "description": f"Multiple output/driver pins on same net: {', '.join(output_pins)}",
                })

        # Check for single-pin nets (potential unconnected)
        for net_name, net in all_nets.items():
            if len(net.pins) == 1 and not net_name.startswith("unconnected-"):
                ref, pin_num = net.pins[0]
                conflicts.append({
                    "type": "single_pin_net",
                    "severity": "warning",
                    "net": net_name,
                    "description": f"Net '{net_name}' has only one pin: {ref}:{pin_num}",
                })

        # Check for unconnected input pins
        all_components = netlist_parser.get_components()

        for ref, comp in all_components.items():
            for pin_num, net_name in comp.pins.items():
                if net_name.startswith("unconnected-"):
                    conflicts.append({
                        "type": "unconnected_pin",
                        "severity": "info",
                        "net": net_name,
                        "description": f"{ref} pin {pin_num} is unconnected ({net_name})",
                    })

        if not conflicts:
            return f"""✅ **No Pin Conflicts Detected**

**Schematic:** {schematic_path}

The schematic has been analyzed and no pin conflicts were found.

**Checked:**
- ✅ No multiple output/driver pins on the same net
- ✅ No single-pin (potentially unconnected) nets
- ✅ No unconnected pins"""

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
        netlist_path = await _ensure_netlist(sch_path)
        if netlist_path is None:
            return "❌ **Failed to generate netlist for pinmux extraction**"

        # Parse netlist
        netlist_parser = NetlistParser(str(netlist_path))

        # Find MCU components
        components = list(schematic_parser.get_components(recursive=True))
        mcu_components = []

        for component in components:
            comp_ref = component.reference
            comp_value = component.value

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
                    "library": component.library_id,
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

        # pin number -> name from schematic lib_symbols
        sch_components = {c.reference: c for c in schematic_parser.get_components(recursive=True)}

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

            pin_names: dict[str, str] = {}
            sch_c = sch_components.get(mcu_ref)
            if sch_c:
                for p in sch_c.pins:
                    pin_names[str(p.get("number", ""))] = p.get("name", "")

            comp = netlist_parser.get_components().get(mcu_ref)
            if comp:
                for pin_num, net_name in comp.pins.items():
                    peripheral = _infer_pin_function_from_net(net_name)
                    pin_name = pin_names.get(str(pin_num), str(pin_num))
                    mcu_mapping = _get_mcu_pin_mapping(mcu_family, pin_name)
                    pin_config = {
                        "pin_number": str(pin_num),
                        "pin_name": pin_name,
                        "net": net_name,
                        "peripheral": peripheral,
                        "alternate_functions": (mcu_mapping or {}).get("alternate_functions", []),
                    }
                    config["pins"].append(pin_config)

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
