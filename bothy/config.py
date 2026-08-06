"""Connection configuration.

Credentials never live in the repo. Bothy reads them from, in order:

  1. $BOTHY_CONFIG                     explicit path to a TOML file
  2. ~/.bothy/config.toml              per-user default
  3. environment variables             BOTHY_PROXMOX_HOST / _USER / _PASSWORD ...

Example ~/.bothy/config.toml:

    [[providers]]
    name = "Home lab"
    type = "proxmox"
    host = "192.168.1.10"
    user = "root@pam"
    password = "..."          # or token_id + token_secret
    verify_ssl = false
    default = true
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProviderConfig:
    name: str
    type: str = "proxmox"
    host: str = ""
    port: int = 8006
    user: str = "root@pam"
    password: str = ""
    token_id: str = ""
    token_secret: str = ""
    verify_ssl: bool = False
    node: str = ""
    default: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.host and (self.password or self.token_secret))

    def redacted(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("password", "token_secret", "extra")}
        d["auth"] = "token" if self.token_secret else "password" if self.password else "none"
        return d


def config_path() -> Path | None:
    env = os.environ.get("BOTHY_CONFIG")
    if env:
        p = Path(env).expanduser()
        return p if p.exists() else None
    p = Path.home() / ".bothy" / "config.toml"
    return p if p.exists() else None


def _from_env() -> list[ProviderConfig]:
    host = os.environ.get("BOTHY_PROXMOX_HOST")
    if not host:
        return []
    return [ProviderConfig(
        name=os.environ.get("BOTHY_PROXMOX_NAME", "Proxmox"),
        type="proxmox",
        host=host,
        port=int(os.environ.get("BOTHY_PROXMOX_PORT", "8006")),
        user=os.environ.get("BOTHY_PROXMOX_USER", "root@pam"),
        password=os.environ.get("BOTHY_PROXMOX_PASSWORD", ""),
        token_id=os.environ.get("BOTHY_PROXMOX_TOKEN_ID", ""),
        token_secret=os.environ.get("BOTHY_PROXMOX_TOKEN_SECRET", ""),
        verify_ssl=os.environ.get("BOTHY_PROXMOX_VERIFY", "0") in ("1", "true", "yes"),
        node=os.environ.get("BOTHY_PROXMOX_NODE", ""),
        default=True,
    )]


def load_providers() -> list[ProviderConfig]:
    path = config_path()
    if path:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        out = []
        for p in raw.get("providers", []):
            known = {f for f in ProviderConfig.__dataclass_fields__ if f != "extra"}
            cfg = ProviderConfig(**{k: v for k, v in p.items() if k in known})
            cfg.extra = {k: v for k, v in p.items() if k not in known}
            out.append(cfg)
        if out:
            return out
    return _from_env()


def _toml_escape(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def dump_providers(providers: list[ProviderConfig]) -> str:
    """Render providers back to TOML. Hand-written rather than pulling in a
    writer dependency: the schema is six scalars and we control it."""
    out = ["# Bothy provider configuration.",
           "# Written by the add-provider wizard. Safe to edit by hand.", ""]
    for p in providers:
        out.append("[[providers]]")
        out.append(f'name = "{_toml_escape(p.name)}"')
        out.append(f'type = "{_toml_escape(p.type)}"')
        out.append(f'host = "{_toml_escape(p.host)}"')
        out.append(f"port = {int(p.port)}")
        out.append(f'user = "{_toml_escape(p.user)}"')
        if p.token_secret:
            out.append(f'token_id = "{_toml_escape(p.token_id)}"')
            out.append(f'token_secret = "{_toml_escape(p.token_secret)}"')
        elif p.password:
            out.append(f'password = "{_toml_escape(p.password)}"')
        if p.node:
            out.append(f'node = "{_toml_escape(p.node)}"')
        out.append(f"verify_ssl = {str(bool(p.verify_ssl)).lower()}")
        out.append(f"default = {str(bool(p.default)).lower()}")
        out.append("")
    return "\n".join(out)


def save_providers(providers: list[ProviderConfig], path: Path | None = None) -> Path:
    """Persist providers, keeping the file readable only by the owner."""
    target = path or (Path.home() / ".bothy" / "config.toml")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():                      # keep one generation back
        target.replace(target.with_suffix(".toml.bak"))
    target.write_text(dump_providers(providers), encoding="utf-8")
    try:
        target.chmod(0o600)                  # no-op semantics on Windows, correct on POSIX
    except OSError:
        pass
    return target


def default_provider() -> ProviderConfig | None:
    ps = load_providers()
    if not ps:
        return None
    return next((p for p in ps if p.default), ps[0])
