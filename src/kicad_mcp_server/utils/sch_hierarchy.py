"""Sheet hierarchy of KiCad projects.

A KiCad project has one root schematic: the .kicad_sch file with the same
name as the .kicad_pro file, in the same directory. The root schematic holds
sheet symbols, and each sheet symbol refers to a sub-sheet file through its
"Sheetfile" property. A sub-sheet can hold more sheet symbols.

This module finds the root schematic of a sub-sheet. It does not guess from
the directory layout only: it reads the sheet tree of each candidate root,
and it accepts a root only when the tree holds the file.

Limit: the candidate roots are the projects in the directory of the file and
in each parent directory. A sub-sheet outside the directory tree of its
project (for example ``../common/power.kicad_sch``) has no link back to its
project in the file system, thus this module cannot find its root.
"""

import hashlib
import json
import os
import re
from pathlib import Path

SCH_SUFFIX = ".kicad_sch"
PRO_SUFFIX = ".kicad_pro"
PRO_LOCK_SUFFIX = PRO_SUFFIX + ".lck"

# One S-expression token: a parenthesis, a quoted string (with backslash
# escapes), or a bare symbol or number.
_TOKEN = re.compile(r'[()]|"(?:[^"\\]|\\.)*"|[^\s()"]+')
_TEXT_VAR = re.compile(r"\$\{([^}]+)\}")
# KiCad 6 writes "Sheet file", KiCad 7 and later write "Sheetfile".
_SHEET_FILE_KEYS = {"Sheetfile", "Sheet file"}
# The sheet file names of each schematic content, by the digest of the content.
# One tool call reads the same hierarchy more than one time, and a large
# schematic takes a long time to tokenize.
_NAMES_CACHE: dict[bytes, list[str]] = {}
_NAMES_CACHE_SIZE = 1024


class AmbiguousRootError(Exception):
    """A sub-sheet is part of more than one root schematic."""

    def __init__(self, sheet: Path, roots: list[Path]):
        self.sheet = sheet
        self.roots = roots
        names = ", ".join(str(root) for root in roots)
        super().__init__(f"{sheet} is a sub-sheet of more than one root schematic: {names}")


def _unquote(token: str) -> str:
    value = re.sub(r"\\(.)", r"\1", token[1:-1])
    # KiCad reads a string that is not valid UTF-8 as an empty string
    # (DSNLEXER::FromUTF8()). Such bytes are lone surrogates here.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return ""
    return value


def _sheet_file_names(content: str) -> list[str]:
    """Return the "Sheetfile" values of the sheet symbols of a schematic.

    Only a property that is a direct child of a top-level (sheet ...) list
    counts. A symbol field with the same name is not a sheet file.

    Raises:
        ValueError: The parentheses are not balanced. KiCad cannot load
            such a file.
    """
    names = []
    # The head of each open list, and the strings that follow the head.
    heads: list[str] = []
    strings: list[list[str]] = []
    for match in _TOKEN.finditer(content):
        token = match.group()
        if token == "(":
            heads.append("")
            strings.append([])
        elif token == ")":
            if not heads:
                raise ValueError("unbalanced parentheses")
            head = heads.pop()
            values = strings.pop()
            if (
                head == "property"
                and len(heads) == 2
                and heads[-1] == "sheet"
                and len(values) >= 2
                and values[0] in _SHEET_FILE_KEYS
            ):
                names.append(values[1])
        elif heads and heads[-1] == "":
            heads[-1] = token
        elif heads and token.startswith('"'):
            strings[-1].append(_unquote(token))
    if heads:
        raise ValueError("unbalanced parentheses")
    return names


def _schematic_sheet_file_names(path: Path) -> list[str]:
    """Return the sheet file names of a schematic file, with a cache.

    KiCad loads a file that is not valid UTF-8: it reads each string with an
    invalid byte as an empty string. The structure of the file stays, thus the
    bytes are decoded with surrogateescape and not refused.

    Raises:
        OSError: The file cannot be read.
        ValueError: The parentheses are not balanced.
    """
    data = path.read_bytes()
    key = hashlib.blake2b(data, digest_size=16).digest()
    names = _NAMES_CACHE.get(key)
    if names is None:
        names = _sheet_file_names(data.decode("utf-8", errors="surrogateescape"))
        if len(_NAMES_CACHE) >= _NAMES_CACHE_SIZE:
            _NAMES_CACHE.clear()
        _NAMES_CACHE[key] = names
    return names


