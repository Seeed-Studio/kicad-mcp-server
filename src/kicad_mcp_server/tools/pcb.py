"""PCB analysis tools for KiCad MCP Server."""

from __future__ import annotations

from ..server import mcp


def _get_parser(file_path: str):
    """Try pcbnew parser first, fall back to text parser."""
    try:
        from ..parsers.pcb_parser_kicad import PCBParserKiCad
        return PCBParserKiCad(file_path)
    except (ImportError, Exception):
        from ..parsers.pcb_parser import PCBParser
        return PCBParser(file_path)


def _is_pcbnew(parser) -> bool:
    """Check if parser is the pcbnew-based one."""
    from ..parsers.pcb_parser_kicad import PCBParserKiCad
    return isinstance(parser, PCBParserKiCad)


@mcp.tool()
async def list_pcb_footprints(
    file_path: str,
    filter_layer: str | None = None,
) -> str:
    """List all footprints in a KiCad PCB file.

    Args:
        file_path: Path to .kicad_pcb file
        filter_layer: Optional filter by layer (e.g., 'F.Cu', 'B.Cu')

    Returns:
        Formatted list of footprints
    """
    try:
        parser = _get_parser(file_path)

        if _is_pcbnew(parser):
            footprints = parser.get_footprints()
            if filter_layer:
                footprints = [f for f in footprints if f.layer == filter_layer]

            if not footprints:
                return "No footprints found."

            lines = [
                f"# Footprints in {file_path}",
                f"Total: {len(footprints)} footprint(s)",
                "",
                "| Reference | Value | Library | Layer | Position | Rotation | Pads |",
                "|-----------|-------|---------|-------|----------|----------|------|",
            ]
            for fp in footprints:
                pos_str = f"({fp.position[0]:.2f}, {fp.position[1]:.2f})"
                lines.append(
                    f"| {fp.reference} | {fp.value} | {fp.library} | {fp.layer} | {pos_str} | {fp.rotation:.1f}° | {fp.pads_count} |"
                )
            return "\n".join(lines)
        else:
            footprints = parser.get_footprints()
            if filter_layer:
                footprints = [f for f in footprints if f.layer == filter_layer]

            if not footprints:
                return "No footprints found."

            lines = [
                f"# Footprints in {file_path}",
                f"Total: {len(footprints)} footprint(s)",
                "",
                "| Reference | Value | Footprint | Layer | Position | Rotation | Pads |",
                "|-----------|-------|-----------|-------|----------|----------|------|",
            ]
            for fp in footprints:
                fp_name = fp.footprint_id.split(":")[-1] if ":" in fp.footprint_id else fp.footprint_id
                pos_str = f"({fp.position[0]:.2f}, {fp.position[1]:.2f})"
                lines.append(
                    f"| {fp.reference} | {fp.value} | {fp_name} | {fp.layer} | {pos_str} | {fp.rotation:.1f}° | {fp.pad_count} |"
                )
            return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


@mcp.tool()
async def get_pcb_statistics(file_path: str) -> str:
    """Get statistics about a KiCad PCB design.

    Args:
        file_path: Path to .kicad_pcb file

    Returns:
        PCB statistics and metrics
    """
    try:
        parser = _get_parser(file_path)

        if _is_pcbnew(parser):
            info = parser.get_board_info()
            rules = parser.get_design_rules()

            lines = [
                f"# PCB Statistics: {file_path}",
                "",
                "## Board Information",
                f"**Dimensions:** {info['board_width_mm']:.2f} x {info['board_height_mm']:.2f} mm",
                f"**Copper Layers:** {rules['copper_layers']}",
                f"**Board Thickness:** {rules['board_thickness_mm']:.3f} mm",
                "",
                "## Elements",
                f"**Footprints:** {info['footprints_count']}",
                f"**Track Segments:** {info['tracks_count']}",
                f"**Vias:** {info['vias_count']}",
                f"**Copper Zones:** {info['zones_count']}",
                f"**Nets:** {info['nets_count']}",
                "",
                "## Design Rules",
                f"**Smallest Clearance:** {rules['smallest_clearance_mm']:.4f} mm",
                f"**Default Track Width:** {rules['current_track_width_mm']:.4f} mm",
                f"**Default Via Size/Drill:** {rules['current_via_size_mm']:.4f} / {rules['current_via_drill_mm']:.4f} mm",
                f"**Diff Pair Width/Gap:** {rules['current_diff_pair_width_mm']:.4f} / {rules['current_diff_pair_gap_mm']:.4f} mm",
            ]
            return "\n".join(lines)
        else:
            stats = parser.get_statistics()
            lines = [
                f"# PCB Statistics: {file_path}",
                "",
                "## Board Information",
                f"**Dimensions:** {stats['board_width']:.2f} x {stats['board_height']:.2f} mm",
                f"**Layers:** {stats['layers']}",
                f"**Thickness:** {stats['thickness']:.2f} mm",
                "",
                "## Elements",
                f"**Footprints:** {stats['total_footprints']}",
                f"**Total Pads:** {stats['total_pads']}",
                f"**Track Segments:** {stats['total_tracks']}",
                f"**Vias:** {stats['total_vias']}",
                f"**Copper Zones:** {stats['total_zones']}",
                "",
                "## Averages",
                f"**Pads per Footprint:** {stats['total_pads'] / max(stats['total_footprints'], 1):.1f}",
            ]
            return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


