"""Schematic editing tools for KiCad MCP Server."""

import re
import uuid
from pathlib import Path

from ..server import mcp


def _get_date_string() -> str:
    """Get current date in ISO format."""
    from datetime import datetime

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

# Pin definitions for common symbols (fallback when library not found)
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


def _find_symbol_library_file(library_name: str) -> Path | None:
    """Find the .kicad_sym file for a KiCad symbol library."""
    from ..utils.kicad_version import get_kicad_symbol_dir

    sym_dir = get_kicad_symbol_dir()
    if sym_dir:
        sym_path = sym_dir / f"{library_name}.kicad_sym"
        if sym_path.exists():
            return sym_path
    return None


def _extract_symbol_from_kicad_sym(kicad_sym_path: Path, symbol_name: str) -> str | None:
    """Extract a complete symbol block from a .kicad_sym library file."""
    try:
        content = kicad_sym_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Match the top-level symbol definition (not sub-symbols like "R_0_1")
    pattern = r'\(symbol\s+"' + re.escape(symbol_name) + r'"(?!\w)'
    match = re.search(pattern, content)
    if not match:
        return None

    # Extract balanced block using parenthesis counting
    start = match.start()
    depth = 0
    for i in range(start, len(content)):
        if content[i] == "(":
            depth += 1
        elif content[i] == ")":
            depth -= 1
            if depth == 0:
                return content[start : i + 1]
    return None


def _convert_symbol_to_lib_symbols_format(
    symbol_block: str, library_name: str, symbol_name: str
) -> str:
    """Convert a symbol block from .kicad_sym to lib_symbols format.

    Key changes:
    - Prefix symbol name with library: "R" -> "Device:R"
    - Strip kicad_sym-specific attributes: show_name, do_not_autoplace,
      in_pos_files, duplicate_pin_numbers_are_jumpers
    - Keep: exclude_from_sim, in_bom, on_board, embedded_fonts
    - Normalize indentation
    """
    result = symbol_block

    # Prefix the symbol name with library name
    result = re.sub(
        r'\(symbol\s+"' + re.escape(symbol_name) + r'"',
        f'(symbol "{library_name}:{symbol_name}"',
        result,
        count=1,
    )

    # Also prefix sub-symbol references (e.g. "R_0_1" stays as-is since
    # they are nested and don't need the library prefix)

    # Strip kicad_sym-specific attributes
    result = re.sub(r"\n?\s*\(show_name\s+\w+\)", "", result)
    result = re.sub(r"\n?\s*\(do_not_autoplace\s+\w+\)", "", result)
    result = re.sub(r"\n?\s*\(in_pos_files\s+\w+\)", "", result)
    result = re.sub(r"\n?\s*\(duplicate_pin_numbers_are_jumpers\s+\w+\)", "", result)

    # Normalize indentation: strip leading whitespace and re-indent with tabs
    lines = result.split("\n")
    # Find minimum indentation (ignoring empty lines)
    min_indent = float("inf")
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            indent = len(line) - len(stripped)
            min_indent = min(min_indent, indent)

    if min_indent == float("inf"):
        min_indent = 0

    normalized = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            normalized.append("")
            continue
        original_indent = len(line) - len(line.lstrip())
        # Convert to tab-based indentation (base = 2 tabs inside lib_symbols)
        tab_depth = max(0, (original_indent - min_indent)) // 2
        normalized.append("\t\t" + "\t" * tab_depth + stripped)

    return "\n".join(normalized)


def _symbol_exists_in_lib_symbols(content: str, lib_id: str) -> bool:
    """Check if a symbol definition already exists in the lib_symbols section."""
    ls_match = re.search(r"\(lib_symbols\b", content)
    if not ls_match:
        return False
    # Search from lib_symbols start for the symbol
    section = content[ls_match.start() :]
    return bool(re.search(r'\(symbol\s+"' + re.escape(lib_id) + r'"', section))


