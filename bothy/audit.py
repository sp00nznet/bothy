"""Catalog audit — actually check the links, and be honest when there are none.

The handoff's second premise is that definition links are unverified. Running
this against a real catalog exposes the sharper problem: most definitions carry
no upstream link at all, so there is nothing to verify. A checker that only
reported "verified / broken" would quietly imply coverage it does not have.

So the audit records three outcomes and a reason:

    verified    a link was found and it resolves
    broken      a link was found and it does not resolve
    unreviewed  no link was recorded for this definition (reason says so)

Results persist to ~/.bothy/audit.json and override the provisional split in
catalog._audit_for().
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests
import urllib3

from .catalog import BROKEN, UNREVIEWED, VERIFIED, Catalog, Definition

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TIMEOUT = 8.0
UA = "Bothy-audit/0.1 (+link checker)"

# URLs inside install scripts are the real provenance: they are what the
# installer actually fetches, so a dead one is a genuinely broken definition.
_URL_RE = re.compile(r"https?://[a-zA-Z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
# skip anything with shell interpolation or an obvious placeholder
_SKIP = ("$", "{", "<", "example.com", "localhost", "127.0.0.1", "0.0.0.0")


def store_path() -> Path:
    return Path.home() / ".bothy" / "audit.json"


@dataclass
class AuditResult:
    key: str
    state: str
    url: str = ""
    code: str = ""
    reason: str = ""
    source: str = ""          # "definition" | "install-script"
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


def clean_url(u: str) -> str:
    return u.rstrip(").,;'\"")


def candidate_urls(d: Definition,
                   extra: dict[str, list[str]] | None = None) -> list[tuple[str, str]]:
    """[(url, source)] worth checking, the definition's own link first.

    The distinction matters. An install script that fetches download.docker.com
    tells you nothing about whether *this* definition's upstream is alive — many
    unrelated apps share that URL. Only a link the definition itself declares can
    make it "verified"; a dependency URL can only ever make it "broken".
    """
    out: list[tuple[str, str]] = []
    if d.upstream:
        out.append((d.upstream, "definition"))
    for u in (extra or {}).get(d.key, []):
        out.append((u, "install-script"))
    seen, uniq = set(), []
    for u, src in out:
        u = clean_url(u)
        if not u or any(s in u for s in _SKIP) or u in seen:
            continue
        seen.add(u)
        uniq.append((u, src))
    return uniq


def urls_from_install_scripts(path: str | Path) -> dict[str, list[str]]:
    """Map definition key -> URLs referenced by its install script.

    The legacy install_scripts.py is one module of per-app shell strings; the
    key is whatever assignment or dict entry the URLs sit under.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    out: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        m = re.match(r'\s*["\']([a-z0-9][a-z0-9_-]{1,40})["\']\s*:', line)
        if m:
            current = m.group(1)
        m2 = re.match(r"\s*([A-Z][A-Z0-9_]{2,})\s*=", line)
        if m2:
            current = m2.group(1).lower().replace("_install_script", "").replace("_script", "")
        for u in _URL_RE.findall(line):
            u = clean_url(u)
            if current and not any(s in u for s in _SKIP):
                out.setdefault(current, [])
                if u not in out[current]:
                    out[current].append(u)
    return out


def check_url(url: str) -> tuple[str, str]:
    """(code, reason). HEAD first; some hosts refuse HEAD, so fall back to GET."""
    headers = {"User-Agent": UA}
    try:
        r = requests.head(url, timeout=TIMEOUT, allow_redirects=True,
                          headers=headers, verify=False)
        if r.status_code in (403, 405, 501):
            r = requests.get(url, timeout=TIMEOUT, allow_redirects=True,
                             headers=headers, verify=False, stream=True)
            r.close()
        return str(r.status_code), ""
    except requests.exceptions.SSLError:
        return "tls", "TLS verification failed"
    except requests.exceptions.Timeout:
        return "timeout", f"no response in {TIMEOUT:.0f}s"
    except requests.exceptions.ConnectionError as e:
        return "unreachable", "DNS or connection failure" if "NameResolution" in str(e) else "connection failed"
    except Exception as e:  # pragma: no cover
        return "error", type(e).__name__