@mcp.tool()
async def analyze_pcb_nets(file_path: str) -> str:
    """Analyze nets in a KiCad PCB file.

    Provides track width distribution, via distribution, per-net track
    length ranking, layer coverage, and design rule comparison.

    Args:
        file_path: Path to .kicad_pcb file

    Returns:
        Net information and routing analysis from PCB
    """
    try:
        parser = _get_parser(file_path)

        if not _is_pcbnew(parser):
            data = parser._parse_file()
            tracks = data["tracks"]
            vias = data["vias"]
            zones = data["zones"]

            lines = [
                f"# PCB Routing Analysis: {file_path}",
                "",
                "⚠️ pcbnew not available — text-based analysis (limited precision)",
                "",
                "## Overview",
                f"**Track Segments:** {len(tracks)}",
                f"**Vias:** {len(vias)}",
                f"**Copper Zones:** {len(zones)}",
            ]

            # Track width distribution
            width_counts: dict[str, int] = {}
            for t in tracks:
                key = f"{t['width']:.3f}mm"
                width_counts[key] = width_counts.get(key, 0) + 1
            if width_counts:
                lines += [
                    "",
                    "## Track Width Distribution",
                    "| Width | Count |",
                    "|-------|-------|",
                ]
                for w, c in sorted(width_counts.items(), key=lambda x: -x[1]):
                    lines.append(f"| {w} | {c}x |")

            # Via drill distribution
            drill_counts: dict[str, int] = {}
            for v in vias:
                key = f"{v['drill']:.3f}mm"
                drill_counts[key] = drill_counts.get(key, 0) + 1
            if drill_counts:
                lines += [
                    "",
                    "## Via Drill Distribution",
                    f"**Total vias:** {len(vias)}",
                    "",
                    "| Drill Size | Count |",
                    "|------------|-------|",
                ]
                for d, c in sorted(drill_counts.items(), key=lambda x: -x[1]):
                    lines.append(f"| {d} | {c}x |")

            # Per-net track stats
            net_stats: dict[str, dict] = {}
            for t in tracks:
                net = t.get("net", "(unnamed)")
                if net not in net_stats:
                    net_stats[net] = {"total_length": 0.0, "segment_count": 0, "widths": [], "layers": set()}
                s = net_stats[net]
                s["total_length"] += t.get("length", 0)
                s["segment_count"] += 1
                s["widths"].append(t["width"])
                s["layers"].add(t["layer"])

            top_nets = sorted(net_stats.items(), key=lambda x: -x[1]["total_length"])[:20]
            if top_nets:
                lines += [
                    "",
                    "## Top 20 Nets by Track Length",
                    "| Net | Length (mm) | Segments | Widths | Layers |",
                    "|-----|-------------|----------|--------|--------|",
                ]
                for name, s in top_nets:
                    unique_widths = sorted({f"{w:.3f}" for w in s["widths"]})
                    widths_str = ", ".join(unique_widths)
                    layers_str = ", ".join(sorted(s["layers"]))
                    lines.append(
                        f"| {name} | {s['total_length']:.2f} | {s['segment_count']} | {widths_str} | {layers_str} |"
                    )

            return "\n".join(lines)

        net_stats = parser.get_net_track_stats()
        via_stats = parser.get_via_stats()
        rules = parser.get_design_rules()
        zones = parser.get_zones()
        info = parser.get_board_info()

        lines = [
            f"# PCB Routing Analysis: {file_path}",
            "",
            "## Overview",
            f"**Board:** {info['board_width_mm']:.2f} x {info['board_height_mm']:.2f} mm, "
            f"{rules['copper_layers']} copper layers",
            f"**Tracks:** {info['tracks_count']} segments across {len(net_stats)} nets",
            f"**Vias:** {info['vias_count']}",
            f"**Zones:** {len(zones)} copper zones",
        ]

        # Track width distribution
        width_counts: dict[str, int] = {}
        for s in net_stats.values():
            for w in s["widths"]:
                key = f"{w:.3f}mm"
                width_counts[key] = width_counts.get(key, 0) + 1

        if width_counts:
            lines += [
                "",
                "## Track Width Distribution",
                "| Width | Count |",
                "|-------|-------|",
            ]
            for w, c in sorted(width_counts.items(), key=lambda x: -x[1]):
                lines.append(f"| {w} | {c}x |")

        # Via drill distribution
        if via_stats["count"] > 0:
            lines += [
                "",
                "## Via Drill Distribution",
                f"**Total vias:** {via_stats['count']}",
                "",
                "| Drill Size | Count |",
                "|------------|-------|",
            ]
            for drill, count in via_stats["drill_sizes"].items():
                lines.append(f"| {drill} | {count}x |")

            lines += ["", "### Via Layer Spans"]
            for span, count in via_stats["layer_spans"].items():
                lines.append(f"- {span}: {count}x")

        # Layer coverage — count each track on its own layer. Previously this
        # added each net's TOTAL segment count to EVERY layer the net touches,
        # inflating multi-layer net totals by the layer fanout.
        layer_counts: dict[str, int] = {}
        for t in parser.get_tracks():
            layer_counts[t.layer] = layer_counts.get(t.layer, 0) + 1

        if layer_counts:
            lines += [
                "",
                "## Track Segments by Layer",
                "| Layer | Segments |",
                "|-------|----------|",
            ]
            for layer, count in sorted(layer_counts.items(), key=lambda x: -x[1]):
                lines.append(f"| {layer} | {count} |")

        # Top nets by total track length
        top_nets = sorted(net_stats.items(), key=lambda x: -x[1]["total_length"])[:20]
        if top_nets:
            lines += [
                "",
                "## Top 20 Nets by Track Length",
                "| Net | Length (mm) | Segments | Widths | Layers |",
                "|-----|-------------|----------|--------|--------|",
            ]
            for name, s in top_nets:
                unique_widths = sorted({f"{w:.3f}" for w in s["widths"]})
                widths_str = ", ".join(unique_widths)
                layers_str = ", ".join(s["layers"])
                lines.append(
                    f"| {name} | {s['total_length']:.2f} | {s['segment_count']} | {widths_str} | {layers_str} |"
                )

        # Design rule comparison
        if net_stats:
            all_widths = [w for s in net_stats.values() for w in s["widths"]]
            min_width = min(all_widths) if all_widths else 0
            rule_width = rules["current_track_width_mm"]
            lines += [
                "",
                "## Design Rule Comparison",
                f"**Min track width in design:** {min_width:.4f} mm",
                f"**Default track width (design rules):** {rule_width:.4f} mm",
                f"**Smallest clearance:** {rules['smallest_clearance_mm']:.4f} mm",
            ]
            if min_width < rule_width * 0.5:
                lines.append(f"⚠️ Some tracks are significantly narrower than the default ({min_width:.4f} vs {rule_width:.4f} mm)")

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