def _insert_symbol_into_lib_symbols(content: str, symbol_text: str) -> str:
    """Insert a symbol definition into the lib_symbols section of a schematic."""
    ls_match = re.search(r"\(lib_symbols\b", content)
    if not ls_match:
        # No lib_symbols section - create one before the first schematic element
        insert_pattern = r"(\n\t\((?:symbol|wire|label|global_label|junction|text|sheet|sheet_instances)\b)"
        m = re.search(insert_pattern, content)
        if m:
            insert_pos = m.start()
            new_section = f"\n\t(lib_symbols\n{symbol_text}\n\t)"
            return content[:insert_pos] + new_section + content[insert_pos:]
        # Last resort: insert before final closing paren
        stripped = content.rstrip()
        if stripped.endswith(")"):
            return stripped[:-1] + f"\n\t(lib_symbols\n{symbol_text}\n\t)\n)\n"
        return content

    # lib_symbols exists - find its closing paren
    start = ls_match.start()
    depth = 0
    end_pos = start
    for i in range(start, len(content)):
        if content[i] == "(":
            depth += 1
        elif content[i] == ")":
            depth -= 1
            if depth == 0:
                end_pos = i
                break

    # Insert before the closing paren of lib_symbols
    return content[:end_pos] + "\n" + symbol_text + "\n" + content[end_pos:]


def _extract_pins_from_symbol_block(symbol_block: str) -> list[tuple[str, str, str]]:
    """Extract pin numbers, types, and names from a symbol definition."""
    pins = []
    pin_pattern = re.compile(
        r"\(pin\s+(\w+)\s+\w+\s+[\s\S]*?"
        r'\(name\s+"([^"]*)"[\s\S]*?\)'
        r'\s*\(number\s+"([^"]*)"',
    )
    for m in pin_pattern.finditer(symbol_block):
        elec_type = m.group(1)
        pin_name = m.group(2)
        pin_number = m.group(3)
        pins.append((pin_number, elec_type, pin_name))
    return pins


# ---------------------------------------------------------------------------
# Pin anchor geometry (for label placement)
# ---------------------------------------------------------------------------

_PIN_GEOM_RE = re.compile(
    r"\(pin\s+(?P<etype>\w+)\s+\w+\s+"
    r"\(at\s+(?P<x>-?[\d.]+)\s+(?P<y>-?[\d.]+)\s+(?P<angle>-?[\d.]+)\)"
    r"[\s\S]*?"
    r'\(number\s+"(?P<number>[^"]*)"'
)


def _lib_symbols_block(content: str) -> str:
    """Text of the (lib_symbols ...) section, or ''."""
    m = re.search(r"\(lib_symbols\b", content)
    if not m:
        return ""
    start = m.start()
    depth = 0
    for i in range(start, len(content)):
        if content[i] == "(":
            depth += 1
        elif content[i] == ")":
            depth -= 1
            if depth == 0:
                return content[start : i + 1]
    return ""


def _symbol_def_block(lib_block: str, lib_id: str) -> str | None:
    m = re.search(r'\(symbol\s+"' + re.escape(lib_id) + r'"(?!\w)', lib_block)
    if not m:
        return None
    start = m.start()
    depth = 0
    for i in range(start, len(lib_block)):
        if lib_block[i] == "(":
            depth += 1
        elif lib_block[i] == ")":
            depth -= 1
            if depth == 0:
                return lib_block[start : i + 1]
    return None


