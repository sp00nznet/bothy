"""Provider adapters. Each returns Service records for the estate."""
from __future__ import annotations

from ..config import ProviderConfig
from .base import Provider, ProviderError, ProviderStatus

_REGISTRY: dict[str, type[Provider]] = {}


def register(kind: str, cls: type[Provider]) -> None:
    _REGISTRY[kind] = cls


def build(cfg: ProviderConfig) -> Provider:
    from . import proxmox  # noqa: F401  (registers itself)
    cls = _REGISTRY.get(cfg.type)
    if cls is None:
        raise ProviderError(f"no adapter for provider type {cfg.type!r}")
    return cls(cfg)


# provider types the UI always lists, with what each one needs when unconfigured
KNOWN_TYPES = [
    ("proxmox", "Proxmox", "Requires host + user/token"),
    ("vmware", "VMware", "Requires vCenter host + user"),
    ("aws", "AWS", "Requires region + IAM key"),
    ("azure", "Azure", "Requires tenant + client secret"),
    ("gcp", "GCP", "Service-account JSON"),
    ("hyperv", "Hyper-V", "Requires WinRM host + credentials"),
    ("xcpng", "XCP-ng", "Pool master address"),
    ("kvm", "KVM", "qemu+ssh URI"),
]

# Fields each provider actually needs. The wizard renders only these, which is
# the fix for "provider setup is confusing" — Proxmox asks for a node and token,
# AWS for a region and IAM key, and neither is shown the other's fields.
#   (name, label, kind, placeholder, required)
_F = lambda n, l, k="text", ph="", req=True: {
    "name": n, "label": l, "kind": k, "placeholder": ph, "required": req}

PROVIDER_FIELDS: dict[str, list[dict]] = {
    "proxmox": [
        _F("host", "Host", "text", "192.168.1.10"),
        _F("port", "Port", "number", "8006", False),
        _F("user", "User", "text", "root@pam"),
        _F("password", "Password", "secret", "", False),
        _F("token_id", "Token ID", "text", "bothy", False),
        _F("token_secret", "Token secret", "secret", "", False),
        _F("node", "Default node", "text", "leave blank for all", False),
    ],
    "vmware": [
        _F("host", "vCenter host", "text", "vcenter.example.com"),
        _F("user", "User", "text", "administrator@vsphere.local"),
        _F("password", "Password", "secret"),
    ],
    "aws": [
        _F("node", "Region", "text", "eu-west-1"),
        _F("user", "Access key ID", "text"),
        _F("password", "Secret access key", "secret"),
    ],
    "azure": [
        _F("host", "Tenant ID", "text"),
        _F("user", "Client ID", "text"),
        _F("password", "Client secret", "secret"),
    ],
    "gcp": [
        _F("host", "Project ID", "text"),
        _F("password", "Service-account JSON path", "text", "C:\path\to\sa.json"),
    ],
    "hyperv": [
        _F("host", "WinRM host", "text", "WIN-HV01"),
        _F("user", "User", "text", "Administrator"),
        _F("password", "Password", "secret"),
    ],
    "xcpng": [
        _F("host", "Pool master address", "text"),
        _F("user", "User", "text", "root"),
        _F("password", "Password", "secret"),
    ],
    "kvm": [
        _F("host", "libvirt URI", "text", "qemu+ssh://user@host/system"),
        _F("user", "SSH user", "text", "", False),
    ],
}

# only adapters that actually exist can be tested / saved as working
IMPLEMENTED = {"proxmox"}

__all__ = ["Provider", "ProviderError", "ProviderStatus", "build", "register",
           "KNOWN_TYPES", "PROVIDER_FIELDS", "IMPLEMENTED"]
