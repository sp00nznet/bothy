"""Proxmox VE adapter — reads the live cluster."""
from __future__ import annotations

import urllib3

from ..config import ProviderConfig
from ..estate import Service
from . import register
from .base import ProviderError, ProviderStatus


def _fmt_uptime(seconds: float | int | None) -> str:
    s = int(seconds or 0)
    if s <= 0:
        return "—"
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _friendly(e: Exception) -> str:
    """Connection failures arrive wrapped in several layers of urllib3 detail.
    Surface the cause, not the plumbing."""
    msg = str(e)
    low = msg.lower()
    if "401" in msg or "authentication" in low or "login failed" in low:
        return "authentication failed — check the user and password/token"
    if "connecttimeout" in low or "timed out" in low:
        return "connection timed out — host unreachable on that port"
    if "refused" in low:
        return "connection refused — nothing listening on that port"
    if "certificate" in low or "ssl" in low:
        return "TLS error — try disabling certificate verification"
    if "name or service not known" in low or "nodename nor servname" in low or "getaddrinfo" in low:
        return "host not found — check the address"
    return msg.split("\n")[0][:160]


class ProxmoxProvider:
    """Talks to /api2/json via proxmoxer.

    Guests come from the cluster resource endpoint in one call rather than
    walking nodes, so a 20-guest estate is one request, not twenty.
    """

    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self._api = None

    # ---- connection ----------------------------------------------------
    def _connect(self):
        if self._api is not None:
            return self._api
        try:
            from proxmoxer import ProxmoxAPI
        except ImportError as e:  # pragma: no cover
            raise ProviderError("proxmoxer is not installed") from e
        if not self.cfg.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        kwargs = dict(host=self.cfg.host, port=self.cfg.port,
                      verify_ssl=self.cfg.verify_ssl, timeout=15)
        if self.cfg.token_secret:
            kwargs.update(user=self.cfg.user, token_name=self.cfg.token_id,
                          token_value=self.cfg.token_secret)
        else:
            kwargs.update(user=self.cfg.user, password=self.cfg.password)
        try:
            self._api = ProxmoxAPI(**kwargs)
        except Exception as e:
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        return self._api

    def test(self) -> ProviderStatus:
        try:
            api = self._connect()
            ver = api.version.get()
            nodes = api.nodes.get()
            storages = api.storage.get()
            release = ver.get("version") or ver.get("release", "")
            detail = (f"pve-manager/{release} · {len(nodes)} node"
                      f"{'s' if len(nodes) != 1 else ''} · {len(storages)} storages")
            return ProviderStatus(ok=True, detail=detail, version=release, nodes=len(nodes))
        except Exception as e:
            return ProviderStatus(ok=False, error=_friendly(e), detail=_friendly(e))

    # ---- data ----------------------------------------------------------
    def services(self) -> list[Service]:
        api = self._connect()
        try:
            resources = api.cluster.resources.get(type="vm")
        except Exception as e:
            raise ProviderError(f"cluster/resources: {e}") from e

        out: list[Service] = []
        for r in resources:
            if self.cfg.node and r.get("node") != self.cfg.node:
                continue
            vmid = int(r.get("vmid") or 0)
            status = r.get("status", "unknown")
            maxmem = int(r.get("maxmem") or 0)
            mem = int(r.get("mem") or 0)
            # cpu is a 0..1 fraction of allocated cores
            cpu_pct = round(float(r.get("cpu") or 0) * 100)
            kind = "vm" if r.get("type") == "qemu" else "lxc"
            out.append(Service(
                vmid=vmid,
                hostname=r.get("name") or str(vmid),
                address="",                       # filled by _enrich
                node=r.get("node", ""),
                provider="proxmox",
                status="running" if status == "running" else "stopped",
                cpu_pct=cpu_pct,
                mem_used_mb=mem // (1024 * 1024),
                mem_total_mb=max(1, maxmem // (1024 * 1024)),
                uptime=_fmt_uptime(r.get("uptime")),
                route="n/a",
                group=(r.get("pool") or "Unassigned"),
                definition_key=(r.get("name") or "").split("-")[0],
                kind=kind,
            ))
        self._enrich_addresses(api, out)
        return sorted(out, key=lambda s: s.vmid)

    def _enrich_addresses(self, api, services: list[Service]) -> None:
        """Pull IPs from guest config. One call per guest, running guests only.

        LXC config carries `net0: ...,ip=10.0.0.5/24`. QEMU has no IP in config,
        so it needs the guest agent; if that is unavailable the address stays
        blank rather than being guessed.
        """
        for s in services:
            if s.status != "running":
                continue
            try:
                if s.kind == "lxc":
                    cfg = api.nodes(s.node).lxc(s.vmid).config.get()
                    net = cfg.get("net0", "")
                    for part in net.split(","):
                        if part.startswith("ip="):
                            val = part[3:].split("/")[0]
                            # "ip=dhcp" is a directive, not an address. Taking it
                            # literally gave every DHCP guest the address "dhcp",
                            # which then failed every reachability probe.
                            if val and val not in ("dhcp", "manual", "auto"):
                                s.address = val
                            break
                    if not s.address:
                        # ask the running guest what it actually got
                        try:
                            for iface in api.nodes(s.node).lxc(s.vmid).interfaces.get():
                                if iface.get("name", "").startswith("lo"):
                                    continue
                                ip = (iface.get("inet") or "").split("/")[0]
                                if ip:
                                    s.address = ip
                                    break
                        except Exception:
                            pass
                else:
                    info = api.nodes(s.node).qemu(s.vmid).agent("network-get-interfaces").get()
                    for iface in info.get("result", []):
                        if iface.get("name", "").startswith("lo"):
                            continue
                        for ip in iface.get("ip-addresses", []):
                            if ip.get("ip-address-type") == "ipv4":
                                s.address = ip["ip-address"]
                                break
                        if s.address:
                            break
            except Exception:
                # unreachable agent / permission / stopped mid-scan: leave blank,
                # never fabricate an address
                continue


register("proxmox", ProxmoxProvider)
