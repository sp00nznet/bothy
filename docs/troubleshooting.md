# Troubleshooting

Most of these are real failures hit while building Bothy, not hypotheticals.

## Providers

### "authentication failed — check the user and password/token"

The user must include the realm: `root@pam`, not `root`. For an API token, set
`token_id` and `token_secret` and leave `password` empty — supplying both makes
proxmoxer prefer the token.

### "TLS error — try disabling certificate verification"

Proxmox ships a self-signed certificate. Set `verify_ssl = false` in
`~/.bothy/config.toml`, or tick "accept self-signed" in the wizard.

### "connection timed out" / "connection refused"

Port 8006, not 443. Check the host is reachable and `pveproxy` is running.

### The estate is empty but the provider tests fine

The provider is configured with `node = "..."` and every guest lives on a
different node. Clear `node` to read the whole cluster.

### Every guest appears twice

Two nodes of the same cluster are configured as separate providers. Every
Proxmox node reports the whole cluster, so this is expected — Bothy
deduplicates on `(provider, node, vmid)`, but two *providers* pointing at one
cluster will still double. Configure one.

## The estate

### A running service shows no address

For LXC, the address comes from `net0` in the container config. A DHCP guest
literally contains `ip=dhcp`, which is a directive, not an address; Bothy asks
the running guest what it actually got. If that also fails the field stays
blank — it will never invent one.

For QEMU there is no address in the config at all, so it needs the guest agent.
Without it, the field stays blank.

### A service is marked "needs attention" but it works

Only `5xx`, timeouts and refused connections count as unreachable. If yours is
flagged, the probe genuinely got one of those — check from the Bothy host
rather than your desktop, since it is the one doing the probing.

### A refresh wiped the audit

It should not: `adopt_reachability()` carries results onto the rebuilt
services. If results vanished, the vmid changed — results are keyed by vmid.

## Deploying

### "no LXC template on <node> — upload one with pveam first"

Bothy only selects templates already present. Download one on the node:

```bash
pveam update && pveam available | grep debian-12
pveam download local debian-12-standard_12.12-1_amd64.tar.zst
```

### The UI says "Live deploy" but nothing is created

The server must be started with `BOTHY_DEPLOY=real`, and at least one
configured Proxmox provider must exist — asking for live with nothing to deploy
to silently falls back to dry run. Demo mode always refuses.

### "pct create failed: <exitstatus>"

Read the task in the Proxmox UI. Common causes: the VMID is taken, the storage
name is wrong (`local-lvm` vs `local`), or the node is out of disk.

### The install script failed but the container still exists

Deliberate. The container is left in place so you can read
`/root/bothy-install.sh` inside it and the guest's own logs. Destroy it
yourself when done:

```bash
pct stop <vmid> && pct destroy <vmid> --purge
```

### The install log is full of `[1G[0K` or braille characters

Fixed — terminal control sequences, dpkg's save/restore-cursor progress bar and
spinner frames are stripped. If you see them again, the pattern is new: they
are handled in `install.clean_output()`.

### A six-minute install logged one line

Also fixed, and worth knowing why: the SSH channel was polled with
`exit_status_ready()`, which won the race against data still buffered in the
channel. It now reads to EOF.

### An install script hangs

The per-script timeout is 1800 seconds. Anything interactive will hang until
then — install scripts must be non-interactive. Set `DEBIAN_FRONTEND=noninteractive`
and pass `-y` to `apt-get`.

## The catalog audit

### Almost everything says "no upstream link recorded"

That is the finding, not a failure. Definitions historically carried no
upstream field. Run `bothy import` to resolve them — it recovers about two
thirds from public catalogues and from Steam and LinuxGSM identifiers already
stored in the definitions. See [catalog sources](catalog-sources.md).

### An apt repository is reported broken but works

It should not be: a `403` on a repository root is by design and counts as
reachable. Only `404`, `410`, `5xx` and transport failures are broken. If a
repository really is broken, check the `/dists/<suite>/Release` path by hand.

### A definition became "verified" and should not have

Only a link the definition itself declares can verify it. A URL that merely
appears in an install script is a dependency — dozens of apps share
`download.docker.com` — and can only ever mark a definition *broken*.

## Demo and screenshots

### Demo mode shows my real providers

It cannot; `BOTHY_DEMO=1` replaces both the estate and the provider list before
anything is read. If you see real hosts, the variable is not set in the
environment the server actually started in.

### Screenshots come out blank for the Windows client

`Graphics.CopyFromScreen` returns blank for DWM-composited WPF windows. The app
renders its own visual tree instead — use `--shot <path>`, which is what
`docs/shoot_desktop.ps1` does.

## Windows client

### "API unreachable — showing placeholder data"

It reads `BOTHY_API`, default `http://127.0.0.1:8760`. Start the console first.
The client deliberately keeps its placeholder rows and says so rather than
showing an empty window.

### Stale servers answering on a port

On Windows, `pkill` does not reliably kill these. Use PowerShell:

```powershell
Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
  Where-Object { $_.CommandLine -like '*bothy*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

An old build still bound to the port answers requests and produces
inexplicable 404s on routes that exist in your source.
