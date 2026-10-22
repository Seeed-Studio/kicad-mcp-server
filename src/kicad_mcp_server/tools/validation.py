"""Design Rule Checking (DRC) and Electrical Rules Check (ERC) tools for KiCad MCP Server."""

import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ..models.types import DRCError, ERCError, ERCItem
from ..parsers.check_report_parser import (
    erc_position_scale,
    parse_drc_report,
    parse_erc_report,
)
from ..server import mcp
from ..utils.kicad_cli import english_env, run_kicad_cli


def _temp_dir() -> Path:
    return Path(tempfile.gettempdir())


def _report_path(source: Path, kind: str) -> Path:
    """Deterministic report path in the temp directory for one source file.

    A short digest of the resolved source path is in the name, so two projects
    with the same file stem do not overwrite each other's reports. The
    reports are in a subdirectory, so reports from older server versions
    (different format, localized text) are not used again.
    """
    digest = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:8]
    report_dir = _temp_dir() / "kicad-mcp-server"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / f"{source.stem}_{digest}_{kind}.json"


def _schematic_files(sch_path: Path) -> list[Path]:
    """Return the schematic files of the project of sch_path."""
    return sorted(sch_path.parent.glob("*.kicad_sch"))


def _erc_sources(sch_path: Path) -> list[Path]:
    """Return the files that change the ERC result."""
    return _schematic_files(sch_path) + sorted(sch_path.parent.glob("*.kicad_pro"))


def _drc_sources(pcb: Path) -> list[Path]:
    """Return the files that change the DRC result."""
    return (
        [pcb]
        + sorted(pcb.parent.glob("*.kicad_pro"))
        + sorted(pcb.parent.glob("*.kicad_dru"))
        + _schematic_files(pcb)
    )


def _report_is_stale(report: Path, sources: list[Path]) -> bool:
    """Return True if the report is missing or older than one of the sources."""
    if not report.exists():
        return True
    report_mtime = report.stat().st_mtime
    return any(src.exists() and src.stat().st_mtime > report_mtime for src in sources)


