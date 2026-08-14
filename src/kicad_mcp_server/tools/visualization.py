"""Board visualization export tools.

These wrap kicad-cli's rendering and 3D/2D exporters so that MCP clients
(and the multimodal LLMs behind them) can *see* a design:

- render_pcb: 3D-rendered PNG/JPEG of the board (top/bottom/isometric views)
- export_pcb_3d: STEP model for mechanical CAD handoff
- export_schematic_svg: per-page schematic SVGs

render_pcb returns a FastMCP Image so capable clients display the picture
inline instead of just a path.
"""

from pathlib import Path

from fastmcp.utilities.types import Image

from ..server import mcp
from ..utils.kicad_cli import run_kicad_cli

_RENDER_SIDES = {"top", "bottom", "left", "right", "front", "back"}
_RENDER_QUALITIES = {"basic", "high", "user", "job_settings"}


@mcp.tool()
async def render_pcb(
    pcb_path: str,
    side: str = "top",
    output_path: str = "",
    width: int = 1600,
    height: int = 900,
    quality: str = "basic",
    rotate: str = "",
) -> Image | str:
    """Render a 3D view of the PCB to a PNG image.

    Produces a photorealistic render of the assembled board via kicad-cli
    (footprints must have 3D models assigned; otherwise plain board geometry
    is rendered). Returns the image itself, so multimodal clients show it
    directly — useful for AI-assisted layout review.

    Args:
        pcb_path: Path to the .kicad_pcb file.
        side: Camera side: top, bottom, left, right, front, back.
        output_path: Output PNG (default: <pcb>_render_<side>.png next to
            the PCB).
        width: Image width in pixels.
        height: Image height in pixels.
        quality: Render quality: basic (fast) or high (slower, raytraced).
        rotate: Optional board rotation 'X,Y,Z' in degrees for isometric
            views, e.g. '-30,0,25'.

    Returns:
        The rendered image, or an error message string.
    """
    try:
        pcb = Path(pcb_path)
        if not pcb.exists():
            return f"❌ PCB file not found: {pcb_path}"
        if side not in _RENDER_SIDES:
            return f"❌ Invalid side '{side}'. Options: {', '.join(sorted(_RENDER_SIDES))}"
        if quality not in _RENDER_QUALITIES:
            return f"❌ Invalid quality '{quality}'. Options: {', '.join(sorted(_RENDER_QUALITIES))}"

        out = Path(output_path) if output_path else pcb.parent / f"{pcb.stem}_render_{side}.png"
        out.parent.mkdir(parents=True, exist_ok=True)

        args = [
            "pcb",
            "render",
            "--output",
            str(out),
            "--side",
            side,
            "--width",
            str(width),
            "--height",
            str(height),
            "--quality",
            quality,
        ]
        if rotate:
            args += ["--rotate", rotate]
        args.append(str(pcb))

        result = await run_kicad_cli(args, timeout=180)

        if result.returncode != 0 or not out.exists():
            stderr = (result.stderr or b"").decode("utf-8", "replace").strip()
            return (
                f"❌ PCB render failed (kicad-cli rc={result.returncode}):\n\n"
                f"{stderr or '(no stderr, and no output file produced)'}"
            )

        return Image(path=str(out))
    except FileNotFoundError:
        return (
            "❌ kicad-cli not found (PATH or KiCad install directory). "
            "Rendering requires KiCad 8+."
        )
    except Exception as e:
        import traceback

        return f"❌ Error rendering PCB: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
async def export_pcb_3d(
    pcb_path: str,
    output_path: str = "",
    board_only: bool = False,
) -> str:
    """Export the PCB as a STEP 3D model for mechanical CAD handoff.

    Includes board body, footprints and their assigned 3D models.

    Args:
        pcb_path: Path to the .kicad_pcb file.
        output_path: Output .step file (default: <pcb>.step next to the PCB).
        board_only: Export only the board body, without component models.

    Returns:
        Confirmation with the output path and file size.
    """
    try:
        pcb = Path(pcb_path)
        if not pcb.exists():
            return f"❌ PCB file not found: {pcb_path}"

        out = Path(output_path) if output_path else pcb.parent / f"{pcb.stem}.step"
        out.parent.mkdir(parents=True, exist_ok=True)

        args = ["pcb", "export", "step", "--output", str(out), "--force", str(pcb)]
        if board_only:
            args.insert(-1, "--board-only")

        result = await run_kicad_cli(args, timeout=300)

        if result.returncode != 0 or not out.exists():
            stderr = (result.stderr or b"").decode("utf-8", "replace").strip()
            return (
                f"❌ STEP export failed (kicad-cli rc={result.returncode}):\n\n"
                f"{stderr or '(no stderr, and no output file produced)'}"
            )

        size_mb = out.stat().st_size / (1024 * 1024)
        return f"""✅ STEP 3D model exported.

**PCB:** {pcb_path}
**Output:** {out}
**Size:** {size_mb:.1f} MB

Import into Fusion 360 / SolidWorks / FreeCAD for enclosure design."""
    except FileNotFoundError:
        return (
            "❌ kicad-cli not found (PATH or KiCad install directory). "
            "STEP export requires KiCad 7+."
        )
    except Exception as e:
        import traceback

        return f"❌ Error exporting STEP: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
async def export_schematic_svg(
    schematic_path: str,
    output_dir: str = "",
) -> str:
    """Export schematic pages to SVG images.

    Renders every page of the (hierarchical) schematic as an SVG file via
    kicad-cli. SVGs are vector graphics — clients and humans can zoom into
    any detail without quality loss.

    Args:
        schematic_path: Path to the root .kicad_sch file.
        output_dir: Output directory (default: <schematic>_svg/ next to it).

    Returns:
        Confirmation listing the generated SVG files.
    """
    try:
        sch = Path(schematic_path)
        if not sch.exists():
            return f"❌ Schematic file not found: {schematic_path}"

        out_dir = Path(output_dir) if output_dir else sch.parent / f"{sch.stem}_svg"
        out_dir.mkdir(parents=True, exist_ok=True)

        result = await run_kicad_cli(
            ["sch", "export", "svg", "--output", str(out_dir), str(sch)],
            timeout=120,
        )

        if result.returncode != 0:
            stderr = (result.stderr or b"").decode("utf-8", "replace").strip()
            return (
                f"❌ Schematic SVG export failed (kicad-cli rc={result.returncode}):\n\n"
                f"{stderr or '(no stderr)'}"
            )

        svgs = sorted(out_dir.glob("*.svg"))
        if not svgs:
            return (
                f"⚠️ kicad-cli reported success but produced no SVG files in {out_dir}."
            )

        listing = "\n".join(f"- {s.name}" for s in svgs)
        return f"""✅ Schematic SVG export complete.

**Schematic:** {schematic_path}
**Output directory:** {out_dir}

**Files generated ({len(svgs)}):**
{listing}"""
    except FileNotFoundError:
        return (
            "❌ kicad-cli not found (PATH or KiCad install directory). "
            "SVG export requires KiCad 7+."
        )
    except Exception as e:
        import traceback

        return f"❌ Error exporting schematic SVG: {e}\n\n{traceback.format_exc()}"
