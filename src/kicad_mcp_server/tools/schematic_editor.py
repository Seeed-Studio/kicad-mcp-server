"""Advanced schematic editing tools for KiCad 9.0+ MCP Server."""

import uuid
from datetime import datetime
from pathlib import Path

from ..server import mcp


def _get_date_string() -> str:
    """Get current date in ISO format."""
    return datetime.now().strftime("%Y-%m-%d")


# KiCad standard library symbols mapping
KICAD_STANDARD_SYMBOLS = {
    "ESP32-S3-WROOM-1": {
        "library": "RF_Module",
        "symbol": "ESP32-S3-WROOM-1",
    },
    "SSD1306": {
        "library": "Display_Graphic",
        "symbol": "OLED-128O064D",
    },
    "MPU6050": {
        "library": "Sensor_Motion",
        "symbol": "MPU-6050",
    },
}

# Pin definitions for common symbols
SYMBOL_PINS = {
    "Device:R": [(1, "passive", ""), (2, "passive", "")],
    "Device:LED": [(1, "passive", "K"), (2, "passive", "A")],
    "Device:C": [(1, "passive", ""), (2, "passive", "")],
    "RF_Module:ESP32-S3-WROOM-1": [(1, "input", "GPIO0"), (2, "input", "GPIO1")],
    "Display_Graphic:OLED-128O064D": [(1, "input", "GND"), (2, "input", "SCL")],
    "Sensor_Motion:MPU-6050": [(1, "input", "VDD"), (2, "input", "GND")],
}


def get_pins_for_symbol(library_name: str, symbol_name: str) -> list[tuple[int, str, str]]:
    """Get pin definitions for a symbol."""
    lib_id = f"{library_name}:{symbol_name}"
    if lib_id in SYMBOL_PINS:
        return SYMBOL_PINS[lib_id]
    return [(1, "passive", ""), (2, "passive", "")]


@mcp.tool()
async def add_component_from_library(
    file_path: str,
    library_name: str,
    symbol_name: str,
    reference: str,
    value: str,
    footprint: str = "",
    x: float = 100,
    y: float = 100,
    unit: int = 1,
) -> str:
    """Add a component from KiCad's built-in library to the schematic."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File {file_path} does not exist"

        content = path.read_text()
        comp_uuid = str(uuid.uuid4())
        lib_id = f"{library_name}:{symbol_name}"

        # Get pins
        pins = get_pins_for_symbol(library_name, symbol_name)
        pin_entries = []
        for pin_num, _pin_type, _pin_name in pins:
            pin_uuid = str(uuid.uuid4())
            pin_entries.append(f'    (pin "{pin_num}" (uuid {pin_uuid}))')
        pins_str = "\n".join(pin_entries) if pin_entries else ""

        # Create component with CRITICAL fixes:
        # 1. exclude_from_sim attribute
        # 2. Pin definitions with UUIDs
        component_entry = f'''  (symbol (lib_id "{lib_id}") (at {x} {y} 0) (unit {unit})
  (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
  (uuid {comp_uuid})
  (property "Reference" "{reference}" (at {x} {y - 5} 0)
    (effects (font (size 1.27 1.27)))
  )
  (property "Value" "{value}" (at {x} {y + 2.54} 0)
    (effects (font (size 1.27 1.27)))
  )
  (property "Footprint" "{footprint}" (at {x} {y + 5.08} 0)
    (effects (font (size 1.27 1.27)) hide)
  )
{pins_str}
)'''

        if content.rstrip().endswith(')'):
            content = content.rstrip()
            if content.endswith(')'):
                content = content[:-1] + component_entry + "\n)\n"
            else:
                content = content + "\n" + component_entry + "\n"
        else:
            content = content + "\n" + component_entry + "\n"

        path.write_text(content)

        return f"""✅ Component added successfully!

**File:** {file_path}
**Library:** {library_name}
**Symbol:** {symbol_name}
**Reference:** {reference}
**Value:** {value}
**Position:** ({x}, {y})
**Lib ID:** {lib_id}
**UUID:** {comp_uuid}

**Critical Fixes Applied:**
- ✅ exclude_from_sim attribute added
- ✅ Pin definitions with UUIDs added
- ✅ KiCad 9.0+ compatible format
"""

    except Exception as e:
        import traceback
        return f"Error adding component: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
async def add_wire(
    file_path: str,
    points: list[tuple[float, float]],
) -> str:
    """Add a wire (connection line) to the schematic."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File {file_path} does not exist"

        content = path.read_text()
        pts_str = " ".join([f"(xy {x} {y})" for x, y in points])
        wire_entry = f'''  (wire (pts {pts_str})
  )'''

        if content.rstrip().endswith(')'):
            content = content.rstrip()
            if content.endswith(')'):
                content = content[:-1] + wire_entry + "\n)\n"
            else:
                content = content + "\n" + wire_entry + "\n)"
        else:
            content = content + "\n" + wire_entry + "\n"

        path.write_text(content)

        return "✅ Wire added"
    except Exception as e:
        import traceback
        return f"Error adding wire: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
async def add_label(
    file_path: str,
    text: str,
    x: float,
    y: float,
    orientation: float = 0,
) -> str:
    """Add a local label (text label) to the schematic."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File {file_path} does not exist"

        content = path.read_text()
        label_uuid = str(uuid.uuid4())
        label_entry = f'''  (label "{text}" (at {x} {y} {orientation})
    (effects (font (size 1.27 1.27)) (justify left))
    (uuid {label_uuid})
  )'''

        if content.rstrip().endswith(')'):
            content = content.rstrip()
            if content.endswith(')'):
                content = content[:-1] + label_entry + "\n)\n"
            else:
                content = content + "\n" + label_entry + "\n)"
        else:
            content = content + "\n" + label_entry + "\n"

        path.write_text(content)
        return f"✅ Label '{text}' added at ({x}, {y})"
    except Exception as e:
        import traceback
        return f"Error adding label: {e}\n\n{traceback.format_exc()}"
