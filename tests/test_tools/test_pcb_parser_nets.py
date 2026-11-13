"""Text PCB parser: tracks/vias in KiCad 9 (net codes) and KiCad 10 (net names)."""

import pytest

from kicad_mcp_server.parsers.pcb_parser import PCBParser

KICAD9 = """(kicad_pcb
\t(version 20241229)
\t(generator "pcbnew")
\t(net 0 "")
\t(net 1 "GND")
\t(net 2 "Net-(D1-K)")
\t(segment
\t\t(start 10 20)
\t\t(end 13 24)
\t\t(width 0.25)
\t\t(layer "F.Cu")
\t\t(net 1)
\t\t(uuid "00000000-0000-0000-0000-000000000001")
\t)
\t(segment
\t\t(start -5.5 -2)
\t\t(end -5.5 1)
\t\t(width 0.4)
\t\t(layer "B.Cu")
\t\t(net 2)
\t\t(uuid "00000000-0000-0000-0000-000000000002")
\t)
\t(arc
\t\t(start 0 -1)
\t\t(mid 1 0)
\t\t(end 0 1)
\t\t(width 0.2)
\t\t(layer "F.Cu")
\t\t(net 1)
\t\t(uuid "00000000-0000-0000-0000-000000000003")
\t)
\t(via
\t\t(at -3 7)
\t\t(size 0.6)
\t\t(drill 0.3)
\t\t(layers "F.Cu" "B.Cu")
\t\t(net 1)
\t\t(uuid "00000000-0000-0000-0000-000000000004")
\t)
)
"""

# Same board as KiCad 10 writes it: no net table, net names inline.
KICAD10 = (
    KICAD9.replace("(version 20241229)", "(version 20260206)")
    .replace('\t(net 0 "")\n\t(net 1 "GND")\n\t(net 2 "Net-(D1-K)")\n', "")
    .replace("(net 1)", '(net "GND")')
    .replace("(net 2)", '(net "Net-(D1-K)")')
)


@pytest.fixture(params=[("kicad9", KICAD9), ("kicad10", KICAD10)], ids=lambda p: p[0])
def board(request, tmp_path):
    path = tmp_path / "board.kicad_pcb"
    path.write_text(request.param[1])
    return PCBParser(str(path))._parse_file()


def test_all_tracks_found(board):
    assert len(board["tracks"]) == 3
    assert {t["type"] for t in board["tracks"]} == {"segment", "arc"}


def test_track_nets_resolved(board):
    nets = [t["net"] for t in board["tracks"]]
    assert nets == ["GND", "Net-(D1-K)", "GND"]


def test_negative_coordinates_kept(board):
    seg = board["tracks"][1]
    assert seg["start"] == {"x": -5.5, "y": -2.0}
    assert seg["length"] == pytest.approx(3.0)


def test_arc_length_is_half_circle(board):
    arc = next(t for t in board["tracks"] if t["type"] == "arc")
    assert arc["length"] == pytest.approx(3.14159265, rel=1e-6)


def test_via_has_net_and_layers(board):
    (via,) = board["vias"]
    assert via["net"] == "GND"
    assert via["at"] == {"x": -3.0, "y": 7.0}
    assert (via["top_layer"], via["bottom_layer"]) == ("F.Cu", "B.Cu")
