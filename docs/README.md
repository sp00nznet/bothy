# Bothy documentation

## Using it

- **[CLI reference](cli.md)** — every command and option
- **[HTTP API](api.md)** — what the web console and Windows client both talk to
- **[Configuration](configuration.md)** — credentials, environment variables, catalog sources
- **[Deploying](deploying.md)** — dry run, real runs, install scripts, batches
- **[Troubleshooting](troubleshooting.md)** — symptoms, causes, fixes

## The catalog

- **[Application catalog](catalog.md)** — all 855 definitions, generated
- **[Catalog sources](catalog-sources.md)** — where definitions and upstream links come from, and their licences

## How it is built

- **[Architecture](architecture.md)** — modules, data flow, where state lives
- **[Decisions](decisions.md)** — why things behave the way they do
- **[Screens](screenshots.md)** — every screenshot, full size

## Regenerating

```bash
# the catalog page
bothy --catalog containers.py import --out catalog.json
python docs/gen_catalog.py catalog.json

# screenshots — always from demo mode, so nothing real is published
BOTHY_DEMO=1 python -m bothy.cli serve --port 8760
python docs/shoot.py http://127.0.0.1:8760
powershell -File docs/shoot_desktop.ps1
```
