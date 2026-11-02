"""Tests for the quoting of strings in the S-expression writes and reads.

A label name, a property value or a title with a '"' or a '\\' made a
schematic that KiCad could not load. The round-trip tests let kicad-cli load
and save the file: KiCad writes its strings with the same escapes.
"""

import asyncio
import re
import subprocess
import sys
import uuid as uuidlib

import pytest

from kicad_mcp_server.parsers.sexpr import STRING, quote, unquote
from kicad_mcp_server.tools.pcb_layout import setup_pcb_layout
from kicad_mcp_server.tools.schematic_editor import (
    add_component_from_library,
    add_global_label,
    add_hierarchical_label,
    add_label,
)
from kicad_mcp_server.utils.kicad_cli import find_kicad_cli
from kicad_mcp_server.utils.kicad_version import get_kicad_symbol_dir

NAME = 'A "B" \\C'
QUOTED = '"A \\"B\\" \\\\C"'

SCH = """(kicad_sch
\t(version 20250114)
\t(generator "eeschema")
\t(generator_version "9.0")
\t(uuid "%s")
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

needs_kicad_cli = pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli not found")


@pytest.fixture
def sch(tmp_path):
    path = tmp_path / "t.kicad_sch"
    path.write_text(SCH % uuidlib.uuid4(), encoding="utf-8")
    return path


def _add_all_labels(sch, name):
    return [
        asyncio.run(add_label(str(sch), name, 50, 50)),
        asyncio.run(add_global_label(str(sch), "", "", name, x=60, y=60)),
        asyncio.run(add_hierarchical_label(str(sch), "", "", name, x=70, y=70)),
    ]


def _kicad_resave(path):
    """Let KiCad load and save the schematic. Return the saved text."""
    result = subprocess.run(
        [find_kicad_cli(), "sch", "upgrade", "--force", str(path)],
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, (result.stdout + result.stderr).decode("utf-8", "replace")
    return path.read_text(encoding="utf-8")


class TestQuote:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("GND", '"GND"'),
            ("", '""'),
            (NAME, QUOTED),
            ("a\nb\rc", '"a\\nb\\rc"'),
            ("µA/Ω", '"µA/Ω"'),
        ],
    )
    def test_escapes_as_kicad_writes(self, value, expected):
        assert quote(value) == expected


class TestUnquote:
    @pytest.mark.parametrize("value", ["GND", "", NAME, "a\nb\rc", "µA/Ω", "\\n"])
    def test_reverses_quote(self, value):
        assert unquote(quote(value)) == value

    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ('"\\a\\b\\f\\t\\v"', "\x07\x08\x0c\t\x0b"),
            ('"\\x41\\x4"', "A\x04"),
            ('"\\101\\7"', "A\x07"),
            ('"\\xc2\\xb5"', "µ"),
            # Escapes that the lexer reads as the characters themselves.
            ('"\\x"', "x"),
            ('"\\q"', "\\q"),
            # A byte that is not valid UTF-8 does not stop the read.
            ('"\\xff\\377"', "\udcff\udcff"),
        ],
    )
    def test_reads_as_the_kicad_lexer(self, token, expected):
        assert unquote(token) == expected

    def test_token_includes_escaped_quotes(self):
        text = f"(label {QUOTED} (at 1 2 0))"
        assert re.search(STRING, text).group(0) == QUOTED


class TestLabels:
    def test_names_are_quoted(self, sch):
        for result in _add_all_labels(sch, NAME):
            assert "✅" in result, result
        content = sch.read_text(encoding="utf-8")
        for kind in ("label", "global_label", "hierarchical_label"):
            assert f"({kind} {QUOTED} " in content

    @pytest.mark.parametrize("name", ["A\nB", "A\rB"])
    def test_line_break_is_refused(self, sch, name):
        before = sch.read_text(encoding="utf-8")
        for result in _add_all_labels(sch, name):
            assert "line break" in result, result
        assert sch.read_text(encoding="utf-8") == before

    @needs_kicad_cli
    def test_kicad_loads_the_names(self, sch):
        for result in _add_all_labels(sch, NAME):
            assert "✅" in result, result
        content = _kicad_resave(sch)
        for kind in ("label", "global_label", "hierarchical_label"):
            assert f"({kind} {QUOTED}" in content


class TestFieldValues:
    @pytest.mark.parametrize("bad", ["A\nB", "A\rB", "A\tB"])
    @pytest.mark.parametrize("field", ["reference", "value", "footprint"])
    def test_line_break_or_tab_is_refused(self, sch, field, bad):
        before = sch.read_text(encoding="utf-8")
        args = {"reference": "R1", "value": "10k", "footprint": "", field: bad}
        result = asyncio.run(add_component_from_library(str(sch), "Device", "R", **args))
        assert "line break or a tab" in result, result
        assert sch.read_text(encoding="utf-8") == before


@pytest.mark.skipif(get_kicad_symbol_dir() is None, reason="KiCad symbol libraries not installed")
class TestComponent:
    def test_label_finds_the_pin_of_a_quoted_reference(self, sch):
        result = asyncio.run(add_component_from_library(str(sch), "Device", "R", NAME, "10k"))
        assert "✅" in result, result
        result = asyncio.run(add_global_label(str(sch), NAME, "1", "SDA"))
        assert "(100.0, 96.19)" in result, result

    def test_second_component_does_not_copy_the_symbol(self, sch):
        for ref in ("R1", "R2"):
            result = asyncio.run(add_component_from_library(str(sch), "Device", "R", ref, "10k"))
            assert "✅" in result, result
        assert sch.read_text(encoding="utf-8").count('(symbol "Device:R"') == 1

    def test_properties_are_quoted(self, sch):
        result = asyncio.run(
            add_component_from_library(str(sch), "Device", "R", "R1", NAME, footprint=NAME)
        )
        assert "✅" in result, result
        content = sch.read_text(encoding="utf-8")
        assert f'(property "Value" {QUOTED} ' in content
        assert f'(property "Footprint" {QUOTED} ' in content

    @needs_kicad_cli
    def test_kicad_loads_the_properties(self, sch):
        result = asyncio.run(
            add_component_from_library(str(sch), "Device", "R", "R1", NAME, footprint=NAME)
        )
        assert "✅" in result, result
        content = _kicad_resave(sch)
        assert f'(property "Value" {QUOTED}' in content
        assert f'(property "Footprint" {QUOTED}' in content


@pytest.mark.skipif(sys.platform == "win32", reason="Windows file names cannot hold '\"'")
def test_board_title_is_quoted(tmp_path):
    sch = tmp_path / 'A "B" \\C.kicad_sch'
    sch.write_text(SCH % uuidlib.uuid4(), encoding="utf-8")
    result = asyncio.run(setup_pcb_layout(str(sch)))
    assert "✅" in result, result
    content = sch.with_suffix(".kicad_pcb").read_text(encoding="utf-8")
    assert f"(title {QUOTED})" in content
