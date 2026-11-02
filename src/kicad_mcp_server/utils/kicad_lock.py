"""Guard for KiCad files that a KiCad editor has open.

Some tools write a .kicad_sch or .kicad_pcb file directly. When a KiCad
editor has the file open, KiCad does not read the change, and the next save
in KiCad removes it. Thus each such tool calls a check of this module just
before the write, and refuses the write when KiCad has the file open.

KiCad 8 and later writes the lock file ``~<file name>.lck`` next to the file
that an editor opens, for example ``~board.kicad_sch.lck``. The lock file
holds ``{"username": ..., "hostname": ...}``. The schematic editor locks only
the root schematic of the hierarchy, not the sub-sheets. Thus the check of a
schematic also finds the root schematics that hold it (see sch_hierarchy).

After a crash, KiCad does not remove its lock file. The guard cannot know if
KiCad still runs, thus it also refuses the write for such a lock file. The
error message tells how to remove it.
"""

import json
import os
from pathlib import Path

from .sch_hierarchy import in_hierarchy, project_root_schematics


def lock_file_path(file_path: Path) -> Path:
    """Return the path of the KiCad lock file for a file."""
    return file_path.with_name(f"~{file_path.name}.lck")


def _existing_lock(file_path: Path) -> Path | None:
    """Return the lock file of a file, if it exists.

    KiCad writes the lock file next to the path that it opened. When that
    path is a symbolic link, the lock file is not next to the target. Thus
    the function does a check of the path as given and of the real path.
    """
    absolute = Path(os.path.abspath(file_path))
    for path in (absolute, absolute.resolve()):
        lock = lock_file_path(path)
        if lock.exists():
            return lock
    return None


def _lock_owner(lock_path: Path) -> str:
    """Return 'user@host' from a KiCad lock file, or 'unknown'."""
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        return f"{data['username']}@{data['hostname']}"
    except (OSError, ValueError, KeyError, TypeError):
        return "unknown"


def _open_error(opened: Path, lock_path: Path, document: str, editor: str) -> str:
    return (
        f"Error: KiCad has the {document} open: {opened} "
        f"(lock file {lock_path}, owner {_lock_owner(lock_path)}). "
        "This tool writes the file directly. KiCad does not read such a change, "
        "and the next save in KiCad removes it. Thus the tool did not write the file.\n\n"
        f"Tell the user to save the {document} and close the {editor} window. "
        "Then do this operation again. "
        f"After the write, tell the user to open the {document} again to see the change.\n\n"
        "If KiCad does not run, the lock file stays from a crash of KiCad. "
        f"Then tell the user to open the {document} in KiCad and close it again, "
        "or to delete the lock file."
    )


def check_schematic_not_open(file_path: str | Path) -> str | None:
    """Do a check if KiCad has a schematic open, before a tool writes it.

    KiCad has the schematic open when the file has a lock file, or when a
    root schematic that holds the file in its hierarchy has a lock file.

    Args:
        file_path: Path to the .kicad_sch file that the tool writes.

    Returns:
        None if KiCad does not have the schematic open. Else, an error
        message for the LLM that tells the user to close the schematic editor.
    """
    path = Path(os.path.abspath(file_path))
    lock = _existing_lock(path)
    if lock:
        return _open_error(path, lock, "schematic", "schematic editor")
    for root in project_root_schematics(path):
        lock = _existing_lock(root)
        if lock and in_hierarchy(path, root):
            return _open_error(root, lock, "schematic", "schematic editor")
    return None


def check_board_not_open(file_path: str | Path) -> str | None:
    """Do a check if KiCad has a board open, before a tool writes it.

    Args:
        file_path: Path to the .kicad_pcb file that the tool writes.

    Returns:
        None if KiCad does not have the board open. Else, an error message
        for the LLM that tells the user to close the PCB editor.
    """
    path = Path(os.path.abspath(file_path))
    lock = _existing_lock(path)
    if lock:
        return _open_error(path, lock, "board", "PCB editor")
    return None


FileStamp = tuple[int, int] | None


def file_stamp(path: Path) -> FileStamp:
    """Return the modification time and the size of a file, or None if no file.

    A tool gets the stamp before it reads the file, and gives it to
    write_schematic() or write_board(). When the stamp changed before the
    write, an other program (for example KiCad, before it closed) saved the
    file in the meantime, and the write would remove that save.
    """
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _guarded_write(
    path: Path, content: str, stamp: FileStamp, encoding: str | None, open_error: str | None
) -> str | None:
    if open_error:
        return open_error
    if file_stamp(path) != stamp:
        return (
            f"Error: The file {path} changed after this tool read it. "
            "Thus the tool did not write the file, to keep that change. "
            "Do this operation again."
        )
    path.write_text(content, encoding=encoding)
    return None


def write_schematic(
    path: Path, content: str, stamp: FileStamp, encoding: str | None = None
) -> str | None:
    """Write a schematic file, if KiCad does not have it open.

    Each tool that writes a schematic must use this function. The checks are
    just before the write, to keep the time between them and the write short.

    Args:
        path: The .kicad_sch file.
        content: The new content of the file.
        stamp: The file_stamp() of the file before the tool read it.
        encoding: The encoding of the file.

    Returns:
        None after the write. Else, the error message for the LLM.
    """
    return _guarded_write(path, content, stamp, encoding, check_schematic_not_open(path))


def write_board(
    path: Path, content: str, stamp: FileStamp, encoding: str | None = None
) -> str | None:
    """Write a board file, if KiCad does not have it open.

    Each tool that writes a board must use this function. The checks are
    just before the write, to keep the time between them and the write short.

    Args:
        path: The .kicad_pcb file.
        content: The new content of the file.
        stamp: The file_stamp() of the file before the tool read it, or
            before the tool made the new content.
        encoding: The encoding of the file.

    Returns:
        None after the write. Else, the error message for the LLM.
    """
    return _guarded_write(path, content, stamp, encoding, check_board_not_open(path))
