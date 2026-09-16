"""KiCad project creation tools for KiCad MCP Server.

Empty projects are written by the installed KiCad itself (pcbnew API plus
kicad-cli), so the files are always in that KiCad's native format. Template
projects are copied the way KiCad's "New Project from Template" does it.
"""

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from ..server import mcp
from ..utils.kicad_cli import get_kicad_version, run_kicad_cli
from ..utils.kicad_python import find_kicad_python, run_kicad_python
from ..utils.kicad_version import find_kicad_install

EMPTY_TEMPLATE = "empty"

# Runs under KiCad's Python (see utils/kicad_python.py), so it must be
# self-contained. NewBoard + SaveBoard also write the default .kicad_pro and
# .kicad_prl next to the board.
# argv: pcb_path, title, company, date
_NEW_BOARD_SCRIPT = """\
import sys
import pcbnew

pcb_path, title, company, date = sys.argv[1:5]
board = pcbnew.NewBoard(pcb_path)
title_block = board.GetTitleBlock()
title_block.SetTitle(title)
title_block.SetCompany(company)
title_block.SetDate(date)
if not pcbnew.SaveBoard(pcb_path, board):
    sys.exit("pcbnew.SaveBoard failed")
"""

# KiCad 9's schematic format, the oldest this server supports. `kicad-cli sch
# upgrade` then rewrites it in the installed KiCad's native format.
_EMPTY_SCHEMATIC = """\
(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "9.0")
\t(uuid "{uuid}")
\t(paper "A4")
\t(lib_symbols)
\t(sheet_instances
\t\t(path "/"
\t\t\t(page "1")
\t\t)
\t)
\t(embedded_fonts no)
)
"""


def _kicad_template_dirs() -> list[Path]:
    """Return the installed KiCad's template directories."""
    kicad = find_kicad_install()
    if not kicad:
        return []
    install_path, version_marker = kicad
    # Linux/macOS installs are detected at share/kicad (or SharedSupport)
    # already; Windows at the top-level versioned directory.
    if version_marker in ("linux", "macos"):
        template_dir = install_path / "template"
    else:
        template_dir = install_path / "share" / "kicad" / "template"
    return [template_dir] if template_dir.is_dir() else []


def _list_kicad_templates() -> list[str]:
    return sorted(
        d.name
        for base in _kicad_template_dirs()
        for d in base.iterdir()
        if d.is_dir() and any(d.glob("*.kicad_pro"))
    )


def _find_kicad_template(template: str) -> Path | None:
    """Resolve a template name (or a path to a template directory)."""
    candidates = [base / template for base in _kicad_template_dirs()] + [Path(template)]
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.kicad_pro")):
            return candidate
    return None


def _copy_template(template_dir: Path, dest_dir: Path, project_name: str) -> list[str]:
    """Copy a template into dest_dir, mirroring KiCad's PROJECT_TEMPLATE::CreateProject.

    meta/ (the template chooser's icon and description) is skipped. File names
    have the template's project base name replaced by project_name; directories
    such as footprint libraries (*.pretty) keep their names because the
    project's library tables refer to them.

    Returns the names of the created top-level entries.
    """
    pro_files = list(template_dir.glob("*.kicad_pro"))
    basename = pro_files[0].stem if len(pro_files) == 1 else template_dir.name

    created = []
    for src in sorted(template_dir.iterdir()):
        if src.is_dir():
            if src.name == "meta":
                continue
            shutil.copytree(src, dest_dir / src.name, dirs_exist_ok=True)
            created.append(f"{src.name}/")
        else:
            name = src.name
            if src.suffix != ".kicad_wks":
                name = src.stem.replace(basename, project_name) + src.suffix
            shutil.copy(src, dest_dir / name)
            created.append(name)
    return created


def _sexpr_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _set_title_block(content: str, title: str, company: str, date: str) -> str:
    """Set title/date/company in a schematic's (title_block ...), creating it if absent."""
    if "(title_block" not in content:
        # KiCad writes the title block right after (paper ...).
        content = re.sub(
            r'\(paper "[^"]*"[^)]*\)',
            lambda m: m.group(0) + "\n\t(title_block)",
            content,
            count=1,
        )
    # Each field is inserted at the start of the block, so go in reverse order.
    for field, value in (("company", company), ("date", date), ("title", title)):
        if not value:
            continue
        entry = f'({field} "{_sexpr_escape(value)}")'
        pattern = rf'\({field} "(?:[^"\\]|\\.)*"\)'
        if re.search(pattern, content):
            content = re.sub(pattern, lambda _m, e=entry: e, content, count=1)
        else:
            content = content.replace("(title_block", f"(title_block\n\t\t{entry}", 1)
    return content


def _personalize_template_project(
    path: Path, project_name: str, title: str, company: str, date: str
) -> None:
    """Give a copied template project its own name, root sheet UUID and title block."""
    sch_file = path / f"{project_name}.kicad_sch"
    root_uuid = str(uuid.uuid4())

    if sch_file.exists():
        content = sch_file.read_text(encoding="utf-8")
        m = re.search(r'\(uuid "([^"]*)"\)', content)
        if m:
            # Symbol instance paths ("/<root uuid>") reference it too.
            content = content.replace(m.group(1), root_uuid)
        content = _set_title_block(content, title, company, date)
        sch_file.write_text(content, encoding="utf-8")

    pro_file = path / f"{project_name}.kicad_pro"
    if pro_file.exists():
        pro_data = json.loads(pro_file.read_text(encoding="utf-8"))
        pro_data.setdefault("meta", {})["filename"] = pro_file.name
        if pro_data.get("sheets"):
            pro_data["sheets"] = [[root_uuid, "Root"]]
        pro_file.write_text(json.dumps(pro_data, indent=2), encoding="utf-8")


