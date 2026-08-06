"""Deploy engine — the queue behind W4.

A job runs on a worker thread and appends to its own log buffer, which the web
console tails. Jobs are never silently dropped: a failure records the reason and
the on-failure policy decides whether the rest of the batch continues.

`dry_run` is the default. Creating a container is irreversible enough that it
should be an explicit choice, not something a mis-click does.
"""
from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable

QUEUED, RUNNING, COMPLETE, FAILED, BLOCKED, CANCELLED = (
    "queued", "installing", "complete", "failed", "blocked", "cancelled")

_batch_counter = itertools.count(1)

MAX_LOG_LINES = 4000       # ceiling per job; the middle is trimmed, never the head
HEAD_LOG_LINES = 40        # the configured commands, always kept


@dataclass
class LogLine:
    t: str
    kind: str          # cmd | detail | ok | secret | error
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeployJob:
    key: str                       # definition key
    name: str
    target: str = ""               # "pve01 · vmid 120"
    node: str = ""
    vmid: int | None = None
    storage: str = ""
    cores: int = 1
    memory_mb: int = 512
    disk_gb: int = 8
    hostname: str = ""
    template: str = ""             # e.g. local:vztmpl/debian-12-standard_....tar.zst
    bridge: str = "vmbr0"
    unprivileged: bool = True
    nesting: bool = False
    start_after: bool = True
    install_script: str = ""       # bash, run inside the guest after creation
    env: dict = field(default_factory=dict)
    secret_names: list = field(default_factory=list)
    status: str = QUEUED
    pct: int = 0
    step: str = ""
    reason: str = ""
    started_at: float | None = None
    ended_at: float | None = None
    log: list[LogLine] = field(default_factory=list)

    @property
    def elapsed(self) -> str:
        if not self.started_at:
            return "—"
        end = self.ended_at or time.time()
        s = int(end - self.started_at)
        return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"

    def emit(self, kind: str, text: str) -> None:
        # An install script is arbitrary user bash; nothing stops it printing
        # forever. Keep the head (what was configured) and drop from the middle,
        # so a runaway tail can never cost unbounded memory.
        if len(self.log) >= MAX_LOG_LINES:
            del self.log[HEAD_LOG_LINES:HEAD_LOG_LINES + 500]
            self.log.insert(HEAD_LOG_LINES,
                            LogLine("", "detail", "… earlier output trimmed …"))
        self.log.append(LogLine(time.strftime("%H:%M:%S"), kind, text))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["elapsed"] = self.elapsed
        d["log"] = [l.to_dict() for l in self.log]
        return d


class Batch:
    def __init__(self, jobs: list[DeployJob], on_failure: str = "stop"):
        self.id = next(_batch_counter)
        self.jobs = jobs
        self.on_failure = on_failure      # stop | continue | rollback
        self.created_at = time.time()
        self.paused = False
        self.aborted = False

    @property
    def done(self) -> int:
        return sum(1 for j in self.jobs if j.status in (COMPLETE, FAILED, CANCELLED))

    @property
    def finished(self) -> bool:
        return all(j.status in (COMPLETE, FAILED, CANCELLED, BLOCKED) for j in self.jobs)

    def to_dict(self) -> dict:
        return {"id": self.id, "on_failure": self.on_failure, "paused": self.paused,
                "aborted": self.aborted, "done": self.done, "total": len(self.jobs),
                "finished": self.finished, "jobs": [j.to_dict() for j in self.jobs]}


