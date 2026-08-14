"""kicad-cli invocation helpers.

Centralizes two concerns that every kicad-cli call site needs:

1. Locating the executable. On Windows, KiCad's installer does NOT add its
   bin directory to PATH, so a bare "kicad-cli" only works if the user
   patched PATH by hand. We fall back to the detected install location
   (``find_kicad_install``), where kicad-cli sits next to the versioned
   ``share/kicad`` directory.
2. Running it off the asyncio event loop. All MCP tools are ``async def``;
   calling ``subprocess.run`` inline blocks the whole server for the duration
   of an ERC/DRC/export (up to minutes), so callers must use the async
   ``run_kicad_cli`` wrapper instead.

The sync ``run_kicad_cli_sync`` variant exists for tests and other
non-async contexts.
"""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from .kicad_version import find_kicad_install

_cached_exe: str | None = None


def find_kicad_cli() -> str | None:
    """Locate the kicad-cli executable.

    Resolution order:
    1. ``KICAD_CLI`` environment variable (explicit user override).
    2. ``shutil.which("kicad-cli")`` (PATH lookup — default on Linux/macOS
       and on Windows installs whose bin dir was added to PATH).
    3. Known KiCad install locations via ``find_kicad_install()``.

    Returns the executable path, or None when KiCad cannot be found.
    """
    global _cached_exe
    if _cached_exe is not None:
        return _cached_exe

    override = os.environ.get("KICAD_CLI")
    if override and Path(override).is_file():
        _cached_exe = override
        return _cached_exe

    found = shutil.which("kicad-cli")
    if found:
        _cached_exe = found
        return _cached_exe

    install = find_kicad_install()
    if install:
        install_path, _version = install
        exe_name = "kicad-cli.exe" if os.name == "nt" else "kicad-cli"
        # Windows: <install>/bin/kicad-cli.exe
        # macOS: install_path is .../Contents/SharedSupport, the binary is
        #        in the sibling MacOS directory.
        # Linux: distro packages put kicad-cli on PATH, which step 2 found.
        candidates = [
            install_path / "bin" / exe_name,
            install_path.parent / "MacOS" / "kicad-cli",
        ]
        for candidate in candidates:
            if candidate.is_file():
                _cached_exe = str(candidate)
                return _cached_exe

    return None


def run_kicad_cli_sync(
    args: list[str],
    timeout: float = 60.0,
) -> subprocess.CompletedProcess:
    """Run kicad-cli synchronously (blocking).

    Raises FileNotFoundError when kicad-cli cannot be located, so callers can
    distinguish "KiCad not installed" from a failed run.
    """
    exe = find_kicad_cli()
    if exe is None:
        raise FileNotFoundError(
            "kicad-cli not found in PATH or known KiCad install locations. "
            "Install KiCad 7+ or set the KICAD_CLI environment variable."
        )
    return subprocess.run([exe] + args, capture_output=True, timeout=timeout)


async def run_kicad_cli(
    args: list[str],
    timeout: float = 60.0,
) -> subprocess.CompletedProcess:
    """Run kicad-cli off the event loop (non-blocking for the server).

    Raises FileNotFoundError when kicad-cli cannot be located — same contract
    as the sync variant, so existing ``except FileNotFoundError`` handlers
    keep working.
    """
    return await asyncio.to_thread(run_kicad_cli_sync, args, timeout)
