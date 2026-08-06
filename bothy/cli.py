"""Bothy CLI — the same data layer the web console and Windows client use.

    bothy catalog --search git --type lxc
    bothy show gitea
    bothy estate
    bothy audit
    bothy serve --port 8760
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .catalog import AUDIT_LABEL, Catalog
from .estate import Estate

# ANSI, disabled when not a tty or when NO_COLOR is set
_TTY = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

# Windows consoles default to cp1252, which cannot encode the block glyphs or
# the middle dot used in resource summaries. Prefer UTF-8; fall back to ASCII
# art rather than crashing with UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    _UNICODE = True
except Exception:  # pragma: no cover - very old/odd streams
    _UNICODE = False


def _enc_ok(sample: str) -> bool:
    try:
        sample.encode(sys.stdout.encoding or "utf-8")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _UNICODE and _enc_ok("█·")
BAR_FULL = "█" if _UNICODE else "#"
BAR_EMPTY = "·" if _UNICODE else "."


def plain(text: str) -> str:
    """Downgrade separators the console cannot render."""
    return text if _UNICODE else text.replace("·", "*").replace("≤", "<=").replace("–", "-")


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


DIM, BOLD = "2", "1"
OK, WARN, DANGER, ACCENT = "32", "33", "31", "36"
AUDIT_COLOR = {"verified": OK, "unreviewed": WARN, "broken": DANGER}


def load_catalog(path: str | None) -> Catalog:
    src = path or os.environ.get("BOTHY_CATALOG")
    if not src:
        return Catalog.from_mapping({})
    return Catalog.from_legacy(src) if src.endswith(".py") else Catalog.from_json(src)


def cmd_catalog(args) -> int:
    cat = load_catalog(args.catalog)
    items = cat.search(args.search or "", args.type or (), args.footprint or (),
                       args.audit or (), sort=args.sort)
    if args.json:
        print(json.dumps([d.to_dict() for d in items], indent=1))
        return 0
    if not items:
        print("no definitions match", file=sys.stderr)
        return 1
    print(f"{c('KEY', DIM):<28} {c('NAME', DIM):<26} {c('TYPE', DIM):<7} "
          f"{c('RESOURCES', DIM):<18} {c('AUDIT', DIM)}")
    for d in items[: args.limit]:
        print(f"{d.key:<28} {d.name[:25]:<26} {d.type_label:<7} "
              f"{d.resource_summary:<18} {c(d.audit_label, AUDIT_COLOR.get(d.audit_state, DIM))}")
    if len(items) > args.limit:
        print(c(f"... {len(items) - args.limit} more of {len(items)} matches", DIM))
    else:
        print(c(f"{len(items)} of {len(cat)} definitions", DIM))
    return 0


def cmd_show(args) -> int:
    cat = load_catalog(args.catalog)
    d = cat.get(args.key)
    if d is None:
        print(f"no definition named {args.key!r}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(d.to_dict(), indent=1))
        return 0
    print(f"{c(d.name, BOLD)}  {c(d.key, DIM)}")
    print(f"  {d.description}")
    rows = [
        ("type", d.type_label), ("category", d.category or "—"),
        ("resources", plain(d.resource_summary)), ("footprint", d.footprint),
        ("ports", ", ".join(map(str, d.ports)) or "—"),
        ("env vars", str(len(d.env_vars))), ("volumes", str(len(d.volumes))),
        ("tags", ", ".join(d.tags) or "—"),
        ("audit", d.audit_label + (f" ({d.audit_verified_at})" if d.audit_verified_at else "")),
        ("source", d.source_ref),
    ]
    for k, v in rows:
        print(f"  {c(k + ':', DIM):<22} {v}")
    return 0


def cmd_estate(args) -> int:
    est = Estate.from_providers()
    if not est.configured:
        print("no providers configured - see ~/.bothy/config.toml", file=sys.stderr)
        return 2
    for err in est.errors:
        print(c(f"provider error: {err}", DANGER), file=sys.stderr)
    if args.audit:
        est.run_audit()
    if args.json:
        print(json.dumps([s.to_dict() for s in est.services], indent=1))
        return 0
    counts = est.counts()
    W = 22   # hostnames like "gitlab-runner-debian" overflow a 16-wide column
    print(f"{c('VMID', DIM):<7} {c('HOSTNAME', DIM):<{W}} {c('ADDRESS', DIM):<17} "
          f"{c('NODE', DIM):<9} {c('CPU', DIM):<6} {c('MEMORY', DIM):<12} {c('ROUTE', DIM)}")
    for s in est.services:
        colour = {"ok": OK, "danger": DANGER, "warn": WARN, "accent": ACCENT}.get(s.route_kind, DIM)
        name = s.hostname if len(s.hostname) <= W - 1 else s.hostname[: W - 2] + "…"
        print(f"{s.vmid:<7} {name:<{W}} {(s.address or '-'):<17} {s.node:<9} "
              f"{str(s.cpu_pct) + '%':<6} {s.mem_label:<12} {c(s.route, colour)}")
    print(c(f"{counts['total']} services · {counts['degraded']} degraded · "
            f"{counts['unreachable']} unreachable · {est.capacity_pct()}% capacity", DIM))
    return 0


def cmd_queue(args) -> int:
    jobs = []
    if args.json:
        print(json.dumps([j.to_dict() for j in jobs], indent=1))
        return 0
    if not jobs:
        print(c("queue is empty", DIM))
        return 0
    for j in jobs:
        colour = {"complete": OK, "installing": ACCENT, "blocked": DANGER}.get(j.status, DIM)
        bar_w = 24
        filled = int(bar_w * j.pct / 100)
        bar = BAR_FULL * filled + BAR_EMPTY * (bar_w - filled)
        status = c(f"{j.status.upper():<10}", colour)
        print(f"{status} {j.name:<10} {c(bar, colour)} {j.pct:>3}%  {j.reason or j.step}")
    return 0


def cmd_audit(args) -> int:
    cat = load_catalog(args.catalog)
    from .audit import AuditStore, run_audit, urls_from_install_scripts
    store = AuditStore.load()
    if args.run:
        src = args.catalog or os.environ.get("BOTHY_CATALOG", "")
        extra = {}
        if src.endswith(".py"):
            import pathlib as _p
            sib = _p.Path(src).with_name("install_scripts.py")
            if sib.exists():
                extra = {k: v for k, v in urls_from_install_scripts(sib).items() if cat.get(k)}
        print(c(f"checking links for {len(cat)} definitions ...", DIM), file=sys.stderr)
        res = run_audit(cat, extra=extra)
        store.update(res)
        broken = [r for r in res.values() if r.state == "broken"]
        if broken:
            print(c(f"{len(broken)} broken:", DANGER), file=sys.stderr)
            for r in broken:
                print(f"  {r.key:<20} {r.code:<10} {r.url}", file=sys.stderr)
    store.apply(cat)
    s = cat.audit_summary()
    if args.json:
        print(json.dumps(s, indent=1))
        return 0
    cov = store.coverage(cat)
    print(f"{s['total']} definitions · {cov['checked']} checked ({cov['pct']}%)")
    for state in ("verified", "unreviewed", "broken"):
        n, pct = s["counts"][state], s["pct"][state]
        bar = BAR_FULL * max(1, round(pct / 2))
        print(f"  {c(AUDIT_LABEL[state] + ':', DIM):<22} {n:>5}  "
              f"{c(bar, AUDIT_COLOR[state])} {pct}%")
    return 0


def cmd_serve(args) -> int:
    from .web import create_app
    app = create_app(args.catalog or os.environ.get("BOTHY_CATALOG"))
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bothy", description="Bothy — infrastructure deployment console")
    p.add_argument("--catalog", help="path to containers.py or a catalog JSON snapshot")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        return sp

    c1 = common(sub.add_parser("catalog", help="browse definitions by facet"))
    c1.add_argument("-s", "--search", help="substring over name, key, description, tags")
    c1.add_argument("-t", "--type", action="append", choices=["lxc", "vm", "docker"])
    c1.add_argument("-f", "--footprint", action="append", choices=["small", "medium", "large"])
    c1.add_argument("-a", "--audit", action="append", choices=["verified", "unreviewed", "broken"])
    c1.add_argument("--sort", default="name", choices=["name", "memory", "audit"])
    c1.add_argument("--limit", type=int, default=40)
    c1.set_defaults(func=cmd_catalog)

    c2 = common(sub.add_parser("show", help="show one definition"))
    c2.add_argument("key")
    c2.set_defaults(func=cmd_show)

    c4 = common(sub.add_parser("estate", help="deployed services"))
    c4.add_argument("--audit", action="store_true", help="probe reachability before printing")
    c4.set_defaults(func=cmd_estate)
    common(sub.add_parser("queue", help="deploy queue")).set_defaults(func=cmd_queue)
    c5 = common(sub.add_parser("audit", help="catalog audit summary"))
    c5.add_argument("--run", action="store_true", help="actually check every link now")
    c5.set_defaults(func=cmd_audit)

    c3 = sub.add_parser("serve", help="run the web console")
    c3.add_argument("--host", default="127.0.0.1")
    c3.add_argument("--port", type=int, default=8760)
    c3.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
