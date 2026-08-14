"""PCB layout and routing tools."""

import re
import uuid
from pathlib import Path

from ..server import mcp
from ..utils.kicad_cli import run_kicad_cli
from ..utils.kicad_version import get_pcb_version

_KICAD_CLI_MISSING_MSG = """⚠️ kicad-cli not found (PATH or KiCad install directory).

Gerber export requires KiCad's command-line tools.

Please:
1. Install KiCad 7+ (https://www.kicad.org/)
2. Ensure kicad-cli is in system PATH, or set the KICAD_CLI
   environment variable to its full path
   (on Windows typically C:\\Program Files\\KiCad\\<ver>\\bin\\kicad-cli.exe)

**Manual export:**
Open the board in KiCad's PCB editor → File → Fabrication Outputs → Gerbers.
"""


@mcp.tool()
async def setup_pcb_layout(
    schematic_path: str,
    width: float = 100.0,
    height: float = 100.0,
    unit: str = "mm",
) -> str:
    """Initialize an empty PCB with the specified board outline dimensions.

    Writes a .kicad_pcb next to the schematic containing only the board
    outline (Edge.Cuts), a standard 2-layer stack and default design rules —
    no footprints, tracks or nets. KiCad stores .kicad_pcb coordinates in
    millimetres (plain decimals), so dimensions are emitted directly in mm.

    Args:
        schematic_path: Path to the .kicad_sch the board is based on (used to
            derive the .kicad_pcb path and board title).
        width: Board width in the given unit.
        height: Board height in the given unit.
        unit: "mm" (default) or "mil".

    Returns:
        Confirmation reporting the actual outline size, layer count and
        element counts read back from the written file.
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ Schematic file not found: {schematic_path}"

        pcb_path = sch_path.with_suffix(".kicad_pcb")

        # KiCad .kicad_pcb coordinates are millimetres (plain decimals), NOT
        # nanometres — multiplying by 1e6 wrote ~100 km outlines (issue #17).
        if unit == "mil":
            w = width * 0.0254
            h = height * 0.0254
        else:
            w = float(width)
            h = float(height)

        pcb_version = get_pcb_version()

        # KiCad 9 layer numbering (from the bundled template): copper layers
        # use the modern odd-pair scheme (B.Cu = 2, not 31) and Edge.Cuts is
        # layer 25 (not the KiCad-5 value 44). The old numbers made KiCad 9
        # read the stack back as a single layer.
        pcb_content = f'''(kicad_pcb (version {pcb_version}) (generator "kicad-mcp-server")

  (general
    (thickness 1.6)
    (legacy_thru_hole_to_restricted yes)
  )

  (paper "A4")

  (title_block
    (title "{sch_path.stem}")
  )

  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (9 "F.Adhes" user "F.Adhesive")
    (11 "B.Adhes" user "B.Adhesive")
    (13 "F.Paste" user)
    (15 "B.Paste" user)
    (5 "F.SilkS" user "F.Silkscreen")
    (7 "B.SilkS" user "B.Silkscreen")
    (1 "F.Mask" user)
    (3 "B.Mask" user)
    (17 "Dwgs.User" user "User.Drawings")
    (19 "Cmts.User" user "User.Comments")
    (21 "Eco1.User" user "User.Eco1")
    (23 "Eco2.User" user "User.Eco2")
    (25 "Edge.Cuts" user)
    (27 "Margin" user)
    (31 "F.CrtYd" user "F.Courtyard")
    (29 "B.CrtYd" user "B.Courtyard")
    (35 "F.Fab" user)
    (33 "B.Fab" user)
  )

  (setup
    (pad_to_mask_clearance 0)
    (aux_axis_origin 0 0)
    (grid_origin 0 0)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros false)
      (usegerberextensions false)
      (usegerberattributes true)
      (usegerberadvancedattributes true)
      (creategerberjobfile true)
      (excludeedgelayer true)
      (linewidth 0.100000)
      (plotframeref false)
      (viasonmask false)
      (mode 1)
      (useauxorigin false)
      (hpglpennumber 1)
      (hpglpenspeed 20)
      (hpglpendiameter 15.000000)
      (dxfpolygonmode true)
      (dxfimperialunits true)
      (dxfusepcbnewfont true)
      (psnegative false)
      (psa4output false)
      (plotreference true)
      (plotvalue true)
      (plotinvisibletext false)
      (sketchpadsonfab false)
      (subtractmaskfromsilk false)
      (outputformat 1)
      (mirror false)
      (drillshape 0)
      (scaleselection 1)
      (outputdirectory ""))
  )

  (net 0 "")

  (gr_line (start 0 0) (end {w} 0)
    (stroke (width 0.15) (type default))
    (layer "Edge.Cuts") (uuid "{uuid.uuid4()}"))
  (gr_line (start {w} 0) (end {w} {h})
    (stroke (width 0.15) (type default))
    (layer "Edge.Cuts") (uuid "{uuid.uuid4()}"))
  (gr_line (start {w} {h}) (end 0 {h})
    (stroke (width 0.15) (type default))
    (layer "Edge.Cuts") (uuid "{uuid.uuid4()}"))
  (gr_line (start 0 {h}) (end 0 0)
    (stroke (width 0.15) (type default))
    (layer "Edge.Cuts") (uuid "{uuid.uuid4()}"))

)
'''

        pcb_path.write_text(pcb_content, encoding="utf-8")

        # Report what is actually in the file, never features the write did
        # not produce (issue #17).
        report = _summarize_pcb(pcb_path)
        return f"""✅ PCB layout initialized.

