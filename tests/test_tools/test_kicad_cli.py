"""Tests for the kicad-cli wrapper (utils/kicad_cli)."""

import asyncio
import sys
from pathlib import Path

import pytest

from kicad_mcp_server.utils import kicad_cli
from kicad_mcp_server.utils.kicad_cli import (
    find_kicad_cli,
    run_kicad_cli,
    run_kicad_cli_sync,
)


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    """Start every test with a clean executable cache and no override."""
    monkeypatch.setattr(kicad_cli, "_cached_exe", None)
    monkeypatch.delenv("KICAD_CLI", raising=False)
    yield
    # monkeypatch restores _cached_exe's original value (None) on teardown.


class TestFindKicadCli:
    def test_env_override_wins(self, monkeypatch, tmp_path):
        fake = tmp_path / "kicad-cli.exe"
        fake.write_bytes(b"")
        monkeypatch.setenv("KICAD_CLI", str(fake))
        monkeypatch.setattr(kicad_cli.shutil, "which", lambda name: None)
        monkeypatch.setattr(kicad_cli, "find_kicad_install", lambda: None)
        assert find_kicad_cli() == str(fake)

    def test_env_override_ignored_when_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KICAD_CLI", str(tmp_path / "does-not-exist"))
        monkeypatch.setattr(kicad_cli.shutil, "which", lambda name: None)
        monkeypatch.setattr(kicad_cli, "find_kicad_install", lambda: None)
        assert find_kicad_cli() is None

    def test_path_lookup(self, monkeypatch, tmp_path):
        on_path = tmp_path / "kicad-cli"
        monkeypatch.setattr(
            kicad_cli.shutil, "which", lambda name: str(on_path) if name == "kicad-cli" else None
        )
        monkeypatch.setattr(kicad_cli, "find_kicad_install", lambda: None)
        assert find_kicad_cli() == str(on_path)

    def test_install_dir_fallback_windows_layout(self, monkeypatch, tmp_path):
        """bin/kicad-cli(.exe) next to the detected share/kicad directory."""
        # The wrapper looks for kicad-cli.exe only on Windows; the bare name
        # elsewhere. Mirror that so the test exercises the branch its platform
        # actually uses (the CI matrix covers both).
        exe_name = "kicad-cli.exe" if sys.platform == "win32" else "kicad-cli"
        exe = tmp_path / "bin" / exe_name
        exe.parent.mkdir()
        exe.write_bytes(b"")
        monkeypatch.setattr(kicad_cli.shutil, "which", lambda name: None)
        monkeypatch.setattr(kicad_cli, "find_kicad_install", lambda: (tmp_path, "10.0"))
        assert find_kicad_cli() == str(exe)

    def test_install_dir_fallback_macos_layout(self, monkeypatch, tmp_path):
        """macOS: install_path is .../SharedSupport, binary in sibling MacOS/."""
        contents = tmp_path / "KiCad.app" / "Contents"
        shared_support = contents / "SharedSupport"
        shared_support.mkdir(parents=True)
        exe = contents / "MacOS" / "kicad-cli"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        monkeypatch.setattr(kicad_cli.shutil, "which", lambda name: None)
        monkeypatch.setattr(kicad_cli, "find_kicad_install", lambda: (shared_support, "macos"))
        assert find_kicad_cli() == str(exe)

    def test_install_dir_without_binary_not_found(self, monkeypatch, tmp_path):
        monkeypatch.setattr(kicad_cli.shutil, "which", lambda name: None)
        monkeypatch.setattr(kicad_cli, "find_kicad_install", lambda: (tmp_path, "10.0"))
        assert find_kicad_cli() is None

    def test_nothing_found_returns_none(self, monkeypatch):
        monkeypatch.setattr(kicad_cli.shutil, "which", lambda name: None)
        monkeypatch.setattr(kicad_cli, "find_kicad_install", lambda: None)
        assert find_kicad_cli() is None


class TestRunKicadCli:
    def test_sync_raises_when_not_found(self, monkeypatch):
        monkeypatch.setattr(kicad_cli, "find_kicad_cli", lambda: None)
        with pytest.raises(FileNotFoundError):
            run_kicad_cli_sync(["version"])

    def test_async_raises_when_not_found(self, monkeypatch):
        monkeypatch.setattr(kicad_cli, "find_kicad_cli", lambda: None)
        with pytest.raises(FileNotFoundError):
            asyncio.run(run_kicad_cli(["version"]))

    def test_runs_executable_off_event_loop(self, monkeypatch):
        """End-to-end subprocess execution using the current interpreter."""
        monkeypatch.setattr(kicad_cli, "find_kicad_cli", lambda: sys.executable)
        code = "import sys; sys.stdout.write('wrapper-ok')"
        result = asyncio.run(run_kicad_cli(["-c", code], timeout=30))
        assert result.returncode == 0
        assert b"wrapper-ok" in result.stdout

    def test_nonzero_exit_is_surfaced(self, monkeypatch):
        monkeypatch.setattr(kicad_cli, "find_kicad_cli", lambda: sys.executable)
        result = asyncio.run(run_kicad_cli(["-c", "import sys; sys.exit(3)"], timeout=30))
        assert result.returncode == 3

    @pytest.mark.skipif(
        not Path("C:/Program Files/KiCad").is_dir(), reason="KiCad not installed"
    )
    def test_real_kicad_cli_version(self):
        """On this machine the wrapper must find and run the real kicad-cli."""
        result = run_kicad_cli_sync(["version"], timeout=30)
        assert result.returncode == 0
        assert result.stdout.decode(errors="replace").strip()
