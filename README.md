# Bothy

**Deploy things to your homelab without remembering how you did it last time.**

A web console, a native Windows client and a CLI over one shared data layer.
Point it at a Proxmox cluster and it reads your estate, browses a catalog of
~686 application definitions, and deploys them — dry-run first, always.

![Overview](docs/screenshots/W1-overview.png)

## Look around first

Bothy is useless without a provider, which makes it awkward to evaluate. So
there is a demo mode: a fixed sample estate, no provider contacted, deploys
forced to dry run.

```bash
pip install flask
BOTHY_DEMO=1 python -m bothy.cli serve --port 8760
```

Open <http://127.0.0.1:8760>. Nothing in it is real, including the addresses —
that is also why every screenshot here is safe to publish.

## Two ideas

Bothy is the public successor to a private homelab deployer. The redesign fixes
the two things that made the old single-page UI stop working.

**Categories are not navigation.** Once a catalog passes a few hundred entries,
a category dropdown is a filing cabinet, not a way in. Bothy browses by *facets*
— deployment type, footprint, audit state — plus collections you define
yourself. Category survives as an auditable field and nothing more.

![Catalog](docs/screenshots/W2-catalog.png)

**Definitions carry an audit state.** Verified, unreviewed, or broken link —
surfaced in the catalog, in a dedicated audit queue, and as live reachability
checks against the running estate. The audit is a real HTTP checker, and its
headline finding is an absence: of 686 definitions, **zero** declare their own
upstream link.

![Audit queue](docs/screenshots/W7-audit-queue.png)

## Deploying

Select one app or twenty, configure the batch, and watch it run. The queue polls
live, pauses, aborts, and tails the log with Follow. Install scripts run inside
the new guest with their output streamed as it happens.

![Queue](docs/screenshots/W4-queue.png)

Deploys are **dry-run by default**. The preview prints the exact `pct create`
the real run will issue — same code path, same resolved template — because a
preview that shows a different command than the real call is worse than no
preview. `BOTHY_DEPLOY=real` is the only thing that opts in.

## A real Windows client

Not a browser in a frame. WPF on .NET 8, reading the same REST API: a tree of
nodes, a sortable estate grid, a detachable deployment monitor, a tray icon, and
`F5` / `Ctrl+M` / `Ctrl+B` where you expect them.

![Windows client](docs/screenshots/D1-main-window.png)

<details>
<summary>Deploy wizard, monitor, provider sheet, tray</summary>

![Deploy wizard](docs/screenshots/D2-deploy-wizard.png)
![Monitor](docs/screenshots/D3-monitor.png)
![Provider properties](docs/screenshots/D4-provider-properties.png)
![Tray and toast](docs/screenshots/D5-tray-toast.png)

</details>

**[→ Every screen, full size](docs/screenshots.md)**

## Run it for real

```bash
export BOTHY_CATALOG=/path/to/containers.py      # or a catalog JSON snapshot
python -m bothy.cli serve --port 8760            # web console
python -m bothy.cli catalog -s git --type lxc    # CLI
python -m bothy.cli audit
python tests/test_catalog.py                     # 33 checks, no framework
```

```powershell
cd desktop; dotnet build -c Release
.\bin\Release\net8.0-windows\Bothy.exe
```

Credentials go in `~/.bothy/config.toml`, never in the repository.
**[→ Configuration](docs/configuration.md)**

## What works

| | |
|---|---|
| Estate | live, from the Proxmox `cluster/resources` API |
| Reachability audit | real parallel HTTP probes, estate-wide or per service |
| Catalog | facets, search, sort, multi-select, saved collections |
| Catalog link audit | real HTTP checks, persisted, via CLI or the UI |
| Deploy | batches, live queue, pause/resume/abort, on-failure policy |
| Install scripts | run inside the guest, output streamed to the log |
| Providers | add-provider wizard, test-before-save, real handshake |
| History | deploys, audits, provider and collection changes |
| Windows client | D1–D5 built, live estate over `/api/estate` |

Bothy targets Proxmox. The config layer is provider-agnostic and the wizard
lists other types, but none of them have an adapter and they refuse to test
rather than pretend to connect — an AWS or Azure adapter is not something this
project can honestly verify.

## Layout

```
bothy/
  catalog.py     definitions, facets, audit state
  estate.py      services, reachability, deploy queue
  deploy.py      queue engine, dry run, Proxmox runner
  install.py     install scripts inside the guest, over SSH
  demo.py        the sample estate behind BOTHY_DEMO=1
  cli.py         command line
  web/           Flask + Jinja console
desktop/         native Windows client (WPF, .NET 8)
docs/            screenshots, capture scripts, the writing
tests/
```

## Docs

- **[Screens](docs/screenshots.md)** — every screenshot, full size
- **[Configuration](docs/configuration.md)** — credentials, environment, catalog sources
- **[Decisions](docs/decisions.md)** — why things behave the way they do, mostly because the obvious version was wrong first
- **[Catalog sources](docs/catalog-sources.md)** — where definitions and upstream links can come from, and what each is worth

## License

MIT — see [LICENSE](LICENSE).
