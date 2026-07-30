"""Parts registry tools — search and fetch verified KiCad parts.

Backed by an open, no-login registry (default: PartReel, https://partreel.com;
configurable via PARTS_REGISTRY_URL). Lets the assistant pull real, quality-
gated footprints/symbols/3D models instead of drawing them from scratch.
"""

import asyncio
import json
import os
from pathlib import Path

from ..server import mcp
from ..utils.parts_registry import (
    FORMAT_EXTENSIONS,
    RegistryClient,
    RegistryError,
)


@mcp.tool()
async def search_parts_registry(query: str, limit: int = 20) -> str:
    """Search an open registry of 21,000+ verified KiCad parts (no login).

    Matches part id, name, family, category, manufacturer and keywords.
    Example queries: "usb c connector", "0402 capacitor", "nrf9151".

    Args:
        query: Search terms (all terms must match; '*' wildcards allowed)
        limit: Maximum number of results (default 20)

    Returns:
        JSON list of matches (id, name, family, page URL)
    """
    client = RegistryClient()
    try:
        hits = await asyncio.to_thread(client.search, query, limit)
    except RegistryError as exc:
        return f"❌ Registry search failed: {exc}"
    if not hits:
        return f"No registry parts matched '{query}'."
    rows = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "family": p.get("family"),
            "category": p.get("category"),
            "manufacturer": p.get("manufacturer"),
            "page": p.get("page"),
        }
        for p in hits
    ]
    return json.dumps({"count": len(rows), "parts": rows}, indent=2)


@mcp.tool()
async def get_registry_part(part_id: str) -> str:
    """Get the full registry record for one part.

    Includes download URLs (footprint/symbol/3D), datasheet link, dimension
    provenance and field reports from real builds.

    Args:
        part_id: Registry part id (from search_parts_registry)

    Returns:
        JSON part record
    """
    client = RegistryClient()
    try:
        part = await asyncio.to_thread(client.get_part, part_id)
    except RegistryError as exc:
        return f"❌ Registry lookup failed: {exc}"
    return json.dumps(part, indent=2)


@mcp.tool()
async def download_registry_part(
    part_id: str, save_dir: str, formats: list[str] | None = None
) -> str:
    """Download a registry part's files into a local directory.

    Downloads are HTTPS-only, restricted to the registry's own hosts,
    capped at 50 MB per file, and saved with extension-checked filenames.

    Args:
        part_id: Registry part id (from search_parts_registry)
        save_dir: Existing local directory (e.g. the project library folder)
        formats: Which files — any of "footprint", "symbol", "step",
            "preview" (default: footprint + symbol)

    Returns:
        Saved file paths, or an error
    """
    formats = formats or ["footprint", "symbol"]
    unknown = [f for f in formats if f not in FORMAT_EXTENSIONS]
    if unknown:
        return f"❌ Unknown formats: {unknown} (allowed: {sorted(FORMAT_EXTENSIONS)})"

    dest = Path(save_dir)
    if not dest.is_dir():
        return f"❌ Not a directory: {save_dir}"
    # Confine writes to the working dir or the user's home tree
    # (extend via PARTS_REGISTRY_SAVE_ROOTS, comma-separated).
    roots = [Path.cwd(), Path.home()]
    roots += [
        Path(r.strip())
        for r in os.environ.get("PARTS_REGISTRY_SAVE_ROOTS", "").split(",")
        if r.strip()
    ]
    real = dest.resolve()
    if not any(real == r.resolve() or r.resolve() in real.parents for r in roots):
        return f"❌ save_dir outside allowed roots (cwd/home): {save_dir}"

    client = RegistryClient()
    try:
        part = await asyncio.to_thread(client.get_part, part_id)
    except RegistryError as exc:
        return f"❌ Registry lookup failed: {exc}"

    files = part.get("files") or {}
    saved, missing = [], []
    for fmt in formats:
        url = files.get(fmt)
        if not url:
            missing.append(fmt)
            continue
        try:
            path = await asyncio.to_thread(
                client.download_asset, url, str(real), part_id, fmt
            )
            saved.append(path)
        except RegistryError as exc:
            return f"❌ Download failed for {fmt}: {exc} (saved so far: {saved})"
    out = {"saved": saved, "not_available": missing, "license": part.get("license")}
    return json.dumps(out, indent=2)
