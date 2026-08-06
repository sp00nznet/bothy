"""Importing definitions and upstream links from public catalogues.

The catalog audit's headline finding is that no definition declares its own
upstream link. Hand-writing several hundred URLs is not the answer: the links
already exist, spread across public repositories and — for game servers —
inside our own definitions, as Steam app IDs and LinuxGSM server names.

This module pulls those together. It is deliberately offline-friendly: each
source is a repository tarball fetched once and cached, so a re-import does not
hammer anyone's servers, and an import can be repeated from cache with no
network at all.

Licensing is not incidental here. community-scripts, Pelican eggs and LinuxGSM
are MIT, so their scripts and metadata can be redistributed with attribution.
awesome-selfhosted-data is CC-BY-SA, which would make a bulk copy of its prose
a share-alike derivative — so only its URLs are taken, which are facts about
where software lives rather than authored content. `SOURCES` records this and
`build()` writes it into the output.
"""
from __future__ import annotations

import csv
import io
import json
import re
import tarfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

UA = "bothy-importer (+https://github.com/sp00nznet/bothy)"
CACHE_TTL = 24 * 3600


@dataclass(frozen=True)
class Source:
    key: str
    repo: str
    ref: str
    licence: str
    url: str
    takes: str          # what we take, which the licence has to permit


SOURCES = {
    s.key: s for s in [
        Source("community-scripts", "community-scripts/ProxmoxVE", "main", "MIT",
               "https://github.com/community-scripts/ProxmoxVE",
               "install scripts"),
        # the per-app metadata is NOT in the main repo; this is its current home
        Source("community-scripts-meta", "community-scripts/ProxmoxVE-Local", "main", "MIT",
               "https://github.com/community-scripts/ProxmoxVE-Local",
               "app metadata: website, ports, resources"),
        Source("community-scripts-meta-archive", "community-scripts/ProxmoxVE-Frontend-Archive",
               "main", "MIT", "https://github.com/community-scripts/ProxmoxVE-Frontend-Archive",
               "app metadata (archived, fills gaps the current repo has dropped)"),
        Source("pelican-steamcmd", "pelican-eggs/games-steamcmd", "main", "MIT",
               "https://github.com/pelican-eggs/games-steamcmd",
               "game server definitions and Steam app IDs"),
        Source("pelican-standalone", "pelican-eggs/games-standalone", "main", "MIT",
               "https://github.com/pelican-eggs/games-standalone",
               "game server definitions"),
        Source("pelican-minecraft", "pelican-eggs/minecraft", "main", "MIT",
               "https://github.com/pelican-eggs/minecraft",
               "Minecraft server flavours (Paper, Purpur, Forge, proxies)"),
        Source("pelican-voice", "pelican-eggs/voice", "main", "MIT",
               "https://github.com/pelican-eggs/voice",
               "voice server definitions"),
        Source("linuxgsm", "GameServerManagers/LinuxGSM", "master", "MIT",
               "https://github.com/GameServerManagers/LinuxGSM",
               "game server list and server-page links"),
        Source("awesome-selfhosted", "awesome-selfhosted/awesome-selfhosted-data", "master",
               "CC-BY-SA-3.0", "https://github.com/awesome-selfhosted/awesome-selfhosted-data",
               "upstream URLs only — see the module docstring"),
    ]
}


def cache_dir() -> Path:
    d = Path.home() / ".bothy" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch(source: Source, refresh: bool = False) -> Path:
    """Download a repository tarball, cached. Returns the local path."""
    dest = cache_dir() / f"{source.key}.tar.gz"
    fresh = dest.exists() and (time.time() - dest.stat().st_mtime) < CACHE_TTL
    if fresh and not refresh:
        return dest
    url = f"https://codeload.github.com/{source.repo}/tar.gz/refs/heads/{source.ref}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    dest.write_bytes(data)
    return dest


