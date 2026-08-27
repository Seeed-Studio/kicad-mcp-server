"""Pin geometry and net-connectivity tools for agent-driven schematic drawing.

The existing schematic_editor tools place symbols and wires at raw
coordinates, but an agent has no way to know WHERE a placed component's
pins actually are — that requires the pin offsets from the embedded
lib_symbols geometry plus the instance rotation. Without it, wires and
labels float detached and nothing connects.

These tools close that gap:

- get_component_pins: absolute pin positions/names/types of a placed symbol
- connect_pins: label-based connection between two pins (same-name labels
  are electrically connected — no wire geometry needed)
- add_power_net: power symbols (GND, +3V3, ...) from KiCad's power library,
  so power nets stay ERC-clean
"""

import re
import uuid
from pathlib import Path

from ..server import mcp

# ---------------------------------------------------------------------------
# Pin geometry from embedded lib_symbols
# ---------------------------------------------------------------------------

# A pin block inside a lib symbol definition:
#   (pin <electrical_type> <graphical_style> (at X Y A) (length L) ...
#     (name ".." ...) (number ".." ...))
_PIN_RE = re.compile(
    r"\(pin\s+(?P<etype>\w+)\s+\w+\s+"
    r"\(at\s+(?P<x>-?[\d.]+)\s+(?P<y>-?[\d.]+)\s+(?P<angle>-?[\d.]+)\)\s+"
    r"\(length\s+(?P<length>-?[\d.]+)\)"
    r"[\s\S]*?"
    r'\(name\s+"(?P<name>[^"]*)"'
    r"[\s\S]*?"
    r'\(number\s+"(?P<number>[^"]*)"',
)

# Sub-symbol blocks: (symbol "Lib:Name_U_C" ...) where U = unit (0 = all
# units) and C = convert style. Pin geometry lives only in these.
_SUBSYMBOL_RE = re.compile(r'\(symbol\s+"([^"]+)"')


def _lib_symbols_block(content: str) -> str:
    """Return the text of the (lib_symbols ...) section, or ''."""
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


def _symbol_definition_block(lib_block: str, lib_id: str) -> str | None:
    """Return the text of one top-level symbol definition inside lib_symbols."""
    pattern = r'\(symbol\s+"' + re.escape(lib_id) + r'"(?!\w)'
    m = re.search(pattern, lib_block)
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


def _iter_subsymbol_spans(symbol_block: str):
    """Yield (sub_name, span_text) for each nested sub-symbol block."""
    spans = []
    for m in _SUBSYMBOL_RE.finditer(symbol_block):
        # skip the top-level name itself (first match starts at the block)
        start = m.start()
        depth = 0
        for i in range(start, len(symbol_block)):
            if symbol_block[i] == "(":
                depth += 1
            elif symbol_block[i] == ")":
                depth -= 1
                if depth == 0:
                    spans.append((m.group(1), symbol_block[start : i + 1]))
                    break
    return spans


def _placed_instances(content: str) -> list[dict]:
    """Parse placed symbol instances (not lib_symbols definitions)."""
    instances = []
    # restrict to everything AFTER the lib_symbols section: instance blocks
    # are top-level (symbol (lib_id ...) (at ...))
    lib = _lib_symbols_block(content)
    body = content.replace(lib, "") if lib else content
    inst_re = re.compile(
        r'\(symbol\s+\(lib_id\s+"(?P<lib_id>[^"]+)"\)\s+'
        r"\(at\s+(?P<x>-?[\d.]+)\s+(?P<y>-?[\d.]+)\s+(?P<angle>-?[\d.]+)\)\s+"
        r"\(unit\s+(?P<unit>\d+)\)",
    )
    for m in inst_re.finditer(body):
        instances.append(
            {
                "lib_id": m.group("lib_id"),
                "x": float(m.group("x")),
                "y": float(m.group("y")),
                "angle": float(m.group("angle")),
                "unit": int(m.group("unit")),
                # capture the full block for property extraction
                "block_start": m.start(),
            }
        )
    # attach reference/value per instance from its property fields
    for inst in instances:
        tail = body[inst["block_start"] : inst["block_start"] + 4000]
        ref_m = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', tail)
        val_m = re.search(r'\(property\s+"Value"\s+"([^"]*)"', tail)
        inst["reference"] = ref_m.group(1) if ref_m else ""
        inst["value"] = val_m.group(1) if val_m else ""
    return instances


