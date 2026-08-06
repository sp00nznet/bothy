"""Estate: deployed services, reachability results and the deploy queue.

Reachability is an explicit user-triggered audit (per the design), never a
background poll, and every result records when it was checked.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Literal

Status = Literal["running", "degraded", "stopped", "deploying"]


@dataclass
class Service:
    vmid: int
    hostname: str
    address: str
    node: str
    provider: str = "proxmox"
    status: Status = "running"
    cpu_pct: int = 0
    mem_used_mb: int = 0
    mem_total_mb: int = 1024
    uptime: str = ""
    route: str = "direct"          # 200 OK | 502 | timeout | direct | n/a | deploying
    group: str = "Unassigned"
    definition_key: str = ""
    kind: str = "lxc"          # lxc | vm

    @property
    def mem_label(self) -> str:
        """e.g. '2.3/4G' or '27M/512M' - the unit belongs to each number, not
        bolted onto the end (that produced '512MG')."""
        def fmt(mb: int, unit: bool) -> str:
            if mb >= 1024:
                v = f"{mb / 1024:.1f}".rstrip("0").rstrip(".")
                return f"{v}G" if unit else v
            return f"{mb}M"
        total = fmt(self.mem_total_mb, True)
        # only drop the used-value unit when both sides share it
        same_unit = (self.mem_used_mb >= 1024) == (self.mem_total_mb >= 1024)
        return f"{fmt(self.mem_used_mb, not same_unit)}/{total}"

    @property
    def route_kind(self) -> str:
        """Colour class for the Route cell.

        A 3xx/401/403 means the service ANSWERED — it is reachable, just
        redirecting or protected. Only 5xx, timeouts and refused connections
        are genuine unreachability, and only those feed the 'needs attention'
        count. Treating an auth challenge as an outage cries wolf.
        """
        r = self.route
        if r in ("direct", "n/a", ""):
            return "muted"
        if r == "deploying":
            return "accent"
        if r[:1] in ("2", "3"):
            return "ok"
        if r[:1] == "4":
            return "warn"          # reachable, needs auth / not found
        return "danger"            # 5xx, timeout, closed, tls, error

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(mem_label=self.mem_label, route_kind=self.route_kind)
        return d


@dataclass
class ReachabilityResult:
    url: str
    via: str
    code: str
    note: str = ""
    checked_at: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return self.code.startswith("2")


@dataclass
class Job:
    key: str
    name: str
    target: str
    status: str = "queued"          # complete | installing | queued | blocked
    pct: int = 0
    step: str = ""
    elapsed: str = ""
    reason: str = ""
    log: list[tuple[str, str, str]] = field(default_factory=list)  # (time, kind, text)

    def to_dict(self) -> dict:
        return asdict(self)


class Estate:
    """The live estate, populated by provider adapters."""

    def __init__(self, services: list[Service] | None = None):
        self.services: list[Service] = services or []
        self.reachability: dict[int, list[ReachabilityResult]] = {}
        self.audited_at: float | None = None
        self.errors: list[str] = []          # per-provider failures, surfaced in the UI
        self.provider_names: list[str] = []

    @classmethod
    def from_providers(cls, configs=None) -> "Estate":
        """Read every configured provider. A provider that fails is recorded in
        .errors rather than raising, so one dead credential cannot blank the UI."""
        from .config import load_providers
        from .providers import build

        est = cls()
        for cfg in (configs if configs is not None else load_providers()):
            if not cfg.configured:
                continue
            est.provider_names.append(cfg.name)
            try:
                est.services.extend(build(cfg).services())
            except Exception as e:
                est.errors.append(f"{cfg.name}: {type(e).__name__}: {e}")
        # Every node of a Proxmox cluster reports the whole cluster, so two
        # configured members of one cluster would list each guest twice.
        seen: set[tuple] = set()
        unique: list[Service] = []
        for s in est.services:
            key = (s.provider, s.node, s.vmid)
            if key in seen:
                continue
            seen.add(key)
            unique.append(s)
        est.services = sorted(unique, key=lambda s: s.vmid)
        return est

    @property
    def configured(self) -> bool:
        return bool(self.provider_names)

    def adopt_reachability(self, previous: "Estate") -> None:
        """Carry audit results across a refresh.

        Refreshing re-reads the providers and builds new Service objects, which
        would otherwise silently discard the last audit and reset every Route to
        'n/a' — making a refresh look like the estate had gone dark.
        """
        if previous is None:
            return
        self.reachability = dict(previous.reachability)
        self.audited_at = previous.audited_at
        from .reachability import summarise
        for s in self.services:
            res = self.reachability.get(s.vmid)
            if res:
                s.route = summarise(res)

    # ---- queries -------------------------------------------------------
    def by_vmid(self, vmid: int) -> Service | None:
        return next((s for s in self.services if s.vmid == vmid), None)

    def counts(self) -> dict:
        running = sum(1 for s in self.services if s.status == "running")
        degraded = sum(1 for s in self.services if s.status == "degraded")
        unreachable = sum(1 for s in self.services if s.route_kind == "danger")
        return {
            "total": len(self.services),
            "running": running,
            "degraded": degraded,
            "unreachable": unreachable,
        }

    def capacity_pct(self) -> int:
        if not self.services:
            return 0
        used = sum(s.mem_used_mb for s in self.services)
        total = sum(s.mem_total_mb for s in self.services) or 1
        return round(used * 100 / total)

    def groups(self) -> dict[str, list[Service]]:
        out: dict[str, list[Service]] = {}
        for s in self.services:
            out.setdefault(s.group, []).append(s)
        return out

    # ---- reachability --------------------------------------------------
    def run_audit(self, vmid: int | None = None) -> int:
        """Explicit, user-triggered probe. Returns number of services checked."""
        from .reachability import audit as run, summarise

        targets = [s for s in self.services if vmid is None or s.vmid == vmid]
        results = run(targets)
        self.reachability.update(results)
        for s in targets:
            s.route = summarise(results.get(s.vmid, []))
        self.audited_at = time.time()
        return len(targets)

    def audited_ago(self) -> str:
        if not self.audited_at:
            return "never"
        secs = int(time.time() - self.audited_at)
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60} min ago"
        return f"{secs // 3600}h ago"
