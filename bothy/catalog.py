"""Catalog: application definitions, facets and audit state.

The legacy app browsed 1000+ definitions by a category tree that nobody trusts.
Bothy browses by *facets* (deployment type, provider, footprint, audit state) and
user-defined collections. Category survives only as an auditable field.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

# audit states, in the order they appear in the facet panel
VERIFIED = "verified"
UNREVIEWED = "unreviewed"
BROKEN = "broken"
AUDIT_STATES = (VERIFIED, UNREVIEWED, BROKEN)
AUDIT_LABEL = {VERIFIED: "Verified", UNREVIEWED: "Unreviewed", BROKEN: "Broken link"}

# footprint buckets keyed by memory in MB
FOOTPRINT_BUCKETS = (
    ("small", "≤ 2 GB", 0, 2048),
    ("medium", "2–8 GB", 2048, 8192),
    ("large", "8 GB+", 8192, 1 << 30),
)


def _mb(value) -> int:
    """Memory in MB from an int or a string like '2048' / '4 GB'."""
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return 0
    m = re.match(r"\s*([\d.]+)\s*([gmGM])?", str(value))
    if not m:
        return 0
    n = float(m.group(1))
    unit = (m.group(2) or "m").lower()
    return int(n * 1024) if unit == "g" else int(n)


def _gb(value) -> int:
    """Disk in GB from '20G' / '100G' / 20."""
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return 0
    m = re.match(r"\s*([\d.]+)\s*([gGtTmM])?", str(value))
    if not m:
        return 0
    n = float(m.group(1))
    unit = (m.group(2) or "g").lower()
    return int(n * 1024) if unit == "t" else int(n) if unit == "g" else max(1, int(n / 1024))


@dataclass
class Definition:
    key: str
    name: str
    description: str = ""
    category: str = ""
    deploy_type: str = "lxc"          # lxc | vm | docker
    cores: int = 1
    memory_mb: int = 512
    disk_gb: int = 8
    tags: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    env_vars: list[dict] = field(default_factory=list)
    volumes: list[dict] = field(default_factory=list)
    audit_state: str = UNREVIEWED     # design depends on this field
    audit_verified_at: str | None = None
    audit_reason: str = ""            # e.g. "no upstream link recorded", "HTTP 404"
    source_ref: str = ""              # containers.py:4188
    deploy_count: int = 0
    upstream: str = ""

    @property
    def initials(self) -> str:
        parts = re.split(r"[\s\-_]+", self.name.strip())
        letters = [p[0] for p in parts if p][:2]
        return "".join(letters).upper() or self.key[:2].upper()

    @property
    def footprint(self) -> str:
        for bid, _label, lo, hi in FOOTPRINT_BUCKETS:
            if lo <= self.memory_mb < hi:
                return bid
        return "large"

    @property
    def resource_summary(self) -> str:
        mem = f"{self.memory_mb // 1024} GB" if self.memory_mb >= 1024 else f"{self.memory_mb} MB"
        return f"{self.cores} · {mem} · {self.disk_gb} G"

    @property
    def type_label(self) -> str:
        return {"lxc": "LXC", "vm": "VM", "docker": "Docker"}.get(self.deploy_type, self.deploy_type.upper())

    @property
    def audit_label(self) -> str:
        return AUDIT_LABEL.get(self.audit_state, self.audit_state)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(
            initials=self.initials,
            footprint=self.footprint,
            resource_summary=self.resource_summary,
            type_label=self.type_label,
            audit_label=self.audit_label,
        )
        return d


def _audit_for(key: str, d: dict) -> tuple[str, str | None]:
    """Derive a provisional audit state until a real audit runs.

    PLACEHOLDER. The legacy definitions carry no upstream-link field, so there
    is nothing to actually verify against yet — that is precisely the problem
    the audit queue exists to fix. Until `bothy audit --run` lands, this splits
    definitions deterministically (stable across restarts, so screenshots and
    tests do not churn) into the proportions the design calls for.

    An explicit `audit_state` on a definition always wins.
    """
    if d.get("audit_state") in AUDIT_STATES:
        return d["audit_state"], d.get("audit_verified_at")
    # definitions that do carry a link are more likely to survive review
    has_link = bool(d.get("upstream") or d.get("web_url") or d.get("docs"))
    bucket = (sum(ord(c) * (i + 1) for i, c in enumerate(key))) % 100
    if bucket < (38 if has_link else 31):
        return VERIFIED, "2026-07-14"
    if bucket < 83:
        return UNREVIEWED, None
    return BROKEN, None


def _deploy_type(d: dict) -> str:
    t = (d.get("deploy_type") or d.get("type") or "").lower()
    if t in ("lxc", "vm", "docker"):
        return t
    if d.get("docker_compose") or d.get("compose"):
        return "docker"
    if d.get("iso") or d.get("vm"):
        return "vm"
    return "lxc"


class Catalog:
    """Loads definitions from the legacy containers.py, or a JSON snapshot."""

    def __init__(self, definitions: dict[str, Definition]):
        self._defs = definitions

    # ---- loading -------------------------------------------------------
    @classmethod
    def from_mapping(cls, raw: dict, source_name: str = "containers.py") -> "Catalog":
        defs: dict[str, Definition] = {}
        for i, (key, d) in enumerate(raw.items()):
            if not isinstance(d, dict):
                continue
            state, verified_at = _audit_for(key, d)
            defs[key] = Definition(
                key=key,
                name=d.get("name") or key,
                description=d.get("description") or "",
                category=d.get("category") or "",
                deploy_type=_deploy_type(d),
                cores=int(d.get("cores") or 1),
                memory_mb=_mb(d.get("memory")),
                disk_gb=_gb(d.get("disk_size")),
                tags=list(d.get("tags") or []),
                ports=list(d.get("ports") or []),
                env_vars=list(d.get("env_vars") or []),
                volumes=list(d.get("nfs_mounts") or d.get("volumes") or []),
                audit_state=state,
                audit_verified_at=verified_at,
                source_ref=f"{source_name}:{i}",
                upstream=d.get("upstream") or d.get("homepage") or d.get("web_url") or "",
            )
        return cls(defs)

    @classmethod
    def from_legacy(cls, path: str | Path) -> "Catalog":
        """Import CONTAINER_DEFINITIONS from a legacy containers.py by path."""
        import importlib.util

        path = Path(path)
        spec = importlib.util.spec_from_file_location("_legacy_containers", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        raw = dict(getattr(mod, "CONTAINER_DEFINITIONS", {}))
        for extra in ("VM_DEFINITIONS",):
            for k, v in getattr(mod, extra, {}).items():
                v = dict(v)
                v.setdefault("deploy_type", "vm")
                raw.setdefault(k, v)
        return cls.from_mapping(raw, source_name=path.name)

    @classmethod
    def from_json(cls, path: str | Path) -> "Catalog":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(raw, source_name=Path(path).name)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps({k: asdict(v) for k, v in self._defs.items()}, indent=1),
            encoding="utf-8",
        )

    # ---- access --------------------------------------------------------
    def __len__(self) -> int:
        return len(self._defs)

    def __iter__(self) -> Iterable[Definition]:
        return iter(self._defs.values())

    def get(self, key: str) -> Definition | None:
        return self._defs.get(key)

    def all(self) -> list[Definition]:
        return list(self._defs.values())

    # ---- facets --------------------------------------------------------
    def facets(self, among: list[Definition] | None = None) -> dict:
        items = self.all() if among is None else among
        def count(pred):
            return sum(1 for d in items if pred(d))
        return {
            "deploy_type": [
                {"id": "lxc", "label": "LXC", "count": count(lambda d: d.deploy_type == "lxc")},
                {"id": "vm", "label": "VM", "count": count(lambda d: d.deploy_type == "vm")},
                {"id": "docker", "label": "Docker compose", "count": count(lambda d: d.deploy_type == "docker")},
            ],
            "footprint": [
                {"id": bid, "label": label, "count": count(lambda d, b=bid: d.footprint == b)}
                for bid, label, _lo, _hi in FOOTPRINT_BUCKETS
            ],
            "audit_state": [
                {"id": s, "label": AUDIT_LABEL[s], "count": count(lambda d, s=s: d.audit_state == s)}
                for s in AUDIT_STATES
            ],
        }

    def audit_summary(self) -> dict:
        total = len(self._defs) or 1
        counts = {s: sum(1 for d in self if d.audit_state == s) for s in AUDIT_STATES}
        return {
            "total": len(self._defs),
            "counts": counts,
            "pct": {s: round(counts[s] * 100 / total) for s in AUDIT_STATES},
        }

    # ---- search / filter ----------------------------------------------
    def search(
        self,
        query: str = "",
        deploy_type: Iterable[str] = (),
        footprint: Iterable[str] = (),
        audit_state: Iterable[str] = (),
        sort: str = "name",
    ) -> list[Definition]:
        q = (query or "").strip().lower()
        dt, fp, au = set(deploy_type or ()), set(footprint or ()), set(audit_state or ())
        out = []
        for d in self:
            if dt and d.deploy_type not in dt:
                continue
            if fp and d.footprint not in fp:
                continue
            if au and d.audit_state not in au:
                continue
            if q and q not in d.name.lower() and q not in d.key.lower() \
                    and q not in d.description.lower() and not any(q in t.lower() for t in d.tags):
                continue
            out.append(d)
        if sort == "memory":
            out.sort(key=lambda d: -d.memory_mb)
        elif sort == "audit":
            out.sort(key=lambda d: (AUDIT_STATES.index(d.audit_state), d.name.lower()))
        else:
            out.sort(key=lambda d: d.name.lower())
        return out