def _rotate_offset(dx: float, dy: float, angle_deg: float) -> tuple[float, float]:
    """Convert a lib-space pin offset to a sheet-space offset.

    Symbol libraries use a Y-UP axis while schematic sheets store Y growing
    DOWNWARD, so the offset's Y is negated on placement. The instance angle
    (CCW visually) is applied in the library's coordinate space first:
    forgetting the Y flip mirrors every pin vertically and lands labels on
    the wrong pins.
    """
    r = int(round(angle_deg)) % 360
    if r == 90:
        dx, dy = -dy, dx
    elif r == 180:
        dx, dy = -dx, -dy
    elif r == 270:
        dx, dy = dy, -dx
    # non-orthogonal angles are not produced by the editor; treat as 0
    return dx, -dy


def get_pin_geometry(
    content: str, reference: str
) -> list[dict] | None:
    """Compute absolute pin positions for a placed component by reference.

    Returns a list of {number, name, electrical_type, x, y} dicts, or None
    when the reference is not found in the schematic.
    """
    instances = _placed_instances(content)
    inst = next((i for i in instances if i["reference"] == reference), None)
    if inst is None:
        return None

    lib_block = _lib_symbols_block(content)
    symbol_block = _symbol_definition_block(lib_block, inst["lib_id"])
    if symbol_block is None:
        return []

    unit = inst["unit"]
    base_name = inst["lib_id"].split(":")[-1]
    pins: list[dict] = []
    seen: set[str] = set()
    for sub_name, sub_text in _iter_subsymbol_spans(symbol_block):
        # Sub-symbol naming: "<lib_id>_<unit>_<convert>"; unit 0 = common to
        # all units. The embedded definition may use either the full
        # "Device:R_0_1" form or the bare "R_0_1" form.
        sub_unit = None
        for prefix in (inst["lib_id"], base_name):
            m = re.match(re.escape(prefix) + r"_(\d+)_(\d+)$", sub_name)
            if m:
                sub_unit = int(m.group(1))
                break
        if sub_unit is None or sub_unit not in (0, unit):
            continue
        for pm in _PIN_RE.finditer(sub_text):
            number = pm.group("number")
            if number in seen:
                continue
            seen.add(number)
            dx, dy = _rotate_offset(
                float(pm.group("x")), float(pm.group("y")), inst["angle"]
            )
            pins.append(
                {
                    "number": number,
                    "name": pm.group("name"),
                    "electrical_type": pm.group("etype"),
                    "x": round(inst["x"] + dx, 3),
                    "y": round(inst["y"] + dy, 3),
                }
            )
    return pins


# ---------------------------------------------------------------------------
# Writing labels / power symbols
# ---------------------------------------------------------------------------


def _append_before_close(content: str, entry: str) -> str:
    """Insert a top-level element before the file's final closing paren."""
    stripped = content.rstrip()
    if not stripped.endswith(")"):
        return content + "\n" + entry + "\n"
    return stripped[:-1] + entry + "\n)\n"


def _insert_local_label(content: str, text: str, x: float, y: float) -> str:
    entry = (
        f'\t(label "{text}" (at {x} {y} 0)\n'
        f"\t\t(effects (font (size 1.27 1.27)) (justify left))\n"
        f'\t\t(uuid "{uuid.uuid4()}")\n'
        f"\t)\n"
    )
    return _append_before_close(content, entry)


def _find_pin(pins: list[dict], pin: str) -> dict | None:
    return next((p for p in pins if p["number"] == pin), None)


