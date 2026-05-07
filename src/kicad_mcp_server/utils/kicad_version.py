"""KiCad installation detection and version utilities."""

import re
from pathlib import Path

_cached_install: tuple[Path, str] | None = None


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string like '10.0' into tuple for sorting."""
    try:
        return tuple(int(x) for x in version_str.split("."))
    except (ValueError, AttributeError):
        return (0,)


def find_kicad_install() -> tuple[Path, str] | None:
    """Find the installed KiCad directory and version string.

    Scans known install locations, preferring the newest version.

    Returns:
        (install_path, version_string) or None if not found
    """
    global _cached_install
    if _cached_install is not None:
        return _cached_install

    # Windows: C:/Program Files/KiCad/{version}/
    win_base = Path("C:/Program Files/KiCad")
    if win_base.is_dir():
        try:
            version_dirs = sorted(
                [d for d in win_base.iterdir() if d.is_dir()],
                key=lambda d: _parse_version(d.name),
                reverse=True,
            )
            for vd in version_dirs:
                if (vd / "share" / "kicad").is_dir():
                    _cached_install = (vd, vd.name)
                    return _cached_install
        except OSError:
            pass

    # macOS: single app bundle
    mac_base = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport")
    if mac_base.is_dir():
        _cached_install = (mac_base, "macos")
        return _cached_install

    # Linux: standard paths
    for linux_base in [
        Path("/usr/share/kicad"),
        Path("/usr/local/share/kicad"),
    ]:
        if linux_base.is_dir():
            _cached_install = (linux_base, "linux")
            return _cached_install

    return None


def get_kicad_symbol_dir() -> Path | None:
    """Get the KiCad symbol library directory (.kicad_sym files)."""
    kicad = find_kicad_install()
    if kicad:
        install_path, _version = kicad
        sym_dir = install_path / "share" / "kicad" / "symbols"
        if sym_dir.is_dir():
            return sym_dir
    return None


def get_pcb_version() -> str:
    """Get the correct PCB file version string for the installed KiCad.

    Reads from a template PCB file if available, falls back to '20240130'.
    """
    kicad = find_kicad_install()
    if kicad:
        install_path, _version = kicad
        for template_name in ["Arduino_Mega", "EuroCard160mmX100mm"]:
            template_pcb = (
                install_path / "share" / "kicad" / "template" / template_name / f"{template_name}.kicad_pcb"
            )
            if template_pcb.exists():
                try:
                    content = template_pcb.read_text(encoding="utf-8", errors="replace")
                    m = re.search(r"\(kicad_pcb\s+\(version\s+(\d+)\)", content)
                    if m:
                        return m.group(1)
                except OSError:
                    pass
    return "20240130"
