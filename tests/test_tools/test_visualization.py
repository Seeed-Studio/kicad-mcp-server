"""Tests for visualization export tools (render / STEP / schematic SVG)."""

import asyncio

import pytest

from kicad_mcp_server.tools import visualization
from kicad_mcp_server.tools.visualization import (
    export_pcb_3d,
    export_schematic_svg,
    render_pcb,
)


class _FakeResult:
    def __init__(self, returncode=0, stderr=b""):
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture
def pcb_file(tmp_path):
    f = tmp_path / "board.kicad_pcb"
    f.write_text("(kicad_pcb (version 20240130))", encoding="utf-8")
    return f


@pytest.fixture
def sch_file(tmp_path):
    f = tmp_path / "root.kicad_sch"
    f.write_text("(kicad_sch (version 20231120))", encoding="utf-8")
    return f


class TestRenderPcb:
    def test_args_include_input_file(self, monkeypatch, pcb_file, tmp_path):
        """Regression: the input file MUST be the last positional arg — an
        earlier version omitted it and kicad-cli failed with rc=1."""
        captured = {}

        async def fake(args, timeout=60.0):
            captured["args"] = args
            return _FakeResult()

        monkeypatch.setattr(visualization, "run_kicad_cli", fake)
        out = tmp_path / "r.png"
        result = asyncio.run(
            render_pcb(str(pcb_file), side="top", output_path=str(out))
        )
        assert captured["args"][0:2] == ["pcb", "render"]
        assert captured["args"][-1] == str(pcb_file)
        assert "--side" in captured["args"]
        assert isinstance(result, object)  # Image or str, not an exception

    def test_rejects_invalid_side(self, pcb_file):
        result = asyncio.run(render_pcb(str(pcb_file), side="diagonal"))
        assert isinstance(result, str) and "Invalid side" in result

    def test_rejects_invalid_quality(self, pcb_file):
        result = asyncio.run(render_pcb(str(pcb_file), quality="ultra"))
        assert isinstance(result, str) and "Invalid quality" in result

    def test_missing_pcb_file(self, tmp_path):
        result = asyncio.run(render_pcb(str(tmp_path / "nope.kicad_pcb")))
        assert isinstance(result, str) and "not found" in result

    def test_rotate_appended_before_input(self, monkeypatch, pcb_file, tmp_path):
        captured = {}

        async def fake(args, timeout=60.0):
            captured["args"] = args
            return _FakeResult()

        monkeypatch.setattr(visualization, "run_kicad_cli", fake)
        asyncio.run(
            render_pcb(
                str(pcb_file), output_path=str(tmp_path / "r.png"), rotate="-60,0,30"
            )
        )
        args = captured["args"]
        assert args[-3:-1] == ["--rotate", "-60,0,30"]
        assert args[-1] == str(pcb_file)


class TestExportStep:
    def test_args_include_input_file(self, monkeypatch, pcb_file, tmp_path):
        captured = {}

        async def fake(args, timeout=60.0):
            captured["args"] = args
            return _FakeResult()

        monkeypatch.setattr(visualization, "run_kicad_cli", fake)
        out = tmp_path / "b.step"
        # create the file so the success path sees it
        out.write_bytes(b"ISO-10303-21;")
        result = asyncio.run(export_pcb_3d(str(pcb_file), output_path=str(out)))
        assert captured["args"][0:4] == ["pcb", "export", "step", "--output"]
        assert captured["args"][-1] == str(pcb_file)
        assert "✅" in result

    def test_board_only_inserted_before_input(self, monkeypatch, pcb_file, tmp_path):
        captured = {}

        async def fake(args, timeout=60.0):
            captured["args"] = args
            return _FakeResult()

        monkeypatch.setattr(visualization, "run_kicad_cli", fake)
        out = tmp_path / "b.step"
        out.write_bytes(b"ISO-10303-21;")
        asyncio.run(export_pcb_3d(str(pcb_file), output_path=str(out), board_only=True))
        assert captured["args"][-2] == "--board-only"
        assert captured["args"][-1] == str(pcb_file)


class TestExportSchematicSvg:
    def test_args_include_input_file(self, monkeypatch, sch_file, tmp_path):
        captured = {}

        async def fake(args, timeout=60.0):
            captured["args"] = args
            (tmp_path / "page.svg").write_text("<svg/>", encoding="utf-8")
            return _FakeResult()

        monkeypatch.setattr(visualization, "run_kicad_cli", fake)
        result = asyncio.run(export_schematic_svg(str(sch_file), output_dir=str(tmp_path)))
        assert captured["args"][0:4] == ["sch", "export", "svg", "--output"]
        assert captured["args"][-1] == str(sch_file)
        assert "✅" in result

    def test_missing_schematic(self, tmp_path):
        result = asyncio.run(
            export_schematic_svg(str(tmp_path / "nope.kicad_sch"))
        )
        assert "not found" in result
