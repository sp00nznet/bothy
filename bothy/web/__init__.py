"""Bothy web console — Flask app factory and routes.

Three navigation groups (Operate / Build / Configure) replace the single page.
Every screen reads the same data layer the CLI and the Windows client use.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from flask import (Blueprint, Flask, current_app, jsonify, redirect,
                   render_template, request, url_for)

from ..audit import AuditStore, run_audit, urls_from_install_scripts
from ..catalog import Catalog
from ..collections import CollectionStore
from ..config import load_providers
from ..demo import DEMO_TEMPLATE, demo_estate, demo_history, demo_providers
from ..deploy import DeployEngine, DeployJob, dry_run_runner
from ..estate import Estate
from ..history import History

main = Blueprint("main", __name__)


def _nav(st) -> dict:
    return {
        "estate": len(st["estate"].services),
        "queue": st["engine"].active_count(),
        "catalog": len(st["catalog"]),
        "collections": len(st["collections"].all()),
        "providers": f"{st['configured']}/8",
    }


def create_app(catalog_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    src = catalog_path or os.environ.get("BOTHY_CATALOG")
    if src and Path(src).suffix == ".py":
        catalog = Catalog.from_legacy(src)
    elif src:
        catalog = Catalog.from_json(src)
    else:
        catalog = Catalog.from_mapping({})

    # link URLs live in the legacy install scripts, next to containers.py
    link_urls: dict[str, list[str]] = {}
    if src and Path(src).suffix == ".py":
        sibling = Path(src).with_name("install_scripts.py")
        if sibling.exists():
            link_urls = {k: v for k, v in urls_from_install_scripts(sibling).items()
                         if catalog.get(k)}

    install_scripts: dict[str, str] = {}
    if src and Path(src).suffix == ".py":
        sib = Path(src).with_name("install_scripts.py")
        if sib.exists():
            from ..install import load_scripts
            install_scripts = load_scripts(sib)

    audit_store = AuditStore.load()
    audit_store.apply(catalog)

    # Demo mode serves a fixed sample estate and never contacts a provider, so
    # the UI can be seen (and documented) without credentials. It also forces
    # dry run: a demo must not be one env var away from creating containers.
    demo = os.environ.get("BOTHY_DEMO") == "1"
    providers = demo_providers() if demo else load_providers()

    # BOTHY_DEPLOY=real is the only way to reach the runner that creates
    # containers. Anything else — unset, typo, empty — stays dry.
    live = os.environ.get("BOTHY_DEPLOY", "dry") == "real" and not demo
    runner = dry_run_runner
    if live:
        from ..deploy import make_proxmox_runner
        from ..providers import build as _build
        cfg = next((p for p in providers if p.configured and p.type == "proxmox"), None)
        if cfg is None:
            live = False        # asked for live with nothing to deploy to
        else:
            runner = make_proxmox_runner(_build(cfg))
    engine = DeployEngine(runner)
    app.extensions["bothy"] = {
        "catalog": catalog,
        "estate": demo_estate() if demo else Estate.from_providers(providers),
        "engine": engine,
        "dry_run": not live,
        "demo": demo,
        "collections": CollectionStore.load(),
        "audit_store": audit_store,
        "history": demo_history() if demo else History(),
        "link_urls": link_urls,
        "install_scripts": install_scripts,
        "providers": providers,
        "configured": sum(1 for p in providers if p.configured),
        "loaded_at": time.time(),
    }
    app.register_blueprint(main)
    return app


def _state():
    return current_app.extensions["bothy"]


def _by_node(est) -> dict:
    out: dict[str, dict] = {}
    for s in est.services:
        row = out.setdefault(s.node or "—", {"total": 0, "running": 0})
        row["total"] += 1
        if s.status == "running":
            row["running"] += 1
    return dict(sorted(out.items()))


def _tilde(p: Path) -> str:
    """Render a path under the home directory as ~/… — screenshots and
    screen-shares should not have to publish the operator's username."""
    try:
        return "~/" + p.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(p)


def _without(param: str, value: str) -> dict:
    """Current query string minus one param=value, for the filter chips."""
    args = request.args.to_dict(flat=False)
    if param in args:
        args[param] = [v for v in args[param] if v != value]
        if not args[param]:
            del args[param]
    return {k: v for k, v in args.items()}


@main.app_context_processor
def _inject():
    st = _state()
    return {"nav": _nav(st), "estate_errors": st["estate"].errors, "without": _without}


