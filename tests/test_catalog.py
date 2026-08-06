"""Runnable checks for the catalog logic. `python tests/test_catalog.py`"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bothy.catalog import AUDIT_STATES, Catalog, _gb, _mb
from bothy.estate import Estate, Service
from fixtures import sample_estate, sample_queue

RAW = {
    "gitea": {"name": "Gitea", "description": "Lightweight Git server", "category": "DevOps",
              "cores": 2, "memory": 2048, "disk_size": "30G", "tags": ["git"], "ports": [3000]},
    "plex": {"name": "Plex Media Server", "description": "Media", "category": "Media",
             "cores": 2, "memory": 4096, "disk_size": "20G", "tags": ["media"]},
    "tiny": {"name": "Tiny", "memory": 512, "disk_size": "8G"},
    "big": {"name": "Big VM", "memory": "16 GB", "disk_size": "1T", "deploy_type": "vm"},
}


def test_units():
    assert _mb(2048) == 2048 and _mb("16 GB") == 16384 and _mb(None) == 0
    assert _gb("30G") == 30 and _gb("1T") == 1024 and _gb(20) == 20


def test_parsing():
    c = Catalog.from_mapping(RAW)
    assert len(c) == 4
    g = c.get("gitea")
    assert g.name == "Gitea" and g.deploy_type == "lxc" and g.memory_mb == 2048
    assert g.initials == "G" and g.type_label == "LXC"
    assert c.get("big").deploy_type == "vm" and c.get("big").disk_gb == 1024
    assert c.get("plex").initials == "PM"          # two words -> two letters


def test_footprint_buckets():
    c = Catalog.from_mapping(RAW)
    assert c.get("tiny").footprint == "small"      # 512 MB
    assert c.get("gitea").footprint == "medium"    # 2 GB is the boundary -> medium
    assert c.get("big").footprint == "large"       # 16 GB


def test_audit_is_deterministic_and_covers_all_states():
    a = Catalog.from_mapping(RAW)
    b = Catalog.from_mapping(RAW)
    for k in RAW:
        assert a.get(k).audit_state == b.get(k).audit_state, "audit must be stable across loads"
        assert a.get(k).audit_state in AUDIT_STATES
    summary = a.audit_summary()
    assert summary["total"] == 4
    assert sum(summary["counts"].values()) == 4


def test_search_and_facets():
    c = Catalog.from_mapping(RAW)
    assert [d.key for d in c.search("git")] == ["gitea"]
    assert [d.key for d in c.search("MEDIA")] == ["plex"]        # case-insensitive
    assert [d.key for d in c.search(deploy_type=["vm"])] == ["big"]
    assert c.search("nothing-matches-this") == []
    f = c.facets()
    assert sum(x["count"] for x in f["deploy_type"]) == 4
    assert sum(x["count"] for x in f["audit_state"]) == 4
    # combining facets narrows, never widens
    assert len(c.search(deploy_type=["lxc"], footprint=["small"])) <= len(c.search(deploy_type=["lxc"]))


def test_estate_derived_fields():
    e = sample_estate()
    counts = e.counts()
    assert counts["total"] == len(e.services)
    assert counts["degraded"] >= 1
    assert 0 <= e.capacity_pct() <= 100
    jelly = next(s for s in e.services if s.hostname == "jellyfin")
    assert jelly.route_kind == "danger"           # 502
    plex = e.by_vmid(100)
    assert plex.route_kind == "ok" and "/" in plex.mem_label
    assert Estate([]).audited_ago() == "never"    # nothing checked yet
    assert e.run_audit() == len(e.services)
    assert e.audited_ago() != "never"


def test_queue_shapes():
    jobs = sample_queue()
    assert {j.status for j in jobs} == {"complete", "installing", "blocked"}
    blocked = next(j for j in jobs if j.status == "blocked")
    assert blocked.reason and blocked.pct == 0


def test_route_classification():
    """A 3xx/4xx means the service answered - only 5xx/timeout/closed are outages."""
    def kind(route):
        return Service(vmid=1, hostname="x", address="", node="n", route=route).route_kind
    assert kind("200 OK") == "ok" and kind("302") == "ok"
    assert kind("401") == "warn" and kind("404") == "warn"
    assert kind("502") == "danger" and kind("timeout") == "danger" and kind("closed") == "danger"
    assert kind("direct") == "muted" and kind("n/a") == "muted"
    # an auth challenge must not inflate the needs-attention count
    est = Estate([Service(vmid=1, hostname="a", address="", node="n", route="403"),
                  Service(vmid=2, hostname="b", address="", node="n", route="502")])
    assert est.counts()["unreachable"] == 1


def test_memory_label_units():
    def lbl(u, t):
        return Service(vmid=1, hostname="x", address="", node="n",
                       mem_used_mb=u, mem_total_mb=t).mem_label
    assert lbl(2400, 4096) == "2.3/4G"
    assert lbl(27, 512) == "27M/512M"      # regression: used to render "512MG"
    assert lbl(0, 8192) == "0M/8G"
    assert "MG" not in lbl(27, 512)


def test_refresh_preserves_audit():
    """A refresh rebuilds Service objects; it must not silently drop the audit."""
    from bothy.estate import ReachabilityResult
    old = Estate([Service(vmid=7, hostname="a", address="1.2.3.4", node="n")])
    old.reachability[7] = [ReachabilityResult(url="u", via="direct", code="200")]
    old.audited_at = 123.0
    new = Estate([Service(vmid=7, hostname="a", address="1.2.3.4", node="n")])
    assert new.services[0].route == "direct"
    new.adopt_reachability(old)
    assert new.services[0].route == "200 OK"
    assert new.audited_at == 123.0


def test_collections_roundtrip():
    import tempfile, pathlib as _p
    from bothy.collections import CollectionStore
    with tempfile.TemporaryDirectory() as d:
        path = _p.Path(d) / "c.json"
        st = CollectionStore([], path)
        c = st.add("Git & CI", ["gitea", "gitlab", "gitea"])   # duplicate key
        assert c["count"] == 2 and len(c["keys"]) == 2
        st.add("Git & CI", ["forgejo"])                        # merges by name
        assert len(st.all()) == 1 and st.all()[0]["count"] == 3
        assert CollectionStore.load(path).all()[0]["name"] == "Git & CI"
        assert st.remove(c["id"]) and CollectionStore.load(path).all() == []


def test_deploy_engine_runs_a_batch():
    from bothy.deploy import DeployEngine, DeployJob
    seen = []

    def runner(job):
        seen.append(job.key)
        job.pct = 100

    eng = DeployEngine(runner)
    b = eng.submit([DeployJob(key="a", name="A"), DeployJob(key="b", name="B")])
    for _ in range(100):
        if b.finished:
            break
        time.sleep(0.05)
    assert b.finished and seen == ["a", "b"]
    assert all(j.status == "complete" for j in b.jobs)
    assert b.done == 2 and eng.active_count() == 0


def test_deploy_stop_on_failure_blocks_the_rest():
    from bothy.deploy import DeployEngine, DeployJob

    def runner(job):
        if job.key == "boom":
            raise RuntimeError("no template")

    eng = DeployEngine(runner)
    b = eng.submit([DeployJob(key="boom", name="Boom"), DeployJob(key="next", name="Next")],
                   on_failure="stop")
    for _ in range(100):
        if b.finished:
            break
        time.sleep(0.05)
    assert b.jobs[0].status == "failed" and "no template" in b.jobs[0].reason
    # the rest must be BLOCKED with a reason, never silently skipped
    assert b.jobs[1].status == "blocked" and b.jobs[1].reason


def test_only_continue_carries_on_after_a_failure():
    """rollback is offered but unimplemented; it must not be the loosest policy."""
    from bothy.deploy import DeployEngine, DeployJob

    def runner(job):
        if job.key == "boom":
            raise RuntimeError("boom")

    def run(policy):
        eng = DeployEngine(runner)
        b = eng.submit([DeployJob(key="boom", name="B"), DeployJob(key="next", name="N")],
                       on_failure=policy)
        for _ in range(100):
            if b.finished:
                break
            time.sleep(0.05)
        return b.jobs[1].status

    assert run("continue") == "complete"
    assert run("stop") == "blocked"
    assert run("rollback") == "blocked"      # was "complete": the least safe option
    assert run("typo") == "blocked"          # an unknown policy must not run on


def test_dry_run_never_prints_none_for_vmid():
    from bothy.deploy import DeployJob, dry_run_runner
    j = DeployJob(key="gitea", name="Gitea", storage="local-lvm")
    dry_run_runner(j)
    joined = " ".join(l.text for l in j.log)
    assert "None" not in joined, joined
    assert "<next>" in joined and j.pct == 95


def test_provider_config_toml_roundtrip():
    """The wizard writes TOML by hand; it must survive quotes and backslashes."""
    import tomllib
    from bothy.config import ProviderConfig, dump_providers
    ps = [ProviderConfig(name='Lab "A"', type="proxmox", host="10.0.0.5",
                         user="root@pam", password='p\\w"x', default=True),
          ProviderConfig(name="Token lab", type="proxmox", host="10.0.0.6",
                         token_id="bothy", token_secret="s3cr3t", node="pve01")]
    d = tomllib.loads(dump_providers(ps))["providers"]
    assert d[0]["name"] == 'Lab "A"' and d[0]["password"] == 'p\\w"x'
    assert d[0]["default"] is True and d[1]["default"] is False
    # a token provider must not emit an empty password field
    assert "password" not in d[1] and d[1]["token_secret"] == "s3cr3t"
    assert d[1]["node"] == "pve01"


def test_save_providers_keeps_a_backup(tmp_path=None):
    import tempfile, pathlib as _p
    from bothy.config import ProviderConfig, save_providers
    with tempfile.TemporaryDirectory() as d:
        target = _p.Path(d) / "config.toml"
        save_providers([ProviderConfig(name="one", host="h", password="p")], target)
        save_providers([ProviderConfig(name="two", host="h", password="p")], target)
        assert target.exists() and target.with_suffix(".toml.bak").exists()
        assert "two" in target.read_text() and "one" in target.with_suffix(".toml.bak").read_text()


def test_every_provider_type_has_a_field_spec():
    """The wizard renders PROVIDER_FIELDS[kind]; a missing entry means an
    unusable step-2 with no fields at all."""
    from bothy.providers import KNOWN_TYPES, PROVIDER_FIELDS, IMPLEMENTED
    for key, label, _needs in KNOWN_TYPES:
        assert key in PROVIDER_FIELDS, f"no field spec for {key}"
        assert PROVIDER_FIELDS[key], f"empty field spec for {key}"
        for f in PROVIDER_FIELDS[key]:
            assert {"name", "label", "kind", "required"} <= set(f)
    assert IMPLEMENTED <= {k for k, _l, _n in KNOWN_TYPES}


def test_friendly_provider_errors():
    """Users should see a cause, not a urllib3 traceback."""
    from bothy.providers.proxmox import _friendly
    assert "authentication failed" in _friendly(Exception("401 Unauthorized"))
    assert "timed out" in _friendly(Exception("ConnectTimeout: ... connect timeout=15"))
    assert "refused" in _friendly(Exception("Connection refused"))
    assert "host not found" in _friendly(Exception("getaddrinfo failed"))
    long = _friendly(Exception("x" * 500))
    assert len(long) <= 160


def test_audit_reachable_classification():
    """A 403 from an apt-repo root is normal; only 404/5xx/transport are broken."""
    from bothy.audit import _reachable
    assert _reachable("200") and _reachable("301") and _reachable("302")
    assert _reachable("403") and _reachable("401")     # answered, just forbidden
    assert not _reachable("404") and not _reachable("410")
    assert not _reachable("500") and not _reachable("timeout") and not _reachable("unreachable")


def test_audit_no_link_is_a_finding_not_a_failure():
    from bothy.audit import audit_definition
    from bothy.catalog import Catalog
    d = Catalog.from_mapping({"x": {"name": "X"}}).get("x")
    r = audit_definition(d, extra={})
    assert r.state == "unreviewed" and "no upstream link" in r.reason
    assert r.url == "" and r.code == ""


def test_audit_never_launders_dependency_urls_into_upstream():
    """A shared install-script URL must not become the definition's own link,
    or the next run would promote it to 'verified' coverage we never had."""
    from bothy.audit import AuditStore
    from bothy.catalog import Catalog
    cat = Catalog.from_mapping({"gitea": {"name": "Gitea"}, "harbor": {"name": "Harbor"}})
    store = AuditStore({
        "gitea": {"key": "gitea", "state": "unreviewed", "url": "https://download.docker.com/x",
                  "code": "200", "source": "install-script", "reason": "deps reachable",
                  "checked_at": 0},
        "harbor": {"key": "harbor", "state": "verified", "url": "https://harbor.example",
                   "code": "200", "source": "definition", "reason": "", "checked_at": 0},
    })
    store.apply(cat)
    assert cat.get("gitea").upstream == "", "dependency URL leaked into upstream"
    assert cat.get("harbor").upstream == "https://harbor.example"
    assert cat.get("gitea").audit_state == "unreviewed"


def test_url_extraction_skips_interpolated_and_placeholder_urls():
    import tempfile, pathlib as _p
    from bothy.audit import urls_from_install_scripts
    with tempfile.TemporaryDirectory() as d:
        f = _p.Path(d) / "s.py"
        f.write_text("\n".join([
            '"gitea": """',
            '  curl https://real.example/key.gpg',
            '  curl http://$(hostname -I)/thing',
            '  curl https://example.com/placeholder',
            '"""']), encoding="utf-8")
        got = urls_from_install_scripts(f)
        assert got["gitea"] == ["https://real.example/key.gpg"], got


