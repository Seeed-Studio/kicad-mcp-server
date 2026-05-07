"""Type definitions for KiCad MCP Server."""


from pydantic import BaseModel, Field


class ComponentInfo(BaseModel):
    """Information about a schematic component."""

    reference: str = Field(description="Component reference designator (e.g., R1, U1)")
    value: str = Field(description="Component value (e.g., 10k, ATmega328P)")
    footprint: str | None = Field(default=None, description="Assigned footprint")
    library_id: str = Field(description="Symbol library identifier")
    properties: dict[str, str] = Field(default_factory=dict, description="Additional properties")
    position: tuple[float, float] = Field(description="X, Y coordinates in schematic")
    unit: int | None = Field(default=None, description="Multi-unit part unit number")


class NetInfo(BaseModel):
    """Information about a net."""

    name: str = Field(description="Net name")
    code: int = Field(description="Internal net code")
    node_count: int = Field(description="Number of connected pins")
    pins: list[str] = Field(default_factory=list, description="Connected pins (ref:pin)")


class PinInfo(BaseModel):
    """Information about a component pin."""

    number: str = Field(description="Pin number")
    name: str = Field(description="Pin name/function")
    type: str = Field(description="Electrical type (input, output, power, etc.)")


class SymbolInfo(BaseModel):
    """Detailed information about a schematic symbol."""

    reference: str = Field(description="Component reference designator")
    value: str = Field(description="Component value")
    library_id: str = Field(description="Symbol library identifier")
    pins: list[PinInfo] = Field(default_factory=list, description="Pin definitions")
    properties: dict[str, str] = Field(default_factory=dict, description="Symbol properties")
    unit_count: int = Field(default=1, description="Number of units in symbol")


class FootprintInfo(BaseModel):
    """Information about a PCB footprint."""

    reference: str = Field(description="Component reference designator")
    footprint_id: str = Field(description="Footprint library identifier")
    value: str = Field(description="Component value")
    layer: str = Field(description="PCB layer (F.Cu, B.Cu, etc.)")
    position: tuple[float, float] = Field(description="X, Y coordinates")
    rotation: float = Field(description="Rotation angle in degrees")
    pads: int = Field(default=0, description="Number of pads")


class PCBStatistics(BaseModel):
    """Statistics about a PCB design."""

    total_footprints: int = Field(description="Total number of footprints")
    total_pads: int = Field(description="Total number of pads")
    total_tracks: int = Field(description="Total number of track segments")
    total_vias: int = Field(description="Total number of vias")
    total_zones: int = Field(description="Total number of copper zones")
    board_width: float = Field(description="Board width in mm")
    board_height: float = Field(description="Board height in mm")
    layers: int = Field(description="Number of copper layers")


class ERCError(BaseModel):
    """Electrical Rules Check error."""

    severity: str = Field(description="Error severity (error, warning)")
    type: str = Field(description="Error type")
    description: str = Field(description="Error description")
    components: list[str] = Field(default_factory=list, description="Involved components")


class DRCError(BaseModel):
    """Design Rules Check error."""

    severity: str = Field(description="Error severity (error, warning)")
    type: str = Field(description="Error type")
    description: str = Field(description="Error description")
    location: tuple[float, float] = Field(description="X, Y coordinates")
