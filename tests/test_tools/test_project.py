"""Tests for create_kicad_project (tools/project.py)."""

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from kicad_mcp_server.tools import project
from kicad_mcp_server.tools.project import _set_title_block, create_kicad_project
from kicad_mcp_server.utils import kicad_python
from kicad_mcp_server.utils.kicad_cli import find_kicad_cli
from kicad_mcp_server.utils.kicad_python import find_kicad_python

ROOT_UUID = "e63e39d7-6ac0-4ffd-8aa3-1841a4541b55"


class _FakeResult:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def _kicad_version(monkeypatch):
    async def fake_version():
        return "10.0.6"

    monkeypatch.setattr(project, "get_kicad_version", fake_version)


@pytest.fixture
def template_base(tmp_path, monkeypatch):
    """A fake KiCad template directory shaped like template/Arduino_Mega."""
    base = tmp_path / "templates"
    tpl = base / "Arduino_Mega"
    (tpl / "meta").mkdir(parents=True)
    (tpl / "meta" / "info.html").write_text("<html/>", encoding="utf-8")
    (tpl / "Arduino_MountingHole.pretty").mkdir()
    (tpl / "Arduino_MountingHole.pretty" / "MountingHole_3.2mm.kicad_mod").write_text(
        "(footprint)", encoding="utf-8"
    )
    (tpl / "fp-lib-table").write_text(
        '(fp_lib_table (lib (name "Arduino_MountingHole")'
        '(uri "${KIPRJMOD}/Arduino_MountingHole.pretty")))',
        encoding="utf-8",
    )
    (tpl / "Arduino_Mega.kicad_pcb").write_text("(kicad_pcb (version 20260206))", encoding="utf-8")
    (tpl / "Arduino_Mega.kicad_sch").write_text(
        f'(kicad_sch\n\t(version 20250114)\n\t(uuid "{ROOT_UUID}")\n\t(paper "A4")\n'
        f'\t(symbol (instances (project "Arduino_Mega" (path "/{ROOT_UUID}" (reference "J1")))))\n)\n',
        encoding="utf-8",
    )
    (tpl / "Arduino_Mega.kicad_pro").write_text(
        json.dumps({"meta": {"filename": "Arduino_Mega.kicad_pro"}, "sheets": [[ROOT_UUID, "Root"]]}),
        encoding="utf-8",
    )
    (tpl / "custom.kicad_wks").write_text("(kicad_wks)", encoding="utf-8")
    monkeypatch.setattr(project, "_kicad_template_dirs", lambda: [base])
    return base


class TestSetTitleBlock:
    def test_creates_block_after_paper_when_absent(self):
        content = '(kicad_sch\n\t(uuid "x")\n\t(paper "A4")\n\t(lib_symbols)\n)\n'
        out = _set_title_block(content, "Board", "ACME", "2026-01-02")
        assert re.search(
            r'\(paper "A4"\)\s*\(title_block\s*\(title "Board"\)\s*'
            r'\(date "2026-01-02"\)\s*\(company "ACME"\)\s*\)',
            out,
        )

    def test_replaces_existing_fields(self):
        content = '(paper "A4")\n(title_block\n(title "Old")\n(date "2000-01-01")\n)'
        out = _set_title_block(content, "New", "", "2026-01-02")
        assert '(title "New")' in out and "Old" not in out
        assert '(date "2026-01-02")' in out
        assert "(company" not in out

    def test_escapes_quotes_and_backslashes(self):
        out = _set_title_block('(paper "A4")', 'A "B" \\C', "", "2026-01-02")
        assert '(title "A \\"B\\" \\\\C")' in out
        # Re-applying must find and replace the escaped value, not add another.
        again = _set_title_block(out, "D", "", "2026-01-02")
        assert again.count("(title ") == 1 and '(title "D")' in again


