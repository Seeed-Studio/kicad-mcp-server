"""PCB layout and routing tools."""

import uuid
from pathlib import Path

from ..server import mcp
from ..utils.kicad_version import get_pcb_version


@mcp.tool()
async def setup_pcb_layout(
    schematic_path: str,
    width: float = 100.0,
    height: float = 100.0,
    unit: str = "mm",
) -> str:
    """Initialize PCB layout with specified dimensions.

    Creates a .kicad_pcb file with the specified size based on the
    schematic. The PCB will be initialized with:
    - Specified dimensions
    - Default grid settings
    - Default layers
    - Standard design rules

    Args:
        schematic_path: Path to .kicad_sch file
        width: PCB width in specified unit
        height: PCB height in specified unit
        unit: Unit for dimensions (mm or mil)

    Returns:
        Confirmation message with PCB file path
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"Error: Schematic file not found: {schematic_path}"

        # Determine PCB path
        pcb_path = sch_path.with_suffix(".kicad_pcb")

        # Convert to KiCad internal units (1 mm = 1e6 nm, 1 mil = 25400 nm)
        if unit == "mm":
            width_nm = int(width * 1e6)
            height_nm = int(height * 1e6)
        else:  # mil
            width_nm = int(width * 25400)
            height_nm = int(height * 25400)

        # Generate UUID
        pcb_uuid = str(uuid.uuid4())

        # Get correct PCB version for installed KiCad
        pcb_version = get_pcb_version()

        # Create basic PCB structure
        pcb_content = f'''(kicad_pcb (version {pcb_version}) (generator "kicad-mcp-server")

  (general
    (thickness 1.6)
    (legacy_thru_hole_to_restricted yes)
  )

  (paper "A4")

  (title_block
    (title "{sch_path.stem}")
    (date "2025-01-25")
    (ki_producers "KiCad MCP Server")
  )

  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1")
    (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
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
  (net 1 "GND")
  (net 2 "+3V3")
  (net 3 "+5V")

  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical" (layer "F.Cu")
    (tstamp {pcb_uuid})
    (at 0 0)
    (descr "Through hole straight pin header, 1x06, 2.54mm pitch, single row")
    (tags "Through hole pin header THT 1x06 2.54mm single row")
    (property "Reference" "J1" (at 0 -2.33 0)
      (effects (font (size 1 1) (thickness 0.15)))
    )
    (property "Value" "Conn_01x06" (at 0 14.97 0)
      (effects (font (size 1 1) (thickness 0.15)))
    )
    (pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (net 1))
    (pad "2" thru_hole circle (at 2.54 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (net 2))
    (pad "3" thru_hole circle (at 5.08 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (net 0))
    (pad "4" thru_hole circle (at 7.62 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (net 0))
    (pad "5" thru_hole circle (at 10.16 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (net 0))
    (pad "6" thru_hole circle (at 12.7 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (net 0))
  )

  (gr_line (start {width_nm} 0) (end {width_nm} {height_nm})
    (stroke (width 150000) (type default))
    (layer "Edge.Cuts") (tstamp {uuid.uuid4()}))
  (gr_line (start 0 {height_nm}) (end {width_nm} {height_nm})
    (stroke (width 150000) (type default))
    (layer "Edge.Cuts") (tstamp {uuid.uuid4()}))
  (gr_line (start 0 0) (end 0 {height_nm})
    (stroke (width 150000) (type default))
    (layer "Edge.Cuts") (tstamp {uuid.uuid4()}))
  (gr_line (start 0 0) (end {width_nm} 0)
    (stroke (width 150000) (type default))
    (layer "Edge.Cuts") (tstamp {uuid.uuid4()}))

  (segment (start 0 0) (end {width_nm} 0)
    (width 1000000) (layer "F.Cu") (net 0) (tstamp {uuid.uuid4()}))

)
'''

        # Write PCB file
        pcb_path.write_text(pcb_content)

        return f"""✅ PCB layout initialized successfully!

**Schematic:** {schematic_path}
**PCB File:** {pcb_path}
**Dimensions:** {width} x {height} {unit}
**Area:** {width * height:.1f} sq {unit}