def _md(text: str) -> str:
    """Escape a value for a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def _erc_item_text(item: ERCItem) -> str:
    """Give a short text for one ERC item: pin, label or symbol."""
    if item.pin_number:
        ref = f"{item.reference}." if item.reference else ""
        name = f" {item.pin_name}" if item.pin_name else ""
        pin_type = f" ({item.pin_type})" if item.pin_type else ""
        return f"{ref}{item.pin_number}{name}{pin_type}"
    if item.label:
        return item.description
    if item.reference:
        return f"{item.reference} [{item.value}]" if item.value else item.reference
    return item.description


def _position_text(x: float | None, y: float | None) -> str:
    return f"({x:.2f}, {y:.2f})" if x is not None and y is not None else ""


def _join_cells(values: list[str]) -> str:
    return _md("; ".join(v for v in values if v)) or "-"


def _severity_cell(severity: str, excluded: bool) -> str:
    icon = "❌" if severity == "error" else "⚠️"
    return f"{icon} {severity} (excluded)" if excluded else f"{icon} {severity}"


_ERC_TABLE_HEADER = (
    "| Severity | Type | Description | Components | Items | Position (mm) |\n"
    "|----------|------|-------------|------------|-------|---------------|\n"
)


def _erc_row(error: ERCError, description_limit: int | None = None) -> str:
    """Format one ERC violation as a Markdown table row."""
    description = error.description[:description_limit] if description_limit else error.description
    components = ", ".join(dict.fromkeys(error.components)) or "N/A"
    items = _join_cells([_erc_item_text(i) for i in error.items])
    positions = _join_cells([_position_text(i.x_mm, i.y_mm) for i in error.items])
    return (
        f"| {_severity_cell(error.severity, error.excluded)} | {error.type} "
        f"| {_md(description)} | {components} | {items} | {positions} |\n"
    )


_DRC_TABLE_HEADER = (
    "| Severity | Type | Location | Description | Items |\n"
    "|----------|------|----------|-------------|-------|\n"
)


def _drc_row(error: DRCError, description_limit: int | None = None) -> str:
    """Format one DRC violation as a Markdown table row."""
    description = error.description[:description_limit] if description_limit else error.description
    x, y = error.location
    items = _join_cells([i.description for i in error.items])
    return (
        f"| {_severity_cell(error.severity, error.excluded)} | {error.type} "
        f"| ({x:.2f}, {y:.2f}) | {_md(description)} | {items} |\n"
    )


def _count_text(errors: list[ERCError] | list[DRCError]) -> str:
    """Give the error, warning and exclusion counts as Markdown list lines."""
    active = [e for e in errors if not e.excluded]
    error_count = sum(1 for e in active if e.severity == "error")
    warning_count = sum(1 for e in active if e.severity == "warning")
    text = f"- Errors: {error_count}\n- Warnings: {warning_count}"
    excluded_count = len(errors) - len(active)
    if excluded_count:
        text += f"\n- Excluded: {excluded_count}"
    return text


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


def _parse_erc_report(
    report_path: Path, schematic_files: list[Path] | None = None
) -> list[ERCError]:
    """Parse ERC report file (JSON or XML format).

    Args:
        report_path: Path to ERC report file
        schematic_files: Schematic files of the project. They are used to
            find the scale of the report positions (see
            ``erc_position_scale``).

    Returns:
        List of ERC errors/warnings
    """
    errors = []
    content = report_path.read_text(encoding="utf-8", errors="replace")

    try:
        data = json.loads(content)
        # KiCad 8-10 ERC JSON: sheets[].violations (see check_report_parser).
        scale, _source = erc_position_scale(data, schematic_files or [])
        return parse_erc_report(data, scale)
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
        # KiCad 9+ DRC JSON: top-level lists "violations", "unconnected_items"
        # and "schematic_parity" (no "sheets" key).
        return parse_drc_report(data)
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
        # schematic, so the report is named after the ROOT schematic — not
        # the (possibly sub-sheet) input, which would never match.
        erc_report_path = _report_path(sch_path, "erc")
        # Remove the old report: after the run, a report file must be the
        # result of this run.
        erc_report_path.unlink(missing_ok=True)

        # Run ERC using kicad-cli (KiCad 7+). --severity-all also gives the
        # excluded violations, with "excluded": true. The English locale
        # makes the item text parsable (pin number, pin name and pin type).
        result = await run_kicad_cli(
            [
                "sch",
                "erc",
                "--format",
                "json",
                "--severity-all",
                "--output",
                str(erc_report_path),
                str(sch_path),
            ],
            timeout=60,
            env=english_env(),
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
            errors = _parse_erc_report(erc_report_path, _schematic_files(sch_path))

            if not any(not e.excluded for e in errors):
                excluded_note = (
                    f"\n\n{len(errors)} excluded violation(s) are not counted." if errors else ""
                )
                return f"""✅ **ERC Check Passed**

**Schematic:** {schematic_path}

No electrical violations detected!{excluded_note}{subsheet_note}"""

            # Format violations
            violations_table = _ERC_TABLE_HEADER
            for error in errors[:20]:  # Limit to first 20
                violations_table += _erc_row(error, description_limit=50)

            if len(errors) > 20:
                violations_table += f"\n*... and {len(errors) - 20} more violations*\n"

            return f"""❌ **ERC Violations Detected**

**Schematic:** {schematic_path}
**Total Violations:** {len(errors)}
{_count_text(errors)}{subsheet_note}

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

