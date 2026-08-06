# Configuration

Credentials never live in the repository. Bothy reads them from, in order:

1. `$BOTHY_CONFIG` — an explicit path to a TOML file
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

Saving a provider through the wizard rewrites this file and keeps one generation
at `config.toml.bak`. It is `chmod 600` on POSIX.

Collections persist to `~/.bothy/collections.json`, history to
`~/.bothy/history.jsonl`, and the catalog audit to `~/.bothy/audit.json`.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `BOTHY_CATALOG` | — | Path to a catalog source (see below) |
| `BOTHY_CONFIG` | `~/.bothy/config.toml` | Provider credentials |
| `BOTHY_DEMO` | unset | `1` serves a fixed sample estate, contacts no provider, forces dry run |
| `BOTHY_DEPLOY` | `dry` | `real` opts into actually creating containers |
| `BOTHY_API` | `http://127.0.0.1:8760` | Where the Windows client looks for the console |

## Catalog sources

`BOTHY_CATALOG` accepts a legacy `containers.py` directly — it imports
`CONTAINER_DEFINITIONS` and `VM_DEFINITIONS` — or a JSON snapshot written by
`Catalog.to_json()`. If the file has a sibling `install_scripts.py`, Bothy also
reads install scripts and upstream link URLs from it.

## Deploying for real

Deploys are dry-run by default. `BOTHY_DEPLOY=real` is the only thing that
reaches the runner which creates containers; anything else — unset, empty, a
typo — logs the exact commands without touching the cluster. Creating
infrastructure should be a deliberate choice, not a mis-click.

Demo mode wins over it: with `BOTHY_DEMO=1` set, `BOTHY_DEPLOY=real` is ignored.
A demo must not be one environment variable away from building something.
