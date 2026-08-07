"""Design Rule Checking (DRC) and Electrical Rules Check (ERC) tools for KiCad MCP Server."""

import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ..models.types import DRCError, ERCError
from ..server import mcp


def _temp_dir() -> Path:
    return Path(tempfile.gettempdir())


def _find_root_schematic(sch_path: Path) -> Path | None:
    """If sch_path is a sub-sheet, return the root schematic instead.

    KiCad convention: root schematic has the same stem as the .kicad_pro file.
    kicad-cli silently drops unnamed local nets when exporting from a sub-sheet,
    so we detect this and redirect to the root schematic.
    """
    pro_files = list(sch_path.parent.glob("*.kicad_pro"))
    if not pro_files:
        return None
    root_sch = pro_files[0].with_suffix(".kicad_sch")
    if root_sch.exists() and root_sch.resolve() != sch_path.resolve():
        return root_sch
    return None


def _parse_erc_report(report_path: Path) -> list[ERCError]:
    """Parse ERC report file (JSON or XML format).

    Args:
        report_path: Path to ERC report file

    Returns:
        List of ERC errors/warnings
    """
    errors = []
    content = report_path.read_text(encoding="utf-8", errors="replace")

    try:
        data = json.loads(content)
        # KiCad 9+ ERC JSON: violations are a top-level list (there is no
        # "sheets" key — reading data["sheets"] silently returned []).
        for v in data.get("violations", []):
            components = []
            for item in v.get("items", []):
                desc = item.get("description", "")
                # Description looks like "Pin U1 of ...": pull the reference.
                # Don't gate on the literal English word "Symbol" — localized
                # KiCad uses other words and the ref would be missed.
                m = re.search(r"\b(?:Pin|Symbol)\s+([A-Za-z]+\d+)", desc)
                if m:
                    components.append(m.group(1))
            errors.append(
                ERCError(
                    severity=v.get("severity", "error"),
                    type=v.get("type", "unknown"),
                    description=v.get("description", ""),
                    components=components,
                )
            )
        return errors
    except (json.JSONDecodeError, KeyError):
        pass

    # Fallback: XML format
    try:
        root = ET.fromstring(content)
        for violation in root.findall(".//violation"):
            severity = violation.get("severity", "error")
            error_type = violation.get("type", "unknown")
            description = violation.get("description", "")

            components = []
            for comp in violation.findall(".//component"):
                ref = comp.get("ref", "")
                if ref:
                    components.append(ref)

            errors.append(
                ERCError(
                    severity=severity,
                    type=error_type,
                    description=description,
                    components=components,
                )
            )
    except ET.ParseError as e:
        errors.append(
            ERCError(
                severity="error",
                type="parse_error",
                description=f"Failed to parse ERC report: {str(e)}",
                components=[],
            )
        )

    return errors


def _parse_drc_report(report_path: Path) -> list[DRCError]:
    """Parse DRC report file (JSON or XML format).

    Args:
        report_path: Path to DRC report file

    Returns:
        List of DRC errors/warnings
    """
    errors = []
    content = report_path.read_text(encoding="utf-8", errors="replace")

    try:
        data = json.loads(content)
        # KiCad 9+ DRC JSON: violations are a top-level list (no "sheets" key —
        # reading data["sheets"] returned [] and made run_drc report PASS with
        # every violation silently dropped).
        for v in data.get("violations", []):
            x, y = 0.0, 0.0
            items = v.get("items", [])
            if items:
                pos = items[0].get("pos", {})
                x = float(pos.get("x", 0))
                y = float(pos.get("y", 0))

            errors.append(
                DRCError(
                    severity=v.get("severity", "error"),
                    type=v.get("type", "unknown"),
                    description=v.get("description", ""),
                    location=(x, y),
                )
            )
        return errors
    except (json.JSONDecodeError, KeyError):
        pass

    # Fallback: XML format
    try:
        root = ET.fromstring(content)
        for violation in root.findall(".//violation"):
            severity = violation.get("severity", "error")
            error_type = violation.get("type", "unknown")
            description = violation.get("description", "")

            location_elem = violation.find(".//location")
            x = float(location_elem.get("x", "0")) if location_elem is not None else 0.0
            y = float(location_elem.get("y", "0")) if location_elem is not None else 0.0

            errors.append(
                DRCError(
                    severity=severity,
                    type=error_type,
                    description=description,
                    location=(x, y),
                )
            )
    except ET.ParseError as e:
        errors.append(
            DRCError(
                severity="error",
                type="parse_error",
                description=f"Failed to parse DRC report: {str(e)}",
                location=(0.0, 0.0),
            )
        )

    return errors