# ---------------------------------------------------------------- Operate
@main.route("/")
def overview():
    st = _state()
    est = st["estate"]
    return render_template(
        "overview.html", active="overview",
        counts=est.counts(), capacity=est.capacity_pct(),
        services=est.services, audit=st["catalog"].audit_summary(),
        queue_count=st["engine"].active_count(),
        audited=est.audited_ago(), configured=est.configured,
        providers_label=" · ".join(est.provider_names) or "no providers configured",
        by_node=_by_node(est),
    )


@main.route("/estate")
def estate_view():
    est = _state()["estate"]
    return render_template("estate.html", active="estate", services=est.services,
                           counts=est.counts(), audited=est.audited_ago(),
                           configured=est.configured)


@main.route("/estate/<int:vmid>")
def service_detail(vmid: int):
    st = _state()
    svc = st["estate"].by_vmid(vmid)
    if svc is None:
        return ("not found", 404)
    seed = svc.vmid
    spark = [30 + (seed * (i + 3) * 7) % 65 for i in range(14)]
    return render_template("service.html", active="estate", s=svc, spark=spark,
                           audited=st["estate"].audited_ago(),
                           results=st["estate"].reachability.get(vmid, []))


@main.route("/queue")
def queue():
    st = _state()
    batch = st["engine"].current()
    jobs = batch.jobs if batch else []
    focus = next((j for j in jobs if j.status == "installing"), jobs[0] if jobs else None)
    return render_template("queue.html", active="queue", batch=batch, jobs=jobs,
                           job=focus, dry_run=st["dry_run"])


@main.route("/history")
def history():
    st = _state()
    return render_template("history.html", active="history",
                           days=st["history"].by_day(300))


# ------------------------------------------------------------------ Build
@main.route("/catalog")
def catalog():
    st = _state()
    cat = st["catalog"]
    q = request.args.get("q", "")
    sort = request.args.get("sort", "name")
    sel = {
        "deploy_type": request.args.getlist("deploy_type"),
        "footprint": request.args.getlist("footprint"),
        "audit_state": request.args.getlist("audit_state"),
    }
    results = cat.search(q, sel["deploy_type"], sel["footprint"], sel["audit_state"], sort=sort)
    chips = []
    if q:
        chips.append({"label": f'"{q}"', "param": "q", "value": q})
    for group, vals in sel.items():
        for v in vals:
            chips.append({"label": v, "param": group, "value": v})
    return render_template(
        "catalog.html", active="catalog", q=q, sel=sel, sort=sort,
        facets=cat.facets(), results=results[:120], shown=min(len(results), 120),
        total=len(cat), matched=len(results),
        collections=st["collections"].all(), active_chips=chips,
    )


@main.route("/catalog/<key>")
def app_detail(key: str):
    d = _state()["catalog"].get(key)
    if d is None:
        return ("not found", 404)
    st = _state()
    nodes = sorted({s.node for s in st["estate"].services if s.node})
    return render_template("app.html", active="catalog", d=d,
                           deploy=request.args.get("deploy") == "1",
                           nodes=nodes, dry_run=st["dry_run"])


@main.route("/batch", methods=["POST"])
def batch():
    """Configure a batch from a catalog selection or a whole collection."""
    st = _state()
    keys = request.form.getlist("keys")
    if not keys and request.form.get("collection"):
        c = st["collections"].get(request.form["collection"])
        keys = c["keys"] if c else []
    defs = [d for d in (st["catalog"].get(k) for k in dict.fromkeys(keys)) if d]
    if not defs:
        return redirect(url_for("main.catalog"))
    nodes = sorted({x.node for x in st["estate"].services if x.node})
    totals = {"cores": sum(d.cores for d in defs),
              "memory_mb": sum(d.memory_mb for d in defs),
              "disk_gb": sum(d.disk_gb for d in defs)}
    return render_template("batch.html", active="catalog", defs=defs, nodes=nodes,
                           totals=totals, dry_run=st["dry_run"])


@main.route("/collections")
def collections():
    st = _state()
    cat = st["catalog"]
    items = []
    for c in st["collections"].all():
        items.append({**c, "defs": [cat.get(k) for k in c["keys"] if cat.get(k)]})
    return render_template("collections.html", active="collections", collections=items)


