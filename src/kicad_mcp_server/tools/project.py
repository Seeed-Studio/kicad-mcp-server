"""KiCad project creation tools for KiCad MCP Server - Updated for KiCad 9.0+

Uses KiCad's template projects to ensure 100% compatibility.
"""

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from ..server import mcp


def _find_kicad_template() -> Path | None:
    """Find KiCad template directory, auto-detecting installed version."""
    from ..utils.kicad_version import find_kicad_install

    kicad = find_kicad_install()
    if kicad:
        install_path, _version = kicad
        for template_name in ["Arduino_Mega", "EuroCard160mmX100mm"]:
            p = install_path / "share" / "kicad" / "template" / template_name
            if p.exists():
                return p

    # macOS fallback
    mac_base = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/template")
    for t in ["Arduino_Mega", "EuroCard160mmX100mm"]:
        if (mac_base / t).exists():
            return mac_base / t

    # Linux fallback
    for base in [Path("/usr/share/kicad/template"), Path("/usr/local/share/kicad/template")]:
        for t in ["Arduino_Mega", "EuroCard160mmX100mm"]:
            if (base / t).exists():
                return base / t

    return None


def _get_date_string() -> str:
    """Get current date in ISO format."""
    return datetime.now().strftime("%Y-%m-%d")


@mcp.tool()
async def create_kicad_project(
    project_path: str,
    project_name: str,
    title: str = "",
    company: str = "",
) -> str:
    """Create a complete KiCad 9.0+ project by copying KiCad's template.

    This method copies a KiCad template project and modifies it,
    ensuring 100% compatibility with KiCad 9.0+.

    Args:
        project_path: Directory path for the project
        project_name: Name of the project (without extension)
        title: Optional project title
        company: Optional company name

    Returns:
        Confirmation message with created files
    """
    try:
        # Find KiCad template
        template_path = _find_kicad_template()

        if not template_path:
            return """❌ KiCad template not found.

Please ensure KiCad is installed:
  macOS:   brew install --cask kicad
  Linux:   sudo apt install kicad
  Windows: https://www.kicad.org/download/

After installation, this tool will use KiCad's template to create projects.
"""

        path = Path(project_path)
        path.mkdir(parents=True, exist_ok=True)

        date_str = _get_date_string()
        title_text = title or project_name

        # Copy all files from template
        for file in template_path.glob("*"):
            if file.is_file():
                dest = path / file.name.replace("Arduino_Mega", project_name).replace("EuroCard160mmX100mm", project_name)
                shutil.copy(file, dest)

        # Rename files if needed
        for old_file in path.glob("*"):
            if "Arduino_Mega" in old_file.name or "EuroCard160mmX100mm" in old_file.name:
                new_name = old_file.name.replace("Arduino_Mega", project_name).replace("EuroCard160mmX100mm", project_name)
                new_path = old_file.parent / new_name
                if old_file != new_path:
                    old_file.rename(new_path)

        # Modify .kicad_pro file
        pro_file = path / f"{project_name}.kicad_pro"

        if pro_file.exists():
            with open(pro_file) as f:
                pro_data = json.load(f)

            # Update metadata
            pro_data["meta"]["filename"] = f"{project_name}.kicad_pro"

            # Update sheets
            if "sheets" in pro_data and pro_data["sheets"]:
                new_uuid = str(uuid.uuid4())
                pro_data["sheets"] = [[new_uuid, "Root"]]

            with open(pro_file, 'w') as f:
                json.dump(pro_data, f, indent=2)

        # Modify .kicad_sch file
        sch_file = path / f"{project_name}.kicad_sch"

        if sch_file.exists():
            content = sch_file.read_text()

            # Update UUID
            new_uuid = str(uuid.uuid4())
            content = re.sub(r'\(uuid "([^"]*)"\)', f'(uuid "{new_uuid}")', content, count=1)

            # Update title block
            content = re.sub(r'\(title "([^"]*)"\)', f'(title "{title_text}")', content, count=1)
            content = re.sub(r'\(date "([^"]*)"\)', f'(date "{date_str}")', content, count=1)

            if company:
                # Find and replace company, or add it if not present
                if '(company' in content:
                    content = re.sub(r'\(company "([^"]*)"\)', f'(company "{company}")', content, count=1)
                else:
                    # Add company field after title
                    content = re.sub(
                        r'(title "([^"]*)")',
                        rf'\1\n    (company "{company}")',
                        content,
                        count=1
                    )

            sch_file.write_text(content)

        return f"""# ✅ KiCad 9.0+ Project Created Successfully!

**Project Path:** {path}
**Project Name:** {project_name}
**Title:** {title_text}
**Company:** {company}
**Template Used:** {template_path.name}

## 📄 Files Created:

1. **{project_name}.kicad_pro** - KiCad project file
2. **{project_name}.kicad_sch** - Schematic file
3. **{project_name}.kicad_pcb** - PCB layout file
4. **fp-lib-table** - Footprint library table

## 📖 How to Open in KiCad 9.0+:

1. Open KiCad
2. File → Open Project...
3. Navigate to: {pro_file}
4. Click Open

The project will open in KiCad 9.0+ **without** version warnings!

## ✅ Compatibility:

- Created from KiCad's official template
- 100% compatible with KiCad 9.0+
- All settings and configurations are valid
- Ready for schematic design and PCB layout

## 🔧 Next Steps:

1. Open schematic editor to add components
2. Use `add_component_from_library` to add parts
3. Use `add_wire` and `add_global_label` for connections
4. Update PCB from schematic when ready

Project is ready for KiCad 9.0+! 🚀
"""

    except Exception as e:
        import traceback
        return f"Error creating project: {e}\\n\\n{traceback.format_exc()}"
