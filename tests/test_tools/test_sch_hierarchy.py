"""Tests for the sheet hierarchy of KiCad projects."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from kicad_mcp_server.utils.sch_hierarchy import (
    AmbiguousRootError,
    _sheet_file_names,
    find_root_schematic,
    is_project_root,
    roots_containing,
    sheet_files,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def sch(*sheet_files: str, key: str = "Sheetfile") -> str:
    """Return a schematic with one sheet symbol for each sheet file."""
    sheets = "".join(
        f"""\t(sheet
\t\t(at 100 50)
\t\t(size 20 10)
\t\t(uuid "00000000-0000-4000-8000-{index:012d}")
\t\t(property "Sheetname" "S{index}" (at 100 49 0))
\t\t(property "{key}" "{name}" (at 100 61 0))
\t)
"""
        for index, name in enumerate(sheet_files)
    )
    return f'(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n{sheets})\n'


def write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or sch(), encoding="utf-8")
    return path


def project(directory: Path, name: str, *sheet_names: str) -> Path:
    """Write a .kicad_pro and its root schematic, and return the root."""
    write(directory / f"{name}.kicad_pro", "{}")
    return write(directory / f"{name}.kicad_sch", sch(*sheet_names))


class TestSheetFileNames:
    def test_kicad_7_and_kicad_6_property_names(self):
        assert _sheet_file_names(sch("a.kicad_sch")) == ["a.kicad_sch"]
        assert _sheet_file_names(sch("a.kicad_sch", key="Sheet file")) == ["a.kicad_sch"]

    def test_symbol_field_named_sheetfile_is_not_a_sheet(self):
        content = (
            '(kicad_sch\n\t(symbol (lib_id "Device:R")\n'
            '\t\t(property "Sheetfile" "fake.kicad_sch" (at 0 0 0))\n\t)\n)\n'
        )
        assert _sheet_file_names(content) == []

    def test_escaped_quote_and_parenthesis_in_strings(self):
        content = sch('dir (1)/a \\"b\\".kicad_sch')
        assert _sheet_file_names(content) == ['dir (1)/a "b".kicad_sch']

    @pytest.mark.parametrize("content", ["(kicad_sch))", "(kicad_sch (sheet)"])
    def test_unbalanced_parentheses(self, content):
        with pytest.raises(ValueError):
            _sheet_file_names(content)

    def test_invalid_utf8_name_is_empty(self):
        # KiCad reads a string that is not valid UTF-8 as an empty string.
        content = sch("a\udcff.kicad_sch", "b.kicad_sch")
        assert _sheet_file_names(content) == ["", "b.kicad_sch"]

    def test_kicad_fixture(self):
        content = (FIXTURES / "hier" / "root.kicad_sch").read_text(encoding="utf-8")
        assert _sheet_file_names(content) == ["child.kicad_sch", "missing.kicad_sch"]


class TestSheetFiles:
    def test_names_are_relative_to_the_parent_sheet(self, tmp_path):
        # KiCad makes a sheet file name absolute with the directory of the
        # parent sheet, not of the root (SCH_IO_KICAD_SEXPR::loadHierarchy)
        root = project(tmp_path, "board", "power/power.kicad_sch")
        power = write(tmp_path / "power" / "power.kicad_sch", sch("ldo.kicad_sch"))
        ldo = write(tmp_path / "power" / "ldo.kicad_sch")
        assert sheet_files(root) == [root, power, ldo]

    def test_each_file_one_time_and_no_endless_loop(self, tmp_path):
        root = project(tmp_path, "board", "a.kicad_sch", "a.kicad_sch")
        a = write(tmp_path / "a.kicad_sch", sch("board.kicad_sch"))
        assert sheet_files(root) == [root, a]

    def test_text_variable_that_is_not_a_string(self, tmp_path):
        root = project(tmp_path, "board", "${REV}.kicad_sch")
        (tmp_path / "board.kicad_pro").write_text(
            json.dumps({"text_variables": {"REV": 2}}), encoding="utf-8"
        )
        assert sheet_files(root) == [root]

    def test_missing_file_is_not_in_the_list(self, tmp_path):
        root = project(tmp_path, "board", "missing.kicad_sch")
        assert sheet_files(root) == [root]

    def test_sheet_that_is_not_valid_utf8_is_in_the_list(self, tmp_path):
        # KiCad loads such a sheet: only the string with the invalid byte is
        # empty. The sheets below it stay in the hierarchy.
        root = project(tmp_path, "board", "a.kicad_sch")
        a = tmp_path / "a.kicad_sch"
        content = sch("b.kicad_sch").replace("(generator ", '(label "\udcff") (generator ')
        a.write_bytes(content.encode("utf-8", errors="surrogateescape"))
        b = write(tmp_path / "b.kicad_sch")
        assert sheet_files(root) == [root, a, b]
        assert find_root_schematic(b) == root

    def test_sheet_file_name_that_is_not_valid_utf8_gives_no_file(self, tmp_path):
        root = tmp_path / "board.kicad_sch"
        write(tmp_path / "board.kicad_pro", "{}")
        root.write_bytes(sch("\udcff.kicad_sch").encode("utf-8", errors="surrogateescape"))
        assert sheet_files(root) == [root]

    def test_project_text_variables_and_no_environment(self, tmp_path, monkeypatch):
        root = project(
            tmp_path,
            "board",
            "${PROJECTNAME}_io.kicad_sch",
            "${BLOCK}.kicad_sch",
            "${HOME}.kicad_sch",
        )
        (tmp_path / "board.kicad_pro").write_text(
            json.dumps({"text_variables": {"BLOCK": "usb"}}), encoding="utf-8"
        )
        monkeypatch.setenv("HOME", "env")
        io = write(tmp_path / "board_io.kicad_sch")
        usb = write(tmp_path / "usb.kicad_sch")
        write(tmp_path / "env.kicad_sch")
        assert sheet_files(root) == [root, io, usb]


class TestFindRootSchematic:
    def test_root_schematic_gives_none(self, tmp_path):
        root = project(tmp_path, "board", "sub.kicad_sch")
        assert is_project_root(root)
        assert find_root_schematic(root) is None

    def test_sub_sheet_gives_root(self, tmp_path):
        root = project(tmp_path, "board", "sub.kicad_sch")
        sub = write(tmp_path / "sub.kicad_sch")
        assert find_root_schematic(sub) == root

    def test_sub_sheet_in_a_sub_directory(self, tmp_path):
        root = project(tmp_path, "board", "sheets/sub.kicad_sch")
        sub = write(tmp_path / "sheets" / "sub.kicad_sch")
        assert find_root_schematic(sub) == root

    def test_file_that_no_root_holds_gives_none(self, tmp_path):
        project(tmp_path, "board")
        loose = write(tmp_path / "loose.kicad_sch")
        assert find_root_schematic(loose) is None

    def test_no_project(self, tmp_path):
        assert find_root_schematic(write(tmp_path / "sheet.kicad_sch")) is None

    def test_root_schematic_missing(self, tmp_path):
        write(tmp_path / "board.kicad_pro", "{}")
        assert find_root_schematic(write(tmp_path / "sub.kicad_sch")) is None

    def test_two_projects_in_one_directory(self, tmp_path):
        # Only the root that holds the sheet counts, not the first .kicad_pro
        project(tmp_path, "board")
        root = project(tmp_path, "board_variant", "sub.kicad_sch")
        assert find_root_schematic(write(tmp_path / "sub.kicad_sch")) == root

    def test_two_roots_hold_the_sheet(self, tmp_path):
        a = project(tmp_path, "a", "sub.kicad_sch")
        b = project(tmp_path, "b", "sub.kicad_sch")
        sub = write(tmp_path / "sub.kicad_sch")
        with pytest.raises(AmbiguousRootError) as error:
            find_root_schematic(sub)
        assert error.value.roots == [a, b]

    def test_nested_project_used_as_sub_sheet(self, tmp_path):
        main = project(tmp_path, "main", "usb/usb.kicad_sch")
        usb = project(tmp_path / "usb", "usb")
        # usb.kicad_sch is the root of its own project ...
        assert find_root_schematic(usb) is None
        # ... and a sub-sheet of main
        assert roots_containing(usb) == [usb, main]

    def test_project_through_a_symbolic_link_is_one_root(self, tmp_path):
        root = project(tmp_path / "real" / "proj", "proj", "sub/p.kicad_sch")
        write(tmp_path / "real" / "proj" / "sub" / "p.kicad_sch")
        link = tmp_path / "link"
        try:
            os.symlink(tmp_path / "real", link, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("no permission to make a symbolic link")
        found = find_root_schematic(link / "proj" / "sub" / "p.kicad_sch")
        assert found is not None
        assert found.resolve() == root.resolve()

    def test_sub_sheet_opened_alone_is_not_a_root(self, tmp_path):
        # The schematic editor opened the sub-sheet alone: KiCad wrote the
        # lock file of a project with the name of the sub-sheet
        root = project(tmp_path, "board", "sub.kicad_sch")
        sub = write(tmp_path / "sub.kicad_sch")
        write(tmp_path / "~sub.kicad_pro.lck", "{}")
        assert not is_project_root(sub)
        assert find_root_schematic(sub) == root

    def test_file_that_kicad_cannot_load_is_not_a_root(self, tmp_path):
        write(tmp_path / "board.kicad_pro", "{}")
        write(
            tmp_path / "board.kicad_sch",
            '(kicad_sch (sheet (property "Sheetfile" "sub.kicad_sch"))))',
        )
        sub = write(tmp_path / "sub.kicad_sch")
        assert find_root_schematic(sub) is None

    def test_project_lock_with_no_project_file(self, tmp_path):
        # The schematic editor opened root.kicad_sch alone: KiCad writes the
        # lock file of the project, but no .kicad_pro file
        root = write(tmp_path / "root.kicad_sch", sch("child.kicad_sch"))
        child = write(tmp_path / "child.kicad_sch")
        assert find_root_schematic(child) is None
        write(tmp_path / "~root.kicad_pro.lck", "{}")
        assert find_root_schematic(child) == root


class TestToolsWithTwoRoots:
    """The tools tell the agent when more than one root holds a sub-sheet."""

    @pytest.fixture
    def sub(self, tmp_path):
        project(tmp_path, "a", "sub.kicad_sch")
        project(tmp_path, "b", "sub.kicad_sch")
        return write(tmp_path / "sub.kicad_sch")

    def test_generate_netlist(self, sub):
        from kicad_mcp_server.tools.netlist import generate_netlist

        result = asyncio.run(generate_netlist(str(sub)))
        assert result.startswith("❌") and "more than one root schematic" in result

    def test_run_erc(self, sub):
        from kicad_mcp_server.tools.validation import run_erc

        result = asyncio.run(run_erc(str(sub)))
        assert result.startswith("❌") and "more than one root schematic" in result

    def test_pin_analysis(self, sub):
        from kicad_mcp_server.tools.pin_analysis import analyze_pin_functions

        result = asyncio.run(analyze_pin_functions(str(sub)))
        assert "more than one root schematic" in result