def _text_variables(root: Path) -> dict[str, str]:
    """Return the text variables that KiCad uses to expand a sheet file name.

    KiCad expands a sheet file name with the variables of the project only
    (PROJECT::TextVarResolver): PROJECTNAME and the text variables of the
    .kicad_pro file. It does not use environment variables. The variables
    for date, time and git hash are not applicable to a file name.
    """
    variables: dict[str, str] = {}
    try:
        project = json.loads(root.with_suffix(PRO_SUFFIX).read_text(encoding="utf-8"))
        # KiCad keeps the text variables as strings. Other values are not
        # applicable to a file name.
        variables.update(
            (name, value)
            for name, value in (project.get("text_variables") or {}).items()
            if isinstance(value, str)
        )
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    variables["PROJECTNAME"] = root.stem
    return variables


def _expand(name: str, variables: dict[str, str]) -> str:
    return _TEXT_VAR.sub(lambda m: variables.get(m.group(1), m.group(0)), name)


def sheet_files(root: Path) -> list[Path]:
    """Return the root schematic and all sub-sheet files of its hierarchy.

    The function resolves each sheet file name as KiCad does: it expands the
    text variables, and it makes a relative name absolute with the directory
    of the parent sheet. Each file is in the list one time, also when the
    hierarchy uses it more than one time. A missing file is not in the list.
    A file that KiCad cannot load (unbalanced parentheses) is not in the list.
    A file that is not valid UTF-8 is in the list, as in KiCad. A sheet file
    name that is empty (KiCad reads an invalid name as empty) gives no file.
    """
    root = Path(os.path.abspath(root))
    variables = _text_variables(root)
    found: list[Path] = []
    seen: set[Path] = set()
    pending = [root]
    while pending:
        sheet = pending.pop(0)
        try:
            real = sheet.resolve()
            if real in seen:
                continue
            names = _schematic_sheet_file_names(sheet)
        except (OSError, ValueError):
            continue
        seen.add(real)
        found.append(sheet)
        for name in names:
            if not name:
                continue
            child = Path(_expand(name, variables))
            if not child.is_absolute():
                child = sheet.parent / child
            pending.append(Path(os.path.normpath(child)))
    return found


def project_root_schematics(file_path: Path) -> list[Path]:
    """Return the root schematics of the projects that can hold a file.

    These are the projects in the directory of the file and in each parent
    directory. A project is a .kicad_pro file or its lock file: KiCad writes
    the lock file of the project also when no .kicad_pro file is there, for
    example when the schematic editor opens a .kicad_sch file alone. The root
    schematic does not always exist. When a symbolic link gives two paths to
    one root schematic, the list holds only the first path.
    """
    absolute = Path(os.path.abspath(file_path))
    directories: list[Path] = []
    for directory in [*absolute.parents, *absolute.resolve().parents]:
        if directory not in directories:
            directories.append(directory)

    roots: list[Path] = []
    real_roots: set[Path] = set()
    for directory in directories:
        names = {project.stem for project in directory.glob("*" + PRO_SUFFIX)}
        names.update(
            lock.name[1 : -len(PRO_LOCK_SUFFIX)] for lock in directory.glob("~*" + PRO_LOCK_SUFFIX)
        )
        for name in sorted(names):
            root = directory / (name + SCH_SUFFIX)
            real = root.resolve()
            if real not in real_roots:
                real_roots.add(real)
                roots.append(root)
    return roots


def is_project_root(file_path: Path) -> bool:
    """Return True if a schematic is the root schematic of its own project.

    That is, a .kicad_pro file with the same name is next to the schematic.
    A lock file of a project alone does not count: KiCad writes it also when
    the schematic editor opens a sub-sheet alone.
    """
    absolute = Path(os.path.abspath(file_path))
    return any(path.with_suffix(PRO_SUFFIX).is_file() for path in (absolute, absolute.resolve()))


def in_hierarchy(file_path: Path, root: Path) -> bool:
    """Return True if a file is the root schematic or a sub-sheet of it."""
    target = Path(file_path).resolve()
    return any(sheet.resolve() == target for sheet in sheet_files(root))


def roots_containing(file_path: Path) -> list[Path]:
    """Return the existing root schematics whose hierarchy holds a file."""
    return [
        root
        for root in project_root_schematics(file_path)
        if root.is_file() and in_hierarchy(file_path, root)
    ]


def find_root_schematic(file_path: Path) -> Path | None:
    """Return the root schematic of a sub-sheet, or None.

    Returns:
        None if the file is the root schematic of its own project, or if no
        root schematic holds it. Else, the one root schematic that holds it.

    Raises:
        AmbiguousRootError: More than one root schematic holds the file.
    """
    if is_project_root(file_path):
        return None
    # A lock file of a project can make the file a candidate root of itself
    target = Path(file_path).resolve()
    roots = [root for root in roots_containing(file_path) if root.resolve() != target]
    if len(roots) > 1:
        raise AmbiguousRootError(Path(file_path), roots)
    return roots[0] if roots else None
