"""Tests for the output file of generate_device_tree."""

import asyncio
import sys

import pytest

from kicad_mcp_server.tools import device_tree, pin_analysis

SCH = '(kicad_sch (version 20250114) (generator "eeschema"))\n'
NETLIST = '<?xml version="1.0"?>\n<export version="E"><components/><nets/></export>\n'


@pytest.fixture
def no_kicad(tmp_path, monkeypatch):
    """Give the tool a netlist without kicad-cli."""
    netlist = tmp_path / "board.xml"
    netlist.write_text(NETLIST, encoding="utf-8")

    async def fake_ensure_netlist(_sch_path):
        return netlist

    monkeypatch.setattr(pin_analysis, "_ensure_netlist", fake_ensure_netlist)


def _generate(sch, output):
    return asyncio.run(device_tree.generate_device_tree(str(sch), "stm32f4", str(output)))


# Board names in different scripts. No Windows code page holds all of them,
# and Devanagari has no code page. "𠀀" (CJK Extension B) has 4 bytes in UTF-8
# and is a surrogate pair in UTF-16.
NAMES = [
    "řídicí_Ω",  # Czech and Greek: cp1250, cp1253
    "Плата_питания",  # Russian: cp1251
    "电源板",  # Chinese: cp936
    "電源ボード",  # Japanese: cp932
    "전원보드",  # Korean: cp949
    "لوحة_التحكم",  # Arabic, right to left: cp1256
    "לוח_בקרה",  # Hebrew, right to left: cp1255
    "แผงวงจร",  # Thai: cp874
    "बोर्ड",  # Devanagari: no code page
    "𠀀_板",  # CJK Extension B: 4 bytes in UTF-8
]


@pytest.mark.parametrize("name", NAMES)
def test_output_is_utf8(tmp_path, no_kicad, name):
    # The board name comes from the file name. On Windows the locale encoding
    # is the code page of the region: it cannot encode the names of other
    # scripts, and for its own script it gives bytes that are not UTF-8.
    sch = tmp_path / f"{name}.kicad_sch"
    sch.write_text(SCH, encoding="utf-8")
    output = tmp_path / "out" / "board.dts"
    result = _generate(sch, output)
    assert "Device Tree Generated Successfully" in result, result
    assert f'model = "{name}";'.encode() in output.read_bytes()


@pytest.mark.skipif(sys.platform != "linux", reason="needs a file name that is not UTF-8")
def test_text_that_is_not_valid_does_not_empty_the_output(tmp_path, no_kicad):
    # On Linux a file name can hold a byte that is not UTF-8. Python gives it
    # as a lone surrogate, which UTF-8 cannot encode. open("w") emptied the
    # output file before the encode error.
    sch = tmp_path / "board\udcff.kicad_sch"
    sch.write_text(SCH, encoding="utf-8")
    output = tmp_path / "board.dts"
    output.write_text("/* old */\n", encoding="utf-8")
    result = _generate(sch, output)
    assert "surrogates not allowed" in result, result
    assert output.read_text(encoding="utf-8") == "/* old */\n"