@mcp.tool()
async def find_tracks_by_net(file_path: str, net_name: str) -> str:
    """Find track segments belonging to a specific net.

    Args:
        file_path: Path to .kicad_pcb file
        net_name: Name of the net to search for

    Returns:
        Track information for the specified net with length analysis
    """
    try:
        parser = _get_parser(file_path)

        if not _is_pcbnew(parser):
            # Text parser fallback — tracks have net names from KiCad 10 format
            data = parser._parse_file()
            matched_tracks = [t for t in data["tracks"] if t.get("net") == net_name]
            matched_vias = [v for v in data["vias"] if v.get("net") == net_name]
            matched_zones = [z for z in data["zones"] if z.get("net_name") == net_name]

            if not matched_tracks and not matched_vias:
                # Try case-insensitive partial match
                all_nets = sorted({
                    t.get("net", "") for t in data["tracks"] if t.get("net")
                })
                suggestions = [n for n in all_nets if net_name.lower() in n.lower()]
                if suggestions:
                    return (
                        f"# Tracks for '{net_name}'\n\n"
                        "Exact match not found. Similar nets:\n"
                        + "\n".join(f"- `{n}` ({sum(1 for t in data['tracks'] if t.get('net') == n)} segments)" for n in suggestions)
                    )
                return f"No tracks found for net '{net_name}'."

            total_length = sum(t.get("length", 0) for t in matched_tracks)
            widths = [t["width"] for t in matched_tracks]
            layers = sorted({t["layer"] for t in matched_tracks})

            lines = [
                f"# Track Analysis: {net_name}",
                "",
                "⚠️ pcbnew not available — text-based analysis (lengths are Euclidean approximations)",
                "",
                f"**Track Segments:** {len(matched_tracks)}",
                f"**Vias:** {len(matched_vias)}",
                f"**Copper Zones:** {len(matched_zones)}",
                f"**Total Track Length:** {total_length:.3f} mm (Euclidean approximation)",
                f"**Layers Used:** {', '.join(layers) if layers else 'N/A'}",
            ]

            if widths:
                unique_widths = sorted({f"{w:.4f}" for w in widths})
                lines.append(f"**Track Widths:** {', '.join(unique_widths)} mm")

            if matched_tracks:
                lines += [
                    "",
                    "## Track Segments",
                    "| # | Start | End | Width | Layer | Length |",
                    "|---|-------|-----|-------|-------|--------|",
                ]
                for i, t in enumerate(matched_tracks[:50], 1):
                    lines.append(
                        f"| {i} | ({t['start']['x']:.2f}, {t['start']['y']:.2f}) | "
                        f"({t['end']['x']:.2f}, {t['end']['y']:.2f}) | {t['width']:.4f} | "
                        f"{t['layer']} | {t.get('length', 0):.3f} |"
                    )

            if matched_vias:
                lines += [
                    "",
                    "## Vias",
                    "| # | Position | Drill | Layers |",
                    "|---|----------|-------|--------|",
                ]
                for i, v in enumerate(matched_vias[:20], 1):
                    span = v.get("top_layer", "") + " -> " + v.get("bottom_layer", "") if v.get("top_layer") else v.get("layers", "")
                    lines.append(
                        f"| {i} | ({v['at']['x']:.2f}, {v['at']['y']:.2f}) | "
                        f"{v['drill']:.4f} | {span} |"
                    )

            if matched_zones:
                lines += [
                    "",
                    "## Copper Zones",
                    "| Net | Layer |",
                    "|-----|-------|",
                ]
                for z in matched_zones:
                    lines.append(f"| {z['net_name']} | {z.get('layer', 'N/A')} |")

            return "\n".join(lines)

        tracks = parser.get_tracks_by_net(net_name)
        vias = parser.get_vias_for_net(net_name)
        zones = parser.get_zones_for_net(net_name)

        if not tracks and not vias:
            # Try case-insensitive partial match
            all_tracks = parser.get_tracks()
            matching = [t for t in all_tracks if net_name.lower() in t.net.lower()]
            if matching:
                net_names = sorted({t.net for t in matching})
                return (
                    f"# Tracks for '{net_name}'\n\n"
                    f"Exact match not found. Did you mean one of these?\n"
                    + "\n".join(f"- `{n}` ({sum(1 for t in matching if t.net == n)} segments)" for n in net_names)
                )
            return f"No tracks or vias found for net '{net_name}'."

        total_length = sum(t.length for t in tracks)
        widths = [t.width for t in tracks]
        layers = sorted({t.layer for t in tracks})

        lines = [
            f"# Track Analysis: {net_name}",
            "",
            f"**Track Segments:** {len(tracks)}",
            f"**Vias:** {len(vias)}",
            f"**Copper Zones:** {len(zones)}",
            f"**Total Track Length:** {total_length:.3f} mm",
            f"**Layers Used:** {', '.join(layers) if layers else 'N/A'}",
        ]

        if widths:
            unique_widths = sorted({f"{w:.4f}" for w in widths})
            lines.append(f"**Track Widths:** {', '.join(unique_widths)} mm")
            if len({round(w, 4) for w in widths}) > 1:
                lines.append("⚠️ Mixed track widths detected — may indicate manual routing or design rule override.")

        # Track segment details
        if tracks:
            lines += [
                "",
                "## Track Segments",
                "| # | Start | End | Width | Layer | Length |",
                "|---|-------|-----|-------|-------|--------|",
            ]
            for i, t in enumerate(tracks[:50], 1):
                lines.append(
                    f"| {i} | ({t.start[0]:.2f}, {t.start[1]:.2f}) | "
                    f"({t.end[0]:.2f}, {t.end[1]:.2f}) | {t.width:.4f} | "
                    f"{t.layer} | {t.length:.3f} |"
                )
            if len(tracks) > 50:
                lines.append(f"| ... | ({len(tracks) - 50} more segments) | | | | |")

        # Via details
        if vias:
            lines += [
                "",
                "## Vias",
                "| # | Position | Size | Drill | Span |",
                "|---|----------|------|-------|------|",
            ]
            for i, v in enumerate(vias[:20], 1):
                lines.append(
                    f"| {i} | ({v.position[0]:.2f}, {v.position[1]:.2f}) | "
                    f"{v.size:.3f} | {v.drill:.3f} | {v.top_layer} -> {v.bottom_layer} |"
                )
            if len(vias) > 20:
                lines.append(f"| ... | ({len(vias) - 20} more vias) | | | |")

        # Zone details
        if zones:
            lines += [
                "",
                "## Copper Zones",
                "| Net | Layer | Filled |",
                "|-----|-------|--------|",
            ]
            for z in zones:
                lines.append(f"| {z.net_name} | {z.layer} | {'Yes' if z.filled else 'No'} |")

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


