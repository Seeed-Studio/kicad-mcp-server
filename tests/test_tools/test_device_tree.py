"""Tests for the output file of generate_device_tree."""

import asyncio
import sys

import pytest

from kicad_mcp_server.tools import device_tree, pin_analysis

from .locale_env import can_name, non_utf8_env, run_python

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
    try:
        sch.write_text(SCH, encoding="utf-8")
    except OSError:
        pytest.skip("the file system accepts only UTF-8 file names")
    output = tmp_path / "board.dts"
    output.write_text("/* old */\n", encoding="utf-8")
    result = _generate(sch, output)
    assert "surrogates not allowed" in result, result
    assert output.read_text(encoding="utf-8") == "/* old */\n"


_IN_LOCALE = """
import asyncio
from pathlib import Path
from kicad_mcp_server.tools import device_tree, pin_analysis

directory, name, sch_text, netlist_text = ARGS
sch = Path(directory) / f"{name}.kicad_sch"
sch.write_text(sch_text, encoding="utf-8")
netlist = Path(directory) / "board.xml"
netlist.write_text(netlist_text, encoding="utf-8")
output = Path(directory) / "board.dts"

async def fake_ensure_netlist(_sch_path):
    return netlist

pin_analysis._ensure_netlist = fake_ensure_netlist
message = asyncio.run(device_tree.generate_device_tree(str(sch), "stm32f4", str(output)))
result([message, output.read_bytes().hex() if output.exists() else ""])
"""


@pytest.mark.parametrize("utf8_mode", [False, True])
def test_output_is_utf8_in_a_locale_that_is_not_utf8(tmp_path, utf8_mode):
    # The server runs in a locale that is not UTF-8, as on a system with such
    # a locale. The process makes the schematic file itself, thus the file
    # name uses the encoding of that locale.
    env, encoding = non_utf8_env()
    names = [name for name in NAMES if can_name(name, encoding, utf8_mode)]
    assert names, encoding
    for index, name in enumerate(names):
        directory = tmp_path / str(index)
        directory.mkdir()
        message, data = run_python(_IN_LOCALE, env, utf8_mode, str(directory), name, SCH, NETLIST)
        assert "Device Tree Generated Successfully" in message, message
        assert f'model = "{name}";'.encode() in bytes.fromhex(data)
