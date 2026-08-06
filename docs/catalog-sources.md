# Catalog sources

An audit of where definitions and upstream links can come from, and what each
source is actually worth. Measured 2026-08-06 against our 686-definition
catalog.

## The problem this solves

Bothy's catalog audit reports that **0 of 686 definitions declare their own
upstream link**. That is a real finding, not a checker bug — the definitions
simply never carried the field. Everything below is about closing that gap
without hand-writing 686 URLs.

## What we can reach today

| Source | Entries | Has upstream URL | Licence | Notes |
|---|---:|---|---|---|
| [community-scripts/ProxmoxVE](https://github.com/community-scripts/ProxmoxVE) | 593 apps | via metadata JSON | MIT | 577 `ct/` + 16 `vm/`. The scripts themselves carry no metadata |
| [awesome-selfhosted-data](https://github.com/awesome-selfhosted/awesome-selfhosted-data) | 1,341 | `website_url` + `source_code_url` | CC-BY-SA | Richest. Also carries licence, platform, `archived`, release date |
| [YunoHost/apps](https://github.com/YunoHost/apps) | 703 | `url` on every entry | — | One `apps.toml`; also a maturity `level` and `state` |
| [getumbrel/umbrel-apps](https://github.com/getumbrel/umbrel-apps) | 394 | per-app manifest | — | |
| [runtipi-appstore](https://github.com/runtipi/runtipi-appstore) | 272 | per-app `config.json` | — | |
| [CasaOS-AppStore](https://github.com/IceWhaleTech/CasaOS-AppStore) | 166 | per-app manifest | — | |
| [LinuxGSM](https://github.com/GameServerManagers/LinuxGSM) | 140 game servers | `linuxgsm.com/servers/<name>/` | MIT | `lgsm/data/serverlist.csv` |
| Steam store | — | `store.steampowered.com/app/<id>/` | — | We already hold the app IDs; see below |

### community-scripts metadata is not where you expect

The per-app JSON that backs community-scripts.org is **not in the main repo**.
It lives in, in order of freshness:

| Repo | Entries | State |
|---|---:|---|
| `community-scripts/ProxmoxVE-Local` | 407 | current (`scripts/json/`) |
| `community-scripts/ProxmoxVED` | 115 | dev instance (`json/`) |
| `community-scripts/ProxmoxVE-Frontend-Archive` | 484 | **archived**, frozen 2026-03-12 |

Merged and deduplicated by slug: **607 entries, 582 with a `website`**. The
schema is good — `website`, `documentation`, `logo`, `categories`,
`interface_port`, `config_path`, `default_credentials`, and per-install-method
`resources` (cpu/ram/hdd/os/version).

community-scripts.org itself returns 403 to non-browser clients and exposes no
JSON API, so the repos are the only practical route.

## We already hold more than we thought

The definitions carry `STEAM_APP_ID` and `LINUXGSM_NAME` inside `env_vars`.
Those are exact identifiers, not guesses, and they resolve directly:

- `STEAM_APP_ID` → `https://store.steampowered.com/app/<id>/` — 91 definitions
- `LINUXGSM_NAME` → `https://linuxgsm.com/servers/<name>/` — 136 definitions

Spot-checked: Steam returns 200 or 302 (its own canonical redirect, which the
audit already counts as reachable); LinuxGSM returns 200.

## Coverage if we use all of it

| Source | Definitions it resolves |
|---|---:|
| community-scripts metadata | 298 |
| `STEAM_APP_ID` we already store | 91 |
| `LINUXGSM_NAME` we already store | 68 |
| awesome-selfhosted, matched by name | 50 |
| **Covered** | **507 of 686 (73%)** |
| Still unresolved | 179 |

The 179 remainder is 85 game servers, then long tails of DevOps (13), network
(10), productivity (9) and hypervisor (9) entries.

## Growth

community-scripts has 593 apps to our 686, so it is not bigger than us — but
the overlap is only 292. After discounting 27 `alpine-`/`debian-` re-spins of
apps we already carry, it holds **274 genuinely new applications**. Pulling
those in takes the catalog to roughly **960**.

awesome-selfhosted's 1,341 entries overlap heavily with what we and
community-scripts already have, but it is the best source for *metadata* rather
than *definitions*: it has no deployment recipe, only a description of the
software.

## Dead ends

- **Steam's bulk app list is gone.** `ISteamApps/GetAppList` now answers
  `Method 'GetAppList' not found in interface 'ISteamApps'`. Name→appid lookup
  needs `IStoreService/GetAppList` and an API key. This only matters for game
  servers that do not already carry a `STEAM_APP_ID`.
- **community-scripts.org has no public API.** 403 without a browser
  user-agent, and no JSON endpoint under `/api`.

## Worth stealing beyond links

- **`archived: true`** in awesome-selfhosted, and YunoHost's `state` / `level`.
  A link can return 200 long after a project is abandoned; "upstream is alive"
  and "upstream still exists" are different questions, and the audit currently
  only asks the first.
- **`interface_port`, `config_path`, `default_credentials`** from
  community-scripts — all things a deploy panel would otherwise ask the user for.
- **Logos.** [selfhst/icons](https://github.com/selfhst/icons) is the CDN
  community-scripts already points at. Our `icon` field currently holds strings
  like `play-circle` and `folder`, which are generic glyph names, not app logos.