**Schematic:** {schematic_path}
**PCB File:** {pcb_path}

{report}

Next steps:
1. Import the netlist from the schematic (Update PCB from schematic)
2. Place footprints and route connections
3. Run DRC, then export Gerbers (export_gerber)
"""

    except Exception as e:
        import traceback
        return f"❌ Error setting up PCB layout: {e}\n\n{traceback.format_exc()}"


def _summarize_pcb(pcb_path: Path) -> str:
    """Read a .kicad_pcb back and report its actual outline / layers / elements.

    For a freshly-initialised board the only items carrying start/end coords
    are the four Edge.Cuts gr_lines, so the min/max of those coords is the
    exact board outline.
    """
    text = pcb_path.read_text(encoding="utf-8")

    coords = [
        (float(mx), float(my))
        for mx, my in re.findall(
            r"\((?:start|end)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)", text
        )
    ]
    if coords:
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        outline = f"{max(xs) - min(xs):.3f} × {max(ys) - min(ys):.3f} mm"
    else:
        outline = "(could not parse Edge.Cuts outline)"

    layer_count = len(re.findall(r'^\s*\(\d+\s+"', text, re.MULTILINE))
    n_footprints = len(re.findall(r'\(footprint\s+"', text))
    n_segments = len(re.findall(r'\(segment\s', text))
    n_nets = len(re.findall(r'\(net\s+\d+\s+"', text))

    return (
        f"**Dimensions (read back):** {outline}\n"
        f"**Layers:** {layer_count}\n"
        f"**Elements:** {n_footprints} footprint(s), "
        f"{n_segments} track(s), {n_nets} net(s) declared"
    )


@mcp.tool()
async def export_gerber(
    pcb_path: str,
    output_dir: str = "",
) -> str:
    """Export a PCB to Gerber + drill files for fabrication via kicad-cli.

    Runs KiCad's command-line exporter against the .kicad_pcb and reports the
    files actually produced. Requires KiCad 7+ installed with kicad-cli on PATH.

    Args:
        pcb_path: Path to the .kicad_pcb file.
        output_dir: Directory for output (default: a "gerber" folder next to
            the PCB).

    Returns:
        Confirmation listing the generated files, or an actionable error.
    """
    try:
        pcb = Path(pcb_path)
        if not pcb.exists():
            return f"❌ PCB file not found: {pcb_path}"

        out_path = Path(output_dir) if output_dir else pcb.parent / "gerber"
        out_path.mkdir(parents=True, exist_ok=True)
        # Track name + mtime: a re-export rewrites the same files, and a pure
        # name diff would then look like "nothing was produced".
        before = {p.name: p.stat().st_mtime_ns for p in out_path.iterdir()}

        async def _run(args: list[str]) -> tuple[int, str]:
            r = await run_kicad_cli(args, timeout=180)
            return r.returncode, (r.stderr or b"").decode("utf-8", "replace").strip()

        # Gerbers first (required); drill is best-effort afterwards. Note the
        # subcommand is "gerbers" (plural) and the output flag is "-o", not
        # "--output-dir" — KiCad 7-10 all use this form. With no --layers it
        # plots every layer defined in the board, so it generalises to N-layer.
        try:
            rc, err = await _run(["pcb", "export", "gerbers", "-o", str(out_path), str(pcb)])
        except FileNotFoundError:
            return _KICAD_CLI_MISSING_MSG
        if rc != 0:
            return (
                f"❌ Gerber export failed (kicad-cli rc={rc}):\n\n"
                f"{err or '(no stderr)'}"
            )

        drill_note = ""
        try:
            rc2, err2 = await _run(["pcb", "export", "drill", "-o", str(out_path), str(pcb)])
            if rc2 != 0:
                drill_note = (
                    f"\n\n⚠️ Drill export returned rc={rc2}: "
                    f"{err2 or '(no stderr)'} (Gerbers still produced)"
                )
        except FileNotFoundError:
            # kicad-cli was available for gerber, so this shouldn't happen —
            # surface it rather than swallow.
            drill_note = "\n\n⚠️ kicad-cli unavailable for drill export."

        new_files = sorted(
            p.name
            for p in out_path.iterdir()
            if p.name not in before or p.stat().st_mtime_ns != before[p.name]
        )
        if not new_files:
            return (
                f"⚠️ kicad-cli reported success but produced no files in "
                f"{out_path}.{drill_note}"
            )

        listing = "\n".join(f"- {n}" for n in new_files)
        return f"""✅ Gerber export complete.

**PCB:** {pcb_path}
**Output directory:** {out_path}

**Files generated ({len(new_files)}):**
{listing}{drill_note}

Send all of these to your fabricator (e.g. JLCPCB, PCBWay, OSH Park).
"""

    except Exception as e:
        import traceback
        return f"❌ Error exporting Gerber: {e}\n\n{traceback.format_exc()}"
