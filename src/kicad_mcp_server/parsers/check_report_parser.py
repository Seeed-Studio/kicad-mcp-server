"""Parsers for the ERC and DRC JSON reports of kicad-cli (KiCad 8+).

The tools run kicad-cli with an English locale (see ``utils.kicad_cli``), so
the item text is English. The rules for English text come first. If the text
is localized, language-neutral fallback rules get the reference and the
position, and the pin fields stay empty.
"""

import math
import re
import statistics
from pathlib import Path
from typing import Any

from ..models.types import DRCError, DRCItem, ERCError, ERCItem

# A reference designator: "U13", "AN-GNSS1", "#PWR055", "R1A".
_REF = r"#?[A-Za-z][\w+-]*\d\w*"
_REF_RE = re.compile(rf"^{_REF}$")

# "Symbol U13 Pin D6 [P0.00/XL1, Tri-state, Line]", or "Pin 1 [???, ?]" when
# the library symbol is missing.
_ERC_PIN_EN = re.compile(r"^(?:Symbol (?P<ref>\S+) )?Pin (?P<pin>\S+) \[(?P<attrs>.*)\]$")
# "Symbol U11 [LSM6DSOTR]"
_ERC_SYMBOL_EN = re.compile(r"^Symbol (?P<ref>\S+) \[(?P<value>.*)\]$")
# Localized forms of the two rules above ("Symbol U13 Vývod D6 [...]").
_ERC_PIN_ANY = re.compile(r"^\S+ (?P<ref>\S+) \S+ (?P<pin>\S+) \[(?P<attrs>.*)\]$")
_ERC_SYMBOL_ANY = re.compile(r"^\S+ (?P<ref>\S+) \[(?P<value>.*)\]$")
# "Global Label 'VBAT'", "Label 'SDA'", "Hierarchical Label 'X'"
_QUOTED = re.compile(r"'(?P<text>[^']*)'")

# DRC: "Pad 10 [NET] of U7 on F.Cu", "Reference field of L4", "Footprint C18"
_DRC_BRACKETS = re.compile(r"\[[^\]]*\]")
_DRC_OF_REF = re.compile(rf"\bof (?P<ref>{_REF})\b")
_DRC_FOOTPRINT_REF = re.compile(rf"^Footprint (?P<ref>{_REF})\b")