def _reachable(code: str) -> bool:
    """Did the host answer in a way that proves the resource exists?

    401/403 mean "answered, but you may not list this" — an apt repository root
    returns 403 by design while every file beneath it serves fine. Treating that
    as a broken link produces false alarms on perfectly healthy repos, so only
    404/410, 5xx and transport failures count as broken.
    """
    if not code.isdigit():
        return False                      # timeout / unreachable / tls / error
    n = int(code)
    if n < 400:
        return True
    return n in (401, 403, 405, 429)


def audit_definition(d: Definition, extra: dict[str, list[str]] | None = None) -> AuditResult:
    urls = candidate_urls(d, extra)
    if not urls:
        # not a broken link — a missing one. That is the finding, so say it.
        return AuditResult(key=d.key, state=UNREVIEWED,
                           reason="no upstream link recorded")

    checked_ok: list[str] = []
    for url, source in urls[:3]:
        code, why = check_url(url)
        ok = _reachable(code)
        if not ok:
            # a dead URL is a real defect wherever it came from
            return AuditResult(key=d.key, state=BROKEN, url=url, code=code,
                               source=source, reason=why or f"HTTP {code}")
        if source == "definition":
            return AuditResult(key=d.key, state=VERIFIED, url=url, code=code,
                               source=source)
        checked_ok.append(url)

    # every URL resolved, but none of them was the definition's own link
    return AuditResult(key=d.key, state=UNREVIEWED, url=checked_ok[0], code="200",
                       source="install-script",
                       reason="dependencies reachable; no upstream link recorded")


def run_audit(catalog: Catalog, keys: list[str] | None = None,
              extra: dict[str, list[str]] | None = None,
              workers: int = 12, limit: int | None = None) -> dict[str, AuditResult]:
    defs = [catalog.get(k) for k in keys] if keys else catalog.all()
    defs = [d for d in defs if d]
    if limit:
        defs = defs[:limit]
    results: dict[str, AuditResult] = {}
    if not defs:
        return results
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for d, res in zip(defs, pool.map(lambda x: audit_definition(x, extra), defs)):
            results[d.key] = res
    return results


class AuditStore:
    """Persisted audit results, applied over the catalog on load."""

    def __init__(self, results: dict[str, dict] | None = None, path: Path | None = None):
        self._r = results or {}
        self._path = path or store_path()

    @classmethod
    def load(cls, path: Path | None = None) -> "AuditStore":
        p = path or store_path()
        if p.exists():
            try:
                return cls(json.loads(p.read_text(encoding="utf-8")), p)
            except (json.JSONDecodeError, OSError):
                pass
        return cls({}, p)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._r, indent=1), encoding="utf-8")

    def update(self, results: dict[str, AuditResult]) -> None:
        for k, r in results.items():
            self._r[k] = r.to_dict()
        self.save()

    def get(self, key: str) -> dict | None:
        return self._r.get(key)

    def __len__(self) -> int:
        return len(self._r)

    def apply(self, catalog: Catalog) -> int:
        """Overlay stored results onto the catalog. Returns how many applied."""
        n = 0
        for d in catalog:
            r = self._r.get(d.key)
            if not r:
                continue
            d.audit_state = r["state"]
            d.audit_verified_at = (time.strftime("%Y-%m-%d", time.localtime(r["checked_at"]))
                                   if r.get("state") == VERIFIED else None)
            # Only a URL the definition itself declared may become its upstream.
            # Writing back an install-script URL would let the next run mistake a
            # shared dependency (download.docker.com) for this app's own link and
            # promote it to "verified" - laundering coverage we do not have.
            if r.get("source") == "definition" and r.get("url"):
                d.upstream = r["url"]
            d.audit_reason = r.get("reason", "")
            n += 1
        return n

    def coverage(self, catalog: Catalog) -> dict:
        checked = sum(1 for d in catalog if d.key in self._r)
        return {"checked": checked, "total": len(catalog),
                "pct": round(checked * 100 / max(1, len(catalog)))}
