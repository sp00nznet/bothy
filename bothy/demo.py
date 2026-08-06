"""Sample estate for `BOTHY_DEMO=1`.

Bothy is useless without a provider, which makes it hard to look at before you
commit credentials to it — and it makes documentation screenshots a problem,
since real ones publish your hostnames, addresses and node names.

Demo mode serves this fixed estate instead of reading any provider. Nothing
here is real: the addresses are RFC 5737 documentation space, so a screenshot
cannot leak a topology and a stray probe cannot reach anyone's network.
"""
from __future__ import annotations

import time

from .config import ProviderConfig
from .estate import Estate, ReachabilityResult, Service

# vmid, host, addr, node, status, cpu%, mem used, mem total, uptime, route, group
_ROWS = [
    (100, "plex", "203.0.113.100", "pve01", "running", 12, 2400, 4096, "14d 6h", "200 OK", "Media"),
    (101, "sonarr", "203.0.113.101", "pve01", "running", 4, 700, 2048, "14d 6h", "200 OK", "Media"),
    (102, "radarr", "203.0.113.102", "pve01", "running", 5, 760, 2048, "9d 2h", "200 OK", "Media"),
    (103, "sabnzbd", "203.0.113.103", "pve01", "running", 21, 1100, 2048, "9d 2h", "200 OK", "Media"),
    (104, "jellyfin", "203.0.113.104", "pve01", "degraded", 63, 3600, 4096, "2d 4h", "502", "Media"),
    (110, "gitea", "203.0.113.110", "pve02", "running", 8, 1500, 4096, "31d 1h", "200 OK", "DevOps"),
    (111, "drone", "203.0.113.111", "pve02", "running", 3, 600, 2048, "31d 1h", "direct", "DevOps"),
    (112, "harbor", "203.0.113.112", "pve02", "running", 17, 2900, 4096, "6d 8h", "200 OK", "DevOps"),
    (113, "registry", "203.0.113.113", "pve02", "running", 2, 380, 1024, "6d 8h", "direct", "DevOps"),
    (120, "gitea-new", "203.0.113.120", "pve02", "deploying", 0, 0, 4096, "—", "deploying", "DevOps"),
    (130, "traefik", "203.0.113.130", "pve01", "running", 6, 420, 1024, "44d 3h", "200 OK", "Infrastructure"),
    (131, "pihole", "203.0.113.131", "pve01", "running", 3, 300, 1024, "44d 3h", "200 OK", "Infrastructure"),
    (132, "vaultwarden", "203.0.113.132", "pve03", "running", 2, 260, 1024, "21d 7h", "timeout", "Infrastructure"),
    (133, "uptime-kuma", "203.0.113.133", "pve03", "running", 4, 410, 1024, "21d 7h", "200 OK", "Infrastructure"),
    (140, "nextcloud", "203.0.113.140", "pve03", "running", 19, 3100, 6144, "12d 5h", "200 OK", "Unassigned"),
]


def demo_estate() -> Estate:
    est = Estate([
        Service(vmid=v, hostname=h, address=a, node=n, status=st, cpu_pct=c,
                mem_used_mb=mu, mem_total_mb=mt, uptime=up, route=rt, group=g,
                definition_key=h.split("-")[0])
        for (v, h, a, n, st, c, mu, mt, up, rt, g) in _ROWS
    ])
    est.provider_names = [p.name for p in demo_providers()]
    est.audited_at = time.time() - 1800
    # one audited service, so the service page shows results rather than "never
    # checked" — jellyfin is the degraded one, which is the interesting case
    est.reachability[104] = [
        ReachabilityResult("http://203.0.113.104:8096/web/index.html", "direct", "502",
                           "bad gateway from reverse proxy"),
        ReachabilityResult("https://jellyfin.example.com", "tunnel", "502",
                           "origin unreachable"),
    ]
    est.reachability[110] = [
        ReachabilityResult("http://203.0.113.110:3000", "direct", "200"),
        ReachabilityResult("https://git.example.com", "tunnel", "200"),
    ]
    return est


def demo_providers() -> list[ProviderConfig]:
    """One Proxmox cluster — the three nodes below are its members, which is how
    a real cluster reports itself. The password is a placeholder and connects to
    nothing; demo mode never builds an adapter from these."""
    return [
        ProviderConfig(name="pve-cluster", type="proxmox", host="pve01.example.com",
                       user="root@pam", password="demo", node="", default=True),
    ]


DEMO_HISTORY = [
    ("deploy_done", "Harbor", "pve02 · vmid 118 · 4m 02s", 1500),
    ("audit", "Reachability audit", "15 services · 13 reachable · 2 need attention", 1800),
    ("deploy_failed", "SigNoz", "no provider selected for this app", 5400),
    ("provider", "docker-lab", "added Docker provider", 7200),
    ("catalog_audit", "Catalog audit", "182 definitions · 168 links verified", 10800),
    ("deploy_done", "Gitea", "pve02 · vmid 110 · 2m 51s", 93600),
    ("collection", "Media stack", "5 apps saved as a collection", 97200),
    ("refresh", "Estate refresh", "15 guests across 3 nodes", 180000),
]


def demo_history():
    """A History backed by its own file, seeded with the events above.

    Deliberately NOT the real ~/.bothy/history.jsonl — demo mode must never
    write over the record of things that actually happened.
    """
    import json
    from pathlib import Path

    from .history import History

    h = History(path=Path.home() / ".bothy" / "demo-history.jsonl")
    now = time.time()
    rows = [{"kind": k, "subject": s, "detail": d, "at": now - ago}
            for k, s, d, ago in sorted(DEMO_HISTORY, key=lambda r: -r[3])]
    try:
        h._path.parent.mkdir(parents=True, exist_ok=True)
        h._path.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                           encoding="utf-8")
    except OSError:
        pass          # a blank History screen is not worth failing startup over
    return h


# what a Debian 12 LXC template volid looks like, for the dry-run preview
DEMO_TEMPLATE = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