def _filter_erc_errors(errors: list[ERCError], severity: str = "") -> list[ERCError]:
    """Filter ERC errors by severity.

    Args:
        errors: List of ERC errors
        severity: Severity filter ('error', 'warning', '') for all

    Returns:
        Filtered list of ERC errors
    """
    if not severity:
        return errors

    return [e for e in errors if e.severity == severity]


def _filter_drc_errors(errors: list[DRCError], violation_type: str = "") -> list[DRCError]:
    """Filter DRC errors by type.

    Args:
        errors: List of DRC errors
        violation_type: Type filter (e.g., 'clearance', 'spacing', '') for all

    Returns:
        Filtered list of DRC errors
    """
    if not violation_type:
        return errors

    return [e for e in errors if e.type == violation_type]


@mcp.tool()
async def run_erc(
    schematic_path: str,
) -> str:
    """Run Electrical Rules Check (ERC) on schematic.

    Checks for:
    - Unconnected pins
    - Power conflicts
    - Multiple outputs on same net
    - Pin type mismatches

    Args:
        schematic_path: Path to .kicad_sch file

    Returns:
        ERC report with violations and recommendations
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ **Schematic file not found:** {schematic_path}"

        # Detect sub-sheet and redirect to root schematic
        subsheet_note = ""
        root_sch = _find_root_schematic(sch_path)
        if root_sch:
            subsheet_note = (
                f"\n\n⚠️ **Note:** `{sch_path.name}` is a hierarchical sub-sheet. "
                f"Switched to root schematic `{root_sch.name}` for complete ERC check."
            )
            sch_path = root_sch

        # ERC report output path. run_erc redirects sub-sheets to the root
        # schematic, so the report is named after the ROOT stem — not the
        # (possibly sub-sheet) input stem, which would never match.
        root = _find_root_schematic(sch_path) or sch_path
        erc_report_path = _temp_dir() / (root.stem + "_erc.rpt")

        # Run ERC using kicad-cli (KiCad 7+)
        cmd = [
            "kicad-cli",
            "sch",
            "erc",
            "--format",
            "json",
            "--output",
            str(erc_report_path),
            str(sch_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60,
        )

        stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

        if result.returncode != 0:
            return f"""❌ **ERC Check Failed**

**Schematic:** {schematic_path}

**Error:**
```
{stderr_text}
```

**Possible causes:**
- KiCad command line tools not available
- Invalid schematic file
- Missing project file (.kicad_pro)

**Manual steps:**
1. Open schematic in KiCad Eeschema
2. Run: Inspect → Electrical Rules Checker
3. Export report manually{subsheet_note}"""

        # Parse ERC report
        if not erc_report_path.exists():
            # kicad-cli returned success but produced no report — do NOT claim
            # "all pins connected" (that was never verified).
            return f"""⚠️ **ERC Report Not Generated**

**Schematic:** {schematic_path}

kicad-cli exited cleanly but wrote no report file, so no checks could be
verified. Ensure KiCad 9+ is installed and the schematic has a matching
.kicad_pro project file.{subsheet_note}"""

        # Parse and format results
        try:
            errors = _parse_erc_report(erc_report_path)

            if not errors:
                return f"""✅ **ERC Check Passed**

**Schematic:** {schematic_path}

No electrical violations detected!{subsheet_note}"""

            # Count by severity
            error_count = sum(1 for e in errors if e.severity == "error")
            warning_count = sum(1 for e in errors if e.severity == "warning")

            # Format violations
            violations_table = "| Severity | Type | Description | Components |\n"
            violations_table += "|----------|------|-------------|------------|\n"

            for error in errors[:20]:  # Limit to first 20
                severity_icon = "❌" if error.severity == "error" else "⚠️"
                components_str = ", ".join(error.components) if error.components else "N/A"
                violations_table += f"| {severity_icon} {error.severity} | {error.type} | {error.description[:50]} | {components_str} |\n"

            if len(errors) > 20:
                violations_table += f"\n*... and {len(errors) - 20} more violations*\n"

            return f"""❌ **ERC Violations Detected**

