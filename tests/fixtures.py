"""Sample data for tests.

The estate comes from bothy.demo so the fixture and what `BOTHY_DEMO=1`
actually serves can never drift apart.
"""
from bothy.demo import demo_estate
from bothy.estate import Job


def sample_estate():
    return demo_estate()


def sample_queue() -> list[Job]:
    return [
        Job(key="harbor", name="Harbor", target="pve02 · vmid 118", status="complete",
            pct=100, step="Install complete", elapsed="4m 02s"),
        Job(key="gitea", name="Gitea", target="pve02 · vmid 120", status="installing",
            pct=64, step="Running install script", elapsed="1m 12s",
            log=[("22:01:03", "cmd", "pct create 120 local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"),
                 ("22:01:19", "detail", "  extracting rootfs ..."),
                 ("22:01:44", "ok", "  container 120 created"),
                 ("22:01:45", "cmd", "pct start 120"),
                 ("22:02:02", "secret", "  resolving secret: GITEA_ADMIN_PASSWORD (vault: bothy/gitea)"),
                 ("22:02:07", "detail", "  apt-get install -y git sqlite3"),
                 ("22:02:15", "cmd", "systemctl enable --now gitea")]),
        Job(key="signoz", name="SigNoz", target="—", status="blocked",
            pct=0, step="Blocked", elapsed="—",
            reason="No provider selected for this app"),
    ]