# -------------------------------------------------------------- Configure
@main.route("/providers")
def providers():
    from ..providers import KNOWN_TYPES
    st = _state()
    configured = {p.type: p for p in st["providers"] if p.configured}
    rows = []
    for kind, label, needs in KNOWN_TYPES:
        p = configured.get(kind)
        status = st.get("provider_status", {}).get(kind)
        if p and status:
            rows.append((kind, label, "ok" if status.ok else "warn",
                         "Connected" if status.ok else "Error",
                         status.detail or status.error, p.name))
        elif p:
            rows.append((kind, label, "muted", "Not tested", f"{p.host}:{p.port}", p.name))
        else:
            rows.append((kind, label, "muted", "—", needs, "Not configured"))
    return render_template("providers.html", active="providers", providers=rows,
                           configured=st["configured"])


@main.route("/providers/new")
def provider_wizard():
    from ..providers import IMPLEMENTED, KNOWN_TYPES, PROVIDER_FIELDS
    kind = request.args.get("type", "")
    label = next((l for k, l, _ in KNOWN_TYPES if k == kind), kind)
    return render_template("provider_wizard.html", active="providers",
                           types=KNOWN_TYPES, implemented=IMPLEMENTED,
                           kind=kind, label=label,
                           fields=PROVIDER_FIELDS.get(kind, []))


@main.route("/credentials")
def credentials():
    st = _state()
    return render_template("credentials.html", active="credentials",
                           providers=[p.redacted() for p in st["providers"]],
                           config_path=_tilde(Path.home() / ".bothy" / "config.toml"))


@main.route("/settings")
def settings():
    st = _state()
    src = os.environ.get("BOTHY_CATALOG", "(none)")
    if src != "(none)":
        src = _tilde(Path(src))
    return render_template("simple.html", active="settings", title="Settings",
                           note=f"Catalog source: {src} · "
                                f"{len(st['catalog'])} definitions · "
                                f"{st['configured']} provider(s) configured."
                                + (" · demo mode" if st.get("demo") else ""))


# ----------------------------------------------------------- actions (POST)
@main.route("/actions/refresh", methods=["POST"])
def action_refresh():
    st = _state()
    # demo providers point at nothing, so refreshing from them would empty the
    # sample estate and leave the UI blank
    fresh = demo_estate() if st.get("demo") else Estate.from_providers(st["providers"])
    fresh.adopt_reachability(st["estate"])     # a refresh must not erase the audit
    st["estate"] = fresh
    st["loaded_at"] = time.time()
    st["history"].add("refresh", "Estate refreshed",
                      f"{len(fresh.services)} guests from {len(st['providers'])} provider(s)")
    if request.headers.get("Accept") == "application/json":
        return jsonify({"services": len(st["estate"].services), "errors": st["estate"].errors})
    return redirect(request.referrer or url_for("main.overview"))


@main.route("/actions/audit", methods=["POST"])
def action_audit():
    st = _state()
    vmid = request.form.get("vmid", type=int)
    n = st["estate"].run_audit(vmid)
    st["history"].add("audit", "Reachability audit",
                      f"{n} service(s) checked" + (f" · vmid {vmid}" if vmid else ""))
    if request.headers.get("Accept") == "application/json":
        return jsonify({"checked": n, "audited": st["estate"].audited_ago()})
    return redirect(request.referrer or url_for("main.estate_view"))


@main.route("/actions/provider-test", methods=["POST"])
def action_provider_test():
    from ..providers import build
    st = _state()
    out = {}
    for cfg in st["providers"]:
        if cfg.configured:
            out[cfg.type] = build(cfg).test()
    st["provider_status"] = out
    if request.headers.get("Accept") == "application/json":
        return jsonify({k: {"ok": v.ok, "detail": v.detail or v.error} for k, v in out.items()})
    return redirect(url_for("main.providers"))


@main.route("/actions/catalog-audit", methods=["POST"])
def action_catalog_audit():
    """Check every definition's links. Explicit, like the reachability audit."""
    st = _state()
    keys = request.form.getlist("keys") or None
    res = run_audit(st["catalog"], keys=keys, extra=st["link_urls"])
    st["audit_store"].update(res)
    st["audit_store"].apply(st["catalog"])
    from collections import Counter as _C
    _states = _C(r.state for r in res.values())
    st["history"].add("catalog_audit", "Catalog link audit",
                      f"{len(res)} checked · {_states.get('broken', 0)} broken · "
                      f"{_states.get('verified', 0)} verified")
    if request.headers.get("Accept") == "application/json":
        from collections import Counter
        return jsonify({"checked": len(res),
                        "states": dict(Counter(r.state for r in res.values()))})
    return redirect(request.referrer or url_for("main.audit_queue"))


