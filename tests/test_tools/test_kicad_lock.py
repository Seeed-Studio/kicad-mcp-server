"""Tests for the guard for KiCad files that a KiCad editor has open."""

import asyncio
import os

import pytest

from kicad_mcp_server.tools.pcb_layout import setup_pcb_layout
from kicad_mcp_server.tools.schematic_editor import (
    add_component_from_library,
    add_global_label,
    add_hierarchical_label,
    add_label,
    add_wire,
)
from kicad_mcp_server.utils.kicad_lock import (
    check_board_not_open,
    check_schematic_not_open,
    file_stamp,
    lock_file_path,
    write_board,
    write_schematic,
)

from .test_sch_hierarchy import project, sch, write

OWNER = '{"hostname":"host1","username":"user1"}'


def lock(file_path, content=OWNER):
    path = lock_file_path(file_path)
    path.write_text(content, encoding="utf-8")
    return path


DEVICE_LIBRARY = """(kicad_symbol_lib
	(version 20241209)
	(generator "kicad_symbol_editor")
	(symbol "R"
		(in_bom yes)
		(on_board yes)
		(property "Reference" "R" (at 0 0 0) (effects (font (size 1.27 1.27))))
		(symbol "R_1_1"
			(pin passive line (at 0 3.81 270) (length 1.27)
				(name "~" (effects (font (size 1.27 1.27))))
				(number "1" (effects (font (size 1.27 1.27))))
			)
			(pin passive line (at 0 -3.81 90) (length 1.27)
				(name "~" (effects (font (size 1.27 1.27))))
				(number "2" (effects (font (size 1.27 1.27))))
			)
		)
	)
)
"""


@pytest.fixture(autouse=True)
def device_library(tmp_path, monkeypatch):
    """A symbol library 'Device' with the symbol 'R', also without KiCad.

    add_component_from_library reads the symbol before it writes. Without a
    library, it stops before the guard.
    """
    library_dir = tmp_path / "symbols"
    library_dir.mkdir()
    (library_dir / "Device.kicad_sym").write_text(DEVICE_LIBRARY, encoding="utf-8")
    monkeypatch.setattr(
        "kicad_mcp_server.utils.kicad_version.get_kicad_symbol_dir", lambda: library_dir
    )


@pytest.fixture
def board(tmp_path):
    """A project with a root schematic and a sub-sheet in a sub-directory."""
    root = project(tmp_path, "board", "sheets/power.kicad_sch")
    sub = write(tmp_path / "sheets" / "power.kicad_sch")
    return root, sub


class TestCheckSchematicNotOpen:
    def test_lock_file_name(self, tmp_path):
        assert lock_file_path(tmp_path / "a.kicad_sch") == tmp_path / "~a.kicad_sch.lck"

    def test_no_lock_file(self, board):
        root, sub = board
        assert check_schematic_not_open(root) is None
        assert check_schematic_not_open(sub) is None

    def test_lock_of_the_file(self, board):
        root, _ = board
        lock_path = lock(root)
        error = check_schematic_not_open(str(root))
        assert error is not None
        assert error.startswith("Error: KiCad has the schematic open")
        assert str(lock_path) in error
        assert "user1@host1" in error
        assert "close the schematic editor" in error
        assert "open the schematic again" in error

    def test_lock_of_the_root_blocks_a_sub_sheet(self, board):
        # The schematic editor locks only the root schematic of the hierarchy
        root, sub = board
        lock_path = lock(root)
        error = check_schematic_not_open(sub)
        assert error is not None
        assert str(lock_path) in error

    def test_lock_of_a_sub_sheet_opened_alone(self, board):
        _, sub = board
        lock_path = lock(sub)
        error = check_schematic_not_open(sub)
        assert error is not None
        assert str(lock_path) in error

    def test_lock_of_a_root_that_does_not_hold_the_file(self, board, tmp_path):
        # A schematic of the same directory tree that is not in the
        # hierarchy of the open root
        root, _ = board
        lock(root)
        loose = write(tmp_path / "scratch" / "loose.kicad_sch")
        assert check_schematic_not_open(loose) is None

    def test_lock_of_the_outer_root_blocks_a_nested_project(self, tmp_path):
        # usb/ has its own project, and main uses usb.kicad_sch as a sub-sheet
        main = project(tmp_path, "main", "usb/usb.kicad_sch")
        usb = project(tmp_path / "usb", "usb")
        assert check_schematic_not_open(usb) is None
        lock_path = lock(main)
        error = check_schematic_not_open(usb)
        assert error is not None
        assert str(lock_path) in error

    def test_project_lock_alone_does_not_block(self, board):
        # The project manager locks the .kicad_pro file, but it does not
        # edit the schematic
        root, sub = board
        lock(root.with_suffix(".kicad_pro"))
        assert check_schematic_not_open(root) is None
        assert check_schematic_not_open(sub) is None

    def test_project_lock_with_no_project_file_finds_the_root(self, tmp_path):
        root = write(tmp_path / "root.kicad_sch", sch("child.kicad_sch"))
        child = write(tmp_path / "child.kicad_sch")
        lock(root.with_suffix(".kicad_pro"))
        assert check_schematic_not_open(child) is None
        lock_path = lock(root)
        error = check_schematic_not_open(child)
        assert error is not None
        assert str(lock_path) in error

    @pytest.mark.parametrize("content", ["", "not json", "[]", '{"username": "u"}'])
    def test_unreadable_lock_file_blocks(self, board, content):
        root, _ = board
        lock(root, content)
        error = check_schematic_not_open(root)
        assert error is not None
        assert "owner unknown" in error

    def test_schematic_with_no_project(self, tmp_path):
        sheet = write(tmp_path / "loose.kicad_sch")
        assert check_schematic_not_open(sheet) is None
        lock(sheet)
        assert check_schematic_not_open(sheet) is not None

    def test_symbolic_link(self, tmp_path):
        # KiCad writes the lock file next to the path that it opened
        real = write(tmp_path / "store" / "board.kicad_sch")
        link = tmp_path / "board.kicad_sch"
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError):
            pytest.skip("no permission to make a symbolic link")
        lock(link)
        assert check_schematic_not_open(link) is not None
        lock_file_path(link).unlink()
        lock(real)
        assert check_schematic_not_open(link) is not None