@mcp.tool()
async def analyze_pcb_signal_integrity(
    file_path: str,
    net_name: str = "",
) -> str:
    """Analyze signal integrity: diff pair matching, RF traces, critical nets.

    Auto-detects differential pairs (e.g., USB_N/USB_P, DP/DN) and checks
    length matching. Reports RF trace dimensions and longest signal nets.

    Args:
        file_path: Path to .kicad_pcb file
        net_name: Optional specific net to analyze in detail

    Returns:
        Signal integrity analysis report
    """
    try:
        parser = _get_parser(file_path)

        if not _is_pcbnew(parser):
            data = parser._parse_file()
            tracks = data["tracks"]
            if not tracks:
                return "No tracks found in PCB file."

            # Build net stats from text parser data
            net_stats: dict[str, dict] = {}
            for t in tracks:
                net = t.get("net", "(unnamed)")
                if net not in net_stats:
                    net_stats[net] = {"total_length": 0.0, "segment_count": 0, "widths": [], "layers": set()}
                s = net_stats[net]
                s["total_length"] += t.get("length", 0)
                s["segment_count"] += 1
                s["widths"].append(t["width"])
                s["layers"].add(t["layer"])

            lines = [
                f"# Signal Integrity Analysis: {file_path}",
                "",
                "⚠️ pcbnew not available — text-based analysis (limited)",
            ]

            # Auto-detect differential pairs
            diff_pairs = _detect_diff_pairs(set(net_stats.keys()))
            if diff_pairs:
                lines += [
                    "",
                    "## Differential Pair Analysis",
                    "| Pair | Net P | Net N | Length P | Length N | Delta | Status |",
                    "|------|-------|-------|----------|----------|--------|---------|",
                ]
                for pair_name, net_p, net_n in diff_pairs:
                    len_p = net_stats[net_p]["total_length"] if net_p in net_stats else 0
                    len_n = net_stats[net_n]["total_length"] if net_n in net_stats else 0
                    delta = abs(len_p - len_n)
                    if delta < 0.127:
                        status = "OK"
                    elif delta < 0.5:
                        status = "⚠️ Marginal"
                    else:
                        status = "❌ Mismatch"
                    lines.append(
                        f"| {pair_name} | {net_p} | {net_n} | {len_p:.3f} mm | "
                        f"{len_n:.3f} mm | {delta:.3f} mm | {status} |"
                    )

            # Longest signal nets
            power_keywords = ("VDD", "VCC", "GND", "VSS", "3V3", "5V", "1V8", "PGND", "VBUS")
            signal_nets = [
                (name, s) for name, s in net_stats.items()
                if not any(kw in name.upper() for kw in power_keywords)
            ]
            top_signals = sorted(signal_nets, key=lambda x: -x[1]["total_length"])[:15]
            if top_signals:
                lines += [
                    "",
                    "## Longest Signal Nets (Top 15)",
                    "| Net | Length (mm) | Segments | Layers |",
                    "|-----|-------------|----------|--------|",
                ]
                for name, s in top_signals:
                    layers = ", ".join(sorted(s["layers"]))
                    lines.append(f"| {name} | {s['total_length']:.2f} | {s['segment_count']} | {layers} |")

            return "\n".join(lines)

        net_stats = parser.get_net_track_stats()
        rules = parser.get_design_rules()

        lines = [
            f"# Signal Integrity Analysis: {file_path}",
            "",
            f"**Diff Pair Design Rules:** width={rules['current_diff_pair_width_mm']:.4f} mm, "
            f"gap={rules['current_diff_pair_gap_mm']:.4f} mm",
        ]

        # If specific net requested, show detail
        if net_name:
            tracks = parser.get_tracks_by_net(net_name)
            if not tracks:
                return f"No tracks found for net '{net_name}'."
            total = sum(t.length for t in tracks)
            lines += [
                "",
                f"## Net: {net_name}",
                f"**Segments:** {len(tracks)}, **Total Length:** {total:.3f} mm",
            ]
            return "\n".join(lines)

        # Auto-detect differential pairs
        net_names = set(net_stats.keys())
        diff_pairs = _detect_diff_pairs(net_names)

        if diff_pairs:
            lines += [
                "",
                "## Differential Pair Analysis",
                "| Pair | Net P | Net N | Length P | Length N | Delta | Status |",
                "|------|-------|-------|----------|----------|--------|---------|",
            ]
            for pair_name, net_p, net_n in diff_pairs:
                len_p = net_stats[net_p]["total_length"] if net_p in net_stats else 0
                len_n = net_stats[net_n]["total_length"] if net_n in net_stats else 0
                delta = abs(len_p - len_n)
                # Length mismatch tolerance: 5 mil = 0.127 mm
                if delta < 0.127:
                    status = "OK"
                elif delta < 0.5:
                    status = "⚠️ Marginal"
                else:
                    status = "❌ Mismatch"
                lines.append(
                    f"| {pair_name} | {net_p} | {net_n} | {len_p:.3f} mm | "
                    f"{len_n:.3f} mm | {delta:.3f} mm | {status} |"
                )

        # RF traces (ANT, RF, antenna nets)
        rf_nets = [n for n in net_stats if any(
            kw in n.upper() for kw in ("ANT", "RF", "FEED")
        ) and "VDD" not in n.upper() and "GND" not in n.upper()]

        if rf_nets:
            lines += [
                "",
                "## RF Traces",
                "| Net | Length | Widths | Segments |",
                "|-----|--------|--------|----------|",
            ]
            for name in sorted(rf_nets):
                s = net_stats[name]
                widths = ", ".join(sorted({f"{w:.3f}" for w in s["widths"]}))
                lines.append(f"| {name} | {s['total_length']:.3f} mm | {widths} mm | {s['segment_count']} |")

        # Top signal nets by length (exclude power/GND)
        power_keywords = ("VDD", "VCC", "GND", "VSS", "3V3", "5V", "1V8", "PGND", "VBUS")
        signal_nets = [
            (name, s) for name, s in net_stats.items()
            if not any(kw in name.upper() for kw in power_keywords)
        ]
        top_signals = sorted(signal_nets, key=lambda x: -x[1]["total_length"])[:15]

        if top_signals:
            lines += [
                "",
                "## Longest Signal Nets (Top 15)",
                "| Net | Length (mm) | Segments | Layers |",
                "|-----|-------------|----------|--------|",
            ]
            for name, s in top_signals:
                layers = ", ".join(s["layers"])
                lines.append(f"| {name} | {s['total_length']:.2f} | {s['segment_count']} | {layers} |")

        # Nets with most layer transitions (most vias = most transitions)
        via_stats = parser.get_via_stats()
        if via_stats["count"] > 0:
            top_via_nets = list(via_stats["top_via_nets"].items())[:10]
            lines += [
                "",
                "## Nets with Most Vias (Layer Transitions)",
                "| Net | Via Count |",
                "|-----|-----------|",
            ]
            for name, count in top_via_nets:
                lines.append(f"| {name} | {count} |")

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