def members(path: Path, match) -> list[tuple[str, bytes]]:
    """Read the archive entries whose in-repo path satisfies `match`.

    Paths are returned with the tarball's top directory stripped, so a caller
    never has to know the commit hash GitHub put in the folder name.
    """
    out: list[tuple[str, bytes]] = []
    with tarfile.open(path, "r:gz") as tf:
        for m in tf:
            if not m.isfile():
                continue
            rel = m.name.split("/", 1)[1] if "/" in m.name else m.name
            if not match(rel):
                continue
            f = tf.extractfile(m)
            if f is not None:
                out.append((rel, f.read()))
    return out


def norm(s: str) -> str:
    """Fold a name for cross-source matching: 'ARK: Survival Evolved' -> arksurvivalevolved."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ------------------------------------------------------------------ sources
def community_scripts_meta(refresh: bool = False) -> dict[str, dict]:
    """Per-app metadata, newest source last so it overwrites the archive."""
    meta: dict[str, dict] = {}
    for key in ("community-scripts-meta-archive", "community-scripts-meta"):
        src = SOURCES[key]
        for rel, raw in members(fetch(src, refresh),
                                lambda p: "json/" in p and p.endswith(".json")):
            try:
                d = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            # categories.json and friends are lists, not app records
            if not isinstance(d, dict) or not d.get("name"):
                continue
            meta[d.get("slug") or Path(rel).stem] = d
    return meta


def community_scripts_installers(refresh: bool = False) -> dict[str, str]:
    """The actual `install/*-install.sh` bodies, keyed by slug."""
    src = SOURCES["community-scripts"]
    out = {}
    for rel, raw in members(fetch(src, refresh),
                            lambda p: p.startswith("install/") and p.endswith(".sh")):
        slug = Path(rel).stem
        if slug.endswith("-install"):
            slug = slug[: -len("-install")]
        out[slug] = raw.decode("utf-8", "replace")
    return out


EGG_SOURCES = ("pelican-standalone", "pelican-steamcmd", "pelican-minecraft", "pelican-voice")


# eggs shipped as copy-me templates rather than a real server
PLACEHOLDER_EGGS = {"myserver", "example", "test", "template", "newegg"}


def _images(value) -> list[str]:
    if isinstance(value, dict):
        return [v for v in value.values() if isinstance(v, str)]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def pelican_eggs(refresh: bool = False) -> dict[str, dict]:
    """Game server definitions from Pelican eggs, keyed by normalised name.

    Keying on the egg's own name — not its folder — is what makes this correct
    across repositories. In games-steamcmd a folder is one game holding a
    native and a `pterodactyl` variant that share a name, so they collapse. In
    the minecraft repository a folder is a *category* holding Paper, Purpur,
    Forge and friends, which are genuinely different servers and must not.
    Folder-keying silently turned 95 Minecraft servers into 5.

    Where two eggs do share a name, the one whose filename does not say
    `pterodactyl` wins: it is the maintained native definition.
    """
    games: dict[str, dict] = {}
    for key in EGG_SOURCES:
        src = SOURCES[key]
        for rel, raw in members(fetch(src, refresh), lambda p: p.endswith(".json")):
            try:
                egg = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            name = egg.get("name")
            if not name or not isinstance(name, str):
                continue
            if norm(name) in PLACEHOLDER_EGGS:
                continue          # template eggs, not a real server
            slug = norm(name)
            legacy = "pterodactyl" in rel.lower()
            if slug in games and (legacy or not games[slug]["legacy"]):
                continue
            vars_ = {v.get("env_variable"): v.get("default_value")
                     for v in (egg.get("variables") or []) if v.get("env_variable")}
            appid = vars_.get("SRCDS_APPID") or vars_.get("STEAM_APPID") or vars_.get("APPID")
            games[slug] = {
                "name": name,
                "description": (egg.get("description") or "").strip(),
                "steam_app_id": str(appid) if str(appid or "").isdigit() else "",
                # older eggs list images, newer ones map label -> image
                "docker_images": _images(egg.get("docker_images")),
                "startup": egg.get("startup", ""),
                "variables": vars_,
                "source": key,
                "legacy": legacy,
            }
    return games


def linuxgsm_servers(refresh: bool = False) -> dict[str, dict]:
    """LinuxGSM's supported game servers, from lgsm/data/serverlist.csv."""
    src = SOURCES["linuxgsm"]
    found = members(fetch(src, refresh), lambda p: p.endswith("data/serverlist.csv"))
    if not found:
        return {}
    text = found[0][1].decode("utf-8", "replace")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        short = (row.get("shortname") or "").strip()
        if not short:
            continue
        out[short] = {"name": (row.get("gamename") or "").strip(),
                      "server": (row.get("gameservername") or "").strip(),
                      "os": (row.get("os") or "").strip()}
    return out