def _resolve_reference(content: str, reference: str) -> dict | None:
    inst = next(
        (i for i in _placed_instances(content) if i["reference"] == reference), None
    )
    return inst


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_component_pins(
    file_path: str,
    reference: str,
) -> str:
    """Get absolute pin positions of a placed schematic component.

    Essential before wiring: reports every pin's number, name, electrical
    type and its absolute (x, y) position in the sheet, computed from the
    embedded lib_symbols geometry and the instance rotation. Use these
    coordinates with add_wire/add_label, or let connect_pins place the
    labels for you.

    Args:
        file_path: Path to the .kicad_sch file.
        reference: Component reference (e.g. 'R1', 'U1').

    Returns:
        Pin table with absolute coordinates.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ File not found: {file_path}"
        content = path.read_text(encoding="utf-8", errors="replace")

        pins = get_pin_geometry(content, reference)
        if pins is None:
            return f"❌ Component '{reference}' not found in {file_path}"
        if not pins:
            return (
                f"⚠️ Component '{reference}' found but no pin geometry could "
                f"be read from its lib_symbols definition."
            )

        lines = [
            f"## Pins of {reference}",
            "",
            f"**Component:** {reference} ",
            f"**Total pins:** {len(pins)}",
            "",
            "| Pin | Name | Type | X | Y |",
            "|-----|------|------|---|---|",
        ]
        for p in pins:
            lines.append(
                f"| {p['number']} | {p['name'] or '~'} | {p['electrical_type']} "
                f"| {p['x']} | {p['y']} |"
            )
        return "\n".join(lines)

    except Exception as e:
        import traceback

        return f"❌ Error reading pins: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
async def connect_pins(
    file_path: str,
    ref1: str,
    pin1: str,
    ref2: str,
    pin2: str,
    net_name: str,
) -> str:
    """Connect two component pins with a named net (label-based).

    Places a local label with `net_name` on both pins. Same-name labels are
    electrically connected in KiCad, so this is a correct connection without
    any wire geometry — ideal for agent-drawn schematics. Verify afterwards
    with generate_netlist / trace_netlist_connection.

    Args:
        file_path: Path to the .kicad_sch file.
        ref1: First component reference (e.g. 'R1').
        pin1: First pin number (e.g. '1').
        ref2: Second component reference.
        pin2: Second pin number.
        net_name: Net name to give the connection.

    Returns:
        Confirmation with the exact label positions.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ File not found: {file_path}"
        content = path.read_text(encoding="utf-8", errors="replace")

        pins1 = get_pin_geometry(content, ref1)
        pins2 = get_pin_geometry(content, ref2)
        if pins1 is None:
            return f"❌ Component '{ref1}' not found"
        if pins2 is None:
            return f"❌ Component '{ref2}' not found"
        p1 = _find_pin(pins1, pin1)
        p2 = _find_pin(pins2, pin2)
        if p1 is None:
            avail = ", ".join(p["number"] for p in pins1) or "none found"
            return f"❌ Pin '{pin1}' not found on {ref1} (available: {avail})"
        if p2 is None:
            avail = ", ".join(p["number"] for p in pins2) or "none found"
            return f"❌ Pin '{pin2}' not found on {ref2} (available: {avail})"

        content = _insert_local_label(content, net_name, p1["x"], p1["y"])
        content = _insert_local_label(content, net_name, p2["x"], p2["y"])
        path.write_text(content, encoding="utf-8")

        return f"""✅ Connected {ref1}.{pin1} ↔ {ref2}.{pin2} as net '{net_name}'

**Labels placed at:**
- {ref1} pin {pin1} ({p1['name'] or '~'}): ({p1['x']}, {p1['y']})
- {ref2} pin {pin2} ({p2['name'] or '~'}): ({p2['x']}, {p2['y']})

Verify with `generate_netlist()` + `trace_netlist_connection()`."""
    except Exception as e:
        import traceback

        return f"❌ Error connecting pins: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
