"""User-defined collections — the replacement for the untrusted category tree.

Persisted to ~/.bothy/collections.json so a saved selection survives a restart.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path


def store_path() -> Path:
    return Path.home() / ".bothy" / "collections.json"


class CollectionStore:
    def __init__(self, items: list[dict] | None = None, path: Path | None = None):
        self._items = items or []
        self._path = path or store_path()

    @classmethod
    def load(cls, path: Path | None = None) -> "CollectionStore":
        p = path or store_path()
        if p.exists():
            try:
                return cls(json.loads(p.read_text(encoding="utf-8")), p)
            except (json.JSONDecodeError, OSError):
                pass          # corrupt or unreadable: start empty rather than crash
        return cls([], p)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._items, indent=1), encoding="utf-8")

    def all(self) -> list[dict]:
        return list(self._items)

    def get(self, cid: str) -> dict | None:
        return next((c for c in self._items if c["id"] == cid), None)

    def add(self, name: str, keys: list[str]) -> dict:
        existing = next((c for c in self._items if c["name"].lower() == name.lower()), None)
        if existing:
            merged = list(dict.fromkeys(existing["keys"] + keys))
            existing["keys"] = merged
            existing["count"] = len(merged)
            existing["updated_at"] = time.time()
            self.save()
            return existing
        item = {"id": uuid.uuid4().hex[:8], "name": name, "keys": list(dict.fromkeys(keys)),
                "count": len(set(keys)), "created_at": time.time(), "updated_at": time.time()}
        self._items.append(item)
        self.save()
        return item

    def remove(self, cid: str) -> bool:
        n = len(self._items)
        self._items = [c for c in self._items if c["id"] != cid]
        if len(self._items) != n:
            self.save()
            return True
        return False
