"""Which GitHub repository owns a class. The generated class records it; a repository listing validates it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from py2cs.model import TypeInfo

Listing = dict[str, list[str]]   # repository (Owner/Name) -> its top level folders


class ResolveError(Exception):
    pass


@dataclass
class Resolution:
    repo: str          # canonical spelling from the listing when there is one
    source: str        # marker | scan


def normalise(repo: str) -> str:
    text = repo.strip().rstrip("/")
    if "github.com/" in text:
        text = text.split("github.com/", 1)[1]
    if text.endswith(".git"):
        text = text[:-4]
    return text


def load_listing(path: Path) -> Listing:
    return {k: list(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def build_listing(clones: dict[str, Path]) -> Listing:
    """Records the top level folders of local clones; used to create the offline test listing."""
    return {repo: sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")) for repo, root in sorted(clones.items())}


def resolve_repo(info: TypeInfo, listing: Listing | None = None) -> Resolution:
    by_lower = {k.lower(): k for k in (listing or {})}

    if info.repo:
        wanted = normalise(info.repo)
        if listing is None:
            return Resolution(wanted, "marker")
        canonical = by_lower.get(wanted.lower())
        if canonical is None:
            raise ResolveError(f"{info.clr_name}: repository {wanted} is not in the repository listing (is the GitHub App installed on it?)")
        return Resolution(canonical, "marker")

    if listing is None:
        raise ResolveError(f"{info.clr_name}: no repo recorded and no repository listing to scan")
    matches = [repo for repo, folders in listing.items() if info.assembly.lower() in (f.lower() for f in folders)]
    if len(matches) == 1:
        return Resolution(matches[0], "scan")
    if not matches:
        raise ResolveError(f"{info.clr_name}: no repository has a folder named {info.assembly}")
    raise ResolveError(f"{info.clr_name}: assembly folder {info.assembly} exists in several repositories: {', '.join(sorted(matches))}")