class DeployEngine:
    """Runs batches one job at a time on a background thread."""

    def __init__(self, runner: Callable[[DeployJob], None] | None = None):
        self.batches: list[Batch] = []
        self._runner = runner or (lambda job: None)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ---- queries -------------------------------------------------------
    def current(self) -> Batch | None:
        return self.batches[-1] if self.batches else None

    def all_jobs(self) -> list[DeployJob]:
        return [j for b in self.batches for j in b.jobs]

    def active_count(self) -> int:
        return sum(1 for j in self.all_jobs() if j.status in (QUEUED, RUNNING))

    def get(self, batch_id: int) -> Batch | None:
        return next((b for b in self.batches if b.id == batch_id), None)

    # ---- control -------------------------------------------------------
    def submit(self, jobs: Iterable[DeployJob], on_failure: str = "stop") -> Batch:
        batch = Batch(list(jobs), on_failure)
        with self._lock:
            self.batches.append(batch)
        self._start(batch)
        return batch

    def pause(self, batch_id: int, value: bool = True) -> None:
        b = self.get(batch_id)
        if b:
            b.paused = value

    def abort(self, batch_id: int) -> None:
        b = self.get(batch_id)
        if not b:
            return
        b.aborted = True
        for j in b.jobs:
            if j.status in (QUEUED, RUNNING):
                j.status = CANCELLED
                j.reason = "aborted by user"
                j.ended_at = time.time()

    def _start(self, batch: Batch) -> None:
        self._thread = threading.Thread(target=self._run, args=(batch,), daemon=True)
        self._thread.start()

    def _run(self, batch: Batch) -> None:
        for job in batch.jobs:
            while batch.paused and not batch.aborted:
                time.sleep(0.3)
            if batch.aborted:
                break
            if job.status == BLOCKED:
                continue
            job.status = RUNNING
            job.started_at = time.time()
            try:
                self._runner(job)
                if job.status == RUNNING:
                    job.status = COMPLETE
                    job.pct = 100
                    job.step = "Install complete"
            except Exception as e:
                job.status = FAILED
                job.reason = f"{type(e).__name__}: {e}"
                job.emit("error", job.reason)
                if batch.on_failure == "stop":
                    for rest in batch.jobs:
                        if rest.status == QUEUED:
                            rest.status = BLOCKED
                            rest.reason = "stopped after an earlier failure"
                    job.ended_at = time.time()
                    break
            finally:
                if job.ended_at is None:
                    job.ended_at = time.time()


# ---------------------------------------------------------------- runners
def build_create_params(job: DeployJob) -> dict:
    """The exact arguments a real `pct create` would receive.

    Shared by the dry run and the real runner so the preview cannot drift from
    what actually executes. A dry run that prints different commands than the
    real one is worse than no dry run at all.
    """
    params = {
        "vmid": job.vmid,
        "hostname": job.hostname or job.key,
        "ostemplate": job.template or "<no template selected>",
        "cores": job.cores,
        "memory": job.memory_mb,
        "rootfs": f"{job.storage or 'local-lvm'}:{job.disk_gb}",
        "net0": f"name=eth0,bridge={job.bridge},ip=dhcp",
        "unprivileged": 1 if job.unprivileged else 0,
        "start": 1 if job.start_after else 0,
    }
    if job.nesting:
        params["features"] = "nesting=1"
    return params


def format_create(job: DeployJob) -> str:
    p = dict(build_create_params(job))
    vmid = p.pop("vmid", None) or "<next>"
    return f"pct create {vmid} " + " ".join(f"--{k} {v}" for k, v in p.items())


