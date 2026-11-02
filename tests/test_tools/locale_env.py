"""Run Python code in a process whose locale encoding is not UTF-8.

The tests use it to show the character set problems of a system that does
not use UTF-8, also when the machine of the test uses UTF-8:

- On Windows the locale encoding is the code page of the region. A process
  cannot change it. The CI runner has cp1252.
- On Linux the process gets a locale that is not UTF-8. The CI workflow
  generates zh_CN.GBK, the character set of a Chinese system.

Python turns on its UTF-8 mode in the C locale, thus the C locale cannot
show the problem. The process runs with the UTF-8 mode off or on (``-X
utf8``), as the test asks. The UTF-8 mode is the default from Python 3.15
(PEP 686), thus a server can run in both modes.

When the environment variable KICAD_MCP_TEST_REQUIRE_LOCALE is set (the CI
does it), a missing locale fails the test. Else the test is skipped.
"""

import codecs
import json
import os
import subprocess
import sys

import pytest

LOCALES = ["zh_CN.GBK", "zh_CN.GB18030", "ar_AE.ISO-8859-6", "en_US.ISO-8859-1"]
_PROBE = "import locale; print(locale.getpreferredencoding(False))"


def _base_env() -> dict[str, str]:
    removed = {"PYTHONUTF8", "PYTHONIOENCODING", "LC_ALL", "LC_CTYPE", "LANG"}
    return {name: value for name, value in os.environ.items() if name not in removed}


def non_utf8_env() -> tuple[dict[str, str], str]:
    """Return (environment, locale encoding) of a locale that is not UTF-8."""
    for extra in [{}] + [{"LC_ALL": name} for name in LOCALES]:
        env = {**_base_env(), **extra}
        probe = subprocess.run(
            [sys.executable, "-X", "utf8=0", "-c", _PROBE],
            env=env,
            capture_output=True,
            text=True,
        )
        name = probe.stdout.strip()
        if probe.returncode == 0 and name:
            encoding = codecs.lookup(name).name
            if encoding != "utf-8":
                return env, encoding
    message = f"no locale that is not UTF-8 (tried {', '.join(LOCALES)})"
    if os.environ.get("KICAD_MCP_TEST_REQUIRE_LOCALE"):
        pytest.fail(message)
    pytest.skip(message)


def can_name(text: str, encoding: str, utf8_mode: bool) -> bool:
    """Return True if a file name or an argument can hold the text.

    Windows uses Unicode for file names and arguments. Other systems use the
    bytes of the locale encoding, or UTF-8 in the UTF-8 mode of Python.
    """
    if sys.platform == "win32" or utf8_mode:
        return True
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return False
    return True


def run_python(code: str, env: dict[str, str], utf8_mode: bool, *args) -> object:
    """Run the code with the arguments, and return the JSON that it prints.

    The arguments go to the code as one ASCII JSON value, and the result
    comes back as ASCII JSON, thus the locale cannot change them. The code
    reads ``ARGS`` and calls ``result(value)``.
    """
    prelude = (
        "import json, sys\n"
        "ARGS = json.loads(sys.argv[1])\n"
        "def result(value):\n"
        "    print(json.dumps(value))\n"
    )
    mode = "utf8=1" if utf8_mode else "utf8=0"
    child = subprocess.run(
        [sys.executable, "-X", mode, "-c", prelude + code, json.dumps(list(args))],
        env=env,
        capture_output=True,
        timeout=120,
    )
    assert child.returncode == 0, child.stderr.decode("utf-8", "replace")
    return json.loads(child.stdout)
