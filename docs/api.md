# HTTP API

The web console is a client of this API, and so is the Windows client. There is
no separate "internal" interface.

**No authentication.** Every endpoint below is open to anyone who can reach the
port, including the ones that create containers. Bind to loopback, or put it
behind something that authenticates.

Base URL: `http://127.0.0.1:8760`.

## Read

| Endpoint | Returns |
|---|---|
| `GET /api/estate` | services, counts, capacity |
| `GET /api/catalog` | definitions; `?q=`, `?deploy_type=`, `?footprint=`, `?audit_state=` |
| `GET /api/catalog/<key>` | one definition |
| `GET /api/queue` | the current batch, its jobs and their logs |
| `GET /api/audit` | catalog audit results |
| `GET /api/history` | recent events |
| `GET /api/reachability/<vmid>` | probe results for one service |

```bash
curl -s localhost:8760/api/estate | jq '.counts'
curl -s 'localhost:8760/api/catalog?q=git&footprint=medium' | jq '.count'
curl -s localhost:8760/api/queue | jq '.jobs[] | {name, status, pct}'
```

`GET /api/catalog` returns `{count, total, items[]}` — `count` is how many
matched the filter, `total` how many exist. The Windows client uses
`?q=__none__` to read `total` cheaply.

## Act

All POST, all form-encoded unless noted. Send `Accept: application/json` to get
JSON back instead of a redirect.

| Endpoint | Effect |
|---|---|
| `POST /actions/refresh` | re-read every provider, keeping the audit |
| `POST /actions/deploy` | queue a batch |
| `POST /actions/queue/<batch_id>/<pause\|resume\|abort>` | control a batch |
| `POST /actions/audit` | reachability probe, estate-wide or `vmid=` |
| `POST /actions/catalog-audit` | check catalog links |
| `POST /actions/collection` | save a collection |
| `POST /actions/collection/<id>/delete` | remove one |
| `POST /actions/provider-test` | handshake against supplied credentials |
| `POST /actions/provider-save` | write to `~/.bothy/config.toml` |

### Queueing a deploy

```bash
curl -s -X POST -H "Accept: application/json" \
  -d keys=gitea -d keys=harbor \
  -d node=pve01 -d storage=local-lvm \
  -d vmid_gitea=140 -d hostname_gitea=gitea \
  -d cores_gitea=2 -d memory_gitea=2048 -d disk_gitea=30 \
  -d env_gitea_GITEA_ADMIN_PASSWORD=... \
  localhost:8760/actions/deploy
```

`keys` is repeatable and selects the definitions. Per-definition overrides are
suffixed with the key: `vmid_<key>`, `hostname_<key>`, `cores_<key>`,
`memory_<key>`, `disk_<key>`, and `env_<key>_<VAR>` for environment values.
`on_failure` is `stop` (default), `continue` or `rollback`.

The response is the batch: poll `GET /api/queue` for progress and logs.

**This creates real containers only when the server was started with
`BOTHY_DEPLOY=real`.** Otherwise it runs the dry run and logs the commands it
would have issued. Demo mode refuses regardless.

### Job log shape

```json
{"jobs": [{"key": "gitea", "status": "installing", "pct": 85,
           "step": "Running install script", "elapsed": "1m 12s",
           "log": [{"t": "22:01:03", "kind": "cmd", "text": "pct create ..."}]}]}
```

`kind` is one of `cmd`, `detail`, `ok`, `secret`, `error`. Secret values are
replaced with `$(NAME)` before they reach the log; terminal control sequences
are stripped and consecutive duplicate lines dropped.

## Status codes

| Code | Meaning |
|---|---|
| `400` | no valid definitions selected |
| `403` | demo mode refused a write |
| `404` | unknown key, vmid or batch |