# s-expression tokens: a quoted string, a parenthesis or an atom.
_SEXPR_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[()]|[^\s()"]+')

# Scale factors that the position calibration can select.
_POSITION_SCALES = (1.0, 10.0, 100.0, 1000.0)


def _attrs_to_pin(attrs: str) -> tuple[str, str]:
    """Split the pin attributes into (pin name, pin type).

    The attributes are "name, type, shape" or "type, shape" for a pin without
    a name. The split starts at the right, because a pin name can contain ", ".
    """
    parts = attrs.rsplit(", ", 2)
    if len(parts) == 3:
        return parts[0], parts[1]
    if len(parts) == 2:
        return "", parts[0]
    return "", ""


def _valid_ref(ref: str | None) -> str:
    return ref if ref and _REF_RE.match(ref) else ""


def parse_erc_item(item: dict[str, Any], position_scale: float = 1.0) -> ERCItem:
    """Parse one item of an ERC violation."""
    desc = item.get("description", "")
    out = ERCItem(description=desc, uuid=item.get("uuid", ""))

    pos = item.get("pos") or {}
    if "x" in pos and "y" in pos:
        out.x_mm = round(float(pos["x"]) * position_scale, 4)
        out.y_mm = round(float(pos["y"]) * position_scale, 4)

    m = _ERC_PIN_EN.match(desc)
    if m:
        out.reference = _valid_ref(m["ref"])
        out.pin_number = m["pin"]
        out.pin_name, out.pin_type = _attrs_to_pin(m["attrs"])
        return out

    m = _ERC_SYMBOL_EN.match(desc)
    if m and _valid_ref(m["ref"]):
        out.reference = m["ref"]
        out.value = m["value"]
        return out

    m = _QUOTED.search(desc)
    if m:
        out.label = m["text"]
        return out

    # Localized text: get only the structure. The pin type is not English,
    # thus it stays empty.
    m = _ERC_PIN_ANY.match(desc)
    if m and _valid_ref(m["ref"]):
        out.reference = m["ref"]
        out.pin_number = m["pin"]
        out.pin_name, _ = _attrs_to_pin(m["attrs"])
        return out

    m = _ERC_SYMBOL_ANY.match(desc)
    if m and _valid_ref(m["ref"]):
        out.reference = m["ref"]
        out.value = m["value"]
    return out


def _erc_sheets(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the sheets of an ERC report.

    KiCad 8 to 10 write ``sheets[].violations``. A report with a top-level
    ``violations`` list is also accepted.
    """
    sheets = report.get("sheets")
    if isinstance(sheets, list):
        return sheets
    return [{"path": "", "violations": report.get("violations", [])}]


def parse_erc_report(report: dict[str, Any], position_scale: float = 1.0) -> list[ERCError]:
    """Parse the data of an ERC JSON report into ERC errors."""
    errors = []
    for sheet in _erc_sheets(report):
        for v in sheet.get("violations", []):
            items = [parse_erc_item(i, position_scale) for i in v.get("items", [])]
            errors.append(
                ERCError(
                    severity=v.get("severity", "error"),
                    type=v.get("type", "unknown"),
                    description=v.get("description", ""),
                    components=[i.reference for i in items if i.reference],
                    items=items,
                    excluded=bool(v.get("excluded", False)),
                    comment=v.get("comment", ""),
                    sheet=sheet.get("path", ""),
                )
            )
    return errors


def top_level_positions(text: str) -> dict[str, tuple[float, float]]:
    """Map the UUID of each top-level schematic object to its position.

    A top-level object is a direct child of ``kicad_sch`` (a symbol, a label,
    a sheet and other objects). The function reads its direct ``at`` and
    ``uuid`` children. It reads the token structure, not the indentation,
    thus it accepts all KiCad file formats.
    """
    positions: dict[str, tuple[float, float]] = {}
    # Each frame: [head, atoms, at, uuid]. Atoms are kept only for the
    # children of top-level objects (depth 3).
    stack: list[list[Any]] = []
    for m in _SEXPR_TOKEN.finditer(text):
        tok = m.group()
        if tok == "(":
            stack.append([None, [], None, None])
        elif tok == ")":
            if not stack:
                continue
            head, atoms, at, uid = stack.pop()
            if len(stack) == 2:
                parent = stack[-1]
                if head == "at" and parent[2] is None and len(atoms) >= 2:
                    try:
                        parent[2] = (float(atoms[0]), float(atoms[1]))
                    except ValueError:
                        pass
                elif head == "uuid" and parent[3] is None and atoms:
                    parent[3] = atoms[0].strip('"')
            elif len(stack) == 1 and at is not None and uid:
                positions[uid] = at
        elif stack:
            frame = stack[-1]
            if frame[0] is None:
                frame[0] = tok
            elif len(stack) == 3:
                frame[1].append(tok)
    return positions


def erc_position_scale(report: dict[str, Any], schematic_files: list[Path]) -> tuple[float, str]:
    """Find the factor that changes the ERC report positions to mm.

    KiCad 10.0.6 writes the ERC JSON positions 100 times too small, although
    ``coordinate_units`` is "mm". The function compares the report positions
    with the positions of the same objects (found by UUID) in the schematic
    files. If no object is found, it uses the KiCad version.

    Returns:
        (scale, source). Source is "calibrated", "version" or "report".
    """
    index: dict[str, tuple[float, float]] = {}
    for path in schematic_files:
        try:
            index.update(top_level_positions(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue

    ratios = []
    for sheet in _erc_sheets(report):
        for v in sheet.get("violations", []):
            for item in v.get("items", []):
                ref_pos = index.get(item.get("uuid", ""))
                pos = item.get("pos") or {}
                if ref_pos is None or "x" not in pos or "y" not in pos:
                    continue
                for file_val, rpt_val in zip(ref_pos, (pos["x"], pos["y"]), strict=True):
                    if abs(rpt_val) > 1e-9 and abs(file_val) > 1e-9:
                        ratios.append(file_val / rpt_val)

    if ratios:
        ratio = statistics.median(ratios)
        if ratio > 0:
            scale = min(_POSITION_SCALES, key=lambda s: abs(math.log(ratio / s)))
            if abs(ratio / scale - 1.0) < 0.02:
                return scale, "calibrated"

    # Examined only on KiCad 10.0.6. Examine again for each new KiCad version.
    if str(report.get("kicad_version", "")).startswith("10."):
        return 100.0, "version"
    return 1.0, "report"


def parse_drc_item(item: dict[str, Any]) -> DRCItem:
    """Parse one item of a DRC violation."""
    desc = item.get("description", "")
    out = DRCItem(description=desc, uuid=item.get("uuid", ""))
    pos = item.get("pos") or {}
    if "x" in pos and "y" in pos:
        out.x_mm = float(pos["x"])
        out.y_mm = float(pos["y"])

    # Remove the net names in brackets first: a net name can contain " of ".
    plain = _DRC_BRACKETS.sub("", desc)
    m = _DRC_OF_REF.search(plain) or _DRC_FOOTPRINT_REF.match(plain)
    if m:
        out.reference = m["ref"]
    return out


_DRC_CATEGORIES = (
    ("violations", "violation"),
    ("unconnected_items", "unconnected"),
    ("schematic_parity", "schematic_parity"),
)


def parse_drc_report(report: dict[str, Any]) -> list[DRCError]:
    """Parse the data of a DRC JSON report into DRC errors.

    The DRC report has the top-level lists ``violations``,
    ``unconnected_items`` and ``schematic_parity``. Each list is parsed.
    """
    errors = []
    for key, category in _DRC_CATEGORIES:
        for v in report.get(key, []):
            items = [parse_drc_item(i) for i in v.get("items", [])]
            first = items[0] if items else None
            location = (first.x_mm or 0.0, first.y_mm or 0.0) if first is not None else (0.0, 0.0)
            refs = list(dict.fromkeys(i.reference for i in items if i.reference))
            errors.append(
                DRCError(
                    severity=v.get("severity", "error"),
                    type=v.get("type", "unknown"),
                    description=v.get("description", ""),
                    location=location,
                    category=category,
                    components=refs,
                    items=items,
                    excluded=bool(v.get("excluded", False)),
                    comment=v.get("comment", ""),
                )
            )
    return errors
