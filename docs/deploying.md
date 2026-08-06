# Deploying

## The three modes

| Mode | How | What happens |
|---|---|---|
| Demo | `BOTHY_DEMO=1` | sample estate, no provider contacted, deploys always simulated |
| Dry run | default | real catalog and provider, commands printed, nothing created |
| Real | `BOTHY_DEPLOY=real` | containers are actually created |

Dry run is the default because creating infrastructure should be a deliberate
choice. `BOTHY_DEPLOY=real` is the only value that opts in — unset, empty or a
typo all stay dry. Demo mode overrides it.

## What a deploy does

1. **Select a template.** `pick_template()` chooses one already present on the
   node, preferring `debian-12`. If the node has none it fails loudly rather
   than downloading one as a side effect of pressing Deploy.
2. **Reserve a VMID**, from `cluster/nextid` unless you supplied one.
3. **Create the container** with `nodes(node).lxc.post(**params)`, then poll the
   task until it stops. A non-`OK` exit status raises.
4. **Run the install script**, if the definition has one.

## Install scripts

The script is written to a file, `pct push`ed into the guest and run with
`pct exec bash`. Uploading rather than interpolating means quoting inside the
script can never change the command being run.

Environment values are `shlex`-quoted, so a password containing a space, a
quote or a `$` cannot break out into the surrounding shell. Values of variables
the definition marks `secret` are replaced with `$(NAME)` before any line
reaches the log.

Output is streamed line by line as it happens. A four-thousand-line `apt`
install that only appears once it finishes is not a log, it is a receipt.

Timeout is 1800 seconds per script, which is enough for the slow ones —
GitLab's reconfigure runs for minutes.

## Batches

Select several definitions, or a whole collection, and configure them together.
Jobs run one at a time on a worker thread.

`on_failure` decides what happens when one fails:

| Value | Behaviour |
|---|---|
| `stop` | remaining jobs are marked **blocked** with a reason — never silently skipped |
| `continue` | the rest still run |
| `rollback` | not implemented; halts like `stop` and destroys nothing |

Only `continue` carries on. Anything else halts, including an unknown value —
a policy Bothy does not understand must not be the permissive one. `rollback`
is offered in the UI but does not yet undo anything; it currently just stops.

A batch can be paused, resumed and aborted while it runs.

## Reading the preview

```
pct create <next> --hostname gitea --ostemplate local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst
  --cores 2 --memory 2048 --rootfs local-lvm:30 --net0 name=eth0,bridge=vmbr0,ip=dhcp
  --unprivileged 1 --start 1
```

This is the command the real run issues — both come from
`deploy.build_create_params()`, and the dry run resolves the same template from
the same node. If the preview and the real call could differ, the preview would
be worse than useless.

`<next>` appears when no VMID was supplied; a real run resolves it against the
cluster.

## Before you go real

- Confirm the target node has an LXC template: `pveam list local`.
- Deploy one definition to a scratch VMID first, then destroy it.
- Check the definition's environment variables — anything `required` and
  `secret` must be supplied or the install script will run without it.
- Remember the deploy path has no undo. Bothy will not destroy a container it
  created if the install script fails; the container is left in place so you can
  read `/root/bothy-install.sh` and the guest's own logs.

## Nesting and privilege

`unprivileged` defaults to true. `nesting` is off unless the definition asks
for it — Docker-in-LXC needs it, most things do not. Both are per-job fields on
`DeployJob`, so a definition that needs nesting carries it rather than relying
on a global default.
