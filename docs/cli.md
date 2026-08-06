# CLI reference

```
bothy [--catalog PATH] <command> [options]
```

`--catalog` accepts a legacy `containers.py` or a catalog JSON snapshot, and
falls back to `$BOTHY_CATALOG`. Every command takes `--json` for
machine-readable output.

## catalog

Browse definitions by facet.

```bash
bothy catalog                                  # everything, first 40
bothy catalog -s git                           # substring over name, key, description, tags
bothy catalog -t lxc -f small                  # deploy type and footprint
bothy catalog -a broken --sort audit           # only broken links, worst first
bothy catalog -s minecraft --limit 100 --json
```

| Option | Values |
|---|---|
| `-s, --search` | any substring |
| `-t, --type` | `lxc`, `vm`, `docker` — repeatable |
| `-f, --footprint` | `small`, `medium`, `large` — repeatable |
| `-a, --audit` | `verified`, `unreviewed`, `broken` — repeatable |
| `--sort` | `name`, `memory`, `audit` |
| `--limit` | default 40 |

## show

One definition in full: resources, ports, environment variables, audit state
and upstream link.

```bash
bothy show gitea
bothy show gitea --json
```

## estate

Deployed services, read live from every configured provider.

```bash
bothy estate
bothy estate --audit          # probe reachability before printing
```

Without a configured provider this prints nothing and says so, rather than
inventing rows.

## audit

Catalog link audit.

```bash
bothy audit                   # summary of stored results
bothy audit --run             # actually check every link now
```

`--run` performs real HTTP requests. A `401`/`403`/`405`/`429` counts as
reachable — the server answered. Only `404`, `410`, `5xx` and transport
failures are recorded as broken.

## import

Pull definitions and upstream links from public catalogues.

```bash
bothy --catalog containers.py import --out catalog.json
bothy --catalog catalog.json import --no-games --json
bothy --catalog containers.py import --refresh --out catalog.json
```

| Option | Meaning |
|---|---|
| `--out` | where to write the enriched catalog; without it, nothing is written |
| `--no-games` | do not add game servers from Pelican eggs or LinuxGSM |
| `--refresh` | re-download sources instead of using the daily cache |

An import writes to `--out` rather than over the input: it is a proposal to
review, not something that silently rewrites your catalog. See
[catalog sources](catalog-sources.md).

## queue

The current deploy batch, its jobs and their state.

```bash
bothy queue
```

## serve

Run the web console.

```bash
bothy serve --port 8760
BOTHY_DEMO=1 bothy serve            # sample estate, no provider contacted
BOTHY_DEPLOY=real bothy serve       # opt in to creating containers
```

| Option | Default |
|---|---|
| `--host` | `127.0.0.1` |
| `--port` | `8760` |

Bothy has no authentication. `--host 0.0.0.0` exposes an interface that can
create and destroy infrastructure to anyone who can reach the port; put it
behind something that authenticates, or leave it on loopback.