def _lib_pin_offset(symbol_block: str, lib_id: str, unit: int, pin: str) -> tuple[float, float] | None:
    """Lib-space offset of one pin, honouring the unit sub-symbol filter.

    Sub-symbols are named "<lib_id>_<unit>_<convert>" (or the bare
    "<name>_<unit>_<convert>" form); unit 0 = common to all units.
    """
    base = lib_id.split(":")[-1]
    for sub_m in re.finditer(r'\(symbol\s+"([^"]+)"', symbol_block):
        sub_name = sub_m.group(1)
        if sub_name == lib_id:
            continue
        sub_unit = None
        for prefix in (lib_id, base):
            mm = re.match(re.escape(prefix) + r"_(\d+)_(\d+)$", sub_name)
            if mm:
                sub_unit = int(mm.group(1))
                break
        if sub_unit is None or sub_unit not in (0, unit):
            continue
        # balanced span of this sub-symbol block
        start = sub_m.start()
        depth = 0
        for i in range(start, len(symbol_block)):
            if symbol_block[i] == "(":
                depth += 1
            elif symbol_block[i] == ")":
                depth -= 1
                if depth == 0:
                    break
        for pm in _PIN_GEOM_RE.finditer(symbol_block[start : i + 1]):
            if pm.group("number") == pin:
                return float(pm.group("x")), float(pm.group("y"))
    return None


def _pin_anchor(content: str, reference: str, pin: str) -> tuple[float, float, int] | None:
    """Absolute (x, y) and outward angle of a placed component's pin.

    Symbol libraries use a Y-UP axis while schematic sheets store Y growing
    DOWNWARD, so the pin offset's Y is negated on placement; the returned
    angle (0/90/180/270) points away from the symbol body so labels fan out.
    """
    lib = _lib_symbols_block(content)
    inst_re = re.compile(
        r'\(symbol\s+\(lib_id\s+"(?P<lib_id>[^"]+)"\)\s+'
        r"\(at\s+(?P<x>-?[\d.]+)\s+(?P<y>-?[\d.]+)\s+(?P<angle>-?[\d.]+)\)\s+"
        r"\(unit\s+(?P<unit>\d+)\)"
    )
    body = content.replace(lib, "") if lib else content
    for m in inst_re.finditer(body):
        tail = body[m.start() : m.start() + 4000]
        ref_m = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', tail)
        if not ref_m or ref_m.group(1) != reference:
            continue
        ix, iy, iangle, unit = (
            float(m.group("x")),
            float(m.group("y")),
            float(m.group("angle")),
            int(m.group("unit")),
        )
        block = _symbol_def_block(lib, m.group("lib_id"))
        if block is None:
            return None
        offset = _lib_pin_offset(block, m.group("lib_id"), unit, pin)
        if offset is None:
            return None
        dx, dy = offset
        r = int(round(iangle)) % 360
        if r == 90:
            dx, dy = -dy, dx
        elif r == 180:
            dx, dy = -dx, -dy
        elif r == 270:
            dx, dy = dy, -dx
        sx, sy = dx, -dy  # lib Y-UP -> sheet Y-DOWN
        if abs(sx) >= abs(sy):
            angle = 0 if sx >= 0 else 180
        else:
            angle = 90 if sy < 0 else 270
        return ix + sx, iy + sy, angle
    return None


def _append_top_level(content: str, entry: str) -> str:
    stripped = content.rstrip()
    if not stripped.endswith(")"):
        return content + "\n" + entry + "\n"
    return stripped[:-1] + entry + "\n)\n"


_LABEL_SHAPES = ("input", "output", "bidirectional", "tri_state", "passive")

_JUSTIFY = {0: "left", 180: "right", 90: "bottom", 270: "top"}


def _resolve_label_target(
    file_path: str, reference: str, pin: str, x: float | None, y: float | None
) -> tuple[str, float, float, int] | str:
    """Common target resolution for label tools: exact pin anchor by default,
    explicit coordinates when pin lookups are not applicable."""
    content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    if x is not None and y is not None:
        return content, x, y, 0
    anchor = _pin_anchor(content, reference, pin)
    if anchor is None:
        return (
            f"❌ Pin '{pin}' not found on component '{reference}' — place the "
            f"component first, or pass explicit x/y coordinates."
        )
    return content, anchor[0], anchor[1], anchor[2]


