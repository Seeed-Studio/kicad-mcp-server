"""Schematic file parser wrapper using kicad-skip."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..utils.file_handlers import validate_kicad_file

# KiCad-defined boolean flags (fixed set, not user-extensible)
KICAD_SYMBOL_FLAGS = ("dnp", "in_bom", "on_board", "exclude_from_sim")
KICAD_FLAG_DEFAULTS = {"dnp": False, "in_bom": True, "on_board": True, "exclude_from_sim": False}


@dataclass
class SchematicComponent:
    """Component from schematic file."""

    reference: str
    value: str
    library_id: str
    footprint: Optional[str] = None
    properties: dict[str, str] = field(default_factory=dict)
    position: tuple[float, float] = (0.0, 0.0)
    unit: Optional[int] = None
    pins: list[dict[str, Any]] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=lambda: dict(KICAD_FLAG_DEFAULTS))

    @classmethod
    def from_kicad_skip(cls, data: dict[str, Any]) -> "SchematicComponent":
        """Create from kicad-skip data structure."""
        # Extract properties
        properties = {}
        for prop in data.get("properties", []):
            key = prop.get("key", "")
            value = prop.get("value", "")
            if key and value:
                properties[key] = value

        # Get position
        at = data.get("at", {})
        position = (float(at.get("x", 0)), float(at.get("y", 0)))

        # Get unit
        unit = data.get("unit")

        return cls(
            reference=data.get("reference", ""),
            value=properties.get("Value", data.get("value", "")),
            library_id=data.get("lib_id", ""),
            footprint=properties.get("Footprint"),
            properties=properties,
            position=position,
            unit=unit,
            pins=data.get("pins", []),
            flags=data.get("flags", dict(KICAD_FLAG_DEFAULTS)),
        )


@dataclass
class SchematicNet:
    """Net from schematic file."""

    name: str
    code: int
    node_count: int = 0
    pins: list[str] = field(default_factory=list)
    type: str = "unknown"
    position: tuple[float, float] = (0.0, 0.0)

    @classmethod
    def from_kicad_skip(cls, data: dict[str, Any]) -> "SchematicNet":
        """Create from kicad-skip data structure."""
        return cls(
            name=data.get("name", ""),
            code=data.get("code", 0),
            type=data.get("type", "unknown"),
            position=data.get("position", (0.0, 0.0)),
        )


@dataclass
class SchematicPin:
    """Pin definition from symbol."""

    number: str
    name: str
    type: str

    @classmethod
    def from_kicad_skip(cls, data: dict[str, Any]) -> "SchematicPin":
        """Create from kicad-skip data structure."""
        return cls(
            number=data.get("number", ""),
            name=data.get("name", ""),
            type=data.get("electrical_type", ""),
        )


class SchematicParser:
    """Parser for KiCad schematic files (.kicad_sch)."""

    def __init__(self, file_path: str) -> None:
        """Initialize parser with schematic file.

        Args:
            file_path: Path to .kicad_sch file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a .kicad_sch file
        """
        self.file_path = validate_kicad_file(file_path, ".kicad_sch")
        self._data: Optional[dict[str, Any]] = None
        self._lib_symbols_lookup: dict[str, dict[str, dict[str, str]]] = {}

    def _parse_file(self) -> dict[str, Any]:
        """Parse the schematic file.

        Returns:
            Parsed data structure

        Note:
            This is a simplified parser. For production use, integrate kicad-skip
            or use kicad-netlist for proper parsing.
        """
        if self._data is not None:
            return self._data

        # Simple text-based parser for .kicad_sch (S-expression format)
        # In production, use kicad-skip library
        import re

        # Try multiple encodings to handle different KiCad file formats
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        content = None

        for encoding in encodings:
            try:
                content = self.file_path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            # Last resort: read with error handling
            content = self.file_path.read_text(encoding='utf-8', errors='ignore')

        # Parse lib_symbols first so _parse_components can use it
        self._lib_symbols_lookup = self._parse_lib_symbols(content)

        # Extract basic information using regex patterns
        # This is a simplified implementation
        self._data = {
            "path": str(self.file_path),
            "title_block": self._parse_title_block(content),
            "components": self._parse_components(content),
            "nets": self._parse_nets(content),
            "sheets": self._parse_sheets(content),
        }

        return self._data

    def _parse_lib_symbols(self, content: str) -> dict[str, dict[str, dict[str, str]]]:
        """Parse lib_symbols section to extract pin names and electrical types.

        Returns:
            {lib_id: {pin_number: {"name": str, "electrical_type": str}}}
        """
        result = {}

        # Find the (lib_symbols ...) block
        ls_match = re.search(r'\(lib_symbols\b', content)
        if not ls_match:
            return result

        # Extract the full lib_symbols block by counting parens
        start = ls_match.start()
        depth = 0
        i = start
        while i < len(content):
            if content[i] == '(':
                depth += 1
            elif content[i] == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        ls_block = content[start:i + 1]

        # Find top-level symbols (contain ":" like "Device:R") and extract their blocks
        lines = ls_block.split('\n')
        li = 0
        while li < len(lines):
            line = lines[li].strip()
            top_match = re.match(r'\(symbol\s+"([^"]*:[^"]*)"', line)
            if top_match:
                lib_id = top_match.group(1)
                # Extract full block for this top-level symbol
                sym_lines = []
                depth = 0
                j = li
                while j < len(lines):
                    cur = lines[j]
                    depth += cur.count('(') - cur.count(')')
                    sym_lines.append(cur)
                    if depth == 0 and len(sym_lines) > 1:
                        break
                    j += 1
                    if j - li > 500:
                        break
                sym_block = '\n'.join(sym_lines)

                # Extract pins from the entire symbol block (including sub-symbols)
                # Pin format: (pin <elec_type> <graphic> ... (name "X") (number "N"))
                pin_pattern = re.compile(
                    r'\(pin\s+(\w+)\s+\w+\s[\s\S]*?'
                    r'\(name\s+"([^"]*)"[\s\S]*?\)'
                    r'\s*\(number\s+"([^"]*)"',
                )
                pins = {}
                for pin_match in pin_pattern.finditer(sym_block):
                    elec_type = pin_match.group(1)
                    name = pin_match.group(2)
                    number = pin_match.group(3)
                    pins[number] = {
                        "name": name,
                        "electrical_type": elec_type,
                    }
                if pins:
                    result[lib_id] = pins

                li = j + 1
            else:
                li += 1

        return result

    def _parse_title_block(self, content: str) -> dict[str, str]:
        """Parse title block from schematic."""
        title_block = {
            "title": "",
            "date": "",
            "rev": "",
            "company": "",
            "comment": "",
        }

        # Extract title block values using regex
        patterns = {
            "title": r'title\s+"([^"]*)"',
            "date": r'date\s+"([^"]*)"',
            "rev": r'rev\s+"([^"]*)"',
            "company": r'company\s+"([^"]*)"',
            "comment": r'comment\s+\d+\s+"([^"]*)"',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                title_block[key] = match.group(1)

        return title_block

    def _parse_components(self, content: str) -> list[dict[str, Any]]:
        """Parse components from schematic."""
        components = []

        # Find all symbol instances
        # Pattern: (symbol (at x y rotation) (lib_id "...") ... (property "Reference" "...") ...)
        # Match from (symbol to the closing )
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('(symbol') and not line.startswith('(symbol "'):
                # Found a symbol instance, find the entire block
                symbol_block = []
                depth = 0
                j = i
                while j < len(lines):
                    current_line = lines[j]
                    # Count parentheses
                    depth += current_line.count('(') - current_line.count(')')
                    symbol_block.append(current_line)
                    if depth == 0 and len(symbol_block) > 1:
                        break
                    j += 1
                    if j - i > 200:  # Safety limit
                        break

                block_text = '\n'.join(symbol_block)

                # Extract lib_id
                lib_id_match = re.search(r'\(lib_id\s+"([^"]+)"', block_text)
                if not lib_id_match:
                    i = j + 1
                    continue

                lib_id = lib_id_match.group(1)

                # Extract position (at x y rotation)
                at_match = re.search(r'^\s*\(at\s+([\d.]+)\s+([\d.]+)\s+(\d+)\)', block_text, re.MULTILINE)
                if at_match:
                    x = float(at_match.group(1))
                    y = float(at_match.group(2))
                    rotation = float(at_match.group(3))
                else:
                    x, y, rotation = 0.0, 0.0, 0.0

                # Extract reference
                ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block_text)
                reference = ref_match.group(1) if ref_match else ""

                # Extract value
                value_match = re.search(r'\(property\s+"Value"\s+"([^"]+)"', block_text)
                value = value_match.group(1) if value_match else ""

                # Extract footprint
                fp_match = re.search(r'\(property\s+"Footprint"\s+"([^"]+)"', block_text)
                footprint = fp_match.group(1) if fp_match else None

                # Extract pins and enrich with lib_symbols data
                pins = []
                lib_pin_data = self._lib_symbols_lookup.get(lib_id, {})
                for pin_match in re.finditer(r'\(pin\s+"([^"]+)"', block_text):
                    pin_num = pin_match.group(1)
                    pin_info = lib_pin_data.get(pin_num, {})
                    pins.append({
                        "number": pin_num,
                        "name": pin_info.get("name", ""),
                        "electrical_type": pin_info.get("electrical_type", ""),
                    })

                # Extract component flags
                flags = dict(KICAD_FLAG_DEFAULTS)
                for flag in KICAD_SYMBOL_FLAGS:
                    if f"({flag} yes)" in block_text:
                        flags[flag] = True
                    elif f"({flag} no)" in block_text:
                        flags[flag] = False

                # Skip library symbols (no reference)
                if reference and not reference.startswith('#'):
                    # Build properties
                    properties = [
                        {"key": "Reference", "value": reference},
                        {"key": "Value", "value": value},
                    ]
                    if footprint:
                        properties.append({"key": "Footprint", "value": footprint})

                    components.append({
                        "lib_id": lib_id,
                        "reference": reference,
                        "value": value,
                        "properties": properties,
                        "at": {"x": x, "y": y},
                        "pins": pins,
                        "flags": flags,
                    })

                i = j + 1
            else:
                i += 1

        return components

    def _parse_nets(self, content: str) -> list[dict[str, Any]]:
        """Parse nets from schematic."""
        nets = {}

        # KiCad 9.0 uses global_label, label, and wire to define nets
        # Extract global labels
        global_label_pattern = r'\(global_label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.]+)\s+([\d.]+)[^\)]*\)'
        for match in re.finditer(global_label_pattern, content):
            name = match.group(1)
            x = float(match.group(2))
            y = float(match.group(3))
            nets[name] = {
                "name": name,
                "code": len(nets),
                "type": "global",
                "position": (x, y),
            }

        # Extract local labels
        label_pattern = r'\(label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.]+)\s+([\d.]+)[^\)]*\)'
        for match in re.finditer(label_pattern, content):
            name = match.group(1)
            if name not in nets:  # Avoid duplicates
                x = float(match.group(2))
                y = float(match.group(3))
                nets[name] = {
                    "name": name,
                    "code": len(nets),
                    "type": "local",
                    "position": (x, y),
                }

        # Extract power port labels (like +3V3, GND, etc.)
        power_pattern = r'\(symbol\s+\(lib_id\s+"power:([^"]+)"[\s\S]*?\(at\s+([\d.]+)\s+([\d.]+)'
        for match in re.finditer(power_pattern, content):
            name = match.group(1)
            if name not in nets:  # Avoid duplicates
                x = float(match.group(2))
                y = float(match.group(3))
                nets[name] = {
                    "name": name,
                    "code": len(nets),
                    "type": "power",
                    "position": (x, y),
                }

        return list(nets.values())

    def _parse_sheets(self, content: str) -> list[dict[str, str]]:
        """Parse hierarchical sheets."""
        sheets = []

        # Find sheet instances
        sheet_pattern = r'\(sheet\s+\(at\s+(\d+)\s+(\d+)\)\s*\(size\s+\d+\s+\d+\)\s*\(fields_autoplaced\s+yes\)\s*\(stroke[^)]*\)\s*\(fill[^)]*\)\s*\(property\s+"Sheetname"\s+"([^"]+)"[^)]*\(property\s+"Sheetfile"\s+"([^"]+)"'

        for match in re.finditer(sheet_pattern, content):
            sheets.append({
                "name": match.group(3),
                "file": match.group(4),
            })

        return sheets

    def get_components(self) -> list[SchematicComponent]:
        """Get all components from schematic.

        Returns:
            List of components
        """
        data = self._parse_file()
        return [SchematicComponent.from_kicad_skip(c) for c in data["components"]]

    def get_nets(self) -> list[SchematicNet]:
        """Get all nets from schematic.

        Returns:
            List of nets
        """
        data = self._parse_file()
        return [SchematicNet.from_kicad_skip(n) for n in data["nets"]]

    def get_title_block(self) -> dict[str, str]:
        """Get title block information.

        Returns:
            Dictionary with title, date, rev, company, comment
        """
        data = self._parse_file()
        return data["title_block"]

    def get_sheets(self) -> list[dict[str, str]]:
        """Get hierarchical sheets.

        Returns:
            List of sheet information
        """
        data = self._parse_file()
        return data["sheets"]

    def get_component_by_reference(self, reference: str) -> Optional[SchematicComponent]:
        """Get a component by its reference designator.

        Args:
            reference: Component reference (e.g., "R1", "U1")

        Returns:
            Component if found, None otherwise
        """
        for component in self.get_components():
            if component.reference == reference:
                return component
        return None

    def search_components(self, pattern: str) -> list[SchematicComponent]:
        """Search for components by pattern.

        Args:
            pattern: Search pattern (matches reference, value, or library_id)

        Returns:
            List of matching components
        """
        import re

        regex = re.compile(pattern, re.IGNORECASE)
        results = []

        for component in self.get_components():
            if (
                regex.search(component.reference)
                or regex.search(component.value)
                or regex.search(component.library_id)
            ):
                results.append(component)

        return results

    def get_component_connections(self, reference: str) -> dict[str, Any]:
        """Get all network connections for a component.

        Args:
            reference: Component reference (e.g., "R16")

        Returns:
            Dictionary with connection information:
            {
                "nets": ["net_name1", "net_name2"],
                "labels": ["label1", "label2"],
                "connected_components": ["comp1", "comp2"]
            }
        """
        content = self.file_path.read_text()

        # Find the component instance
        comp_pattern = rf'\(symbol\s+[\s\S]*?\(property\s+"Reference"\s+"{re.escape(reference)}"'
        comp_match = re.search(comp_pattern, content, re.DOTALL)

        if not comp_match:
            return {"error": f"Component {reference} not found"}

        # Extract the component block (from symbol to closing paren)
        start = comp_match.start()
        depth = 0
        i = start
        while i < len(content):
            if content[i] == '(':
                depth += 1
            elif content[i] == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1

        comp_block = content[start:i]

        # Find all pins in this component
        pins = []
        for pin_match in re.finditer(r'\(pin\s+"([^"]+)"', comp_block):
            pins.append(pin_match.group(1))

        # Search for connections by finding wires near the component position
        comp = self.get_component_by_reference(reference)
        if not comp:
            return {"error": f"Component {reference} not found"}

        cx, cy = comp.position

        # Find all labels and global labels
        labels = []
        for label_match in re.finditer(r'\((?:global_)?label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.]+)\s+([\d.]+)', content):
            label_name = label_match.group(1)
            lx, ly = float(label_match.group(2)), float(label_match.group(3))
            dist = ((lx - cx)**2 + (ly - cy)**2)**0.5
            labels.append({"name": label_name, "position": (lx, ly), "distance": dist})

        # Find hierarchical labels
        for label_match in re.finditer(r'\(hierarchical_label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.]+)\s+([\d.]+)', content):
            label_name = label_match.group(1)
            lx, ly = float(label_match.group(2)), float(label_match.group(3))
            dist = ((lx - cx)**2 + (ly - cy)**2)**0.5
            labels.append({"name": label_name, "position": (lx, ly), "distance": dist})

        # Filter to nearby labels (within 20mm)
        nearby_labels = [l for l in labels if l["distance"] < 20]

        # Find nearby components (within 15mm)
        components = self.get_components()
        nearby_comps = []
        for c in components:
            if c.reference == reference:
                continue
            dist = ((c.position[0] - cx)**2 + (c.position[1] - cy)**2)**0.5
            if dist < 15:
                nearby_comps.append({
                    "reference": c.reference,
                    "value": c.value,
                    "distance": dist,
                    "position": c.position
                })

        return {
            "component": reference,
            "position": comp.position,
            "pins": pins,
            "nearby_labels": nearby_labels[:10],
            "nearby_components": nearby_comps[:10],
        }

    def trace_net(self, reference: str, pin_number: Optional[str] = None) -> dict[str, Any]:
        """Trace network connections from a component pin.

        Args:
            reference: Component reference (e.g., "R16")
            pin_number: Optional pin number to trace (if None, trace all pins)

        Returns:
            Network trace information
        """
        connections = self.get_component_connections(reference)

        if "error" in connections:
            return connections

        # Analyze the nearby data to infer network connections
        inferred_nets = []

        # Check for hierarchical labels that indicate function
        for label in connections["nearby_labels"]:
            label_name = label["name"]
            if any(keyword in label_name.upper() for keyword in
                   ["I2C", "SCL", "SDA", "SMBUS", "PMIC", "GPIO", "EN", "INT"]):
                inferred_nets.append({
                    "name": label_name,
                    "type": "signal",
                    "distance": label["distance"]
                })

        return {
            "component": reference,
            "position": connections["position"],
            "inferred_connections": inferred_nets,
            "nearby_components": connections["nearby_components"][:5],
        }

    def build_wire_network(self) -> dict[tuple[float, float], list[tuple[float, float]]]:
        """Build a graph of wire connections.

        Returns:
            Dictionary mapping each point to its connected neighbors
        """
        import re

        content = self.file_path.read_text()

        # Find all wire segments
        wire_pattern = r'\(wire\s+\(pts\s+\(xy\s+([\d.]+)\s+([\d.]+)\)\s+\(xy\s+([\d.]+)\s+([\d.]+)\)'

        network = {}

        for match in re.finditer(wire_pattern, content):
            x1, y1 = float(match.group(1)), float(match.group(2))
            x2, y2 = float(match.group(3)), float(match.group(4))

            p1 = (x1, y1)
            p2 = (x2, y2)

            if p1 not in network:
                network[p1] = []
            if p2 not in network:
                network[p2] = []

            network[p1].append(p2)
            network[p2].append(p1)

        # Find junctions and merge connections
        junction_pattern = r'\(junction\s+\(at\s+([\d.]+)\s+([\d.]+)'
        for match in re.finditer(junction_pattern, content):
            jx, jy = float(match.group(1)), float(match.group(2))
            jpos = (jx, jy)

            # For a junction, all wires meeting at this point should be connected
            # Find all wire endpoints at this position (with small tolerance)
            tolerance = 0.01  # 0.01mm tolerance
            connected_points = [p for p in network if
                               abs(p[0] - jx) < tolerance and abs(p[1] - jy) < tolerance]

            # Merge all connections at junction
            all_neighbors = set()
            for p in connected_points:
                all_neighbors.update(network[p])

            for p in connected_points:
                network[p] = list(all_neighbors)

        return network

    def trace_wire_network(self, reference: str, max_depth: int = 20) -> dict[str, Any]:
        """Trace wire connections from a component.

        Args:
            reference: Component reference (e.g., "R16")
            max_depth: Maximum connection depth to trace

        Returns:
            Dictionary with traced connections and labels
        """
        import re

        # Get component position
        comp = self.get_component_by_reference(reference)
        if not comp:
            return {"error": f"Component {reference} not found"}

        cx, cy = comp.position

        # Build wire network
        network = self.build_wire_network()

        # Find all labels
        content = self.file_path.read_text()

        # Find hierarchical labels
        h_labels = []
        for label_match in re.finditer(
            r'\(hierarchical_label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.]+)\s+([\d.]+)',
            content
        ):
            name = label_match.group(1)
            lx, ly = float(label_match.group(2)), float(label_match.group(3))
            h_labels.append({"name": name, "position": (lx, ly)})

        # Find global labels
        g_labels = []
        for label_match in re.finditer(
            r'\(global_label\s+"([^"]+)"[\s\S]*?\(at\s+([\d.]+)\s+([\d.]+)',
            content
        ):
            name = label_match.group(1)
            lx, ly = float(label_match.group(2)), float(label_match.group(3))
            g_labels.append({"name": name, "position": (lx, ly)})

        all_labels = h_labels + g_labels

        # Start from component position and trace
        max_tolerance = 20.0  # 20mm max tolerance (for components with pin offset)
        start_point = None
        min_dist = float('inf')

        # Find the nearest wire endpoint to component
        for point in network:
            dist = ((point[0] - cx)**2 + (point[1] - cy)**2)**0.5
            if dist < min_dist:
                min_dist = dist
                start_point = point

        # Only proceed if the nearest point is within tolerance
        if min_dist > max_tolerance:
            return {
                "component": reference,
                "position": comp.position,
                "connected_labels": [],
                "trace_path": [],
                "error": f"No wire found within {max_tolerance}mm (nearest: {min_dist:.2f}mm)",
            }

        # BFS trace through network
        visited = set()
        queue = [start_point]
        trace_path = []
        connected_labels = []

        while queue and len(visited) < max_depth:
            point = queue.pop(0)
            if point in visited:
                continue
            visited.add(point)

            trace_path.append(point)

            # Check if this point is near a label
            label_tolerance = 5.0  # 5mm tolerance for label matching
            for label in all_labels:
                lx, ly = label["position"]
                dist = ((point[0] - lx)**2 + (point[1] - ly)**2)**0.5
                if dist < label_tolerance and not any(l["name"] == label["name"] for l in connected_labels):
                    connected_labels.append({
                        "name": label["name"],
                        "position": label["position"],
                        "distance": dist,
                    })

            # Add neighbors to queue
            if point in network:
                for neighbor in network[point]:
                    if neighbor not in visited:
                        queue.append(neighbor)

        # Find nearby power symbols
        power_tolerance = 15.0  # 15mm tolerance for power symbols
        power_pattern = r'\(symbol\s+\(lib_id\s+"power:([^"]+)"[\s\S]*?\(at\s+([\d.]+)\s+([\d.]+)'
        for match in re.finditer(power_pattern, content):
            power_name = match.group(1)
            px, py = float(match.group(2)), float(match.group(3))
            dist = ((px - cx)**2 + (py - cy)**2)**0.5
            if dist < power_tolerance:
                connected_labels.append({
                    "name": f"POWER:{power_name}",
                    "position": (px, py),
                    "distance": dist,
                })

        return {
            "component": reference,
            "position": comp.position,
            "connected_labels": connected_labels,
            "trace_path": trace_path,
        }