def test_history_roundtrip_and_tolerates_a_torn_line():
    import tempfile, pathlib as _p
    from bothy.history import History
    with tempfile.TemporaryDirectory() as d:
        path = _p.Path(d) / "h.jsonl"
        h = History(path)
        h.add("deploy", "Batch #1 queued", "2 apps")
        h.add("audit", "Reachability audit", "34 checked")
        with path.open("a", encoding="utf-8") as f:
            f.write('{"kind": "deploy", "subject": "tor')   # crash mid-write
        events = h.all()
        assert len(events) == 2, "a torn final line must not hide earlier events"
        assert events[0].subject == "Reachability audit"     # newest first
        assert events[0].dot == "ok" and events[1].label == "Deploy"
        assert list(h.by_day().values())[0][0].subject == "Reachability audit"


def test_create_params_are_complete():
    """A container with no net0 comes up with no networking, and the old runner
    referenced a field that did not exist, so a real deploy crashed on
    AttributeError before reaching the cluster."""
    from bothy.deploy import DeployJob, build_create_params
    j = DeployJob(key="gitea", name="Gitea", node="n", storage="local-lvm",
                  cores=2, memory_mb=2048, disk_gb=30, hostname="gitea",
                  template="local:vztmpl/debian-12.tar.zst", nesting=True)
    p = build_create_params(j)
    assert p["ostemplate"] == "local:vztmpl/debian-12.tar.zst"
    assert p["net0"] == "name=eth0,bridge=vmbr0,ip=dhcp", "a guest needs a NIC"
    assert p["rootfs"] == "local-lvm:30"
    assert p["features"] == "nesting=1"
    assert p["unprivileged"] == 1 and p["start"] == 1
    assert not hasattr(j, "storage_template")