@mcp.tool()
async def add_hierarchical_label(
    file_path: str,
    reference: str,
    pin: str,
    label_name: str = "",
    shape: str = "input",
    x: float | None = None,
    y: float | None = None,
) -> str:
    """Add a hierarchical label on a component pin (cross-sheet connection).

    Hierarchical labels are how signals cross sheet boundaries in KiCad: a
    label placed in a sub-sheet appears as a same-named pin on the parent
    sheet's sheet symbol, connecting the two. Placing them by hand for
    every cross-sheet signal is the classic tedium this automates.

    The label anchors EXACTLY on the pin (computed from the embedded
    symbol geometry incl. rotation and the library-vs-sheet Y flip), so
    the connection is electrically valid — verify with generate_netlist.

    Args:
        file_path: Path to the .kicad_sch file (the SUB-sheet for signals
            going up to its parent).
        reference: Component reference (e.g. 'U1').
        pin: Pin number.
        label_name: Label text; defaults to the reference+pin when empty.
        shape: Electrical direction: input, output, bidirectional,
            tri_state or passive (ERC uses this).
        x/y: Explicit anchor coordinates (overrides reference/pin).

    Returns:
        Confirmation with the exact anchor position.
    """
    if shape not in _LABEL_SHAPES:
        return f"❌ Invalid shape '{shape}'. Options: {', '.join(_LABEL_SHAPES)}"
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File {file_path} does not exist"

        resolved = _resolve_label_target(file_path, reference, pin, x, y)
        if isinstance(resolved, str):
            return resolved
        content, ax, ay, angle = resolved

        name = label_name or f"{reference}.{pin}"
        justify = _JUSTIFY.get(angle, "left")
        entry = (
            f'\t(hierarchical_label "{name}" (shape {shape}) (at {round(ax, 3)} {round(ay, 3)} {angle})\n'
            f"\t\t(effects (font (size 1.27 1.27)) (justify {justify}))\n"
            f'\t\t(uuid "{uuid.uuid4()}")\n'
            f"\t)\n"
        )
        path.write_text(_append_top_level(content, entry), encoding="utf-8")
        return (
            f"✅ Hierarchical label '{name}' ({shape}) anchored on {reference}.{pin} "
            f"at ({round(ax, 3)}, {round(ay, 3)}) angle {angle}°"
        )
    except Exception as e:
        import traceback

        return f"Error adding hierarchical label: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