def awesome_selfhosted_links(refresh: bool = False) -> dict[str, str]:
    """Normalised software name -> website URL.

    Only the URL is taken. The descriptions are CC-BY-SA prose and copying them
    would make the output a share-alike derivative; a URL is a fact about where
    the software lives. Parsed with a regex rather than a YAML dependency
    because the two fields needed are always flat top-level scalars.
    """
    src = SOURCES["awesome-selfhosted"]
    out: dict[str, str] = {}
    for _rel, raw in members(fetch(src, refresh),
                             lambda p: p.startswith("software/") and p.endswith(".yml")):
        text = raw.decode("utf-8", "replace")

        def field(name: str) -> str:
            m = re.search(rf"^{name}:\s*(.+?)\s*$", text, re.M)
            return m.group(1).strip("'\"") if m else ""

        name, url = field("name"), field("website_url")
        if name and url:
            out[norm(name)] = url
    return out


# ------------------------------------------------------------- link deriving
STEAM_STORE = "https://store.steampowered.com/app/{}/"
LINUXGSM_PAGE = "https://linuxgsm.com/servers/{}/"


def derived_links(defs: dict[str, dict]) -> dict[str, tuple[str, str]]:
    """Upstream links recoverable from what a definition already carries.

    Game servers record STEAM_APP_ID and LINUXGSM_NAME in env_vars. Those are
    exact identifiers, not name guesses, so the resulting URL is authoritative
    in a way that fuzzy matching never is.
    """
    out: dict[str, tuple[str, str]] = {}
    for key, d in defs.items():
        env = {e.get("name"): e.get("default")
               for e in (d.get("env_vars") or []) if isinstance(e, dict)}
        appid = env.get("STEAM_APP_ID")
        gsm = env.get("LINUXGSM_NAME")
        if appid and str(appid).isdigit():
            out[key] = (STEAM_STORE.format(appid), "steam app id")
        elif gsm:
            out[key] = (LINUXGSM_PAGE.format(gsm), "linuxgsm name")
    return out


# -------------------------------------------------------------------- build
def enrich(defs: dict[str, dict], meta: dict, ash: dict,
           gsm: dict) -> tuple[dict[str, dict], dict[str, int]]:
    """Fill in `upstream` on definitions that lack one. Never overwrites.

    Precedence is by how specific the evidence is: an ID we already store beats
    a slug match against another catalogue, which beats matching on name.
    """
    stats: dict[str, int] = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    derived = derived_links(defs)
    gsm_by_name = {norm(v["name"]): k for k, v in gsm.items()}

    for key, d in defs.items():
        if d.get("upstream"):
            bump("already had one")
            continue
        name = norm(d.get("name", ""))
        if key in derived:
            d["upstream"], src = derived[key]
            bump(src)
        elif meta.get(key, {}).get("website"):
            d["upstream"] = meta[key]["website"]
            bump("community-scripts")
        elif name in ash or norm(key) in ash:
            d["upstream"] = ash.get(name) or ash[norm(key)]
            bump("awesome-selfhosted")
        elif name in gsm_by_name:
            d["upstream"] = LINUXGSM_PAGE.format(gsm_by_name[name])
            bump("linuxgsm (by game name)")
        else:
            bump("unresolved")
    return defs, stats


