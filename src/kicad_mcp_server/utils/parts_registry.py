"""
Client for an open parts registry (default: PartReel, https://partreel.com).

Lets tools search a public registry of verified KiCad parts and download
symbol/footprint/3D files without any account or API key. The registry URL is
configurable, so any service exposing the same JSON shape works.

Security posture (all enforced here, not in the tools):
    - Asset downloads are restricted to HTTPS URLs on the registry's own host,
      its subdomains, or hosts explicitly allowed via PARTS_REGISTRY_ASSET_HOSTS.
    - Saved filenames are derived from the remote basename but must match the
      extension allow-list for the requested format (prevents e.g. ``.exe``).
    - Downloads are size-capped (MAX_ASSET_BYTES) and streamed to disk.
    - Destination directories are validated by the caller via PathValidator.
"""

import fnmatch
import json
import os
import urllib.parse
import urllib.request

DEFAULT_REGISTRY_URL = os.environ.get(
    "PARTS_REGISTRY_URL", "https://partreel.com/api/v1"
)
USER_AGENT = "kicad-mcp-parts-registry"
MAX_ASSET_BYTES = 50 * 1024 * 1024  # 50 MB cap for any single asset download
HTTP_TIMEOUT = 30  # seconds

# format name -> allowed file extensions (lowercase)
FORMAT_EXTENSIONS = {
    "footprint": (".kicad_mod",),
    "symbol": (".kicad_sym",),
    "step": (".step", ".stp"),
    "preview": (".glb",),
    "footprint_svg": (".svg",),
    "symbol_svg": (".svg",),
}


class RegistryError(Exception):
    """Raised for registry access or validation failures."""


class _NoCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    """Block HTTP redirects to a different host.

    ``asset_url_allowed`` only checks the URL passed in; urllib otherwise
    silently follows 3xx to any host, letting a compromised registry point
    asset downloads (or JSON metadata) at an attacker-controlled host.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        orig = (urllib.parse.urlparse(req.full_url).hostname or "").lower()
        new = (urllib.parse.urlparse(newurl).hostname or "").lower()
        if orig and new and (new == orig or new.endswith("." + orig)):
            return super().redirect_request(req, fp, code, msg, headers, newurl)
        raise RegistryError(f"redirect to disallowed host blocked: {newurl}")


_DEFAULT_OPENER = urllib.request.build_opener(_NoCrossHostRedirect)


def _fetch(url: str, opener=None) -> bytes:
    """GET a URL with a size cap. ``opener`` is injectable for tests."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    open_fn = opener or _DEFAULT_OPENER.open
    with open_fn(req, timeout=HTTP_TIMEOUT) as resp:
        declared = resp.headers.get("Content-Length")
        data = resp.read(MAX_ASSET_BYTES + 1)
    # Honour Content-Length so a truncated stream (proxy/server drops the
    # connection mid-asset) is caught, not silently written as a half-file.
    if declared and declared.isdigit() and int(declared) > MAX_ASSET_BYTES:
        raise RegistryError(f"asset exceeds {MAX_ASSET_BYTES} byte limit: {url}")
    if len(data) > MAX_ASSET_BYTES:
        raise RegistryError(f"asset exceeds {MAX_ASSET_BYTES} byte limit: {url}")
    return data


def registry_host(registry_url: str = DEFAULT_REGISTRY_URL) -> str:
    """Hostname of the configured registry."""
    return urllib.parse.urlparse(registry_url).hostname or ""


def extra_asset_hosts() -> list[str]:
    """Extra allowed asset hosts from PARTS_REGISTRY_ASSET_HOSTS (comma list)."""
    raw = os.environ.get("PARTS_REGISTRY_ASSET_HOSTS", "")
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def asset_url_allowed(url: str, registry_url: str = DEFAULT_REGISTRY_URL) -> bool:
    """True if ``url`` is HTTPS on the registry host, a subdomain of it, or an
    explicitly allowed extra host."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    root = registry_host(registry_url).lower()
    if not root:
        return False
    if host == root or host.endswith("." + root):
        return True
    return host in extra_asset_hosts()


def filename_for_asset(url: str, part_id: str, fmt: str) -> str:
    """Safe local filename for an asset: the remote basename when its extension
    matches the format's allow-list, else ``<part_id>.<default ext>``."""
    exts = FORMAT_EXTENSIONS.get(fmt)
    if not exts:
        raise RegistryError(f"unknown format: {fmt}")
    remote = os.path.basename(urllib.parse.urlparse(url).path)
    # basename() strips directories; also reject any residual traversal chars
    if remote and ".." not in remote and remote.lower().endswith(exts):
        return remote
    return f"{part_id}{exts[0]}"


# Module-level index cache keyed by registry URL. Previously the cache lived on
# each RegistryClient instance, but the tools build a fresh client per call, so
# the ~21k-entry index was re-downloaded on every search.
_INDEX_CACHE: dict[str, list[dict]] = {}


class RegistryClient:
    """Minimal client for the registry's static JSON API.

    The full parts index is fetched once and cached at module level (keyed by
    registry URL); the tools construct a fresh client per call.
    """

    def __init__(self, registry_url: str = DEFAULT_REGISTRY_URL, opener=None):
        self.registry_url = registry_url.rstrip("/")
        self._opener = opener

    def _get_json(self, url: str):
        try:
            return json.loads(_fetch(url, self._opener).decode("utf-8"))
        except RegistryError:
            raise
        except Exception as exc:  # URLError, HTTPError, JSONDecodeError, ...
            raise RegistryError(f"registry request failed: {exc}") from exc

    def index(self) -> list[dict]:
        """Full parts index (cached at module level)."""
        if self.registry_url not in _INDEX_CACHE:
            doc = self._get_json(f"{self.registry_url}/parts.json")
            if isinstance(doc, list):
                parts = doc
            elif isinstance(doc, dict):
                raw = doc.get("parts") or []
                parts = raw if isinstance(raw, list) else []
            else:
                parts = []  # null / string / number — don't crash
            _INDEX_CACHE[self.registry_url] = parts
        return _INDEX_CACHE[self.registry_url]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Case-insensitive AND-match of query tokens against id, name,
        family, category, manufacturer and keywords. ``*`` wildcards work."""
        tokens = [t.lower() for t in query.split() if t.strip()]
        if not tokens:
            return []
        hits = []
        for part in self.index():
            if not isinstance(part, dict):
                continue
            haystack = " ".join(
                str(part.get(k, ""))
                for k in ("id", "name", "family", "category", "manufacturer")
            ).lower()
            haystack += " " + " ".join(part.get("keywords") or []).lower()
            if all(
                tok in haystack or fnmatch.fnmatch(haystack, f"*{tok}*")
                for tok in tokens
            ):
                hits.append(part)
                if len(hits) >= limit:
                    break
        return hits

    def get_part(self, part_id: str) -> dict:
        """Full record for one part (includes download URLs in ``files``)."""
        if not part_id or not all(c.isalnum() or c in "_-" for c in part_id):
            raise RegistryError(f"invalid part id: {part_id}")
        return self._get_json(f"{self.registry_url}/parts/{part_id}.json")

    def download_asset(self, url: str, dest_dir: str, part_id: str, fmt: str) -> str:
        """Download one asset into ``dest_dir`` (must already be validated by
        the caller). Returns the written file path."""
        if not asset_url_allowed(url, self.registry_url):
            raise RegistryError(f"asset host not allowed: {url}")
        data = _fetch(url, self._opener)
        path = os.path.join(dest_dir, filename_for_asset(url, part_id, fmt))
        with open(path, "wb") as f:
            f.write(data)
        return path