@main.route("/audit")
def audit_queue():
    st = _state()
    cat = st["catalog"]
    which = request.args.get("state", "")
    defs = [d for d in cat if not which or d.audit_state == which]
    defs.sort(key=lambda d: (d.audit_state != "broken", d.name.lower()))
    cov = st["audit_store"].coverage(cat)
    return render_template("audit.html", active="catalog", defs=defs[:200],
                           total=len(defs), summary=cat.audit_summary(),
                           coverage=cov, which=which,
                           linkable=len(st["link_urls"]))


@main.route("/actions/collection", methods=["POST"])
def action_collection():
    st = _state()
    name = (request.form.get("name") or "").strip()
    keys = [k for k in request.form.getlist("keys") if st["catalog"].get(k)]
    if not name or not keys:
        return (jsonify({"error": "name and at least one key required"}), 400)
    c = st["collections"].add(name, keys)
    st["history"].add("collection", f"Collection saved: {name}", f"{len(keys)} app(s)")
    if request.headers.get("Accept") == "application/json":
        return jsonify(c)
    return redirect(url_for("main.collections"))


@main.route("/actions/collection/<cid>/delete", methods=["POST"])
def action_collection_delete(cid: str):
    _state()["collections"].remove(cid)
    return redirect(url_for("main.collections"))


@main.route("/actions/deploy", methods=["POST"])
def action_deploy():
    """Queue a batch. Keys come from the catalog selection or a collection."""
    st = _state()
    keys = request.form.getlist("keys") or request.json.get("keys", []) if request.is_json else request.form.getlist("keys")
    node = request.form.get("node", "")
    storage = request.form.get("storage", "")
    on_failure = request.form.get("on_failure", "stop")
    jobs = []
    for k in keys:
        d = st["catalog"].get(k)
        if d is None:
            continue
        j = DeployJob(key=d.key, name=d.name, node=node, storage=storage,
                      vmid=request.form.get(f"vmid_{k}", type=int),
                      cores=int(request.form.get(f"cores_{k}", d.cores)),
                      memory_mb=int(request.form.get(f"memory_{k}", d.memory_mb)),
                      disk_gb=int(request.form.get(f"disk_{k}", d.disk_gb)),
                      hostname=request.form.get(f"hostname_{k}", d.key),
                      install_script=st["install_scripts"].get(k, ""),
                      secret_names=[e.get("name") for e in (d.env_vars or [])
                                    if e.get("secret")],
                      env={e["name"]: request.form.get(f"env_{k}_{e['name']}", "")
                           for e in (d.env_vars or []) if e.get("name")
                           and request.form.get(f"env_{k}_{e['name']}")})
        j.target = f"{node or 'auto'} · vmid auto"
        if not node and not st["estate"].configured:
            j.status = "blocked"
            j.reason = "No provider selected for this app"
        jobs.append(j)
    # Resolve the template the real run would use, so the dry run previews the
    # actual command rather than a placeholder.
    if st.get("demo"):
        # the demo provider resolves to nothing, so asking it for a template
        # would fill every job with a DNS failure instead of a preview
        for j in jobs:
            j.template = DEMO_TEMPLATE
    elif node:
        try:
            from ..deploy import pick_template
            from ..providers import build as build_provider
            cfg = next((p for p in st["providers"] if p.configured), None)
            if cfg:
                tmpl = pick_template(build_provider(cfg)._connect(), node)
                for j in jobs:
                    j.template = tmpl
        except Exception as e:
            for j in jobs:
                j.reason = j.reason or f"template lookup failed: {e}"

    if not jobs:
        return (jsonify({"error": "no valid definitions selected"}), 400)
    batch = st["engine"].submit(jobs, on_failure)
    st["history"].add("deploy", f"Batch #{batch.id} queued",
                      f"{len(jobs)} app(s): " + ", ".join(j.name for j in jobs[:4]) +
                      (f" +{len(jobs) - 4} more" if len(jobs) > 4 else "") +
                      (" · dry run" if st["dry_run"] else ""))
    if request.headers.get("Accept") == "application/json":
        return jsonify(batch.to_dict())
    return redirect(url_for("main.queue"))