def test_dry_run_prints_exactly_what_the_real_run_would_issue():
    """The preview and the real call must come from one builder, or the dry run
    is reassuring about a command that never runs."""
    from bothy.deploy import DeployJob, dry_run_runner, format_create
    j = DeployJob(key="gitea", name="Gitea", node="n", storage="local-lvm",
                  template="local:vztmpl/debian-12.tar.zst", hostname="gitea")
    expected = format_create(j)
    dry_run_runner(j)
    printed = [l.text for l in j.log if l.text.startswith("pct create")]
    assert printed == [expected], (printed, expected)
    assert "--net0" in expected and "--ostemplate" in expected


def test_pick_template_fails_loudly_when_the_node_has_none():
    """Silently downloading a template would be a surprising side effect of
    pressing Deploy."""
    from bothy.deploy import pick_template

    class FakeStorageList:
        def get(self, **kw):
            return []

    class FakeNode:
        storage = FakeStorageList()

        def __call__(self, _name):
            return self

        @property
        def content(self):
            return FakeStorageList()

    class FakeApi:
        def nodes(self, _n):
            return FakeNode()

    try:
        pick_template(FakeApi(), "n")
    except RuntimeError as e:
        assert "no LXC template" in str(e)
    else:
        raise AssertionError("expected a RuntimeError when no template exists")