def dry_run_runner(job: DeployJob) -> None:
    """Walks the real steps and logs exactly what would be executed."""
    # a dry run has no cluster to ask, so show a placeholder rather than "None"
    vmid = job.vmid if job.vmid else "<next>"
    steps = [
        (10, "Reserving VMID", "cmd", f"pvesh get /cluster/nextid  ->  {vmid}"),
        (25, "Creating container", "cmd", format_create(job)),
        (45, "Starting container", "cmd", f"pct start {vmid}"),
        (60, "Resolving secrets", "secret",
         ("  resolving " + ", ".join(job.secret_names)) if job.secret_names
         else "  no secrets required by this definition"),
    ]
    job.emit("detail", "DRY RUN — no changes will be made")
    if not job.template:
        job.emit("detail", "  no template chosen; a real run selects one present on the node")
    for pct, step, kind, text in steps:
        job.pct, job.step = pct, step
        job.emit(kind, text)
        time.sleep(0.35)

    job.pct, job.step = 85, "Running install script"
    if job.install_script:
        lines = job.install_script.splitlines()
        job.emit("cmd", f"pct exec {vmid} -- bash /root/bothy-install.sh")
        job.emit("detail", f"  {len(lines)}-line script; first lines:")
        for l in [x for x in lines if x.strip()][:6]:
            job.emit("detail", "    " + l[:110])
        if len(lines) > 6:
            job.emit("detail", f"    ... {len(lines) - 6} more lines")
    else:
        job.emit("detail", "  no install script for this definition — container only")
    time.sleep(0.3)
    job.pct = 95
    job.emit("ok", f"dry run complete for {job.name}")


def pick_template(api, node: str, prefer: str = "debian-12") -> str:
    """Choose an LXC template already present on the node.

    Downloading one would be a surprising side effect of pressing Deploy, so
    this only selects from what is there and fails loudly if the node has none.
    """
    found: list[str] = []
    for store in api.nodes(node).storage.get():
        if "vztmpl" not in (store.get("content") or ""):
            continue
        try:
            for item in api.nodes(node).storage(store["storage"]).content.get(content="vztmpl"):
                found.append(item["volid"])
        except Exception:
            continue
    if not found:
        raise RuntimeError(f"no LXC template on {node} — upload one with pveam first")
    return next((v for v in found if prefer in v), found[0])


def make_proxmox_runner(provider) -> Callable[[DeployJob], None]:
    """Real deploys. Only reached when dry_run is explicitly disabled."""
    def run(job: DeployJob) -> None:
        api = provider._connect()
        node = job.node or provider.cfg.node
        if not node:
            node = api.nodes.get()[0]["node"]

        job.pct, job.step = 5, "Selecting template"
        if not job.template:
            job.template = pick_template(api, node)
        job.emit("detail", f"template {job.template}")

        job.pct, job.step = 10, "Reserving VMID"
        if not job.vmid:
            job.vmid = int(api.cluster.nextid.get())
        job.target = f"{node} · vmid {job.vmid}"
        job.emit("cmd", f"reserved vmid {job.vmid} on {node}")

        job.pct, job.step = 30, "Creating container"
        params = build_create_params(job)      # identical to what the dry run printed
        job.emit("cmd", format_create(job))
        upid = api.nodes(node).lxc.post(**params)
        job.emit("detail", f"UPID {upid}")

        job.pct, job.step = 70, "Waiting for task"
        deadline = time.time() + 600
        while True:
            st = api.nodes(node).tasks(upid).status.get()
            if st.get("status") == "stopped":
                if st.get("exitstatus") != "OK":
                    raise RuntimeError(f"pct create failed: {st.get('exitstatus')}")
                break
            if time.time() > deadline:
                raise RuntimeError("pct create did not finish within 10 minutes")
            time.sleep(1.5)

        job.pct, job.step = 80, "Container created"
        job.emit("ok", f"container {job.vmid} created on {node}")

        if job.install_script:
            from .install import NodeSSH, render, run_install

            job.pct, job.step = 85, "Running install script"
            cfg = provider.cfg
            ssh = NodeSSH(host=cfg.host,
                          user=(cfg.user or "root@pam").split("@")[0],
                          password=cfg.password,
                          key_path=(cfg.extra or {}).get("ssh_key", ""))
            secrets = {k: v for k, v in (job.env or {}).items()
                       if k in (job.secret_names or [])}
            try:
                run_install(ssh, job.vmid, render(job.install_script, job.env),
                            lambda kind, text: job.emit(kind, text), secrets)
            finally:
                ssh.close()
        else:
            job.emit("detail", "no install script for this definition — container only")

        job.pct, job.step = 100, "Install complete"
    return run
