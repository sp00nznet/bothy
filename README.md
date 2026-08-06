# Bothy

Multi-provider infrastructure deployment console — a web console, a native Windows
client and a CLI over one shared data layer.

Bothy is the public successor to a private homelab deployer. The redesign fixes two
problems the old single-page UI had: a catalog of ~686 definitions that no longer fit
one page, and category/link data nobody trusted.

- **Categories are not navigation.** The catalog is browsed by *facets* — deployment
  type, footprint, audit state — plus user-defined collections. Category survives as an
  auditable field only.
- **Definitions carry an audit state.** Verified / Unreviewed / Broken link, surfaced in
  the catalog, an audit queue, and per-service reachability checks in the estate views.

## Layout

```
bothy/
  catalog.py     definitions, facets, audit state
  estate.py      services, reachability, deploy queue
  cli.py         command line
  web/           Flask + Jinja console (templates/, static/)
desktop/         native Windows client (WPF, .NET 8)
docs/            screenshots + capture scripts
tests/
```

## Run

Bothy needs a provider to be useful, so there is a demo mode for looking around
before you hand it credentials. It serves a fixed sample estate, never contacts a
provider, and forces dry run — a demo should not be one environment variable away
from creating containers.

```bash
BOTHY_DEMO=1 python -m bothy.cli serve --port 8760
```

Every screenshot in `docs/` is captured this way, which is also why none of them
publish a real hostname: the sample addresses are RFC 5737 documentation space.

```bash
pip install flask
export BOTHY_CATALOG=/path/to/containers.py      # or a catalog JSON snapshot
python -m bothy.cli serve --port 8760            # web console
python -m bothy.cli catalog -s git --type lxc    # CLI
python -m bothy.cli audit
python tests/test_catalog.py
```

```powershell
cd desktop; dotnet build -c Release
.\bin\Release\net8.0-windows\Bothy.exe
.\bin\Release\net8.0-windows\Bothy.exe --shot out.png   # render itself to PNG
.\bin\Release\net8.0-windows\Bothy.exe --screen monitor # deploy | monitor | provider | tray
```

`BOTHY_CATALOG` accepts the legacy `containers.py` directly — it imports
`CONTAINER_DEFINITIONS` and `VM_DEFINITIONS` — or a JSON snapshot written by
`Catalog.to_json()`.

## Screens

| | Built | Screenshot |
|---|---|---|
| W1 Overview | ✅ | `docs/screenshots/W1-overview.png` |
| W2 Catalog + facets | ✅ | `docs/screenshots/W2-catalog.png` |
| W3 App detail + deploy panel | ✅ | `docs/screenshots/W3-deploy-panel.png` |
| W4 Queue + log | ✅ live engine, polling, log tail | `docs/screenshots/W4-queue.png` |
| W5 Providers + add wizard | ✅ | `docs/screenshots/W5-wizard-credentials.png` |
| W6 Service detail | ✅ | `docs/screenshots/W6-service.png` |
| D1 Windows main window | ✅ reads the REST API | `docs/screenshots/D1-main-window.png` |
| D2 Deploy wizard | ✅ | `docs/screenshots/D2-deploy-wizard.png` |
| D3 Detachable monitor | ✅ | `docs/screenshots/D3-monitor.png` |
| D4 Provider property sheet | ✅ | `docs/screenshots/D4-provider-properties.png` |
| D5 Tray + toast | ✅ | `docs/screenshots/D5-tray-toast.png` |

## Configuration

Credentials never live in the repo. Bothy reads them from, in order:

1. `$BOTHY_CONFIG` — explicit path to a TOML file
2. `~/.bothy/config.toml`
3. `BOTHY_PROXMOX_HOST` / `_USER` / `_PASSWORD` / `_TOKEN_ID` / `_TOKEN_SECRET`

```toml
[[providers]]
name = "Home lab"
type = "proxmox"
host = "192.168.1.10"
user = "root@pam"
password = "..."        # or token_id + token_secret
verify_ssl = false
default = true
```

Collections persist to `~/.bothy/collections.json`.

## What works