def test_dhcp_is_not_an_address():
    """`ip=dhcp` in an LXC config is a directive, not an address. Taking it
    literally gave DHCP guests the address "dhcp" and failed every probe."""
    from bothy.config import ProviderConfig
    from bothy.providers.proxmox import ProxmoxProvider

    class Getter:
        def __init__(self, payload): self._p = payload
        def get(self, **kw): return self._p

    class FakeLxc:
        def __init__(self, net, ifaces):
            self.config = Getter({"net0": net})       # .config.get()
            self.interfaces = Getter(ifaces)          # .interfaces.get()

    class FakeNode:
        def __init__(self, lxc): self._lxc = lxc
        def lxc(self, _vmid): return self._lxc

    class FakeApi:
        def __init__(self, lxc): self._n = FakeNode(lxc)
        def nodes(self, _n): return self._n

    prov = ProxmoxProvider(ProviderConfig(name="x", host="h", password="p"))

    static = Service(vmid=1, hostname="a", address="", node="n", status="running")
    prov._enrich_addresses(FakeApi(FakeLxc("name=eth0,ip=10.0.0.5/24", [])), [static])
    assert static.address == "10.0.0.5", static.address

    dyn = Service(vmid=2, hostname="b", address="", node="n", status="running")
    prov._enrich_addresses(
        FakeApi(FakeLxc("name=eth0,ip=dhcp,type=veth",
                        [{"name": "lo", "inet": "127.0.0.1/8"},
                         {"name": "eth0", "inet": "203.0.113.156/24"}])), [dyn])
    assert dyn.address == "203.0.113.156", dyn.address

    # a stopped guest is never probed, and no address is invented
    stopped = Service(vmid=3, hostname="c", address="", node="n", status="stopped")
    prov._enrich_addresses(FakeApi(FakeLxc("name=eth0,ip=dhcp", [])), [stopped])
    assert stopped.address == ""