@mcp.tool()
async def analyze_pcb_power_integrity(file_path: str) -> str:
    """Analyze power integrity: copper zones, power net routing, GND coverage.

    Args:
        file_path: Path to .kicad_pcb file

    Returns:
        Power integrity analysis report
    """
    try:
        parser = _get_parser(file_path)

        if not _is_pcbnew(parser):
            data = parser._parse_file()
            tracks = data["tracks"]
            zones = data["zones"]

            lines = [
                f"# Power Integrity Analysis: {file_path}",
                "",
                "⚠️ pcbnew not available — text-based analysis (limited)",
            ]

            # Power zones
            power_keywords = ("VDD", "VCC", "VBUS", "LDO", "DCDC")
            gnd_keywords = ("GND", "PGND", "AGND", "DGND")

            power_zones = [z for z in zones if any(kw in z.get("net_name", "").upper() for kw in power_keywords)]
            gnd_zones = [z for z in zones if any(kw in z.get("net_name", "").upper() for kw in gnd_keywords)]

            if power_zones:
                lines += [
                    "",
                    "## Power Copper Zones",
                    "| Net | Layer |",
                    "|-----|-------|",
                ]
                for z in power_zones:
                    lines.append(f"| {z['net_name']} | {z.get('layer', 'N/A')} |")

            if gnd_zones:
                lines += [
                    "",
                    "## GND Copper Zones",
                    "| Net | Layer |",
                    "|-----|-------|",
                ]
                for z in gnd_zones:
                    lines.append(f"| {z['net_name']} | {z.get('layer', 'N/A')} |")
                gnd_layers = {z.get("layer", "") for z in gnd_zones}
                lines.append(f"\n**GND Coverage:** {len(gnd_zones)} zones across {len(gnd_layers)} layers")

            # Power net tracks
            net_stats: dict[str, dict] = {}
            for t in tracks:
                net = t.get("net", "")
                if not net:
                    continue
                if net not in net_stats:
                    net_stats[net] = {"total_length": 0.0, "segment_count": 0, "widths": []}
                net_stats[net]["total_length"] += t.get("length", 0)
                net_stats[net]["segment_count"] += 1
                net_stats[net]["widths"].append(t["width"])

            power_tracks = [(n, s) for n, s in net_stats.items() if any(kw in n.upper() for kw in power_keywords)]
            if power_tracks:
                lines += [
                    "",
                    "## Power Net Track Routing",
                    "| Net | Length (mm) | Segments | Min Width | Max Width |",
                    "|-----|-------------|----------|-----------|-----------|",
                ]
                for name, s in sorted(power_tracks, key=lambda x: -x[1]["total_length"]):
                    lines.append(
                        f"| {name} | {s['total_length']:.2f} | {s['segment_count']} | "
                        f"{min(s['widths']):.4f} mm | {max(s['widths']):.4f} mm |"
                    )

            return "\n".join(lines)

        net_stats = parser.get_net_track_stats()
        zones = parser.get_zones()
        rules = parser.get_design_rules()

        lines = [
            f"# Power Integrity Analysis: {file_path}",
            "",
            f"**Board:** {rules['copper_layers']} layers, {rules['board_thickness_mm']:.3f} mm thick",
        ]

        # Identify power nets
        power_keywords = ("VDD", "VCC", "VSS", "3V3", "5V", "1V8", "VBUS", "LDO", "DCDC")
        gnd_keywords = ("GND", "PGND", "AGND", "DGND", "CHASSIS")

        power_zones = [z for z in zones if any(kw in z.net_name.upper() for kw in power_keywords)]
        gnd_zones = [z for z in zones if any(kw in z.net_name.upper() for kw in gnd_keywords)]

        # Power zones by net
        power_zone_by_net: dict[str, list[str]] = {}
        for z in power_zones:
            power_zone_by_net.setdefault(z.net_name, []).append(
                f"{z.layer} ({'filled' if z.filled else 'unfilled'})"
            )

        if power_zone_by_net:
            lines += [
                "",
                "## Power Copper Zones",
                "| Net | Zones | Layers |",
                "|-----|-------|--------|",
            ]
            for net, layer_info in sorted(power_zone_by_net.items()):
                layers_str = ", ".join(layer_info)
                lines.append(f"| {net} | {len(layer_info)} | {layers_str} |")

        # GND zones
        gnd_zone_by_net: dict[str, list[str]] = {}
        for z in gnd_zones:
            gnd_zone_by_net.setdefault(z.net_name, []).append(
                f"{z.layer} ({'filled' if z.filled else 'unfilled'})"
            )

        if gnd_zone_by_net:
            lines += [
                "",
                "## GND Copper Zones",
                "| Net | Zones | Layers |",
                "|-----|-------|--------|",
            ]
            for net, layer_info in sorted(gnd_zone_by_net.items()):
                layers_str = ", ".join(layer_info)
                lines.append(f"| {net} | {len(layer_info)} | {layers_str} |")

            total_gnd_zones = len(gnd_zones)
            filled_gnd_zones = sum(1 for z in gnd_zones if z.filled)
            gnd_layers = {z.layer for z in gnd_zones}
            lines += [
                "",
                f"**GND Coverage:** {total_gnd_zones} zones across {len(gnd_layers)} layers "
                f"({filled_gnd_zones} filled)",
            ]
            if rules["copper_layers"] > 2 and len(gnd_layers) < rules["copper_layers"]:
                lines.append(
                    f"⚠️ GND zones only on {len(gnd_layers)} of {rules['copper_layers']} copper layers. "
                    "Consider adding GND pour on inner layers for better EMI performance."
                )

        # Power net track routing
        power_track_nets = [
            (name, s) for name, s in net_stats.items()
            if any(kw in name.upper() for kw in power_keywords)
        ]
        if power_track_nets:
            lines += [
                "",
                "## Power Net Track Routing",
                "| Net | Length (mm) | Segments | Min Width | Max Width |",
                "|-----|-------------|----------|-----------|-----------|",
            ]
            for name, s in sorted(power_track_nets, key=lambda x: -x[1]["total_length"]):
                min_w = min(s["widths"]) if s["widths"] else 0
                max_w = max(s["widths"]) if s["widths"] else 0
                lines.append(
                    f"| {name} | {s['total_length']:.2f} | {s['segment_count']} | "
                    f"{min_w:.4f} mm | {max_w:.4f} mm |"
                )

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error parsing PCB: {e}"


