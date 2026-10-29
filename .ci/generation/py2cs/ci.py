"""Helpers for the GitHub workflows: which repositories a Python change touches, and a check of a generated package."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from py2cs.compare import compare_manifests
from py2cs.diff import diff_manifests
from py2cs.github import FakeGitHub, FakeRepository, GitHubClient, RestClient
from py2cs.model import Manifest, load_manifest
from py2cs.reader import read_package
from py2cs.resolve import Listing, ResolveError, resolve_repo

def load_allowed(path: Path) -> Listing:
    """The repositories that C# pull requests may be raised in, one Owner/Name per line (# starts a comment).

    A Python pull request names its repository itself (in __bhom__), so without this list it could aim a pull request at any
    repository the GitHub App can reach.
    """
    repos = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
    return {repo: [] for repo in repos}

def affected_repos(base: Manifest, head: Manifest, listing: Listing | None) -> tuple[list[str], list[str]]:
    """(repositories, problems): the repositories that own the added, removed or changed classes."""
    repos: set[str] = set()
    problems: list[str] = []
    for change in diff_manifests(base, head).changes:
        info = head.get(change.clr_name) or base[change.clr_name]
        try:
            repos.add(resolve_repo(info, listing).repo)
        except ResolveError as e:
            problems.append(str(e))
    return sorted(repos), problems

IMPORT_ALL = """
import importlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
failures = []
count = 0
for path in sorted((root / "bhom_schema").rglob("*.py")):
    if path.name == "__init__.py" or "_support" in path.parts:
        continue
    count += 1
    module = ".".join(path.relative_to(root).with_suffix("").parts)
    try:
        importlib.import_module(module)
    except Exception as error:
        failures.append(f"{module}: {type(error).__name__}: {str(error)[:150]}")
print(json.dumps({"count": count, "failures": failures}))
"""

def verify_package(package: Path, manifest: Path | None = None) -> tuple[int, list[str]]:
    """(number of modules, problems): every module of a generated package imports, and it reads back as the C# manifest says.

    The imports run in a separate interpreter, so the checked package does not mix with the one installed in this environment.
    """
    problems: list[str] = []
    environment = dict(os.environ, PYTHONPATH=str(package.parent))
    done = subprocess.run([sys.executable, "-I", "-c", IMPORT_ALL, str(package.parent)], capture_output=True, text=True, env=environment, timeout=900)
    count = 0
    try:
        found = json.loads(done.stdout.strip().splitlines()[-1])
        count = int(found["count"])
        problems += [f"import failed: {f}" for f in found["failures"]]
    except (ValueError, IndexError, KeyError):
        problems.append(f"the import check did not run: {(done.stderr or done.stdout).strip()[:300]}")

    if manifest is not None:
        problems += compare_manifests(load_manifest(manifest), read_package(package), allow_extra=False)
    return count, problems

def make_client(token_env: str | None, offline_repos: list[str] | None = None) -> tuple[GitHubClient, bool]:
    """(client, offline). The token is read from an environment variable, so it is never on a command line.

    Without a token and with offline_repos, empty in-memory repositories stand in, for a dry run on a laptop.
    """
    token = os.environ.get(token_env or "", "")
    if token:
        return RestClient(token), False
    if offline_repos is not None:
        return FakeGitHub({repo: FakeRepository() for repo in offline_repos}), True
    raise ValueError(f"the environment variable {token_env} holds no token")
