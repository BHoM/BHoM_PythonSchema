"""The build plan of Build-Repositories.ps1: the key of each repository, the build order and the restore from the build cache, with no network and no build."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / ".github" / "scripts" / "Build-Repositories.ps1"
SHELL = shutil.which("pwsh") or shutil.which("powershell")
COMMITS = {"BHoM/BHoM": "a" * 40, "BHoM/BHoM_Engine": "b" * 40, "BHoM/JSONSchema_Toolkit": "c" * 40, "BHoM/CSharpSchema_Test": "d" * 40}
DEPENDENCIES = {"BHoM_Engine": ["BHoM/BHoM"], "JSONSchema_Toolkit": ["BHoM/BHoM", "BHoM/BHoM_Engine", "BHoM/Unlisted_Toolkit"], "CSharpSchema_Test": ["BHoM/BHoM"]}

pytestmark = pytest.mark.skipif(SHELL is None, reason="PowerShell is not installed")

def run(folder: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Runs Build-Repositories.ps1 in the folder with the given arguments, without the GitHub output file of an enclosing workflow step.

    Every test here uses it, and fails when the script fails.
    """
    environment = {key: value for key, value in os.environ.items() if key != "GITHUB_OUTPUT"}
    result = subprocess.run([str(SHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *arguments],
                            cwd=folder, env=environment, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return result

def plan(folder: Path, commits: dict[str, str] | None = None, os_name: str = "Windows", tools: str = "tools 1", salt: str = "v1") -> dict[str, Any]:
    """Writes the list, the commits and the dependencies.txt files into the folder, runs the plan and returns it as read from the plan file.

    The tests compare the keys of plans made from small changes to these inputs.
    """
    commits = commits or COMMITS
    (folder / "list.txt").write_text("\n".join(commits) + "\n", encoding="utf-8")
    (folder / "commits.txt").write_text("".join(f"{repository} {commit}\n" for repository, commit in commits.items()), encoding="utf-8")
    for name, dependencies in DEPENDENCIES.items():
        (folder / "dependencies" / name).mkdir(parents=True, exist_ok=True)
        (folder / "dependencies" / name / "dependencies.txt").write_text("\n".join(dependencies) + "\n", encoding="utf-8")
    run(folder, "-List", "list.txt", "-Plan", "-PlanFile", "plan.json", "-CommitsFile", "commits.txt", "-DependenciesRoot", "dependencies",
        "-OS", os_name, "-ToolsVersion", tools, "-Salt", salt)
    return json.loads((folder / "plan.json").read_text(encoding="utf-8-sig"))

def keys(built: dict[str, Any]) -> dict[str, str]:
    """Returns the key of each repository of a plan, by name."""
    return {repository["name"]: repository["key"] for repository in built["repositories"]}

def test_the_order_puts_each_repository_after_its_listed_dependencies(tmp_path: Path):
    """Checks that the plan orders the repositories after their dependencies, keeps only the listed dependencies, and names each entry after the repository and its key.

    Protects the build, where a repository reads its dependencies' assemblies from the installation.
    """
    built = plan(tmp_path)
    order = [repository["name"] for repository in built["repositories"]]
    assert order.index("BHoM") < order.index("BHoM_Engine") < order.index("JSONSchema_Toolkit")
    assert order.index("BHoM") < order.index("CSharpSchema_Test")
    toolkit = next(r for r in built["repositories"] if r["name"] == "JSONSchema_Toolkit")
    assert toolkit["dependencies"] == ["BHoM", "BHoM_Engine"], "an unlisted dependency is left out"
    assert all(r["entry"] == f"{r['name']}-{r['key'][:16]}" for r in built["repositories"])

def test_a_new_commit_changes_the_key_of_the_repository_and_of_what_depends_on_it_only(tmp_path: Path):
    """Checks that a new commit in one repository changes exactly its own key and the keys of the repositories that depend on it, directly or not.

    Protects the point of the cache: a change rebuilds only what it can affect.
    """
    (tmp_path / "before").mkdir()
    before = keys(plan(tmp_path / "before"))
    cases = {
        "BHoM/CSharpSchema_Test": {"CSharpSchema_Test"},
        "BHoM/BHoM_Engine": {"BHoM_Engine", "JSONSchema_Toolkit"},
        "BHoM/BHoM": {"BHoM", "BHoM_Engine", "JSONSchema_Toolkit", "CSharpSchema_Test"},
    }
    for repository, expected in cases.items():
        folder = tmp_path / repository.split("/")[1]
        folder.mkdir()
        after = keys(plan(folder, {**COMMITS, repository: "e" * 40}))
        assert {name for name in before if before[name] != after[name]} == expected, repository

def test_the_salt_the_os_and_the_tools_change_every_key(tmp_path: Path):
    """Checks that a new salt, OS or build tools change the key of every repository, and that only the tools leave the state prefix unchanged.

    Protects the cache from restoring what other tools built, and the refresh gate, which looks the state up on ubuntu without the Windows tools.
    """
    (tmp_path / "base").mkdir()
    base = plan(tmp_path / "base")
    for name, change in (("salt", {"salt": "v2"}), ("os", {"os_name": "Linux"}), ("tools", {"tools": "tools 2"})):
        (tmp_path / name).mkdir()
        changed = plan(tmp_path / name, **change)
        assert all(keys(base)[r] != keys(changed)[r] for r in keys(base)), name
        assert changed["cacheKey"] != base["cacheKey"], name
        assert (changed["statePrefix"] == base["statePrefix"]) == (name == "tools"), name
    assert base["cacheKey"].startswith(base["statePrefix"]) and base["statePrefix"].startswith(base["cachePrefix"])
    assert base["cachePrefix"] == "bhom-build-cache-v1-Windows-"

@pytest.mark.skipif(sys.platform != "win32", reason="the restore copies with robocopy")
def test_a_run_with_every_entry_cached_copies_them_clones_nothing_and_prunes_old_entries(tmp_path: Path):
    """Checks that when the folder holds every planned entry, the build copies them into the installation in build order, clones and builds nothing, deletes the entries of other keys, and writes commits.txt.

    Protects the fast path of the PR checks and the size of the cache.
    """
    built = plan(tmp_path)
    cache = tmp_path / "cache"
    for repository in built["repositories"]:
        assemblies = cache / repository["entry"] / "Assemblies"
        assemblies.mkdir(parents=True)
        (assemblies / f"{repository['name']}.dll").write_text(repository["name"], encoding="utf-8")
        # Shared by two entries: the one built later wins, as in a real build
        (assemblies / "Shared.dll").write_text(repository["name"], encoding="utf-8")
    (cache / "BHoM-0000000000000000").mkdir()
    result = run(tmp_path, "-List", "list.txt", "-PlanFile", "plan.json", "-CacheFolder", "cache", "-BHoMRoot", "installation", "-ReposRoot", "repos")
    installation = tmp_path / "installation"
    assert all((installation / "Assemblies" / f"{name}.dll").exists() for name in keys(built))
    assert (installation / "Assemblies" / "Shared.dll").read_text(encoding="utf-8") == built["repositories"][-1]["name"]
    assert all((installation / folder).is_dir() for folder in ("Datasets", "Upgrades", "Settings", "Developer"))
    assert sorted(p.name for p in cache.iterdir()) == sorted(r["entry"] for r in built["repositories"])
    assert [p.name for p in (tmp_path / "repos").iterdir()] == ["commits.txt"], "nothing is cloned"
    commits = (tmp_path / "repos" / "commits.txt").read_text(encoding="utf-8").splitlines()
    assert commits == [f"{r['repository']} {r['commit']}" for r in built["repositories"]]
    assert "Built: nothing" in result.stdout