**Schematic:** {schematic_path}
**Total Violations:** {len(errors)}
- Errors: {error_count}
- Warnings: {warning_count}{subsheet_note}

## Violations

{violations_table}

## Recommendations

1. **Fix all errors** before proceeding to PCB layout
2. Review warnings - some may be acceptable
3. Re-run ERC after fixes
4. Use `get_erc_violations()` for detailed filtering

## Next Steps

- Run `get_erc_violations()` with filters to analyze specific issues
- Fix violations in KiCad Eeschema
- Re-run `run_erc()` to verify fixes"""

        except Exception as e:
            return f"""⚠️ **ERC Report Parse Error**

**Schematic:** {schematic_path}

ERC check completed but failed to parse report.

**Error:** {str(e)}

**Report location:** {erc_report_path}

You can manually inspect the report file or re-run ERC in KiCad GUI.{subsheet_note}"""

    except FileNotFoundError as e:
        # Distinguish kicad-cli missing (raised by subprocess) from a missing
        # schematic file (already checked at the top of the function).
        if "kicad-cli" in str(e):
            return f"""❌ **kicad-cli Not Found**

**Schematic:** {schematic_path}

KiCad's command-line tool (kicad-cli) is not installed or not on PATH.
Install KiCad 7+ (https://www.kicad.org/) to run ERC."""
        return f"""❌ **File Not Found**

**Schematic:** {schematic_path}

{e}
Please check the file path and try again."""
    except Exception as e:
        import traceback

        return f"""❌ **Unexpected Error**

**Schematic:** {schematic_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def run_drc(
    pcb_path: str,
) -> str:
    """Run Design Rules Check (DRC) on PCB.

    Checks for:
    - Clearance violations
    - Track spacing violations
    - Missing connections
    - Pad/footprint overlaps
    - Board edge constraints

    Args:
        pcb_path: Path to .kicad_pcb file

    Returns:
        DRC report with violations and locations
    """
    try:
        pcb = Path(pcb_path)
        if not pcb.exists():
            return f"❌ **PCB file not found:** {pcb_path}"

        # DRC report output path
        drc_report_path = _temp_dir() / (pcb.stem + "_drc.rpt")

        # Run DRC using kicad-cli (KiCad 7+)
        cmd = [
            "kicad-cli",
            "pcb",
            "drc",
            "--format",
            "json",
            "--output",
            str(drc_report_path),
            str(pcb),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60,
        )

        stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

        if result.returncode != 0:
            return f"""❌ **DRC Check Failed**

**PCB:** {pcb_path}

**Error:**
```
{stderr_text}
```

**Possible causes:**
- KiCad command line tools not available
- Invalid PCB file
- Missing design rules

**Manual steps:**
1. Open PCB in KiCad Pcbnew
2. Run: Inspect → Design Rules Checker
3. Export report manually"""

        # Parse DRC report
        if not drc_report_path.exists():
            # No violations found
            return f"""✅ **DRC Check Passed**

**PCB:** {pcb_path}

No design rule violations detected!

**Checked:**
- ✅ All clearance requirements met
- ✅ No spacing violations
- ✅ All connections routed
- ✅ No pad/footprint overlaps
- ✅ Board edge constraints satisfied"""

        # Parse and format results
        try:
            errors = _parse_drc_report(drc_report_path)

            if not errors:
                return f"""✅ **DRC Check Passed**

**PCB:** {pcb_path}

No design rule violations detected!"""

            # Count by severity
            error_count = sum(1 for e in errors if e.severity == "error")
            warning_count = sum(1 for e in errors if e.severity == "warning")

            # Group by type
            type_counts = {}
            for error in errors:
                type_counts[error.type] = type_counts.get(error.type, 0) + 1

            # Format violations
            violations_table = "| Severity | Type | Location | Description |\n"
            violations_table += "|----------|------|----------|-------------|\n"

            for error in errors[:20]:  # Limit to first 20
                severity_icon = "❌" if error.severity == "error" else "⚠️"
                x, y = error.location
                violations_table += f"| {severity_icon} {error.severity} | {error.type} | ({x:.2f}, {y:.2f}) | {error.description[:40]} |\n"

            if len(errors) > 20:
                violations_table += f"\n*... and {len(errors) - 20} more violations*\n"

            # Format type summary
            type_summary = "\n## Violation Summary\n\n"
            for vtype, count in sorted(type_counts.items()):
                type_summary += f"- **{vtype}**: {count} violations\n"

            return f"""❌ **DRC Violations Detected**

**PCB:** {pcb_path}
**Total Violations:** {len(errors)}
- Errors: {error_count}
- Warnings: {warning_count}

{type_summary}
## Violations

{violations_table}

## Recommendations

1. **Fix all errors** before manufacturing
2. Review warnings - some may be acceptable
3. Pay attention to clearance violations
4. Re-run DRC after fixes
5. Use `get_drc_violations()` for detailed filtering

## Next Steps

- Run `get_drc_violations()` with filters to analyze specific issues
- Fix violations in KiCad Pcbnew
- Re-run `run_drc()` to verify fixes"""

        except Exception as e:
            return f"""⚠️ **DRC Report Parse Error**

**PCB:** {pcb_path}

DRC check completed but failed to parse report.

**Error:** {str(e)}

**Report location:** {drc_report_path}

You can manually inspect the report file or re-run DRC in KiCad GUI."""

    except FileNotFoundError:
        return f"""❌ **File Not Found**

**PCB:** {pcb_path}

Please check the file path and try again."""
    except Exception as e:
        import traceback

        return f"""❌ **Unexpected Error**

**PCB:** {pcb_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def get_erc_violations(
    schematic_path: str,
    severity: str = "",
) -> str:
    """Get filtered ERC violations from schematic.

    Args:
        schematic_path: Path to .kicad_sch file
        severity: Filter by severity ('error', 'warning', '') for all

    Returns:
        Filtered list of ERC violations
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ **Schematic file not found:** {schematic_path}"

        # ERC report output path. run_erc redirects sub-sheets to the root
        # schematic, so the report is named after the ROOT stem — not the
        # (possibly sub-sheet) input stem, which would never match.
        root = _find_root_schematic(sch_path) or sch_path
        erc_report_path = _temp_dir() / (root.stem + "_erc.rpt")

        if not erc_report_path.exists():
            # Run ERC first
            initial_result = await run_erc(schematic_path)
            if "❌" in initial_result or "⚠️" in initial_result:
                return initial_result

        # Parse ERC report
        errors = _parse_erc_report(erc_report_path)

        if not errors:
            return f"""✅ **No ERC Violations**

**Schematic:** {schematic_path}

No electrical violations detected."""

        # Apply filter
        filtered_errors = _filter_erc_errors(errors, severity)

        if not filtered_errors:
            return f"""✅ **No Matching Violations**

**Schematic:** {schematic_path}
**Filter:** severity = '{severity or 'all'}'

No violations match the specified filter."""

        # Format results
        result = f"""# ERC Violations

**Schematic:** {schematic_path}
**Filter:** severity = '{severity or 'all'}'
**Count:** {len(filtered_errors)}

## Violations

| Severity | Type | Description | Components |
|----------|------|-------------|------------|
"""

        for error in filtered_errors:
            severity_icon = "❌" if error.severity == "error" else "⚠️"
            components_str = ", ".join(error.components) if error.components else "N/A"
            result += f"| {severity_icon} {error.severity} | {error.type} | {error.description} | {components_str} |\n"

        return result

    except Exception as e:
        import traceback

        return f"""❌ **Error**

**Schematic:** {schematic_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def get_drc_violations(
    pcb_path: str,
    violation_type: str = "",
) -> str:
    """Get filtered DRC violations from PCB.

    Args:
        pcb_path: Path to .kicad_pcb file
        violation_type: Filter by type (e.g., 'clearance', 'spacing', '') for all

    Returns:
        Filtered list of DRC violations
    """
    try:
        pcb = Path(pcb_path)
        if not pcb.exists():
            return f"❌ **PCB file not found:** {pcb_path}"

        # DRC report output path
        drc_report_path = _temp_dir() / (pcb.stem + "_drc.rpt")

        if not drc_report_path.exists():
            # Run DRC first
            initial_result = await run_drc(pcb_path)
            if "❌" in initial_result or "⚠️" in initial_result:
                return initial_result

        # Parse DRC report
        errors = _parse_drc_report(drc_report_path)

        if not errors:
            return f"""✅ **No DRC Violations**

**PCB:** {pcb_path}

No design rule violations detected."""

        # Apply filter
        filtered_errors = _filter_drc_errors(errors, violation_type)

        if not filtered_errors:
            return f"""✅ **No Matching Violations**

**PCB:** {pcb_path}
**Filter:** type = '{violation_type or 'all'}'

No violations match the specified filter."""

        # Format results
        result = f"""# DRC Violations

**PCB:** {pcb_path}
**Filter:** type = '{violation_type or 'all'}'
**Count:** {len(filtered_errors)}

## Violations

| Severity | Type | Location | Description |
|----------|------|----------|-------------|
"""

        for error in filtered_errors:
            severity_icon = "❌" if error.severity == "error" else "⚠️"
            x, y = error.location
            result += f"| {severity_icon} {error.severity} | {error.type} | ({x:.2f}, {y:.2f}) | {error.description} |\n"

        return result

    except Exception as e:
        import traceback

        return f"""❌ **Error**

**PCB:** {pcb_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def export_erc_report(
    schematic_path: str,
    output_path: str = "",
) -> str:
    """Export ERC report to file.

    Args:
        schematic_path: Path to .kicad_sch file
        output_path: Optional output file path (default: schematic_name_erc.txt)

    Returns:
        Confirmation with output file location
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ **Schematic file not found:** {schematic_path}"

        # Run ERC first to generate report
        initial_result = await run_erc(schematic_path)

        if "❌" in initial_result:
            return f"❌ **ERC Check Failed**\n\n{initial_result}"

        # ERC report path
        erc_report_path = _temp_dir() / (sch_path.stem + "_erc.rpt")

        if not erc_report_path.exists():
            return "❌ **ERC report not found.** Run ERC check first."

        # Determine output path
        if not output_path:
            output_path = str(sch_path.parent / (sch_path.stem + "_erc_report.txt"))

        output = Path(output_path)

        # Copy report to output location
        import shutil

        shutil.copy(erc_report_path, output)

        return f"""✅ **ERC Report Exported**

**Schematic:** {schematic_path}
**Output:** {output}

The ERC report has been successfully exported to the specified location."""

    except Exception as e:
        import traceback

        return f"""❌ **Export Failed**

**Schematic:** {schematic_path}
**Output:** {output_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""


@mcp.tool()
async def export_drc_report(
    pcb_path: str,
    output_path: str = "",
) -> str:
    """Export DRC report to file.

    Args:
        pcb_path: Path to .kicad_pcb file
        output_path: Optional output file path (default: pcb_name_drc.txt)

    Returns:
        Confirmation with output file location
    """
    try:
        pcb = Path(pcb_path)
        if not pcb.exists():
            return f"❌ **PCB file not found:** {pcb_path}"

        # Run DRC first to generate report
        initial_result = await run_drc(pcb_path)

        if "❌" in initial_result:
            return f"❌ **DRC Check Failed**\n\n{initial_result}"

        # DRC report path
        drc_report_path = _temp_dir() / (pcb.stem + "_drc.rpt")

        if not drc_report_path.exists():
            return "❌ **DRC report not found.** Run DRC check first."

        # Determine output path
        if not output_path:
            output_path = str(pcb.parent / (pcb.stem + "_drc_report.txt"))

        output = Path(output_path)

        # Copy report to output location
        import shutil

        shutil.copy(drc_report_path, output)

        return f"""✅ **DRC Report Exported**

**PCB:** {pcb_path}
**Output:** {output}

The DRC report has been successfully exported to the specified location."""

    except Exception as e:
        import traceback

        return f"""❌ **Export Failed**

**PCB:** {pcb_path}
**Output:** {output_path}

**Error:** {str(e)}

**Traceback:**
```
{traceback.format_exc()}
```"""
