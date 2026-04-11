"""PCB file parser using KiCad Python API (pcbnew)."""

from dataclasses import dataclass, field
from typing import Any

from ..utils.file_handlers import validate_kicad_file


@dataclass
class PCBFootprint:
    """Footprint from PCB file."""

    reference: str
    value: str
    library: str
    position: tuple[float, float]
    rotation: float
    pads_count: int
    layer: str
    properties: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.reference}: {self.value} at ({self.position[0]:.2f}, {self.position[1]:.2f})"


@dataclass
class PCBNet:
    """Net from PCB file."""

    name: str
    code: int
    node_count: int = 0


@dataclass
class PCBTrack:
    """Track (segment) from PCB file."""

    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str


class PCBParserKiCad:
    """PCB file parser using KiCad's official Python API (pcbnew).

    This parser uses pcbnew which is the official KiCad Python API.
    It provides reliable access to PCB data without fragile regex parsing.
    """

    def __init__(self, file_path: str) -> None:
        """Initialize parser with PCB file.

        Args:
            file_path: Path to .kicad_pcb file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file has wrong extension
            ImportError: If pcbnew is not available
        """
        self.file_path = validate_kicad_file(file_path, ".kicad_pcb")

        # Try to import pcbnew (KiCad Python API)
        try:
            import pcbnew
        except ImportError as e:
            raise ImportError(
                "pcbnew module not found. Please install KiCad or ensure it's in PATH.\n"
                f"Error: {e}"
            ) from e

        # Load the board
        self.board = pcbnew.LoadBoard(str(self.file_path))

    def get_footprints(self) -> list[PCBFootprint]:
        """Get all footprints from PCB.

        Returns:
            List of footprints
        """
        footprints = []

        for fp in self.board.GetFootprints():
            # Get position in mm
            pos = fp.GetPosition()
            pos_mm = (pos[0] / 1e6, pos[1] / 1e6)  # Convert KiCad internal units to mm

            # Get rotation
            rotation = fp.GetOrientation().AsDegrees()

            # Get layer
            layer = fp.GetLayerName()

            # Get library info
            fpid = fp.GetFPID()
            library = fpid.GetLibItemName() if fpid.IsValid() else ""

            # Get properties
            properties = {}
            for key in ["Reference", "Value", "Footprint", "Datasheet"]:
                try:
                    value = fp.GetProperty(key)
                    if value:
                        properties[key] = value
                except Exception:
                    pass

            footprints.append(PCBFootprint(
                reference=fp.GetReference(),
                value=fp.GetValue(),
                library=library,
                position=pos_mm,
                rotation=rotation,
                pads_count=fp.GetPadCount(),
                layer=layer,
                properties=properties,
            ))

        return footprints

    def get_nets(self) -> list[PCBNet]:
        """Get all nets from PCB.

        Returns:
            List of nets
        """
        nets = []

        # Get net info list
        net_info_list = self.board.GetNetInfo()

        # Iterate through all nets (NetsByName returns a dict)
        nets_dict = net_info_list.NetsByName()
        for net_name, net in nets_dict.items():
            name = str(net_name)
            if name and name not in ["", "GND", "0"]:  # Skip empty/GND nets
                nets.append(PCBNet(
                    name=name,
                    code=net.GetNetCode(),
                    node_count=0,
                ))

        return nets

    def get_tracks(self) -> list[PCBTrack]:
        """Get all tracks from PCB.

        Returns:
            List of tracks
        """
        tracks = []

        for track in self.board.GetTracks():
            start = track.GetStart()
            end = track.GetEnd()
            start_mm = (start[0] / 1e6, start[1] / 1e6)
            end_mm = (end[0] / 1e6, end[1] / 1e6)

            layer_name = self.board.GetLayerName(track.GetLayer())

            tracks.append(PCBTrack(
                start=start_mm,
                end=end_mm,
                width=track.GetWidth() / 1e6,
                layer=layer_name,
            ))

        return tracks

    def get_footprint_by_reference(self, reference: str) -> PCBFootprint | None:
        """Get a footprint by its reference designator.

        Args:
            reference: Footprint reference (e.g., "R1", "U1")

        Returns:
            Footprint if found, None otherwise
        """
        for footprint in self.get_footprints():
            if footprint.reference == reference:
                return footprint
        return None

    def get_board_info(self) -> dict[str, Any]:
        """Get general board information.

        Returns:
            Dictionary with board metadata
        """
        title_block = self.board.GetTitleBlock()

        return {
            "title": title_block.GetTitle(),
            "date": title_block.GetDate(),
            "revision": title_block.GetRevision(),
            "company": title_block.GetCompany(),
            "comment": title_block.GetComment(0),
            "file_path": str(self.file_path),
            "footprints_count": len(self.board.GetFootprints()),
            "tracks_count": len(self.board.GetTracks()),
            "nets_count": self.board.GetNetCount(),
        }
