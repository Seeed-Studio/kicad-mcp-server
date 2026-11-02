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
import codecs
import functools
import locale
import os
import shutil
import subprocess
import sys
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


def _codec(name: str) -> str | None:
    try:
        return codecs.lookup(name).name
    except LookupError:
        return None


def fs_encoding() -> str:
    """Return the encoding that this process uses for file names and arguments.

    It is the locale encoding, or UTF-8 in the UTF-8 mode of Python (the
    default from Python 3.15, PEP 686) and on macOS.
    """
    return _codec(sys.getfilesystemencoding()) or "utf-8"


_LOCALE_PROBE = "import locale, sys; locale.setlocale(locale.LC_CTYPE, sys.argv[1])"


@functools.cache
def _locale_exists(name: str) -> bool:
    # A probe in a child process: setlocale() in this process is not safe
    # while other threads run. A probe that cannot run counts as a locale
    # that does not exist.
    if not sys.executable:
        return False
    try:
        probe = subprocess.run(
            [sys.executable, "-I", "-c", _LOCALE_PROBE, name], capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


@functools.cache
def child_ctype() -> str | None:
    """Return the LC_CTYPE that kicad-cli gets on Linux and macOS, or None.

    kicad-cli decodes its arguments (the file paths) and encodes its output
    with the character set of LC_CTYPE. This process encodes the paths with
    fs_encoding(), thus the character set must be the same. The LC_CTYPE of
    this process has it, except in the UTF-8 mode of Python with a locale
    that is not UTF-8 (for example zh_CN.GBK), and on macOS in the C locale.
    Then the function takes a UTF-8 locale that exists. If no UTF-8 locale
    exists, it gives None (see run_kicad_cli_sync()).
    """
    current = locale.setlocale(locale.LC_CTYPE)
    encoding = fs_encoding()
    if encoding != "utf-8" or _codec(locale.nl_langinfo(locale.CODESET)) == encoding:
        return current
    language = current.split(".")[0].split("@")[0]
    for name in (f"{language}.UTF-8", "C.UTF-8", "C.utf8", "en_US.UTF-8", "UTF-8"):
        if _locale_exists(name):
            return name
    return None


def kicad_cli_env(english: bool = False) -> dict[str, str] | None:
    """Return the environment for kicad-cli, or None for the environment of
    this process.

    With ``english``, kicad-cli writes report text (for example the ERC item
    "Symbol U1 Pin 3 [...]") in English, which the report parsers need.
    KiCad takes its language from LC_ALL, LC_MESSAGES, LANGUAGE and LANG,
    thus the function removes all LC_ variables of the user and sets LANG
    to "C", which each system has. This also keeps a decimal comma of the
    user (LC_NUMERIC) out of the report. On Windows and macOS these variables
    can have no effect. The parsers then fall back to language-neutral rules.

    LC_CTYPE is child_ctype(). A locale that does not exist (for example
    "C.UTF-8" on macOS or on an old Linux) would put kicad-cli in the "C"
    locale, and it would not load a file whose path is not ASCII.

    On Windows kicad-cli uses the UTF-8 code page from its manifest
    (activeCodePage, KiCad 6 and later) and Unicode arguments, thus its
    environment does not change.
    """
    if sys.platform == "win32":
        return None
    current = locale.setlocale(locale.LC_CTYPE)
    # Without a locale of the correct character set, ASCII text stays
    # correct (run_kicad_cli_sync() refuses other text).
    ctype = child_ctype() or current
    env = dict(os.environ)
    if english:
        env = {name: value for name, value in env.items() if not name.startswith("LC_")}
        env.update(LANG="C", LANGUAGE="", LC_CTYPE=ctype)
    elif ctype != current:
        if "LC_ALL" in env:
            # LC_ALL overrides LC_CTYPE. Its value stays the locale of the
            # other categories.
            lc_all = env.pop("LC_ALL")
            env = {name: value for name, value in env.items() if not name.startswith("LC_")}
            env["LANG"] = lc_all
        env["LC_CTYPE"] = ctype
    else:
        return None
    return env


def decode_output(data: bytes | None) -> str:
    """Decode the stdout or the stderr of kicad-cli.

    kicad-cli writes with the character set of its LC_CTYPE, which is
    fs_encoding() (see kicad_cli_env()). On Windows it writes UTF-8.
    """
    if not data:
        return ""
    encoding = "utf-8" if sys.platform == "win32" else fs_encoding()
    return data.decode(encoding, errors="replace")


def run_kicad_cli_sync(
    args: list[str],
    timeout: float = 60.0,
    english: bool = False,
) -> subprocess.CompletedProcess:
    """Run kicad-cli synchronously (blocking).

    ``english`` makes kicad-cli write English report text (see
    kicad_cli_env()).

    Raises RuntimeError when an argument is not ASCII and no locale lets
    kicad-cli decode it as this process encodes it (see child_ctype()).

    Raises FileNotFoundError when kicad-cli cannot be located, so callers can
    distinguish "KiCad not installed" from a failed run.
    """
    exe = find_kicad_cli()
    if exe is None:
        raise FileNotFoundError(
            "kicad-cli not found in PATH or known KiCad install locations. "
            "Install KiCad 7+ or set the KICAD_CLI environment variable."
        )
    if sys.platform != "win32" and child_ctype() is None and not all(a.isascii() for a in args):
        raise RuntimeError(
            "kicad-cli cannot read a file path that is not ASCII on this system. "
            "This server writes file paths as UTF-8 (the UTF-8 mode of Python), but "
            "the system has no UTF-8 locale for kicad-cli. Install a UTF-8 locale "
            "(for example C.UTF-8), or start the server with PYTHONUTF8=0."
        )
    return subprocess.run(
        [exe] + args, capture_output=True, timeout=timeout, env=kicad_cli_env(english)
    )


async def run_kicad_cli(
    args: list[str],
    timeout: float = 60.0,
    english: bool = False,
) -> subprocess.CompletedProcess:
    """Run kicad-cli off the event loop (non-blocking for the server).

    Raises FileNotFoundError when kicad-cli cannot be located — same contract
    as the sync variant, so existing ``except FileNotFoundError`` handlers
    keep working.
    """
    return await asyncio.to_thread(run_kicad_cli_sync, args, timeout, english)


async def get_kicad_version() -> str | None:
    """Return the installed KiCad version (e.g. "10.0.6"), or None if unknown."""
    try:
        result = await run_kicad_cli(["version"], timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return decode_output(result.stdout).strip() or None
