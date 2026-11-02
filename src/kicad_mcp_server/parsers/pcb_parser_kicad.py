"""PCB file parser using KiCad Python API (pcbnew)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.file_handlers import validate_kicad_file

# pcbnew returns user-facing layer names (TOP, BOTTOM, L2 INNER, etc.)
# but users typically reference canonical names (F.Cu, B.Cu, In1.Cu, etc.)
_CANONICAL_LAYER_MAP: dict[str, str] = {
    "TOP": "F.Cu",
    "BOTTOM": "B.Cu",
}
_INNER_RE = __import__("re").compile(r"^L(\d+)\s+INNER$")


def _canonicalize_layer(name: str) -> str:
    """Convert pcbnew layer name to canonical KiCad name."""
    if name in _CANONICAL_LAYER_MAP:
        return _CANONICAL_LAYER_MAP[name]
    m = _INNER_RE.match(name)
    if m:
        # L2 INNER -> In1.Cu (pcbnew L2 = 1st inner = In1.Cu)
        return f"In{int(m.group(1)) - 1}.Cu"
    # Handle "L2 LNNER" typo from some KiCad versions
    m2 = __import__("re").match(r"^L(\d+)\s+LNNER$", name)
    if m2:
        return f"In{int(m2.group(1)) - 1}.Cu"
    return name


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
    net: str = ""
    length: float = 0.0


@dataclass
class PCBVia:
    """Via from PCB file."""

    position: tuple[float, float]
    size: float
    drill: float
    top_layer: str
    bottom_layer: str
    net: str = ""


@dataclass
class PCBZone:
    """Copper zone from PCB file."""

    net_name: str
    layer: str
    filled: bool


class PCBParserKiCad:
    """PCB file parser using KiCad's official Python API (pcbnew)."""

    def __init__(self, file_path: str) -> None:
        self.file_path = validate_kicad_file(file_path, ".kicad_pcb")

        try:
            import pcbnew
        except ImportError as e:
            raise ImportError(
                "pcbnew module not found. Please install KiCad or ensure it's in PATH.\n"
                f"Error: {e}"
            ) from e

        self.board = pcbnew.LoadBoard(str(self.file_path))
        self._pcbnew = pcbnew

    def _to_mm(self, iu_value: int | float) -> float:
        """Convert KiCad internal units (nm) to mm."""
        return float(iu_value) / 1e6

    def _pos_mm(self, pos) -> tuple[float, float]:
        """Convert KiCad position to (x_mm, y_mm)."""
        return (pos.x / 1e6, pos.y / 1e6)

    def _tracks(self) -> list:
        """Return the tracks, arcs and vias of the board.

        BOARD.GetTracks() iterates with it.next() in KiCad 10.0.6 and earlier.
        SWIG 4.4 and later do not have this method, thus the iteration fails
        (KiCad issue 25423, fixed in KiCad 10.0.7). Access by index works with
        each SWIG version. Cast() gives the type of each item (PCB_TRACK,
        PCB_ARC, PCB_VIA), as the iterator of KiCad does.
        """
        tracks = self.board.Tracks()
        return [tracks[i].Cast() for i in range(len(tracks))]

    def _layer_name(self, layer_id_or_name) -> str:
        """Get canonical layer name (F.Cu, B.Cu, In1.Cu, etc.)."""
        raw = self.board.GetLayerName(layer_id_or_name)
        return _canonicalize_layer(raw)

    # ── Footprints ──────────────────────────────────────────

    def get_footprints(self) -> list[PCBFootprint]:
        footprints = []
        for fp in self.board.GetFootprints():
            pos = fp.GetPosition()
            fpid = fp.GetFPID()
            library = fpid.GetLibItemName() if fpid.IsValid() else ""

            properties: dict[str, str] = {}
            for key in ("Reference", "Value", "Footprint", "Datasheet"):
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
                position=self._pos_mm(pos),
                rotation=fp.GetOrientation().AsDegrees(),
                pads_count=fp.GetPadCount(),
                layer=_canonicalize_layer(fp.GetLayerName()),
                properties=properties,
            ))
        return footprints

    def get_footprint_by_reference(self, reference: str) -> PCBFootprint | None:
        for footprint in self.get_footprints():
            if footprint.reference == reference:
                return footprint
        return None

    # ── Nets ────────────────────────────────────────────────

    def get_nets(self) -> list[PCBNet]:
        nets = []
        net_info = self.board.GetNetInfo()
        for _name, net in net_info.NetsByName().items():
            name = str(_name)
            if name:
                nets.append(PCBNet(name=name, code=net.GetNetCode()))
        return nets

    # ── Tracks ──────────────────────────────────────────────

    def get_tracks(self) -> list[PCBTrack]:
        """Get all track segments (excludes vias)."""
        pcbnew = self._pcbnew
        tracks = []
        for track in self._tracks():
            if isinstance(track, pcbnew.PCB_VIA):
                continue
            tracks.append(PCBTrack(
                start=self._pos_mm(track.GetStart()),
                end=self._pos_mm(track.GetEnd()),
                width=self._to_mm(track.GetWidth()),
                layer=self._layer_name(track.GetLayer()),
                net=track.GetNetname(),
                length=self._to_mm(track.GetLength()),
            ))
        return tracks

    def get_tracks_by_net(self, net_name: str) -> list[PCBTrack]:
        """Get track segments for a specific net."""
        return [t for t in self.get_tracks() if t.net == net_name]

    # ── Vias ────────────────────────────────────────────────

    def get_vias(self) -> list[PCBVia]:
        """Get all vias (uses GetWidth(layer) to avoid headless assert)."""
        pcbnew = self._pcbnew
        vias = []
        for track in self._tracks():
            if not isinstance(track, pcbnew.PCB_VIA):
                continue
            top_layer = track.TopLayer()
            size_mm = self._to_mm(track.GetWidth(top_layer))
            vias.append(PCBVia(
                position=self._pos_mm(track.GetStart()),
                size=size_mm,
                drill=self._to_mm(track.GetDrill()),
                top_layer=self._layer_name(top_layer),
                bottom_layer=self._layer_name(track.BottomLayer()),
                net=track.GetNetname(),
            ))
        return vias

    def get_vias_for_net(self, net_name: str) -> list[PCBVia]:
        """Get vias belonging to a specific net."""
        return [v for v in self.get_vias() if v.net == net_name]

    # ── Zones ───────────────────────────────────────────────

    def get_zones(self) -> list[PCBZone]:
        """Get all copper zones."""
        zones = []
        for zone in self.board.Zones():
            zones.append(PCBZone(
                net_name=zone.GetNetname(),
                layer=_canonicalize_layer(zone.GetLayerName()),
                filled=zone.IsFilled(),
            ))
        return zones

    def get_zones_for_net(self, net_name: str) -> list[PCBZone]:
        return [z for z in self.get_zones() if z.net_name == net_name]

    # ── Board Info ──────────────────────────────────────────

    def get_board_info(self) -> dict[str, Any]:
        title_block = self.board.GetTitleBlock()
        bbox = self.board.ComputeBoundingBox(True)
        size = bbox.GetSize()

        return {
            "title": title_block.GetTitle(),
            "date": title_block.GetDate(),
            "revision": title_block.GetRevision(),
            "company": title_block.GetCompany(),
            "file_path": str(self.file_path),
            "board_width_mm": self._to_mm(size.x),
            "board_height_mm": self._to_mm(size.y),
            "footprints_count": len(self.board.GetFootprints()),
            "tracks_count": sum(
                1 for t in self._tracks()
                if not isinstance(t, self._pcbnew.PCB_VIA)
            ),
            "vias_count": sum(
                1 for t in self._tracks()
                if isinstance(t, self._pcbnew.PCB_VIA)
            ),
            "nets_count": self.board.GetNetCount(),
            "zones_count": len(list(self.board.Zones())),
        }

    # ── Design Rules ────────────────────────────────────────

    def get_design_rules(self) -> dict[str, Any]:
        ds = self.board.GetDesignSettings()
        pcbnew = self._pcbnew
        return {
            "board_thickness_mm": pcbnew.ToMM(ds.GetBoardThickness()),
            "copper_layers": ds.GetCopperLayerCount(),
            "smallest_clearance_mm": pcbnew.ToMM(ds.GetSmallestClearanceValue()),
            "biggest_clearance_mm": pcbnew.ToMM(ds.GetBiggestClearanceValue()),
            "current_track_width_mm": pcbnew.ToMM(ds.GetCurrentTrackWidth()),
            "current_via_drill_mm": pcbnew.ToMM(ds.GetCurrentViaDrill()),
            "current_via_size_mm": pcbnew.ToMM(ds.GetCurrentViaSize()),
            "current_diff_pair_width_mm": pcbnew.ToMM(ds.GetCurrentDiffPairWidth()),
            "current_diff_pair_gap_mm": pcbnew.ToMM(ds.GetCurrentDiffPairGap()),
            "drc_epsilon_mm": pcbnew.ToMM(ds.GetDRCEpsilon()),
            "hole_plating_mm": pcbnew.ToMM(ds.GetHolePlatingThickness()),
        }

    # ── Aggregate Stats ─────────────────────────────────────

    def get_net_track_stats(self) -> dict[str, dict[str, Any]]:
        """Per-net track statistics: total_length, segment_count, widths, layers."""
        stats: dict[str, dict[str, Any]] = {}
        for track in self.get_tracks():
            net = track.net or "(unnamed)"
            if net not in stats:
                stats[net] = {
                    "total_length": 0.0,
                    "segment_count": 0,
                    "widths": [],
                    "layers": set(),
                }
            s = stats[net]
            s["total_length"] += track.length
            s["segment_count"] += 1
            s["widths"].append(track.width)
            s["layers"].add(track.layer)
        # Convert sets to sorted lists for JSON
        for s in stats.values():
            s["layers"] = sorted(s["layers"])
        return stats

    def get_via_stats(self) -> dict[str, Any]:
        """Aggregate via statistics."""
        vias = self.get_vias()
        if not vias:
            return {"count": 0}

        drill_counts: dict[str, int] = {}
        layer_span_counts: dict[str, int] = {}
        net_via_counts: dict[str, int] = {}

        for v in vias:
            drill_key = f"{v.drill:.3f}mm"
            drill_counts[drill_key] = drill_counts.get(drill_key, 0) + 1

            span = f"{v.top_layer} -> {v.bottom_layer}"
            layer_span_counts[span] = layer_span_counts.get(span, 0) + 1

            net = v.net or "(unnamed)"
            net_via_counts[net] = net_via_counts.get(net, 0) + 1

        return {
            "count": len(vias),
            "drill_sizes": dict(sorted(drill_counts.items(), key=lambda x: -x[1])),
            "layer_spans": layer_span_counts,
            "top_via_nets": dict(sorted(net_via_counts.items(), key=lambda x: -x[1])[:20]),
        }
