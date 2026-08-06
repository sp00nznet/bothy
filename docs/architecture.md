# Architecture

Three clients, one data layer. The web console, the Windows client and the CLI
all read the same objects, which is why they cannot disagree about the estate —
a class of bug that shows up the moment two surfaces each fetch their own way.

```
   ┌────────────┐   ┌──────────────────┐   ┌────────────┐
   │    CLI     │   │   Web console    │   │  Windows   │
   │ bothy ...  │   │  Flask + Jinja   │   │  client    │
   └─────┬──────┘   └────────┬─────────┘   └─────┬──────┘
         │                   │  HTTP /api/*      │
         │                   └───────────┬───────┘
         │                               │
         ▼                               ▼
   ┌──────────────────────────────────────────────────────┐
   │                      data layer                      │
   │                                                      │
   │  catalog.py    definitions, facets, audit state      │
   │  estate.py     services, reachability, counts        │
   │  deploy.py     queue engine, dry run, real runner    │
   │  install.py    install scripts inside the guest      │
   │  audit.py      link checking, persisted results      │
   │  collections   saved groups of definitions           │
   │  history.py    append-only event log                 │
   └───────────────────────┬──────────────────────────────┘
                           │
                  ┌────────┴─────────┐
                  │ providers/       │
                  │  base.py         │  protocol + status
                  │  proxmox.py      │  the only adapter
                  └────────┬─────────┘
                           │ proxmoxer / HTTPS 8006
                           ▼
                  ┌──────────────────┐
                  │   Proxmox VE     │
                  │  cluster/nodes   │
                  └────────┬─────────┘
                           │ SSH (paramiko) for install scripts
                           ▼
                  ┌──────────────────┐
                  │  LXC / QEMU      │
                  │  guests          │
                  └──────────────────┘
```

## Modules

| Module | Responsibility |
|---|---|
| `bothy/catalog.py` | `Definition`, facets, search, audit state, JSON and legacy loading |
| `bothy/estate.py` | `Service`, `Estate`, reachability results, capacity and counts |
| `bothy/deploy.py` | `DeployJob`, `Batch`, `DeployEngine`, dry run and Proxmox runners |
| `bothy/install.py` | uploads and runs install scripts over SSH, streams output |
| `bothy/audit.py` | catalog link checking, `AuditStore` persistence |
| `bothy/reachability.py` | HTTP probes against running services |
| `bothy/collections.py` | user-defined groups of definitions |
| `bothy/history.py` | append-only JSONL event log |
| `bothy/config.py` | `ProviderConfig`, TOML and environment loading, safe saving |
| `bothy/importer.py` | pulls definitions and upstream links from public catalogues |
| `bothy/demo.py` | the fixed sample estate behind `BOTHY_DEMO=1` |
| `bothy/providers/` | provider protocol and the Proxmox adapter |
| `bothy/web/` | Flask app factory, blueprints, templates, static |
| `desktop/` | WPF client on .NET 8, reads `/api/*` |

## How a deploy flows

```
  catalog selection
        │
        ▼
  DeployJob(s) ──► DeployEngine.submit() ──► worker thread
        │                                        │
        │                    ┌───────────────────┤
        │                    ▼                   ▼
        │            dry_run_runner      make_proxmox_runner
        │            (prints only)               │
        │                                        ├─ pick_template()
        │                                        ├─ cluster.nextid
        │                                        ├─ nodes(n).lxc.post()
        │                                        └─ run_install() over SSH
        ▼                                                 │
   job.log ◄──────────────────── streamed, scrubbed ◄─────┘
```

Both runners build their `pct create` arguments from
`deploy.build_create_params()`, so the dry run cannot print a different command
than the real call issues. That is deliberate — see
[decisions](decisions.md#deploying).

## Provider model

`providers/base.py` defines the protocol: `test()` returns a `ProviderStatus`,
`services()` returns `Service` objects. `providers/__init__.py` holds
`KNOWN_TYPES` (what the wizard lists) and `IMPLEMENTED` (what actually has an
adapter). Only `proxmox` is implemented; the rest are listed so the shape is
visible and refuse to test rather than pretend to connect.

The Proxmox adapter reads `cluster/resources` in one call rather than walking
nodes, so a twenty-guest estate is one request. Because every node reports the
whole cluster, results are deduplicated on `(provider, node, vmid)`.

## Where state lives

Nothing is written inside the repository.

| Path | Contents |
|---|---|
| `~/.bothy/config.toml` | provider credentials, `chmod 600`, one `.bak` generation |
| `~/.bothy/collections.json` | saved collections |
| `~/.bothy/history.jsonl` | append-only event log |
| `~/.bothy/audit.json` | catalog link audit results |
| `~/.bothy/demo-history.jsonl` | demo mode only, never the real log |
| `~/.bothy/cache/` | importer source tarballs, refreshed daily |
