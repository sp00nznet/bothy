# Working through the install scripts

`catalog/` is generated. The sources stay where they are:

| Source | Gives | Precedence |
|---|---|---|
| `myhome/deployer/app` (private) | 686 definitions, 39 scripts | wins |
| `gameservers/<game>/*-setup.sh` | 22 hand-written, tested setups | next |
| `gameservers/proxmox-deployer` | 58 LinuxGSM / Docker templates | fills gaps |

```bash
python catalog/sync.py          # regenerate; fix things upstream, never in catalog/
python tests/test_catalog.py    # includes the check that no LAN map came across
```

`sync.py` strips `default_ip` (the owner's LAN layout), inlines
`lib/common.sh` into each game script, and closes stdin so a `read` prompt
cannot hang under the runner's PTY. It never reads the gitignored one-off
`*.py` at the gameservers root: they hold live credentials.

## The passes

Each script moves through these in order; its catalog audit state records how
far it got.

1. **Static**: `bash -n`, shellcheck, link audit (`bothy audit`). Flags:
   unpinned `latest`, `curl | sh`, hardcoded secrets, prompts, >16 KB (refused on AWS).
   Cheap, so run on all of them every sync.
2. **Dry run**: the exact `pct create` / `run-instances` it would issue.
3. **AWS emulator**: proves the API calls and UserData, boots nothing.
   Only for scripts under 16 KB.
4. **Proxmox, throwaway**: real deploy to a scratch LXC on one node, reachability
   probe on the definition's ports, destroy. Pass → `verified`; fail → the log
   goes on the audit queue entry and the fix goes upstream.

Batches of ~20, most-deployed first. Pass 4 is the only one that proves a
script works; everything before it is triage.

## Known after the first pass

- `gitlab-runner-windows` is PowerShell; bash cannot run it. Needs a Windows VM path or removal.
- `counterstrike` and `arkasa` folder names map by alias (`cs16`, `arksa`).