def test_importer_derives_links_from_ids_we_already_hold():
    from bothy.importer import derived_links

    defs = {
        "ark": {"env_vars": [{"name": "STEAM_APP_ID", "default": "376030"},
                             {"name": "LINUXGSM_NAME", "default": "arkserver"}]},
        "mc": {"env_vars": [{"name": "LINUXGSM_NAME", "default": "mcserver"}]},
        "plex": {"env_vars": [{"name": "CLAIM_TOKEN", "default": "x"}]},
        "junk": {"env_vars": [{"name": "STEAM_APP_ID", "default": "not-a-number"}]},
    }
    got = derived_links(defs)
    # an app ID is more specific than a server name, so it wins
    assert got["ark"] == ("https://store.steampowered.com/app/376030/", "steam app id")
    assert got["mc"] == ("https://linuxgsm.com/servers/mcserver/", "linuxgsm name")
    assert "plex" not in got                  # nothing to derive from
    assert "junk" not in got                  # never build a URL from a non-numeric id


def test_importer_never_overwrites_an_existing_link():
    from bothy.importer import enrich

    defs = {"gitea": {"name": "Gitea", "upstream": "https://mine.example.com"}}
    out, stats = enrich(defs, {"gitea": {"website": "https://about.gitea.com"}}, {}, {})
    assert out["gitea"]["upstream"] == "https://mine.example.com"
    assert stats["already had one"] == 1