async def _create_empty_project(
    path: Path, project_name: str, title: str, company: str, date: str
) -> tuple[list[str], list[str]]:
    """Write an empty project with KiCad's own tooling.

    Returns (created file names, warnings). Raises RuntimeError when pcbnew
    fails to write the board.
    """
    pcb_file = path / f"{project_name}.kicad_pcb"
    result = await run_kicad_python(["-c", _NEW_BOARD_SCRIPT, str(pcb_file), title, company, date])
    if result.returncode != 0:
        raise RuntimeError(
            "pcbnew could not create the board:\n"
            + result.stderr.decode(errors="replace").strip()
        )

    sch_file = path / f"{project_name}.kicad_sch"
    content = _EMPTY_SCHEMATIC.format(uuid=uuid.uuid4())
    sch_file.write_text(_set_title_block(content, title, company, date), encoding="utf-8")

    warnings = []
    upgrade_failure = None
    try:
        upgrade = await run_kicad_cli(["sch", "upgrade", str(sch_file)], timeout=120)
        if upgrade.returncode != 0:
            upgrade_failure = upgrade.stderr.decode(errors="replace").strip()
    except FileNotFoundError as e:
        upgrade_failure = str(e)
    if upgrade_failure is not None:
        warnings.append(
            "The schematic is in KiCad 9 format because `kicad-cli sch upgrade` "
            f"failed ({upgrade_failure}). KiCad converts it on the first save."
        )

    created = [
        f"{project_name}{ext}"
        for ext in (".kicad_pro", ".kicad_prl", ".kicad_sch", ".kicad_pcb")
        if (path / f"{project_name}{ext}").exists()
    ]
    return created, warnings


@mcp.tool()
async def create_kicad_project(
    project_path: str,
    project_name: str,
    title: str = "",
    company: str = "",
    template: str = EMPTY_TEMPLATE,
) -> str:
    """Create a new KiCad project.

    By default the project is empty: a blank board, schematic and project
    file written by the installed KiCad itself, so they are in its native
    file format.

    Args:
        project_path: Directory path for the project
        project_name: Name of the project (without extension)
        title: Optional project title (defaults to project_name)
        company: Optional company name
        template: "empty" (default) for a blank project, or a KiCad template
            to start from, by name (e.g. "Arduino_Uno", "RaspberryPi-HAT") or
            as a path to a template directory. Templates come with their own
            board outline, footprints and schematic.

    Returns:
        Confirmation message with created files
    """
    try:
        path = Path(project_path)
        date_str = datetime.now().strftime("%Y-%m-%d")
        title_text = title or project_name

        existing = [
            f"{project_name}{ext}"
            for ext in (".kicad_pro", ".kicad_sch", ".kicad_pcb")
            if (path / f"{project_name}{ext}").exists()
        ]
        if existing:
            return (
                f"❌ A project named '{project_name}' already exists in {path} "
                f"({', '.join(existing)}). Choose another name or directory."
            )

        if template == EMPTY_TEMPLATE:
            if find_kicad_python() is None:
                return """❌ KiCad's Python (pcbnew) not found.

Creating a project needs KiCad installed:
  macOS:   brew install --cask kicad
  Linux:   sudo apt install kicad
  Windows: https://www.kicad.org/download/

If KiCad is installed in a non-standard location, set KICAD_PYTHON to its
python executable.
"""
            path.mkdir(parents=True, exist_ok=True)
            try:
                created, warnings = await _create_empty_project(
                    path, project_name, title_text, company, date_str
                )
            except RuntimeError as e:
                return f"❌ {e}"
            template_desc = "empty"
        else:
            template_dir = _find_kicad_template(template)
            if template_dir is None:
                available = _list_kicad_templates()
                listing = ", ".join(available) if available else "(no KiCad templates found)"
                return (
                    f"❌ KiCad template '{template}' not found.\n\n"
                    f'Available templates: {listing}\n\nUse template="empty" for a blank project.'
                )
            path.mkdir(parents=True, exist_ok=True)
            created = _copy_template(template_dir, path, project_name)
            _personalize_template_project(path, project_name, title_text, company, date_str)
            warnings = []
            template_desc = f"{template_dir.name} ({template_dir})"

        version = await get_kicad_version()
        kicad_label = f"KiCad {version}" if version else "KiCad"
        pro_file = path / f"{project_name}.kicad_pro"
        files_listing = "\n".join(f"- {n}" for n in created)
        warnings_section = (
            "\n## ⚠️ Warnings:\n\n" + "\n".join(f"- {w}" for w in warnings) + "\n"
            if warnings
            else ""
        )

        return f"""# ✅ {kicad_label} Project Created Successfully!

**Project Path:** {path}
**Project Name:** {project_name}
**Title:** {title_text}
**Company:** {company or '(none)'}
**Template:** {template_desc}

## 📄 Files Created:

{files_listing}
{warnings_section}
## 📖 How to Open in {kicad_label}:

1. Open KiCad
2. File → Open Project...
3. Navigate to: {pro_file}
4. Click Open

## 🔧 Next Steps:

1. Open schematic editor to add components
2. Use `add_component_from_library` to add parts
3. Use `add_wire` and `add_global_label` for connections
4. Update PCB from schematic when ready
"""

    except Exception as e:
        import traceback
        return f"Error creating project: {e}\n\n{traceback.format_exc()}"
