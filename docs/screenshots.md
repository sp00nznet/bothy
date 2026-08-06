# Screens

Every shot is captured from demo mode (`BOTHY_DEMO=1`), which is why none of
them contain a real host: the sample addresses are RFC 5737 documentation
space. Regenerate with:

```bash
BOTHY_DEMO=1 python -m bothy.cli serve --port 8760
python docs/shoot.py http://127.0.0.1:8760       # web, 17 screens
powershell -File docs/shoot_desktop.ps1          # Windows client, 5 screens
```

## Web console

### W1 — Overview

Estate, capacity, queue depth and the catalog audit summary on one page.

![Overview](screenshots/W1-overview.png)

### W2 — Catalog

Browsed by facets, not categories. 686 definitions, filter chips that remove
themselves on click, multi-select into a batch or a saved collection.

![Catalog](screenshots/W2-catalog.png)
![Catalog with facets applied](screenshots/W2-catalog-facets.png)
![Multi-select](screenshots/W2-catalog-selected.png)

### W3 — Application detail and deploy panel

![App detail](screenshots/W3-app-detail.png)
![Deploy panel](screenshots/W3-deploy-panel.png)

### W4 — Queue

A live engine: polling, pause/resume/abort, and a log tail that follows.

![Queue](screenshots/W4-queue.png)
![Batch configuration](screenshots/W4b-batch.png)

### W5 — Providers

Eight provider types are listed so you can see where this is going; only the
ones with an adapter will test or save.

![Providers](screenshots/W5-providers.png)
![Wizard — choose a type](screenshots/W5b-wizard-type.png)
![Wizard — credentials, tested before saving](screenshots/W5-wizard-credentials.png)

### W6 — Service detail

Per-service reachability, with the actual finding rather than a green tick.

![Service detail](screenshots/W6-service.png)

### W7 — Audit queue

Every definition, its audit state, and what the checker actually found.

![Audit queue](screenshots/W7-audit-queue.png)

### W8 — History

Append-only: deploys, audits, provider and collection changes.

![History](screenshots/W8-history.png)

### Estate, collections, credentials

![Estate](screenshots/estate.png)
![Collections](screenshots/collections.png)
![Credentials](screenshots/credentials.png)

## Windows client

Native WPF on .NET 8, reading the same REST API as the web console.

### D1 — Main window

![Main window](screenshots/D1-main-window.png)

### D2 — Deploy wizard

![Deploy wizard](screenshots/D2-deploy-wizard.png)

### D3 — Detachable deployment monitor

![Monitor](screenshots/D3-monitor.png)

### D4 — Provider property sheet

![Provider properties](screenshots/D4-provider-properties.png)

### D5 — Tray menu and toast

![Tray and toast](screenshots/D5-tray-toast.png)