KiCad's command-line tool (kicad-cli) could not be located on PATH or in the
detected KiCad install directory. Install KiCad 7+ (https://www.kicad.org/),
or point the KICAD_CLI environment variable at the kicad-cli executable."""
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
        drc_report_path = _report_path(pcb, "drc")
        # Remove the old report: after the run, a report file must be the
        # result of this run.
        drc_report_path.unlink(missing_ok=True)

        # Run DRC using kicad-cli (KiCad 7+). --severity-all also gives the
        # excluded violations. The schematic parity check is possible only
        # when the schematic of the board is available.
        args = ["pcb", "drc", "--format", "json", "--severity-all"]
        if pcb.with_suffix(".kicad_sch").exists():
            args.append("--schematic-parity")
        result = await run_kicad_cli(
            args + ["--output", str(drc_report_path), str(pcb)],
            timeout=60,
            env=english_env(),
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
            # kicad-cli returned success but wrote no report. Do NOT claim
            # "passed": no check was verified.
            return f"""⚠️ **DRC Report Not Generated**

**PCB:** {pcb_path}

kicad-cli exited cleanly but wrote no report file, so no checks could be
verified. Ensure KiCad 9+ is installed and the board file loads in Pcbnew."""

        # Parse and format results
        try:
            errors = _parse_drc_report(drc_report_path)

            if not any(not e.excluded for e in errors):
                excluded_note = (
                    f"\n\n{len(errors)} excluded violation(s) are not counted." if errors else ""
                )
                return f"""✅ **DRC Check Passed**

**PCB:** {pcb_path}

No design rule violations detected!{excluded_note}"""

            # Group by type (excluded violations are not counted)
            type_counts: dict[str, int] = {}
            for error in errors:
                if not error.excluded:
                    type_counts[error.type] = type_counts.get(error.type, 0) + 1

            # Format violations: the most severe first. Unconnected items and
            # schematic parity errors are at the end of the report, thus
            # they could be lost after the 20-row limit.
            ordered = sorted(
                errors,
                key=lambda e: (e.excluded, e.severity != "error", e.category == "violation"),
            )
            violations_table = _DRC_TABLE_HEADER
            for error in ordered[:20]:  # Limit to first 20
                violations_table += _drc_row(error, description_limit=40)

            if len(errors) > 20:
                violations_table += f"\n*... and {len(errors) - 20} more violations*\n"

            # Format type summary
            type_summary = "\n## Violation Summary\n\n"
            for vtype, count in sorted(type_counts.items()):
                type_summary += f"- **{vtype}**: {count} violations\n"

            return f"""❌ **DRC Violations Detected**

**PCB:** {pcb_path}
**Total Violations:** {len(errors)}
{_count_text(errors)}

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
        # schematic, so the report is named after the ROOT schematic — not
        # the (possibly sub-sheet) input, which would never match.
        root = _find_root_schematic(sch_path) or sch_path
        erc_report_path = _report_path(root, "erc")

        if _report_is_stale(erc_report_path, _erc_sources(root)):
            # Run ERC first. run_erc gives "❌" also when it found violations,
            # thus only a missing report is a failure.
            initial_result = await run_erc(schematic_path)
            if not erc_report_path.exists():
                return initial_result

        # Parse ERC report
        errors = _parse_erc_report(erc_report_path, _schematic_files(root))

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

{_ERC_TABLE_HEADER}"""

        for error in filtered_errors:
            result += _erc_row(error)

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
        drc_report_path = _report_path(pcb, "drc")

        if _report_is_stale(drc_report_path, _drc_sources(pcb)):
            # Run DRC first. run_drc gives "❌" also when it found violations,
            # thus only a missing report is a failure.
            initial_result = await run_drc(pcb_path)
            if not drc_report_path.exists():
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

{_DRC_TABLE_HEADER}"""

        for error in filtered_errors:
            result += _drc_row(error)

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

    The report is the kicad-cli ERC JSON report.

    Args:
        schematic_path: Path to .kicad_sch file
        output_path: Optional output file path (default: schematic_name_erc_report.json)

    Returns:
        Confirmation with output file location
    """
    try:
        sch_path = Path(schematic_path)
        if not sch_path.exists():
            return f"❌ **Schematic file not found:** {schematic_path}"

        # ERC report path. run_erc writes the report of the root schematic.
        root = _find_root_schematic(sch_path) or sch_path
        erc_report_path = _report_path(root, "erc")

        # Run ERC first to generate a current report. run_erc gives "❌" also
        # when it found violations, thus only a missing report is a failure.
        initial_result = await run_erc(schematic_path)

        if not erc_report_path.exists():
            return f"❌ **ERC Check Failed**\n\n{initial_result}"

        # Determine output path
        if not output_path:
            output_path = str(sch_path.parent / (sch_path.stem + "_erc_report.json"))

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

    The report is the kicad-cli DRC JSON report.

    Args:
        pcb_path: Path to .kicad_pcb file
        output_path: Optional output file path (default: pcb_name_drc_report.json)

    Returns:
        Confirmation with output file location
    """
    try:
        pcb = Path(pcb_path)
        if not pcb.exists():
            return f"❌ **PCB file not found:** {pcb_path}"

        drc_report_path = _report_path(pcb, "drc")

        # Run DRC first to generate a current report. run_drc gives "❌" also
        # when it found violations, thus only a missing report is a failure.
        initial_result = await run_drc(pcb_path)

        if not drc_report_path.exists():
            return f"❌ **DRC Check Failed**\n\n{initial_result}"

        # Determine output path
        if not output_path:
            output_path = str(pcb.parent / (pcb.stem + "_drc_report.json"))

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