| | |
|---|---|
| Estate | live, from the Proxmox `cluster/resources` API |
| Refresh | re-reads every provider, keeps the last audit |
| Reachability audit | real parallel HTTP probes, estate-wide or per service |
| Catalog facets, search, sort | live over the definition set |
| Multi-select + Save as collection | persisted to disk |
| Filter chips | click to remove that one filter |
| Test connections | real provider handshake |
| `Ctrl/Cmd K` | focuses search |
| Deploy | queues a batch; engine runs jobs, streams logs, honours on-failure |
| Queue | live polling, pause / resume / abort, log tail with Follow |
| Windows client | loads the live estate from `/api/estate`; D1–D5 built |
| Catalog link audit | real HTTP checks, persisted, `bothy audit --run` or the UI |
| Audit queue | `/audit` — every definition, its state and the actual finding |
| History | `/history` — deploys, audits, provider and collection changes |
| Windows shortcuts | `F5` refresh · `Ctrl+M` monitor · `Ctrl+B` deploy |
| Batch deploy | select in the catalog (or a whole collection) → configure → queue |
| Add-provider wizard | provider-specific fields, test-before-save, writes `~/.bothy/config.toml` |

## Notes

- **The audit is real, and its headline finding is an absence.** Running it over the
  686-definition catalog: **0 declare their own upstream link**, 35 reference a URL only
  inside their install script, and 651 reference nothing at all. So the audit reports
  "no upstream link recorded" for most of the catalog — that is the finding, not a
  checker failure, and it is exactly the problem the handoff describes.
- **Dependency URLs can never make a definition "verified".** An install script that
  fetches `download.docker.com` says nothing about whether *this* app's upstream is
  alive; dozens of unrelated apps share that URL. Only a link the definition itself
  declares can verify it — a dependency URL can only ever mark it *broken*.
- **A 401/403 is not a broken link.** An apt repository root returns 403 by design while
  every file beneath it serves fine; only 404/410, 5xx and transport failures count.
  Without this the checker flagged Plex and Jellyfin's healthy repos as broken.
- Until a definition is audited, `catalog._audit_for()` supplies a deterministic
  provisional state so the UI is populated and tests do not churn. Stored audit results
  always override it.
- **Route colours mean what they say.** A `3xx`/`4xx` means the service answered — it is
  reachable, just redirecting or protected — and does not count as an outage. Only `5xx`,
  timeouts and refused connections feed "needs attention".
- **Guests seen through two nodes of one cluster are deduplicated.** Every Proxmox node
  reports the whole cluster, so two configured members would otherwise list each guest
  twice.
- Sample data lives in `tests/fixtures.py`, never in the shipped package.
- **Deploys are dry-run by default.** `BOTHY_DEPLOY=real` opts into creating
  containers; anything else logs the exact commands without touching the cluster.
  Creating infrastructure should be a deliberate choice, not a mis-click.
- **The dry run prints the command the real run issues** — both come from
  `deploy.build_create_params()`, and the dry run resolves the same template from
  the target node. A preview that shows a different command than the real call is
  worse than no preview.
- **The real runner picks a template already on the node** and fails loudly if there
  is none, rather than downloading one as a side effect of pressing Deploy.
- **`ip=dhcp` is a directive, not an address.** An LXC config for a DHCP guest literally
  contains `ip=dhcp`; parsing it as the address gave such guests the address "dhcp" and
  failed every reachability probe. Bothy now asks the running guest what it actually got.
- **The wizard only offers what exists.** Provider types without an adapter are listed
  (so you can see what Bothy will support) but marked "no adapter yet" and refuse to
  test, rather than pretending to connect. Only Proxmox is implemented.
- **Saving a provider rewrites `~/.bothy/config.toml`** and keeps one generation at
  `config.toml.bak`. The file is chmod 600 on POSIX.
- The Windows client reads `BOTHY_API` (default `http://127.0.0.1:8760`). If the API is
  unreachable it keeps its placeholder rows and says so in the status bar rather than
  showing an empty window.
- Screenshots are captured at 2× — the web via Playwright (`docs/shoot.py`), the desktop
  by the app rendering its own visual tree (`--shot`), because `Graphics.CopyFromScreen`
  returns blank for DWM-composited WPF windows.

## Design tokens

Dark, Fluent-derived. Full token table in the design handoff; the implementation lives in
`bothy/web/static/bothy.css` (`:root`) and `desktop/Theme.xaml`. Accent `#4cc2ff`,
app background `#141417` (web) / `#202024` (Windows), monospace for every identifier,
IP, VMID and log line. No webfonts, no images, no icon fonts — the Windows client uses
Segoe Fluent Icons.