class TestEmptyProject:
    @pytest.fixture
    def fake_kicad(self, monkeypatch):
        """Stub pcbnew and kicad-cli; record their arguments."""
        calls = {}

        async def fake_python(args, timeout=120.0):
            calls["python"] = args
            pcb = Path(args[2])
            pcb.write_text("(kicad_pcb (version 20260206))", encoding="utf-8")
            pcb.with_suffix(".kicad_pro").write_text("{}", encoding="utf-8")
            pcb.with_suffix(".kicad_prl").write_text("{}", encoding="utf-8")
            return _FakeResult()

        async def fake_cli(args, timeout=60.0):
            calls["cli"] = args
            return _FakeResult()

        monkeypatch.setattr(project, "find_kicad_python", lambda: sys.executable)
        monkeypatch.setattr(project, "run_kicad_python", fake_python)
        monkeypatch.setattr(project, "run_kicad_cli", fake_cli)
        return calls

    def test_is_the_default_and_uses_kicad_tooling(self, tmp_path, fake_kicad):
        out_dir = tmp_path / "proj"
        result = asyncio.run(create_kicad_project(str(out_dir), "blank", "My Board", "ACME"))

        py_args = fake_kicad["python"]
        assert py_args[0] == "-c" and "pcbnew.NewBoard" in py_args[1]
        assert py_args[2:5] == [str(out_dir / "blank.kicad_pcb"), "My Board", "ACME"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", py_args[5])
        assert fake_kicad["cli"] == ["sch", "upgrade", str(out_dir / "blank.kicad_sch")]

        sch = (out_dir / "blank.kicad_sch").read_text(encoding="utf-8")
        assert sch.startswith("(kicad_sch")
        assert '(title "My Board")' in sch and '(company "ACME")' in sch
        assert re.search(r'\(uuid "[0-9a-f-]{36}"\)', sch)
        assert "(symbol" not in sch

        assert "KiCad 10.0.6 Project Created" in result
        assert "9.0+" not in result
        assert "**Template:** empty" in result
        for name in ("blank.kicad_pro", "blank.kicad_prl", "blank.kicad_sch", "blank.kicad_pcb"):
            assert f"- {name}" in result
        assert "Warnings" not in result

    def test_title_defaults_to_project_name(self, tmp_path, fake_kicad):
        asyncio.run(create_kicad_project(str(tmp_path), "blank"))
        assert fake_kicad["python"][3] == "blank"
        assert fake_kicad["python"][4] == ""
        sch = (tmp_path / "blank.kicad_sch").read_text(encoding="utf-8")
        assert '(title "blank")' in sch and "(company" not in sch

    def test_upgrade_failure_is_a_warning(self, tmp_path, fake_kicad, monkeypatch):
        async def failing_cli(args, timeout=60.0):
            return _FakeResult(returncode=1, stderr=b"boom")

        monkeypatch.setattr(project, "run_kicad_cli", failing_cli)
        result = asyncio.run(create_kicad_project(str(tmp_path), "blank"))
        assert "Project Created" in result
        assert "Warnings" in result and "boom" in result
        assert (tmp_path / "blank.kicad_sch").exists()

    def test_pcbnew_failure_is_reported(self, tmp_path, fake_kicad, monkeypatch):
        async def failing_python(args, timeout=120.0):
            return _FakeResult(returncode=1, stderr=b"ImportError: pcbnew")

        monkeypatch.setattr(project, "run_kicad_python", failing_python)
        result = asyncio.run(create_kicad_project(str(tmp_path), "blank"))
        assert result.startswith("❌") and "ImportError: pcbnew" in result
        assert not (tmp_path / "blank.kicad_sch").exists()

    def test_missing_kicad_python(self, tmp_path, monkeypatch):
        monkeypatch.setattr(project, "find_kicad_python", lambda: None)
        out_dir = tmp_path / "proj"
        result = asyncio.run(create_kicad_project(str(out_dir), "blank"))
        assert "pcbnew" in result and "KICAD_PYTHON" in result
        assert not out_dir.exists()


class TestTemplateProject:
    def test_copies_directories_and_renames_project_files(self, tmp_path, template_base):
        out_dir = tmp_path / "proj"
        result = asyncio.run(
            create_kicad_project(str(out_dir), "shield", "Shield", template="Arduino_Mega")
        )

        assert sorted(p.name for p in out_dir.iterdir()) == [
            "Arduino_MountingHole.pretty",
            "custom.kicad_wks",
            "fp-lib-table",
            "shield.kicad_pcb",
            "shield.kicad_pro",
            "shield.kicad_sch",
        ]
        # The footprint library the fp-lib-table points at must come along.
        assert (out_dir / "Arduino_MountingHole.pretty" / "MountingHole_3.2mm.kicad_mod").is_file()
        assert "KiCad 10.0.6 Project Created" in result
        assert "9.0+" not in result
        assert "Arduino_Mega" in result and "- Arduino_MountingHole.pretty/" in result

    def test_root_uuid_is_replaced_consistently(self, tmp_path, template_base):
        asyncio.run(create_kicad_project(str(tmp_path), "shield", template="Arduino_Mega"))

        sch = (tmp_path / "shield.kicad_sch").read_text(encoding="utf-8")
        new_uuid = re.search(r'\(uuid "([^"]*)"\)', sch).group(1)
        assert new_uuid != ROOT_UUID and ROOT_UUID not in sch
        assert f'(path "/{new_uuid}"' in sch
        assert '(title "shield")' in sch

        pro = json.loads((tmp_path / "shield.kicad_pro").read_text(encoding="utf-8"))
        assert pro["meta"]["filename"] == "shield.kicad_pro"
        assert pro["sheets"] == [[new_uuid, "Root"]]

    def test_template_by_path(self, tmp_path, template_base, monkeypatch):
        monkeypatch.setattr(project, "_kicad_template_dirs", lambda: [])
        out_dir = tmp_path / "proj"
        asyncio.run(
            create_kicad_project(
                str(out_dir), "shield", template=str(template_base / "Arduino_Mega")
            )
        )
        assert (out_dir / "shield.kicad_pro").is_file()

    def test_unknown_template_lists_available(self, tmp_path, template_base):
        out_dir = tmp_path / "proj"
        result = asyncio.run(create_kicad_project(str(out_dir), "x", template="Nope"))
        assert "'Nope' not found" in result and "Arduino_Mega" in result
        assert not out_dir.exists()

    def test_refuses_to_overwrite_existing_project(self, tmp_path, template_base):
        existing = tmp_path / "shield.kicad_sch"
        existing.write_text("mine", encoding="utf-8")
        result = asyncio.run(create_kicad_project(str(tmp_path), "shield", template="Arduino_Mega"))
        assert "already exists" in result
        assert existing.read_text(encoding="utf-8") == "mine"
        assert not (tmp_path / "shield.kicad_pcb").exists()


class TestFindKicadPython:
    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.setattr(kicad_python, "_cached_python", None)
        monkeypatch.delenv("KICAD_PYTHON", raising=False)
        monkeypatch.setattr(kicad_python.importlib.util, "find_spec", lambda name: None)

    def test_env_override_wins(self, monkeypatch, tmp_path):
        fake = tmp_path / "python.exe"
        fake.write_bytes(b"")
        monkeypatch.setenv("KICAD_PYTHON", str(fake))
        monkeypatch.setattr(kicad_python, "find_kicad_install", lambda: None)
        assert find_kicad_python() == str(fake)

    def test_current_interpreter_when_pcbnew_importable(self, monkeypatch):
        monkeypatch.setattr(kicad_python.importlib.util, "find_spec", lambda name: object())
        assert find_kicad_python() == sys.executable

    def test_windows_bundled_python(self, monkeypatch, tmp_path):
        exe = tmp_path / "bin" / "python.exe"
        exe.parent.mkdir()
        exe.write_bytes(b"")
        monkeypatch.setattr(kicad_python, "find_kicad_install", lambda: (tmp_path, "10.0"))
        assert find_kicad_python() == str(exe)

    def test_macos_bundled_python(self, monkeypatch, tmp_path):
        contents = tmp_path / "KiCad.app" / "Contents"
        shared_support = contents / "SharedSupport"
        shared_support.mkdir(parents=True)
        exe = contents / "Frameworks" / "Python.framework" / "Versions" / "Current" / "bin" / "python3"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        monkeypatch.setattr(kicad_python, "find_kicad_install", lambda: (shared_support, "macos"))
        assert find_kicad_python() == str(exe)

    def test_nothing_found(self, monkeypatch, tmp_path):
        monkeypatch.setattr(kicad_python, "find_kicad_install", lambda: None)
        assert find_kicad_python() is None


def _kicad_available() -> bool:
    python = find_kicad_python()
    if python is None or find_kicad_cli() is None:
        return False
    probe = subprocess.run([python, "-c", "import pcbnew"], capture_output=True, timeout=60)
    return probe.returncode == 0


@pytest.mark.skipif(not _kicad_available(), reason="KiCad with pcbnew not installed")
class TestWithRealKicad:
    @pytest.fixture(autouse=True)
    def _kicad_version(self):
        """Use the real version lookup (overrides the module-level stub)."""

    def test_empty_project_is_native_and_passes_erc(self, tmp_path):
        from kicad_mcp_server.utils.kicad_cli import run_kicad_cli_sync

        result = asyncio.run(create_kicad_project(str(tmp_path), "blank", company="ACME"))
        assert "Project Created" in result and "Warnings" not in result

        pcb = (tmp_path / "blank.kicad_pcb").read_text(encoding="utf-8")
        sch = (tmp_path / "blank.kicad_sch").read_text(encoding="utf-8")
        assert "(footprint " not in pcb
        assert '(company "ACME")' in pcb and '(company "ACME")' in sch
        assert (tmp_path / "blank.kicad_pro").is_file()

        # Both files carry the installed KiCad's own generator version.
        pcb_gen = re.search(r'\(generator_version "([^"]*)"\)', pcb).group(1)
        sch_gen = re.search(r'\(generator_version "([^"]*)"\)', sch).group(1)
        assert pcb_gen == sch_gen

        report = tmp_path / "erc.rpt"
        erc = run_kicad_cli_sync(
            ["sch", "erc", "-o", str(report), str(tmp_path / "blank.kicad_sch")], timeout=120
        )
        assert erc.returncode == 0
        assert "ERC messages: 0" in report.read_text(encoding="utf-8")

    def test_arduino_mega_template_includes_footprint_library(self, tmp_path):
        if "Arduino_Mega" not in project._list_kicad_templates():
            pytest.skip("Arduino_Mega template not installed")

        asyncio.run(create_kicad_project(str(tmp_path), "shield", template="Arduino_Mega"))

        fp_lib_table = (tmp_path / "fp-lib-table").read_text(encoding="utf-8")
        for lib_dir in re.findall(r"\$\{KIPRJMOD\}/([^)\"]+)", fp_lib_table):
            assert (tmp_path / lib_dir).is_dir(), lib_dir
        assert not (tmp_path / "meta").exists()
