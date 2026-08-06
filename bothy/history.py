"""Event history.

Every action that changes something — a deploy, an audit, a provider edit —
appends one line here. Append-only JSONL so a crash mid-write costs at most the
last event, and so it can be tailed with ordinary tools.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# kind -> (label, dot colour class)
KINDS = {
    "deploy": ("Deploy", "accent"),
    "deploy_done": ("Deployed", "ok"),
    "deploy_failed": ("Deploy failed", "danger"),
    "audit": ("Reachability audit", "ok"),
    "catalog_audit": ("Catalog audit", "ok"),
    "provider": ("Provider", "accent"),
    "collection": ("Collection", "muted"),
    "refresh": ("Refresh", "muted"),
}


def store_path() -> Path:
    return Path.home() / ".bothy" / "history.jsonl"


@dataclass
class Event:
    kind: str
    subject: str
    detail: str = ""
    at: float = field(default_factory=time.time)

    @property
    def label(self) -> str:
        return KINDS.get(self.kind, (self.kind.title(), "muted"))[0]

    @property
    def dot(self) -> str:
        return KINDS.get(self.kind, ("", "muted"))[1]

    @property
    def when(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.at))

    @property
    def day(self) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(self.at))

    @property
    def ago(self) -> str:
        s = int(time.time() - self.at)
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60} min ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(label=self.label, dot=self.dot, when=self.when, ago=self.ago)
        return d


class History:
    """Append-only event log, newest first when read."""

    def __init__(self, path: Path | None = None, limit: int = 500):
        self._path = path or store_path()
        self._limit = limit

    def add(self, kind: str, subject: str, detail: str = "") -> Event:
        e = Event(kind=kind, subject=subject, detail=detail)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"kind": e.kind, "subject": e.subject,
                                    "detail": e.detail, "at": e.at}) + "\n")
        except OSError:
            pass          # history is a convenience; never break an action for it
        return e

    def all(self, limit: int | None = None) -> list[Event]:
        if not self._path.exists():
            return []
        out: list[Event] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue          # a torn final line must not hide the rest
                out.append(Event(kind=d.get("kind", "?"), subject=d.get("subject", ""),
                                 detail=d.get("detail", ""), at=float(d.get("at", 0))))
        except OSError:
            return []
        out.reverse()
        return out[: (limit or self._limit)]

    def by_day(self, limit: int | None = None) -> dict[str, list[Event]]:
        groups: dict[str, list[Event]] = {}
        for e in self.all(limit):
            groups.setdefault(e.day, []).append(e)
        return groups

    def clear(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass
