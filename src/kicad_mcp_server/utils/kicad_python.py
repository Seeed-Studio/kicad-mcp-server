"""Helpers for running scripts under a Python that can import ``pcbnew``.

pcbnew only ships with KiCad's own Python. The MCP server may run inside that
interpreter (the recommended install) or under a plain Python without pcbnew,
so tools that need KiCad to write files run a short script in a subprocess
using whichever interpreter has pcbnew.

Scripts must be self-contained (pass them with ``-c`` and their inputs via
argv): KiCad's bundled Python on Windows ignores PYTHONPATH because its
sitecustomize.py resets sys.path, so a script cannot import this package.
"""

import asyncio
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from .kicad_version import find_kicad_install

_cached_python: str | None = None


def find_kicad_python() -> str | None:
    """Locate a Python interpreter that can import pcbnew.

    Resolution order:
    1. ``KICAD_PYTHON`` environment variable (explicit user override).
    2. The current interpreter, when pcbnew is importable in this process.
    3. KiCad's bundled interpreter next to the detected install.
    4. Linux: the system python3, which distro KiCad packages install
       pcbnew for (only when a KiCad install was detected).

    Returns the interpreter path, or None when none can be found.
    """
    global _cached_python
    if _cached_python is not None:
        return _cached_python

    override = os.environ.get("KICAD_PYTHON")
    if override and Path(override).is_file():
        _cached_python = override
        return _cached_python

    if importlib.util.find_spec("pcbnew") is not None:
        _cached_python = sys.executable
        return _cached_python

    install = find_kicad_install()
    if install:
        install_path, _version = install
        # Windows: install_path is <...>/KiCad/<version>.
        # macOS: install_path is .../Contents/SharedSupport.
        contents = install_path.parent
        candidates = [
            install_path / "bin" / "python.exe",
            contents / "Frameworks" / "python3",
            contents / "Frameworks" / "Python.framework" / "Versions" / "Current" / "bin" / "python3",
        ]
        if sys.platform.startswith("linux"):
            candidates.append(Path("/usr/bin/python3"))
        for candidate in candidates:
            if candidate.is_file():
                _cached_python = str(candidate)
                return _cached_python

    return None


def run_kicad_python_sync(
    args: list[str],
    timeout: float = 120.0,
) -> subprocess.CompletedProcess:
    """Run the pcbnew-capable Python synchronously (blocking).

    Raises FileNotFoundError when no such interpreter can be located.
    """
    exe = find_kicad_python()
    if exe is None:
        raise FileNotFoundError(
            "No Python with KiCad's pcbnew module was found. Install KiCad or set "
            "the KICAD_PYTHON environment variable to KiCad's python executable."
        )
    # stdin is the MCP stdio transport; the child must not inherit it.
    return subprocess.run(
        [exe] + args,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )


async def run_kicad_python(
    args: list[str],
    timeout: float = 120.0,
) -> subprocess.CompletedProcess:
    """Run the pcbnew-capable Python off the event loop."""
    return await asyncio.to_thread(run_kicad_python_sync, args, timeout)
