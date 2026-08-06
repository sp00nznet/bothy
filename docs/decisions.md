# Decisions

Why things behave the way they do. Most of these exist because the obvious
version was wrong the first time.

## The catalog audit

**The audit is real, and its headline finding is an absence.** Run over the
686-definition catalog: **0 definitions declare their own upstream link**, 35
reference a URL only inside their install script, and 651 reference nothing at
all. So the audit reports "no upstream link recorded" for most of the catalog.
That is the finding, not a checker failure.

**Dependency URLs can never make a definition "verified".** An install script
that fetches `download.docker.com` says nothing about whether *this* app's
upstream is alive; dozens of unrelated apps share that URL. Only a link the
definition itself declares can verify it — a dependency URL can only ever mark
it *broken*.

**A 401/403 is not a broken link.** An apt repository root returns 403 by design
while every file beneath it serves fine; only 404/410, 5xx and transport
failures count. Without this rule the checker flagged Plex's and Jellyfin's
healthy repositories as broken.

Until a definition is audited, `catalog._audit_for()` supplies a deterministic
provisional state so the UI is populated and tests do not churn. Stored audit
results always override it.

## The estate

**Route colours mean what they say.** A `3xx`/`4xx` means the service answered —
it is reachable, just redirecting or protected — and does not count as an
outage. Only `5xx`, timeouts and refused connections feed "needs attention".
Treating an auth challenge as an outage cries wolf.

**Guests seen through two nodes of one cluster are deduplicated.** Every Proxmox
node reports the whole cluster, so two configured members would otherwise list
each guest twice. Deduplication is on `(provider, node, vmid)`.

**`ip=dhcp` is a directive, not an address.** An LXC config for a DHCP guest
literally contains `ip=dhcp`; parsing it as the address gave such guests the
address "dhcp" and failed every reachability probe. Bothy asks the running guest
what it actually got instead.

**A refresh must not erase the audit.** Refreshing rebuilds `Service` objects
from the provider; reachability results are adopted onto the new objects rather
than dropped.

## Deploying

**Deploys are dry-run by default.** See [configuration](configuration.md).

**The dry run prints the command the real run issues.** Both come from
`deploy.build_create_params()`, and the dry run resolves the same template from
the target node. A preview that shows a different command than the real call is
worse than no preview at all.

**The real runner picks a template already on the node** and fails loudly if
there is none, rather than downloading one as a side effect of pressing Deploy.

**Install scripts are uploaded, not interpolated.** The script is written to a
file, pushed with `pct push` and run with `pct exec bash`, so quoting inside a
script can never change the command being run. Environment values are
`shlex`-quoted, and secret values are replaced with `$(NAME)` before a line
reaches the log.

**Install output is read to EOF, not until the process exits.** Polling
`exit_status_ready()` wins the race against data still sitting in the channel
buffer — a six-minute install once reported success with one line of log.

**A PTY writes `\r\n`.** After splitting the stream on `\n`, every line ends in
`\r`. Treating the last `\r`-segment as the visible state — correct for a
progress redraw — blanks every ordinary line unless the trailing CR goes first.

**Log noise is dropped, and the log is capped.** `apt-get update` under a PTY
produced 5,504 lines, nearly all the same warning. Consecutive duplicates and
lines that clean to nothing are discarded; a job log is capped with its head
preserved, because an install script is arbitrary bash and nothing stops it
printing forever.

## Providers

**The wizard only offers what exists.** Provider types without an adapter are
listed, so you can see what Bothy will support, but marked "no adapter yet" and
refuse to test rather than pretending to connect. Only Proxmox is implemented.

**One dead credential cannot blank the UI.** A provider that fails to read is
recorded in `estate.errors` and surfaced in the interface; the others still
load.

## Demo mode

Bothy is useless without a provider, which makes it hard to look at before you
commit credentials to it, and makes documentation a problem: screenshots taken
against a live estate publish real hostnames, node names and addresses.

`BOTHY_DEMO=1` serves a fixed sample estate, never contacts a provider, and
forces dry run. Its addresses are RFC 5737 documentation space, so a screenshot
cannot leak a topology and a stray probe cannot reach anyone's network. It
writes history to its own file rather than over the record of things that
actually happened, and provider-save returns 403.

Sample data lives in `bothy/demo.py`, and the test fixtures import it, so what
the tests assert and what the demo serves cannot drift apart.

## Clients

The Windows client reads `BOTHY_API` (default `http://127.0.0.1:8760`). If the
API is unreachable it keeps its placeholder rows and says so in the status bar,
rather than showing an empty window.

Paths under the home directory render as `~/…`. Screenshots and screen-shares
should not have to publish an operator's username.

## Screenshots

Captured at 2×. The web console via Playwright (`docs/shoot.py`); the desktop by
the app rendering its own visual tree (`--shot`), because
`Graphics.CopyFromScreen` returns blank for DWM-composited WPF windows.

## Design tokens

Dark, Fluent-derived. The implementation lives in `bothy/web/static/bothy.css`
(`:root`) and `desktop/Theme.xaml`.

| | |
|---|---|
| Accent | `#4cc2ff` |
| App background | `#141417` (web) · `#202024` (Windows) |
| Monospace | every identifier, address, VMID and log line |
| Icons | no webfonts, no images, no icon fonts; the Windows client uses Segoe Fluent Icons |
