"""Capture every web console screen at the design viewport (1440x900).

Run against a server started with BOTHY_DEMO=1, so the shots show the sample
estate rather than somebody's real hostnames and addresses:

    BOTHY_DEMO=1 python -m bothy.cli serve --port 8760
    python docs/shoot.py http://127.0.0.1:8760
"""
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8760"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

# plain page loads: name -> path
PAGES = [
    ("W1-overview", "/"),
    ("W2-catalog", "/catalog?q=git"),
    ("W2-catalog-facets", "/catalog?deploy_type=lxc&footprint=medium"),
    ("W3-app-detail", "/catalog/gitea"),
    ("W3-deploy-panel", "/catalog/gitea?deploy=1"),
    ("W5-providers", "/providers"),
    ("W5b-wizard-type", "/providers/new"),
    ("W5-wizard-credentials", "/providers/new?type=proxmox"),
    ("W6-service", "/estate/104"),
    ("W7-audit-queue", "/audit"),
    ("W8-history", "/history"),
    ("estate", "/estate"),
    ("collections", "/collections"),
    ("credentials", "/credentials"),
]


def submit(keys):
    """Queue a batch so the queue screen has something in flight to show."""
    data = urllib.parse.urlencode(
        [("keys", k) for k in keys] +
        [("node", "pve01"), ("storage", "local-lvm")]).encode()
    req = urllib.request.Request(BASE + "/actions/deploy", data=data,
                                 headers={"Accept": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def shoot(pg, name, path=None):
    if path:
        pg.goto(BASE + path, wait_until="networkidle")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(OUT / f"{name}.png"))
    print(f"  {name}.png")


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)

    for name, path in PAGES:
        shoot(pg, name, path)

    # multi-select then batch config: needs clicks, not a URL
    pg.goto(f"{BASE}/catalog?q=git", wait_until="networkidle")
    for key in ("gitea", "gitlab", "forgejo"):
        box = pg.query_selector(f'.app[data-key="{key}"] .checkbox-sel')
        if box:
            box.click()
    shoot(pg, "W2-catalog-selected")
    btn = pg.query_selector('button:has-text("Configure batch")')
    if btn:
        btn.click()
        pg.wait_for_load_state("networkidle")
        shoot(pg, "W4b-batch")

    # a queue mid-flight says more than an empty one
    submit(["gitea", "harbor", "signoz", "forgejo"])
    time.sleep(2.2)
    shoot(pg, "W4-queue", "/queue")

    b.close()
print("done")
