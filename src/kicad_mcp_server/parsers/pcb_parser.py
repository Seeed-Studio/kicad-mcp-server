"""PCB file parser wrapper using kicad-skip."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.file_handlers import validate_kicad_file


@dataclass
class PCBFootprint:
    """Footprint from PCB file."""

    reference: str
    footprint_id: str
    value: str
    layer: str = "F.Cu"
    position: tuple[float, float] = (0.0, 0.0)
    rotation: float = 0.0
    pad_count: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PCBFootprint":
        """Create from parsed data structure."""
        at = data.get("at", {})
        position = (float(at.get("x", 0)), float(at.get("y", 0)))
        rotation = float(at.get("rotation", 0))

        return cls(
            reference=data.get("reference", ""),
            footprint_id=data.get("footprint_id", ""),
            value=data.get("value", ""),
            layer=data.get("layer", "F.Cu"),
            position=position,
            rotation=rotation,
            pad_count=len(data.get("pads", [])),
        )


def _read_file_with_encoding_fallback(file_path: Path) -> str:
    """Read file with multiple encoding fallback support.

    Args:
        file_path: Path to the file to read

    Returns:
        File content as string

    Note:
        Tries multiple encodings to handle different KiCad file formats
        and potential encoding issues.
    """
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    content = None

    for encoding in encodings:
        try:
            content = file_path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        # Last resort: read with error handling
        content = file_path.read_text(encoding='utf-8', errors='ignore')

    return content


class PCBParser:
    """Parser for KiCad PCB files (.kicad_pcb)."""

    def __init__(self, file_path: str) -> None:
        """Initialize parser with PCB file.

        Args:
            file_path: Path to .kicad_pcb file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a .kicad_pcb file
        """
        self.file_path = validate_kicad_file(file_path, ".kicad_pcb")
        self._data: dict[str, Any] | None = None

    def _parse_file(self) -> dict[str, Any]:
        """Parse the PCB file.

        Returns:
            Parsed data structure
        """
        if self._data is not None:
            return self._data

        content = _read_file_with_encoding_fallback(self.file_path)

        # Extract basic information
        self._data = {
            "path": str(self.file_path),
            "general": self._parse_general(content),
            "footprints": self._parse_footprints(content),
            "tracks": self._parse_tracks(content),
            "vias": self._parse_vias(content),
            "zones": self._parse_zones(content),
            "setup": self._parse_setup(content),
        }

        return self._data

    def _parse_general(self, content: str) -> dict[str, Any]:
        """Parse general section."""
        general = {"thickness": 1.6, "layers": 2}

        # Extract thickness
        thickness_match = re.search(r'thickness\s+([\d.]+)', content)
        if thickness_match:
            general["thickness"] = float(thickness_match.group(1))

        # Count layers
        layer_pattern = r'\(layer\s+"([^"]+)"'
        layers = re.findall(layer_pattern, content)
        # Filter for copper layers. A startswith("F."/"B.") check is wrong:
        # F.SilkS / F.Paste / F.Mask / F.Fab / F.CrtYd / F.Adhes all start with
        # "F." but are NOT copper. Only F.Cu, B.Cu and In<N>.Cu are copper.
        copper_layers = [
            layer for layer in set(layers)
            if layer in ("F.Cu", "B.Cu") or re.match(r"In\d+\.Cu$", layer)
        ]
        general["layers"] = len(copper_layers) or 2

        return general

    def _parse_footprints(self, content: str) -> list[dict[str, Any]]:
        """Parse footprints from PCB.

        Uses multi-line regex to match KiCad footprint instances.
        """
        footprints = []

        # Simpler pattern: Match (footprint "..." followed by (at ... sometime later)
        # We'll find the footprint line, then search forward for the (at ...) line
        footprint_lines_pattern = r'\(footprint\s+"([^"]+)"'

        for match in re.finditer(footprint_lines_pattern, content):
            footprint_id = match.group(1)
            start_pos = match.start()

            # Search forward for the (at ...) line, within a reasonable distance
            search_area = content[start_pos:start_pos + 500]
            at_match = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\)', search_area)

            if at_match:
                x = float(at_match.group(1))
                y = float(at_match.group(2))
                rotation = float(at_match.group(3)) if at_match.group(3) else 0.0

                # Extract a larger block for reference and value
                # Find the matching closing parenthesis for the footprint
                depth = 0
                found_open = False
                end_pos = start_pos
                block_start = start_pos

                # Find where the (footprint block starts (first '(' after the keyword)
                while end_pos < len(content) and end_pos < start_pos + 20:
                    if content[end_pos] == '(':
                        found_open = True
                        block_start = end_pos
                        break
                    end_pos += 1

                if found_open:
                    # Now find the matching closing parenthesis
                    depth = 1
                    end_pos = block_start + 1
                    while end_pos < len(content):
                        if content[end_pos] == '(':
                            depth += 1
                        elif content[end_pos] == ')':
                            depth -= 1
                            if depth == 0:
                                break
                        end_pos += 1

                    footprint_block = content[block_start:end_pos]

                    # Extract reference: KiCad 9+ uses (property "Reference" "..."),
                    # KiCad 4/5 used (fp_text reference "..."). Support both.
                    ref_match = (re.search(r'\(property\s+"Reference"\s+"([^"]+)"', footprint_block)
                                 or re.search(r'\(fp_text\s+reference\s+"([^"]+)"', footprint_block))
                    reference = ref_match.group(1) if ref_match else ""

                    # Extract value (same version split)
                    val_match = (re.search(r'\(property\s+"Value"\s+"([^"]+)"', footprint_block)
                                 or re.search(r'\(fp_text\s+value\s+"([^"]+)"', footprint_block))
                    value = val_match.group(1) if val_match else ""

                    # Extract layer (default to F.Cu if not found)
                    layer_match = re.search(r'\(layer\s+"([^"]+)"', footprint_block)
                    layer = layer_match.group(1) if layer_match else "F.Cu"

                    # Count pads
                    pad_count = len(re.findall(r'\(pad\s+', footprint_block))

                    footprints.append({
                        "footprint_id": footprint_id,
                        "reference": reference,
                        "value": value,
                        "layer": layer,
                        "at": {"x": x, "y": y, "rotation": rotation},
                        "pads": [],
                        "pad_count": pad_count,
                    })

        return footprints

    def _top_level_blocks(self, content: str) -> dict[str, list[str]]:
        """Split the board into its direct children, grouped by keyword.

        Track and via fields are matched inside each block rather than with
        one positional regex, so field order, extra fields, negative
        coordinates and both net syntaxes (KiCad 9: ``(net 3)``, KiCad 10:
        ``(net "name")``) are all handled. Quoted strings are skipped while
        counting parentheses.
        """
        cached = getattr(self, "_blocks_cache", None)
        if cached is not None and cached[0] is content:
            return cached[1]

        blocks: dict[str, list[str]] = {}
        depth = 0
        in_str = False
        escaped = False
        block_start = -1
        for i, ch in enumerate(content):
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "(":
                depth += 1
                if depth == 2:
                    block_start = i
            elif ch == ")":
                if depth == 2 and block_start >= 0:
                    block = content[block_start:i + 1]
                    m = re.match(r"\(([A-Za-z_]+)", block)
                    if m:
                        blocks.setdefault(m.group(1), []).append(block)
                    block_start = -1
                depth -= 1

        self._blocks_cache = (content, blocks)
        return blocks

    def _net_names(self, content: str) -> dict[str, str]:
        """Map net codes to names from the KiCad 9 top-level net table."""
        names: dict[str, str] = {}
        for block in self._top_level_blocks(content).get("net", []):
            m = re.match(r'\(net\s+(\d+)\s+"((?:[^"\\]|\\.)*)"', block)
            if m:
                names[m.group(1)] = m.group(2)
        return names

    @staticmethod
    def _block_net(block: str, net_names: dict[str, str]) -> str:
        """Net name of a track/via block, for KiCad 9 codes and KiCad 10 names."""
        m = re.search(r'\(net\s+(?:"((?:[^"\\]|\\.)*)"|(\d+))', block)
        if not m:
            return ""
        if m.group(1) is not None:
            return m.group(1)
        return net_names.get(m.group(2), "")

    @staticmethod
    def _xy(block: str, key: str) -> tuple[float, float] | None:
        m = re.search(rf"\({key}\s+(-?[\d.]+)\s+(-?[\d.]+)", block)
        return (float(m.group(1)), float(m.group(2))) if m else None

    @staticmethod
    def _arc_length(
        p1: tuple[float, float], pm: tuple[float, float], p2: tuple[float, float]
    ) -> float:
        """Length of the circular arc through start, mid and end."""
        import math

        ax, ay = p1
        bx, by = pm
        cx, cy = p2
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-12:  # collinear: treat as straight
            return math.dist(p1, p2)
        ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay)
              + (cx**2 + cy**2) * (ay - by)) / d
        uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx)
              + (cx**2 + cy**2) * (bx - ax)) / d
        r = math.dist((ux, uy), p1)
        a1 = math.atan2(ay - uy, ax - ux)
        am = math.atan2(by - uy, bx - ux)
        a2 = math.atan2(cy - uy, cx - ux)
        # sweep from a1 to a2 in the direction that passes through am
        sweep = (a2 - a1) % (2 * math.pi)
        if (am - a1) % (2 * math.pi) > sweep:
            sweep = 2 * math.pi - sweep
        return r * sweep

    def _parse_tracks(self, content: str) -> list[dict[str, Any]]:
        """Parse track segments and arc tracks."""
        tracks = []
        blocks = self._top_level_blocks(content)
        net_names = self._net_names(content)

        for kind in ("segment", "arc"):
            for block in blocks.get(kind, []):
                start = self._xy(block, "start")
                end = self._xy(block, "end")
                width = re.search(r"\(width\s+([\d.]+)", block)
                layer = re.search(r'\(layer\s+"([^"]+)"', block)
                if not (start and end and width and layer):
                    continue
                if kind == "arc":
                    mid = self._xy(block, "mid")
                    length = (self._arc_length(start, mid, end) if mid
                              else ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5)
                else:
                    length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
                tracks.append({
                    "type": kind,
                    "start": {"x": start[0], "y": start[1]},
                    "end": {"x": end[0], "y": end[1]},
                    "width": float(width.group(1)),
                    "layer": layer.group(1),
                    "net": self._block_net(block, net_names),
                    "length": length,
                })

        return tracks

    def _parse_vias(self, content: str) -> list[dict[str, Any]]:
        """Parse vias."""
        vias = []
        net_names = self._net_names(content)

        for block in self._top_level_blocks(content).get("via", []):
            at = self._xy(block, "at")
            size = re.search(r"\(size\s+([\d.]+)", block)
            drill = re.search(r"\(drill\s+([\d.]+)", block)
            if not (at and size and drill):
                continue
            layers_m = re.search(r"\(layers((?:\s+\"[^\"]+\")+)\)", block)
            layers = re.findall(r'"([^"]+)"', layers_m.group(1)) if layers_m else []
            vias.append({
                "at": {"x": at[0], "y": at[1]},
                "size": float(size.group(1)),
                "drill": float(drill.group(1)),
                "top_layer": layers[0] if layers else "",
                "bottom_layer": layers[-1] if layers else "",
                "net": self._block_net(block, net_names),
            })

        return vias

    def _parse_zones(self, content: str) -> list[dict[str, Any]]:
        """Parse copper zones."""
        zones = []

        # KiCad 10 format: (zone (net "name") (layer "...") ...)
        zone_pattern = r'\(zone\s+\(net\s+"([^"]+)"\)\s+\(layer\s+"([^"]+)"\)'

        for match in re.finditer(zone_pattern, content):
            zones.append({
                "net_name": match.group(1),
                "layer": match.group(2),
            })

        # Fallback: KiCad 9 format (net code + net_name)
        if not zones:
            zone_pattern_v9 = r'\(zone\s+\(net\s+(\d+)\)\s*\(net_name\s+"([^"]+)"'
            for match in re.finditer(zone_pattern_v9, content):
                zones.append({
                    "net_name": match.group(2),
                    "layer": "",
                })

        return zones

    def _parse_setup(self, content: str) -> dict[str, Any]:
        """Parse setup section for design rules."""
        setup = {
            "trace_min": 0.2,
            "via_min": 0.4,
            "clearance": 0.15,
        }

        # Extract design rules
        setup_match = re.search(
            r'\(setup.*?\(min_resolution\s+([\d.]+)\)', content, re.DOTALL
        )
        if setup_match:
            # Try to extract trace and via sizes
            trace_match = re.search(
                r'\(trace_min\s+([\d.]+)', content[: content.find(setup_match.group(0)) + 500]
            )
            if trace_match:
                setup["trace_min"] = float(trace_match.group(1))

        return setup

    def get_footprints(self) -> list[PCBFootprint]:
        """Get all footprints from PCB.

        Returns:
            List of footprints
        """
        data = self._parse_file()
        return [PCBFootprint.from_dict(f) for f in data["footprints"]]

    def get_statistics(self) -> dict[str, Any]:
        """Get PCB statistics.

        Returns:
            Dictionary with statistics
        """
        data = self._parse_file()

        # Calculate board dimensions from footprint positions
        footprints = self.get_footprints()
        if footprints:
            x_coords = [f.position[0] for f in footprints]
            y_coords = [f.position[1] for f in footprints]
            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)
            # Add margin for board edge
            margin = 5.0
            width = max_x - min_x + (2 * margin)
            height = max_y - min_y + (2 * margin)
        else:
            width = height = 0.0

        # Calculate total pads from pad_count field
        total_pads = sum(f.get("pad_count", 0) for f in data["footprints"])

        return {
            "total_footprints": len(data["footprints"]),
            "total_pads": total_pads,
            "total_tracks": len(data["tracks"]),
            "total_vias": len(data["vias"]),
            "total_zones": len(data["zones"]),
            "board_width": width,
            "board_height": height,
            "layers": data["general"]["layers"],
            "thickness": data["general"]["thickness"],
        }
