"""Tests for netlist cache path collision avoidance."""


from kicad_mcp_server.tools.netlist import netlist_cache_path


class TestNetlistCachePath:
    def test_same_stem_different_projects_do_not_collide(self, tmp_path):
        a = tmp_path / "projA" / "main.kicad_sch"
        b = tmp_path / "projB" / "main.kicad_sch"
        assert netlist_cache_path(a) != netlist_cache_path(b)

    def test_is_deterministic(self, tmp_path):
        sch = tmp_path / "main.kicad_sch"
        assert netlist_cache_path(sch) == netlist_cache_path(sch)

    def test_stays_in_temp_dir_with_xml_suffix(self, tmp_path):
        path = netlist_cache_path(tmp_path / "main.kicad_sch")
        assert path.suffix == ".xml"
        assert path.parent == netlist_cache_path(tmp_path / "other.kicad_sch").parent

    def test_stem_survives_in_name_for_debuggability(self, tmp_path):
        name = netlist_cache_path(tmp_path / "main.kicad_sch").name
        assert name.startswith("main_")
        assert name.endswith(".xml")
        # digest suffix is 8 hex chars
        digest = name[len("main_") : -len(".xml")]
        assert len(digest) == 8
        int(digest, 16)