@main.route("/actions/queue/<int:batch_id>/<what>", methods=["POST"])
def action_queue_control(batch_id: int, what: str):
    eng = _state()["engine"]
    if what == "pause":
        eng.pause(batch_id, True)
    elif what == "resume":
        eng.pause(batch_id, False)
    elif what == "abort":
        eng.abort(batch_id)
    if request.headers.get("Accept") == "application/json":
        b = eng.get(batch_id)
        return jsonify(b.to_dict() if b else {"error": "no such batch"})
    return redirect(url_for("main.queue"))


def _cfg_from_form(form) -> "ProviderConfig":
    from ..config import ProviderConfig
    return ProviderConfig(
        name=form.get("name") or form.get("type", "provider"),
        type=form.get("type", "proxmox"),
        host=form.get("host", ""),
        port=int(form.get("port") or 8006),
        user=form.get("user", "root@pam"),
        password=form.get("password", ""),
        token_id=form.get("token_id", ""),
        token_secret=form.get("token_secret", ""),
        node=form.get("node", ""),
        verify_ssl=bool(form.get("verify_ssl")),
        default=bool(form.get("default")),
    )


@main.route("/actions/provider-try", methods=["POST"])
def action_provider_try():
    """Test credentials from the wizard WITHOUT saving them."""
    from ..providers import IMPLEMENTED, build
    cfg = _cfg_from_form(request.form)
    if cfg.type not in IMPLEMENTED:
        return jsonify({"ok": False, "detail": f"no adapter for {cfg.type} yet"})
    if not cfg.configured:
        return jsonify({"ok": False, "detail": "host and a password or token are required"})
    st = build(cfg).test()
    return jsonify({"ok": st.ok, "detail": st.detail or st.error})


@main.route("/actions/provider-save", methods=["POST"])
def action_provider_save():
    from ..config import load_providers, save_providers
    st = _state()
    if st.get("demo"):
        # demo mode is a look around, not a way to rewrite the real config
        return jsonify({"ok": False, "detail": "demo mode — providers are read-only"}), 403
    cfg = _cfg_from_form(request.form)
    providers = [p for p in load_providers() if p.name != cfg.name]
    if cfg.default:
        for p in providers:
            p.default = False
    providers.append(cfg)
    path = save_providers(providers)
    st["history"].add("provider", f"Provider saved: {cfg.name}",
                      f"{cfg.type} · {cfg.host}")
    # adopt immediately so the estate reflects the new provider without a restart
    st["providers"] = load_providers()
    st["configured"] = sum(1 for p in st["providers"] if p.configured)
    fresh = Estate.from_providers(st["providers"])
    fresh.adopt_reachability(st["estate"])
    st["estate"] = fresh
    if request.headers.get("Accept") == "application/json":
        return jsonify({"saved": str(path), "providers": len(providers)})
    return redirect(url_for("main.providers"))


# ------------------------------------------------------------------- API
@main.route("/api/catalog")
def api_catalog():
    st = _state()
    items = st["catalog"].search(request.args.get("q", ""),
                                request.args.getlist("deploy_type"),
                                request.args.getlist("footprint"),
                                request.args.getlist("audit_state"))
    return jsonify({"total": len(st["catalog"]), "count": len(items),
                    "items": [d.to_dict() for d in items[:200]]})


@main.route("/api/catalog/<key>")
def api_definition(key: str):
    d = _state()["catalog"].get(key)
    return (jsonify(d.to_dict()), 200) if d else (jsonify({"error": "not found"}), 404)


@main.route("/api/estate")
def api_estate():
    est = _state()["estate"]
    return jsonify({"counts": est.counts(), "capacity_pct": est.capacity_pct(),
                    "audited": est.audited_ago(), "errors": est.errors,
                    "services": [s.to_dict() for s in est.services]})


@main.route("/api/reachability/<int:vmid>")
def api_reachability(vmid: int):
    res = _state()["estate"].reachability.get(vmid, [])
    return jsonify([{"url": r.url, "via": r.via, "code": r.code, "note": r.note,
                     "checked_at": r.checked_at} for r in res])


@main.route("/api/queue")
def api_queue():
    b = _state()["engine"].current()
    return jsonify(b.to_dict() if b else {"jobs": [], "total": 0, "done": 0, "finished": True})


@main.route("/api/history")
def api_history():
    return jsonify([e.to_dict() for e in _state()["history"].all(200)])


@main.route("/api/audit")
def api_audit():
    return jsonify(_state()["catalog"].audit_summary())
