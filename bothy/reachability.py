"""Reachability auditing.

Explicit and user-triggered, never a background poll — the design is emphatic
about this, and it is also what makes the timestamp meaningful. Results record
what was checked, how, the code, and when.
"""
from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import urllib3

from .estate import ReachabilityResult, Service

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ports worth probing when a service exposes nothing specific
COMMON_PORTS = (80, 443, 8080, 8006, 3000, 8096, 32400, 9000, 5000)
TIMEOUT = 4.0


def _http(url: str, timeout: float = TIMEOUT) -> tuple[str, str]:
    """Return (code, note). Never raises."""
    t0 = time.time()
    try:
        r = requests.get(url, timeout=timeout, verify=False, allow_redirects=False)
        ms = int((time.time() - t0) * 1000)
        return str(r.status_code), f"{ms} ms"
    except requests.exceptions.SSLError:
        return "tls", "TLS handshake failed"
    except requests.exceptions.ConnectTimeout:
        return "timeout", f"no response in {timeout:.0f}s"
    except requests.exceptions.ReadTimeout:
        return "timeout", f"headers not sent in {timeout:.0f}s"
    except requests.exceptions.ConnectionError:
        return "closed", "connection refused"
    except Exception as e:
        return "error", type(e).__name__


def _port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_service(svc: Service, ports: list[int] | None = None) -> list[ReachabilityResult]:
    """Probe one service. Returns one result per URL tried."""
    if not svc.address:
        return [ReachabilityResult(url="—", via="no address", code="n/a",
                                   note="no IP discovered for this guest")]
    if svc.status != "running":
        return [ReachabilityResult(url=svc.address, via="direct", code="n/a",
                                   note=f"guest is {svc.status}")]

    candidates = ports if ports else [p for p in COMMON_PORTS if _port_open(svc.address, p)]
    if not candidates:
        return [ReachabilityResult(url=svc.address, via="direct", code="closed",
                                   note="no common port open")]

    out = []
    for port in candidates[:4]:
        scheme = "https" if port in (443, 8006) else "http"
        url = f"{scheme}://{svc.address}:{port}/"
        code, note = _http(url)
        out.append(ReachabilityResult(url=url, via="direct", code=code, note=note))
    return out


def audit(services: list[Service], workers: int = 8) -> dict[int, list[ReachabilityResult]]:
    """Probe many services in parallel. Returns {vmid: results}."""
    results: dict[int, list[ReachabilityResult]] = {}
    if not services:
        return results
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for svc, res in zip(services, pool.map(check_service, services)):
            results[svc.vmid] = res
    return results


def summarise(results: list[ReachabilityResult]) -> str:
    """Collapse a service's results into the single Route cell the tables show."""
    if not results:
        return "n/a"
    for r in results:
        if r.code.startswith("2"):
            return f"{r.code} OK"
    for r in results:
        if r.code.startswith("3") or r.code.startswith("4"):
            return r.code
    return results[0].code