def test_importer_enrich_precedence():
    from bothy.importer import enrich

    defs = {
        "a": {"name": "A", "env_vars": [{"name": "STEAM_APP_ID", "default": "10"}]},
        "b": {"name": "Bee"},
        "c": {"name": "Cee"},
        "d": {"name": "Dee"},
    }
    meta = {"a": {"website": "https://meta-a"}, "b": {"website": "https://meta-b"}}
    ash = {"cee": "https://ash-c"}
    gsm = {"deeserver": {"name": "Dee", "server": "deeserver", "os": ""}}
    out, stats = enrich(defs, meta, ash, gsm)
    # an ID we already store beats another catalogue's slug match
    assert out["a"]["upstream"] == "https://store.steampowered.com/app/10/"
    assert out["b"]["upstream"] == "https://meta-b"
    assert out["c"]["upstream"] == "https://ash-c"
    assert out["d"]["upstream"] == "https://linuxgsm.com/servers/deeserver/"
    assert "unresolved" not in stats          # all four were resolvable
    assert sum(stats.values()) == len(defs)   # every definition is accounted for


def test_importer_slug_keys_do_not_collide():
    from bothy.importer import _slug_key

    taken = {}
    for name in ("ARK: Survival Evolved", "ARK Survival Evolved", "ark survival evolved"):
        taken[_slug_key(name, taken)] = 1
    assert sorted(taken) == ["ark-survival-evolved", "ark-survival-evolved-2",
                             "ark-survival-evolved-3"]


def test_importer_handles_both_docker_image_shapes():
    from bothy.importer import _images

    assert _images({"Java 21": "ghcr.io/x:21"}) == ["ghcr.io/x:21"]   # newer eggs
    assert _images(["ghcr.io/x:21"]) == ["ghcr.io/x:21"]              # older eggs
    assert _images(None) == [] and _images("") == []


def test_demo_mode_touches_nothing_real():
    """Demo mode must be safe to run on a machine with real credentials."""
    import ipaddress
    import os

    from bothy.demo import demo_estate, demo_history, demo_providers
    from bothy.history import store_path
    from bothy.web import create_app

    # every sample address is documentation space, so a screenshot cannot leak
    # a topology and a stray probe cannot reach anyone's network
    for s in demo_estate().services:
        assert ipaddress.ip_address(s.address) in ipaddress.ip_network("203.0.113.0/24"), s.address

    assert demo_history()._path != store_path()      # never the real event log

    os.environ["BOTHY_DEMO"] = "1"
    os.environ["BOTHY_DEPLOY"] = "real"              # must not be honoured in demo
    try:
        app = create_app()
        st = app.extensions["bothy"]
        assert st["demo"] is True
        assert st["dry_run"] is True, "demo mode must never reach the real runner"
        assert len(st["estate"].services) == 15
        client = app.test_client()
        assert client.post("/actions/provider-save",
                           data={"name": "x", "type": "proxmox"}).status_code == 403
    finally:
        os.environ.pop("BOTHY_DEMO", None)
        os.environ.pop("BOTHY_DEPLOY", None)