def _slug_key(name: str, taken: dict) -> str:
    """A readable, collision-free catalog key from a display name."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "game"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}-{n}", n + 1
    return key


def _egg_definition(slug: str, egg: dict) -> dict:
    """A Pelican egg rendered as a catalog definition.

    Game servers are memory-hungry and the eggs carry no sizing, so these are
    deliberate defaults rather than measurements — flagged in the tags so a
    reviewer can tell them from figures that came from a source.
    """
    env = [{"name": "STEAM_APP_ID", "default": egg["steam_app_id"], "required": False}] \
        if egg.get("steam_app_id") else []
    return {
        "name": egg["name"],
        "hostname": slug.replace("_", "-"),
        "description": egg.get("description", "")[:300],
        "category": "Gaming",
        "cores": 2,
        "memory": 4096,
        "disk_size": "20G",
        "tags": ["game-server", "imported", "unsized"],
        "ports": [],
        "env_vars": env,
        "upstream": STEAM_STORE.format(egg["steam_app_id"]) if egg.get("steam_app_id") else "",
        # provenance: an imported row should always say where it came from
        "imported_from": SOURCES[egg["source"]].repo,
        "docker_images": egg.get("docker_images") or [],
    }


def build(base: dict[str, dict], *, add_games: bool = True,
          refresh: bool = False) -> tuple[dict[str, dict], dict]:
    """Enrich `base` in place and optionally add game servers we do not carry.

    Returns (definitions, report). The report is what makes an import
    reviewable rather than a wall of diffs.
    """
    meta = community_scripts_meta(refresh)
    ash = awesome_selfhosted_links(refresh)
    gsm = linuxgsm_servers(refresh)

    before = len(base)
    defs = base

    # Add first, enrich second. The other way round, every newly imported game
    # skipped link resolution and arrived with an empty upstream unless its egg
    # happened to carry a Steam app ID.
    added: list[str] = []
    if add_games:
        known = {norm(k) for k in defs} | {norm(d.get("name", "")) for d in defs.values()}
        for slug, egg in sorted(pelican_eggs(refresh).items()):
            if slug in known:
                continue
            key = _slug_key(egg["name"], defs)
            defs[key] = _egg_definition(key, egg)
            known.add(slug)
            added.append(key)
        # LinuxGSM covers games the eggs do not; it carries no sizing either
        for short, row in sorted(gsm.items()):
            if norm(row["name"]) in known or norm(short) in known:
                continue
            key = _slug_key(row["name"], defs)
            defs[key] = {
                "name": row["name"], "hostname": key, "description": "",
                "category": "Gaming", "cores": 2, "memory": 4096, "disk_size": "20G",
                "tags": ["game-server", "imported", "unsized"], "ports": [],
                "env_vars": [{"name": "LINUXGSM_NAME", "default": row["server"],
                              "required": False}],
                "upstream": LINUXGSM_PAGE.format(short),
                "imported_from": SOURCES["linuxgsm"].repo,
            }
            known.add(norm(row["name"]))
            added.append(key)

    defs, stats = enrich(defs, meta, ash, gsm)

    resolved = sum(1 for d in defs.values() if d.get("upstream"))
    report = {
        "definitions_before": before,
        "definitions_after": len(defs),
        "games_added": len(added),
        "added_keys": added,
        "with_upstream": resolved,
        "without_upstream": len(defs) - resolved,
        "link_sources": stats,
        "sources": {s.key: {"repo": s.repo, "licence": s.licence,
                            "url": s.url, "takes": s.takes}
                    for s in SOURCES.values()},
    }
    return defs, report