async def add_power_net(
    file_path: str,
    net_name: str,
    ref: str,
    pin: str,
) -> str:
    """Attach a power net (GND, +3V3, +5V ...) to a component pin.

    Places the matching power symbol from KiCad's power library directly on
    the pin, and adds a #PWR_FLAG on the same net so ERC accepts it as
    driven. The power symbol definition is embedded into lib_symbols just
    like add_component_from_library does.

    Args:
        file_path: Path to the .kicad_sch file.
        net_name: Power net name, e.g. 'GND', '+3V3', '+5V', 'VBUS'.
        ref: Component reference whose pin gets the power net.
        pin: Pin number on that component.

    Returns:
        Confirmation with symbol placement details.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ File not found: {file_path}"
        content = path.read_text(encoding="utf-8", errors="replace")

        pins = get_pin_geometry(content, ref)
        if pins is None:
            return f"❌ Component '{ref}' not found"
        target = _find_pin(pins, pin)
        if target is None:
            avail = ", ".join(p["number"] for p in pins) or "none found"
            return f"❌ Pin '{pin}' not found on {ref} (available: {avail})"

        from .schematic_editor import (
            _convert_symbol_to_lib_symbols_format,
            _extract_symbol_from_kicad_sym,
            _find_symbol_library_file,
            _insert_symbol_into_lib_symbols,
            _symbol_exists_in_lib_symbols,
        )

        power_lib = _find_symbol_library_file("power")
        if power_lib is None:
            return (
                "❌ KiCad 'power' symbol library not found. power.kicad_sym "
                "ships with every KiCad installation."
            )

        for sym_name in (net_name, "PWR_FLAG"):
            if sym_name == "PWR_FLAG" and _symbol_exists_in_lib_symbols(
                content, "power:PWR_FLAG"
            ):
                continue
            block = _extract_symbol_from_kicad_sym(power_lib, sym_name)
            if block is None:
                return (
                    f"❌ Power symbol '{sym_name}' not found in the power "
                    f"library. Use a standard name like GND, +3V3, +5V."
                )
            if not _symbol_exists_in_lib_symbols(content, f"power:{sym_name}"):
                converted = _convert_symbol_to_lib_symbols_format(
                    block, "power", sym_name
                )
                content = _insert_symbol_into_lib_symbols(content, converted)

        # power symbol instance: its connection pin sits at the symbol origin.
        # KiCad 8/9 format: no inner property uuids, (instances) required.
        from .schematic_editor import _ensure_root_uuid

        content, root_uuid = _ensure_root_uuid(content)
        project_name = path.stem

        def _power_instance(lib_sym: str, at_x: float, at_y: float) -> str:
            return (
                f"\t(symbol (lib_id \"power:{lib_sym}\") (at {at_x} {at_y} 0) (unit 1)\n"
                f"\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n"
                f'\t\t(uuid "{uuid.uuid4()}")\n'
                f'\t\t(property "Reference" "#PWR0" (at {at_x} {at_y} 0)\n'
                f"\t\t\t(effects (font (size 1.27 1.27)) hide)\n"
                f"\t\t)\n"
                f'\t\t(property "Value" "{lib_sym}" (at {at_x} {at_y} 0)\n'
                f"\t\t\t(effects (font (size 1.27 1.27)))\n"
                f"\t\t)\n"
                f'\t\t(property "Footprint" "" (at {at_x} {at_y} 0)\n'
                f"\t\t\t(effects (font (size 1.27 1.27)) hide)\n"
                f"\t\t)\n"
                f"\t\t(pin \"1\" (uuid \"{uuid.uuid4()}\"))\n"
                f"\t\t(instances\n"
                f"\t\t\t(project \"{project_name}\"\n"
                f"\t\t\t\t(path \"/{root_uuid}\" (reference \"#PWR0\") (unit 1))\n"
                f"\t\t\t)\n"
                f"\t\t)\n"
                f"\t)\n"
            )

        # Both the power symbol and PWR_FLAG connect at their origin pin;
        # stacking them exactly on the target pin puts all three on the same
        # net — this is precisely how KiCad's own editor does it.
        content = _append_before_close(
            content, _power_instance(net_name, target["x"], target["y"])
        )
        content = _append_before_close(
            content, _power_instance("PWR_FLAG", target["x"], target["y"])
        )

        path.write_text(content, encoding="utf-8")

        return f"""✅ Power net '{net_name}' attached to {ref}.{pin}

**Power symbol:** power:{net_name} at ({target['x']}, {target['y']})
**PWR_FLAG:** stacked on the same point so ERC sees the net as driven

Verify with `run_erc()` and `generate_netlist()`."""
    except Exception as e:
        import traceback

        return f"❌ Error adding power net: {e}\n\n{traceback.format_exc()}"
