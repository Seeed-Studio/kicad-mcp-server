"""PCB file parser wrapper using kicad-skip."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

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
        self._data: Optional[dict[str, Any]] = None

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
        # Filter for copper layers
        copper_layers = [l for l in layers if l.startswith(("F.", "B.", "In"))]
        general["layers"] = len(set(copper_layers))

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
            at_match = re.search(r'\(at\s+([\d.]+)\s+([\d.]+)(?:\s+([\d.\-]+))?\)', search_area)

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

                    # Extract reference from fp_text
                    ref_match = re.search(r'\(fp_text\s+reference\s+"([^"]+)"', footprint_block)
                    reference = ref_match.group(1) if ref_match else ""

                    # Extract value from fp_text
                    val_match = re.search(r'\(fp_text\s+value\s+"([^"]+)"', footprint_block)
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

    def _parse_tracks(self, content: str) -> list[dict[str, Any]]:
        """Parse track segments."""
        tracks = []

        # Pattern: (segment (start ...) (end ...) (width ...) (layer ...))
        segment_pattern = r'\(segment\s+\(start\s+([\d.]+)\s+([\d.]+)\)\s+\(end\s+([\d.]+)\s+([\d.]+)\)\s+\(width\s+([\d.]+)\)\s+\(layer\s+"([^"]+)"'

        for match in re.finditer(segment_pattern, content):
            tracks.append({
                "start": {"x": float(match.group(1)), "y": float(match.group(2))},
                "end": {"x": float(match.group(3)), "y": float(match.group(4))},
                "width": float(match.group(5)),
                "layer": match.group(6),
            })

        return tracks

    def _parse_vias(self, content: str) -> list[dict[str, Any]]:
        """Parse vias."""
        vias = []

        # Pattern: (via (at ...) (size ...) (drill ...) (layers ...) ...)
        via_pattern = r'\(via\s+\(at\s+([\d.]+)\s+([\d.]+)\)\s+\(size\s+([\d.]+)\)\s+\(drill\s+([\d.]+)'

        for match in re.finditer(via_pattern, content):
            vias.append({
                "at": {"x": float(match.group(1)), "y": float(match.group(2))},
                "size": float(match.group(3)),
                "drill": float(match.group(4)),
            })

        return vias

    def _parse_zones(self, content: str) -> list[dict[str, Any]]:
        """Parse copper zones."""
        zones = []

        # Pattern: (zone (net ...) (net_name ...) ...)
        zone_pattern = r'\(zone\s+\(net\s+(\d+)\)\s*\(net_name\s+"([^"]+)"'

        for match in re.finditer(zone_pattern, content):
            zones.append({
                "net": int(match.group(1)),
                "net_name": match.group(2),
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