def test_install_clean_output():
    from bothy.install import clean_output

    # npm and apt draw with CSI sequences and braille spinners under a PTY
    assert clean_output("\x1b[1G\x1b[0K⡦1 packages seeking funding") == \
        "1 packages seeking funding"
    assert clean_output("\x1b[1mnpm\x1b[22m \x1b[96mnotice\x1b[39m New version") == \
        "npm notice New version"
    # a carriage return redraws the line: only the final state was ever visible
    assert clean_output("0% [Working]\r50% [Working]\r100% [Done]") == "100% [Done]"
    # a PTY writes \r\n, so ordinary lines arrive with a trailing CR — dropping
    # the whole line here blanked every line of a six-minute install
    assert clean_output("Hit:1 http://deb.debian.org bookworm InRelease\r") == \
        "Hit:1 http://deb.debian.org bookworm InRelease"
    assert clean_output("Setting up nodejs ...\r\r") == "Setting up nodejs ..."
    # dpkg overlays a progress bar between save- and restore-cursor, then writes
    # the real message; the bar is transient, the message is the log
    assert clean_output("\x1b7Progress: [ 89%] [####..] \x1b8Setting up gpgsm") == \
        "Setting up gpgsm"
    assert clean_output("plain line unaffected") == "plain line unaffected"


def test_install_render_quotes_env():
    from bothy.install import render

    import shlex

    nasty = "a b'c$d\"e"
    out = render("#!/bin/bash\necho hi", {"PW": nasty, "bad-name": "x"})
    line = next(l for l in out.splitlines() if l.startswith("export PW="))
    # the whole assignment must parse back as ONE shell word with the value intact,
    # so spaces, quotes and $ cannot break out into the surrounding shell
    assert shlex.split(line) == ["export", f"PW={nasty}"], shlex.split(line)
    assert "bad-name" not in out          # not a valid identifier, never exported
    assert out.endswith("echo hi")
    assert render("echo hi", {}) == "echo hi"     # no env, script untouched


def test_install_filtered_drops_noise():
    from bothy.install import filtered

    got = []
    sink = filtered(lambda kind, text: got.append(text), {"TOKEN": "s3cret-value"})
    for raw in ["W: retrying", "W: retrying", "W: retrying", "",
                "\x1b[0K", "auth with s3cret-value", "done"]:
        sink(raw)
    # duplicates and lines that clean to nothing never reach the log
    assert got == ["W: retrying", "auth with $(TOKEN)", "done"], got


def test_install_run_drains_the_whole_stream():
    """Regression: polling exit_status_ready() dropped buffered output.

    A six-minute install reported success with one line of log, because the
    process exited while thousands of lines were still in the channel buffer.
    """
    from bothy.install import NodeSSH

    class FakeChan:
        def __init__(self, chunks):
            self.chunks = list(chunks)

        def settimeout(self, t): pass
        def get_pty(self): pass
        def exec_command(self, cmd): self.cmd = cmd
        def recv(self, n):
            return self.chunks.pop(0) if self.chunks else b""
        def recv_exit_status(self): return 0

    class FakeClient:
        def __init__(self, chan): self.chan = chan
        def get_transport(self):
            return type("T", (), {"open_session": lambda _s: self.chan})()

    chan = FakeChan([b"first\nsecond\n", b"third\n", b"tail without newline"])
    ssh = NodeSSH(host="h")
    ssh._client = FakeClient(chan)

    got = []
    assert ssh.run("cmd", got.append) == 0
    assert got == ["first", "second", "third", "tail without newline"], got


def test_deploy_log_is_capped():
    from bothy.deploy import HEAD_LOG_LINES, MAX_LOG_LINES, DeployJob

    job = DeployJob(key="k", name="K")
    for i in range(MAX_LOG_LINES + 900):
        job.emit("detail", f"line {i}")
    assert len(job.log) <= MAX_LOG_LINES + 1, len(job.log)
    # the head — the commands that were actually run — is never what gets dropped
    assert job.log[0].text == "line 0"
    assert job.log[HEAD_LOG_LINES - 1].text == f"line {HEAD_LOG_LINES - 1}"
    assert job.log[-1].text == f"line {MAX_LOG_LINES + 899}"
    assert any("trimmed" in l.text for l in job.log)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(fns)} passed")