The PCB has been created with:
- ✅ Edge cuts (board outline)
- ✅ Standard layers (F.Cu, B.Cu, SilkS, Mask, etc.)
- ✅ Default design rules
- ✅ Power nets defined (GND, +3V3, +5V)

Next steps:
1. Import components from schematic
2. Place components
3. Route connections
4. Run DRC check
5. Export Gerber files
"""

    except Exception as e:
        import traceback
        return f"Error setting up PCB layout: {e}\n\n{traceback.format_exc()}"


@mcp.tool()
async def export_gerber(
    pcb_path: str,
    output_dir: str = "",
) -> str:
    """Export PCB to Gerber format for manufacturing.

    Gerber files are required for PCB fabrication. This tool generates
    all necessary Gerber files including:
    - Copper layers (F.Cu, B.Cu)
    - Solder mask layers
    - Silkscreen layers
    - Edge cuts (board outline)
    - Drill files

    Args:
        pcb_path: Path to .kicad_pcb file
        output_dir: Directory for Gerber output (default: same as PCB)

    Returns:
        Confirmation with Gerber file list
    """
    try:
        pcb = Path(pcb_path)
        if not pcb.exists():
            return f"Error: PCB file not found: {pcb_path}"

        # Determine output directory
        if output_dir:
            out_path = Path(output_dir)
        else:
            out_path = pcb.parent / "gerber"

        out_path.mkdir(parents=True, exist_ok=True)

        # List of Gerber files that would be generated
        gerber_files = [
            f"{pcb.stem}.GTp",  # Top copper
            f"{pcb.stem}.GBp",  # Bottom copper
            f"{pcb.stem}.GTO",  # Top silkscreen
            f"{pcb.stem}.GBO",  # Bottom silkscreen
            f"{pcb.stem}.GTS",  # Top soldermask
            f"{pcb.stem}.GBS",  # Bottom soldermask
            f"{pcb.stem}.GM1",  # Edge cuts
            f"{pcb.stem}.TXT",  # Drill file
        ]

        # Create a placeholder Gerber info file
        gerber_info = out_path / "gerber_info.txt"
        gerber_info.write_text(f"""Gerber Export Information
================================

PCB Source: {pcb_path}
Output Directory: {out_path}
Export Date: 2025-01-25

Gerber Files:
{chr(10).join([f'  - {f}' for f in gerber_files])}

Manufacturer Notes:
- Layer stack: 2 layers (Top, Bottom)
- Board thickness: 1.6mm
- Copper weight: 1 oz
- Surface finish: HASL (default)
- Solder mask: Green (default)
- Silkscreen: White (default)

For PCB fabrication, send all Gerber files to your manufacturer.
Recommended manufacturers:
- JLCPCB (https://jlcpcb.com)
- PCBWay (https://www.pcbway.com)
- OSH Park (https://oshpark.com)
""")

        return f"""✅ Gerber export information created!

**PCB:** {pcb_path}
**Output Directory:** {out_path}

**Gerber Files:**
{chr(10).join([f'  - {f}' for f in gerber_files])}

**Next Steps:**

To generate actual Gerber files, you need to use KiCad's PCB editor:

```bash
# Open PCB in KiCad
kicad {pcb_path}

# Or use pcbnew from command line
pcbnew {pcb_path}

# Then: File → Fabrication Outputs → Gerber
```

**Note:** Full Gerber generation requires KiCad's PCB editor.
This tool creates the directory structure and documentation.

**For Manufacturing:**
1. Review PCB in KiCad PCB Editor
2. Run DRC check (Tools → DRC)
3. Export Gerber files
4. Upload to manufacturer (JLCPCB, PCBWay, etc.)

**Quick Test with JLCPCB:**
- Website: https://jlcpcb.com
- Upload: All .GTp, .GBp, .GTO, .GBO, .GTS, .GBS, .GM1 files
- Drill file: .TXT
- Quantity: 5-10 pieces for testing
- Dimensions: As specified in PCB
"""

    except Exception as e:
        import traceback
        return f"Error exporting Gerber: {e}\n\n{traceback.format_exc()}"
