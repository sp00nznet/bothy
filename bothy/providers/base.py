"""Provider interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import ProviderConfig
from ..estate import Service


class ProviderError(RuntimeError):
    """Adapter could not talk to the provider."""


@dataclass
class ProviderStatus:
    ok: bool
    detail: str = ""          # "pve-manager/8.2.4 · 3 nodes · 5 storages"
    version: str = ""
    nodes: int = 0
    error: str = ""


class Provider(Protocol):
    cfg: ProviderConfig

    def __init__(self, cfg: ProviderConfig) -> None: ...

    def test(self) -> ProviderStatus:
        """Cheap connectivity + auth check. Never raises."""

    def services(self) -> list[Service]:
        """Every guest this provider knows about."""
