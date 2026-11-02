"""Tests for the kicad-cli wrapper (utils/kicad_cli)."""

import asyncio
import locale
import sys
from pathlib import Path

import pytest

from kicad_mcp_server.utils import kicad_cli
from kicad_mcp_server.utils.kicad_cli import (
    decode_output,
    find_kicad_cli,
    kicad_cli_env,
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


class TestCharacterSet:
    @pytest.fixture(autouse=True)
    def _clear_caches(self):
        # The tests replace child_ctype, thus keep the cache_clear of the
        # function of the module.
        caches = [kicad_cli.child_ctype.cache_clear, kicad_cli._locale_exists.cache_clear]
        for cache_clear in caches:
            cache_clear()
        yield
        for cache_clear in caches:
            cache_clear()

    def test_no_change_on_windows(self, monkeypatch):
        # kicad-cli uses the UTF-8 code page of its manifest and Unicode
        # arguments on Windows.
        monkeypatch.setattr(kicad_cli.sys, "platform", "win32")
        assert kicad_cli_env() is None
        assert kicad_cli_env(english=True) is None
        assert decode_output("电源 لوحة".encode()) == "电源 لوحة"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_english_removes_the_locale_of_the_user(self, monkeypatch):
        # "C" exists on each system. LC_NUMERIC of the user would give a
        # decimal comma.
        monkeypatch.setattr(kicad_cli, "child_ctype", lambda: "zh_CN.UTF-8")
        monkeypatch.setenv("LC_ALL", "cs_CZ.UTF-8")
        monkeypatch.setenv("LC_NUMERIC", "de_DE.UTF-8")
        monkeypatch.setenv("LC_MESSAGES", "zh_CN.UTF-8")
        monkeypatch.setenv("LANGUAGE", "zh_CN")
        env = kicad_cli_env(english=True)
        assert env["LANG"] == "C" and env["LANGUAGE"] == ""
        assert env["LC_CTYPE"] == "zh_CN.UTF-8"
        assert not [name for name in env if name.startswith("LC_") and name != "LC_CTYPE"]

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_same_character_set_keeps_the_environment(self, monkeypatch):
        monkeypatch.setattr(kicad_cli, "child_ctype", lambda: locale.setlocale(locale.LC_CTYPE))
        assert kicad_cli_env() is None

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_other_character_set_replaces_lc_all(self, monkeypatch):
        # LC_ALL overrides LC_CTYPE. Its value stays for the other categories.
        monkeypatch.setattr(kicad_cli, "child_ctype", lambda: "C.UTF-8")
        monkeypatch.setattr(kicad_cli.locale, "setlocale", lambda *args: "zh_CN.GBK")
        monkeypatch.setenv("LC_ALL", "zh_CN.GBK")
        env = kicad_cli_env()
        assert "LC_ALL" not in env
        assert env["LANG"] == "zh_CN.GBK" and env["LC_CTYPE"] == "C.UTF-8"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_ctype_in_utf8_mode_with_a_locale_that_is_not_utf8(self, monkeypatch):
        # This process writes the paths as UTF-8, thus kicad-cli needs a
        # UTF-8 locale that exists.
        monkeypatch.setattr(kicad_cli, "fs_encoding", lambda: "utf-8")
        monkeypatch.setattr(kicad_cli.locale, "setlocale", lambda *args: "zh_CN.GBK")
        monkeypatch.setattr(kicad_cli.locale, "nl_langinfo", lambda item: "GBK")
        monkeypatch.setattr(kicad_cli, "_locale_exists", lambda name: name == "C.utf8")
        assert kicad_cli.child_ctype() == "C.utf8"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_no_utf8_locale(self, monkeypatch):
        monkeypatch.setattr(kicad_cli, "fs_encoding", lambda: "utf-8")
        monkeypatch.setattr(kicad_cli.locale, "setlocale", lambda *args: "zh_CN.GBK")
        monkeypatch.setattr(kicad_cli.locale, "nl_langinfo", lambda item: "GBK")
        monkeypatch.setattr(kicad_cli, "_locale_exists", lambda name: False)
        assert kicad_cli.child_ctype() is None

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_no_utf8_locale_refuses_a_path_that_is_not_ascii(self, monkeypatch):
        # The path bytes would be UTF-8, but kicad-cli would read them as GBK.
        monkeypatch.setattr(kicad_cli, "find_kicad_cli", lambda: sys.executable)
        monkeypatch.setattr(kicad_cli, "child_ctype", lambda: None)
        with pytest.raises(RuntimeError, match="no UTF-8 locale"):
            run_kicad_cli_sync(["-c", "pass", "电源板.kicad_sch"], timeout=30)
        # ASCII is the same in the two character sets.
        assert run_kicad_cli_sync(["-c", "pass", "board.kicad_sch"], timeout=30).returncode == 0

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_locale_probe_that_cannot_run(self, monkeypatch):
        monkeypatch.setattr(kicad_cli.sys, "executable", "")
        assert kicad_cli._locale_exists("C.UTF-8") is False
        monkeypatch.setattr(kicad_cli.sys, "executable", "/nonexistent/python")
        assert kicad_cli._locale_exists("en_US.UTF-8") is False

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_ctype_is_kept_when_the_character_sets_agree(self, monkeypatch):
        monkeypatch.setattr(kicad_cli, "fs_encoding", lambda: "gbk")
        monkeypatch.setattr(kicad_cli.locale, "setlocale", lambda *args: "zh_CN.GBK")
        monkeypatch.setattr(kicad_cli.locale, "nl_langinfo", lambda item: "GBK")
        assert kicad_cli.child_ctype() == "zh_CN.GBK"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX locales")
    def test_output_uses_the_encoding_of_the_paths(self, monkeypatch):
        monkeypatch.setattr(kicad_cli, "fs_encoding", lambda: "gbk")
        assert decode_output("电源".encode("gbk")) == "电源"

    def test_no_output(self):
        assert decode_output(None) == ""
        assert decode_output(b"") == ""