class TestCheckBoardNotOpen:
    def test_board(self, tmp_path):
        pcb = write(tmp_path / "board.kicad_pcb", "(kicad_pcb)")
        assert check_board_not_open(pcb) is None
        lock_path = lock(pcb)
        error = check_board_not_open(pcb)
        assert error is not None
        assert error.startswith("Error: KiCad has the board open")
        assert str(lock_path) in error
        assert "close the PCB editor" in error


class TestWriteAfterAChange:
    """An other program saved the file after the tool read it."""

    def test_schematic(self, board):
        root, _ = board
        stamp = file_stamp(root)
        root.write_text(sch("saved/by/kicad.kicad_sch"), encoding="utf-8")
        os.utime(root, ns=(stamp[0] + 1_000_000, stamp[0] + 1_000_000))
        error = write_schematic(root, "(kicad_sch)", stamp)
        assert error is not None and "changed after this tool read it" in error
        assert "saved/by/kicad" in root.read_text(encoding="utf-8")

    def test_board_made_after_the_stamp(self, tmp_path):
        pcb = tmp_path / "board.kicad_pcb"
        stamp = file_stamp(pcb)
        assert stamp is None
        pcb.write_text("(kicad_pcb)", encoding="utf-8")
        error = write_board(pcb, "(kicad_pcb (new))", stamp)
        assert error is not None and "changed after this tool read it" in error
        assert pcb.read_text(encoding="utf-8") == "(kicad_pcb)"

    def test_no_change(self, board):
        root, _ = board
        assert write_schematic(root, "(kicad_sch)", file_stamp(root)) is None
        assert root.read_text(encoding="utf-8") == "(kicad_sch)"


WRITE_TOOLS = [
    pytest.param(
        lambda p: add_component_from_library(p, "Device", "R", "R1", "10k"), id="component"
    ),
    pytest.param(lambda p: add_wire(p, [(0, 0), (10, 0)]), id="wire"),
    pytest.param(lambda p: add_label(p, "NET1", 10, 10), id="label"),
    pytest.param(lambda p: add_global_label(p, "R1", "1", "NET1", x=10, y=10), id="global_label"),
    pytest.param(
        lambda p: add_hierarchical_label(p, "R1", "1", "NET1", x=10, y=10), id="hier_label"
    ),
]


class TestWriteToolsRefuseOpenFiles:
    @pytest.mark.parametrize("call", WRITE_TOOLS)
    def test_tool_does_not_write_an_open_schematic(self, board, call):
        root, sub = board
        lock(root)
        for target in (root, sub):
            before = target.read_text(encoding="utf-8")
            result = asyncio.run(call(str(target)))
            assert result.startswith("Error: KiCad has the schematic open"), result
            assert target.read_text(encoding="utf-8") == before

    def test_tool_writes_a_closed_schematic(self, board):
        _, sub = board
        result = asyncio.run(add_wire(str(sub), [(0, 0), (10, 0)]))
        assert "✅" in result, result
        assert "(wire" in sub.read_text(encoding="utf-8")

    def test_component_tool_writes_a_closed_schematic(self, board):
        _, sub = board
        result = asyncio.run(add_component_from_library(str(sub), "Device", "R", "R1", "10k"))
        assert "✅" in result, result
        assert '(lib_id "Device:R")' in sub.read_text(encoding="utf-8")

    def test_setup_pcb_layout_does_not_write_an_open_board(self, board):
        root, _ = board
        pcb = write(root.with_suffix(".kicad_pcb"), "(kicad_pcb)")
        lock(pcb)
        result = asyncio.run(setup_pcb_layout(str(root)))
        assert result.startswith("Error: KiCad has the board open"), result
        assert pcb.read_text(encoding="utf-8") == "(kicad_pcb)"