# ── Helpers ──────────────────────────────────────────────────


def _detect_diff_pairs(net_names: set[str]) -> list[tuple[str, str, str]]:
    """Auto-detect differential pairs from net names.

    Returns list of (pair_name, net_p, net_n) tuples.
    """
    pairs = []
    seen = set()

    # Common suffix patterns: _P/_N, _DP/_DN, _TXP/_TXN, etc.
    suffix_pairs = [
        ("_P", "_N"), ("_DP", "_DN"), ("_TXP", "_TXN"), ("_RXP", "_RXN"),
        ("_M", "_S"), ("_POS", "_NEG"),
    ]

    for suffix_p, suffix_n in suffix_pairs:
        for name in net_names:
            if name.endswith(suffix_p):
                candidate_n = name[:-len(suffix_p)] + suffix_n
                if candidate_n in net_names and name not in seen and candidate_n not in seen:
                    pair_name = name[:-len(suffix_p)]
                    pairs.append((pair_name, name, candidate_n))
                    seen.add(name)
                    seen.add(candidate_n)

    # Also check for common keywords like USB_C_N/USB_C_P
    keywords = ["USB", "DP", "HDMI", "CSI", "DSI", "SPI", "UART", "I2C"]
    for kw in keywords:
        p_candidates = [n for n in net_names if kw in n.upper() and n.endswith("_P") and n not in seen]
        for p in p_candidates:
            base = p[:-2]
            n_candidate = base + "_N"
            if n_candidate in net_names and n_candidate not in seen:
                pairs.append((base, p, n_candidate))
                seen.add(p)
                seen.add(n_candidate)

    return pairs
