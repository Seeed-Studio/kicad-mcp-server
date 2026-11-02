"""Tests for the pcbnew parser of KiCad boards (parsers/pcb_parser_kicad.py)."""

import math

import pytest

from kicad_mcp_server.parsers.pcb_parser_kicad import PCBParserKiCad

pcbnew = pytest.importorskip("pcbnew", reason="KiCad pcbnew is not installed")


@pytest.fixture
def board(tmp_path):
    """A board with a track, an arc and a via, made with pcbnew."""
    mm = pcbnew.FromMM
    board = pcbnew.BOARD()
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(0, 0))
    track.SetEnd(pcbnew.VECTOR2I(mm(3), mm(4)))
    track.SetWidth(mm(0.2))
    track.SetLayer(pcbnew.F_Cu)
    board.Add(track)
    arc = pcbnew.PCB_ARC(board)
    arc.SetStart(pcbnew.VECTOR2I(mm(1), 0))
    arc.SetMid(pcbnew.VECTOR2I(mm(math.sqrt(0.5)), mm(math.sqrt(0.5))))
    arc.SetEnd(pcbnew.VECTOR2I(0, mm(1)))
    arc.SetWidth(mm(0.2))
    arc.SetLayer(pcbnew.F_Cu)
    board.Add(arc)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(mm(5), mm(5)))
    via.SetWidth(mm(0.6))
    via.SetDrill(mm(0.3))
    board.Add(via)
    path = tmp_path / "board.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    return path


def test_tracks_and_vias(board):
    # KiCad 10.0.6 and earlier with SWIG 4.4 and later: BOARD.GetTracks()
    # fails with "'SwigPyIterator' object has no attribute 'next'".
    parser = PCBParserKiCad(str(board))
    tracks = parser.get_tracks()
    assert sorted(round(track.length, 3) for track in tracks) == [
        round(math.pi / 2, 3),
        5.0,
    ]
    (via,) = parser.get_vias()
    assert via.position == (5.0, 5.0)
    assert via.drill == pytest.approx(0.3)


def test_counts_of_the_board_info(board):
    info = PCBParserKiCad(str(board)).get_board_info()
    assert (info["tracks_count"], info["vias_count"]) == (2, 1)