async def add_global_label(
    file_path: str,
    reference: str,
    pin: str,
    label_name: str,
    shape: str = "input",
    x: float | None = None,
    y: float | None = None,
) -> str:
    """Add a global label on a component pin (project-wide connection).

    Global labels connect same-named signals anywhere in the whole
    hierarchy regardless of sheets — useful for power-style rails and
    cross-cutting signals where a hierarchical parent/child chain would
    be awkward.

    Args:
        file_path: Path to the .kicad_sch file.
        reference: Component reference (e.g. 'U1').
        pin: Pin number.
        label_name: Global net name (required — globals are named nets).
        shape: Electrical direction: input, output, bidirectional,
            tri_state or passive.
        x/y: Explicit anchor coordinates (overrides reference/pin).

    Returns:
        Confirmation with the exact anchor position.
    """
    if shape not in _LABEL_SHAPES:
        return f"❌ Invalid shape '{shape}'. Options: {', '.join(_LABEL_SHAPES)}"
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Error: File {file_path} does not exist"

        resolved = _resolve_label_target(file_path, reference, pin, x, y)
        if isinstance(resolved, str):
            return resolved
        content, ax, ay, angle = resolved

        justify = _JUSTIFY.get(angle, "left")
        entry = (
            f'\t(global_label "{label_name}" (shape {shape}) (at {round(ax, 3)} {round(ay, 3)} {angle})\n'
            f"\t\t(effects (font (size 1.27 1.27)) (justify {justify}))\n"
            f'\t\t(uuid "{uuid.uuid4()}")\n'
            f'\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at 0 0 0)\n'
            f"\t\t\t(effects (font (size 1.27 1.27)) hide)\n"
            f"\t\t)\n"
            f"\t)\n"
        )
        path.write_text(_append_top_level(content, entry), encoding="utf-8")
        return (
            f"✅ Global label '{label_name}' ({shape}) anchored on {reference}.{pin} "
            f"at ({round(ax, 3)}, {round(ay, 3)}) angle {angle}°"
        )
    except Exception as e:
        import traceback

        return f"Error adding global label: {e}\n\n{traceback.format_exc()}"


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

        # --- Insert symbol definition into lib_symbols if needed ---
        lib_inserted = False
        lib_file = _find_symbol_library_file(library_name)
        if lib_file:
            symbol_block = _extract_symbol_from_kicad_sym(lib_file, symbol_name)
            if symbol_block:
                if not _symbol_exists_in_lib_symbols(content, lib_id):
                    converted = _convert_symbol_to_lib_symbols_format(
                        symbol_block, library_name, symbol_name
                    )
                    content = _insert_symbol_into_lib_symbols(content, converted)
                lib_inserted = True

        # --- Determine pins ---
        pins = []
        if lib_file:
            symbol_block = _extract_symbol_from_kicad_sym(lib_file, symbol_name)
            if symbol_block:
                pins = _extract_pins_from_symbol_block(symbol_block)
        if not pins:
            pins = get_pins_for_symbol(library_name, symbol_name)

        pin_entries = []
        for pin_num, _pin_type, _pin_name in pins:
            pin_uuid = str(uuid.uuid4())
            pin_entries.append(f'    (pin "{pin_num}" (uuid "{pin_uuid}"))')
        pins_str = "\n".join(pin_entries) if pin_entries else ""

        # --- Insert component instance ---
        # NOTE: schematic symbol-instance (property ...) blocks must NOT contain
        # a nested (uuid ...) field in this KiCad 9 file format (generator_version
        # "9.0", version 20250114) -- confirmed against KiCad's own
        # template/Arduino_Mega/Arduino_Mega.kicad_sch. Adding one is silently
        # accepted by lenient parsers (sexpdata, kicad-skip) but makes KiCad's own
        # strict loader (kicad-cli and the GUI) refuse to open the file at all.
        component_entry = f'''  (symbol (lib_id "{lib_id}") (at {x} {y} 0) (unit {unit})
  (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
  (uuid "{comp_uuid}")
  (property "Reference" "{reference}" (at {x} {y - 5} 0)
    (effects (font (size 1.27 1.27)))
  )
  (property "Value" "{value}" (at {x} {y + 2.54} 0)
    (effects (font (size 1.27 1.27)))
  )
  (property "Footprint" "{footprint}" (at {x} {y + 5.08} 0)
    (effects (font (size 1.27 1.27)) (hide yes))
  )
{pins_str}
)'''

        # Refuse to write a symbol instance whose lib_id has no matching
        # definition in (lib_symbols) — that yields a broken symbol in KiCad.
        if not lib_inserted:
            return (f"❌ Cannot add component: symbol definition for "
                    f'"{lib_id}" is unavailable (library "{library_name}" not '
                    f"found, or symbol not in it). Install the library or pick a "
                    f"symbol that exists.")

        if content.rstrip().endswith(")"):
            content = content.rstrip()
            if content.endswith(")"):
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
**Symbol definition:** inserted into lib_symbols
**Pins:** {len(pins)} pins detected

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
        wire_entry = f"""  (wire (pts {pts_str})
    (stroke (width 0) (type default))
    (uuid "{uuid.uuid4()}")
  )"""

        if content.rstrip().endswith(")"):
            content = content.rstrip()
            if content.endswith(")"):
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
        label_entry = f"""  (label "{text}" (at {x} {y} {orientation})
    (effects (font (size 1.27 1.27)) (justify left))
    (uuid "{label_uuid}")
  )"""

        if content.rstrip().endswith(")"):
            content = content.rstrip()
            if content.endswith(")"):
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
