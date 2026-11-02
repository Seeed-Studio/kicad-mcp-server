"""S-expression helpers for KiCad files.

The rules come from the KiCad source: ``OUTPUTFORMATTER::Quotes`` in
``common/richio.cpp`` writes a string, and ``DSNLEXER`` in
``common/dsnlexer.cpp`` reads it.
"""

import re

# KiCad escapes these characters in a quoted string. The lexer reads the file
# line by line, thus a literal line break in a string stops the load with
# "Unterminated delimited string".
_ESCAPES = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r"})

# Regex pattern of one quoted string token. A backslash escapes the character
# that follows it, thus '\"' does not end the token.
STRING = r'"(?:[^"\\]|\\.)*"'

# The escape sequences of the lexer: a hex value with 1 or 2 digits, an octal
# value with 1 to 3 digits, or one character.
_ESCAPE_RE = re.compile(rb"\\(x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|.)", re.DOTALL)

_SIMPLE_ESCAPES = {
    b'"': b'"',
    b"\\": b"\\",
    b"a": b"\x07",
    b"b": b"\x08",
    b"f": b"\x0c",
    b"n": b"\n",
    b"r": b"\r",
    b"t": b"\t",
    b"v": b"\x0b",
    b"x": b"x",
}


def quote(value: str) -> str:
    """Return ``value`` as a quoted S-expression string, as KiCad writes it."""
    return '"' + value.translate(_ESCAPES) + '"'


def _unescape(match: re.Match[bytes]) -> bytes:
    seq = match.group(1)
    if seq in _SIMPLE_ESCAPES:
        return _SIMPLE_ESCAPES[seq]
    if seq.startswith(b"x"):
        return bytes([int(seq[1:], 16)])
    if seq[0] in b"01234567":
        # The lexer keeps the low byte of a value larger than 0o377.
        return bytes([int(seq, 8) & 0xFF])
    # The lexer reads an unknown escape as a backslash and the character.
    return b"\\" + seq


def unquote(token: str) -> str:
    """Return the value of a quoted string token that matches ``STRING``.

    The escapes give bytes, as in the lexer. The result is UTF-8. A hex or octal
    escape can give a byte that is not valid UTF-8. That byte becomes a lone
    surrogate (``surrogateescape``), thus the value stays different from each
    valid string and the read does not stop.
    """
    raw = _ESCAPE_RE.sub(_unescape, token[1:-1].encode("utf-8"))
    return raw.decode("utf-8", errors="surrogateescape")
