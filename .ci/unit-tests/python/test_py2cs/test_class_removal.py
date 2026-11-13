"""A class removed in Python is removed from the C# too: the plan, the pull request and the report, run against fake C# trees and an in-memory GitHub."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from helpers import Recorder, csharp_tree, demo_package, mock_github, module, package, require_patcher
from py2cs.__main__ import main
from py2cs.diff import diff_manifests
from py2cs.github import RestClient
from py2cs.plan import Plan, make_plan
from py2cs.pr import PythonPr, branch_name, raise_pr
from py2cs.reader import read_package
from py2cs.report import render_report

REPO = "BHoM/Demo_Toolkit"
LISTING = {REPO: ["Demo_oM"], "BHoM/Other_Toolkit": ["Other_oM"]}
PR = PythonPr("BHoM/BHoM_PythonSchema", 9, "https://github.com/BHoM/BHoM_PythonSchema/pull/9")
DOOR = "Demo_oM/Elements/Door.cs"
SEVERAL = "Demo_oM/Misc/Several.cs"

def door() -> str:
    """Returns the Python module of the class Door, which sits alone in its C# file in the fake repository."""
    return module("Door", "BH.oM.Demo.Elements.Door", "BH.oM.Demo.Elements", "Demo_oM", body=["Width: float = 0.0"])

def several(name: str) -> str:
    """Returns the Python module of Alpha or Beta, which share one C# file in the fake repository."""
    return module(name, f"BH.oM.Demo.{name}", "BH.oM.Demo", "Demo_oM", body=["Size: int = 0"])

def thing() -> str:
    """Returns the Python module of Thing, which belongs to another C# repository in the listing."""
    return module("Thing", "BH.oM.Other.Thing", "BH.oM.Other", "Other_oM", repo="BHoM/Other_Toolkit")

def tree_hash(root: Path) -> str:
    """Hashes every file under a folder, to prove that planning wrote nothing into the C# checkout."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()

def plan_removal(tmp_path: Path, base_modules: dict[str, str], head_modules: dict[str, str] | None = None, extra: list[str] | None = None,
                 only_repo: str | None = None, drop: list[str] | None = None) -> tuple[Plan, Path]:
    """Plans the change from a base package with the given modules added to the demo package to a head that has `head_modules` instead (none by default, so everything extra is removed).

    Returns the plan and the fake C# repository it was made against. Every test of this file starts from it.
    """
    require_patcher()
    repo_root = csharp_tree(tmp_path / "clones")
    base = read_package(package(demo_package(tmp_path / "base").parent, base_modules))
    head_root = package(demo_package(tmp_path / "head", extra or []).parent, head_modules or {})
    for name in drop or []:
        (head_root / name).unlink()

    head = read_package(head_root)
    plan = make_plan(diff_manifests(base, head), head, base, lambda r: repo_root if r == REPO else None, LISTING, only_repo=only_repo)
    return plan, repo_root

def write_plan(plan: Plan, out: Path) -> Path:
    """Writes a plan folder the way `py2cs plan` does (no file for a delete) and returns it, as the input of `raise_pr`."""
    for f in plan.files:
        if f.action == "delete":
            continue

        target = out / f.repo.replace("/", "__") / f.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.text, encoding="utf-8-sig" if f.bom else "utf-8", newline="")

    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan.summary()), encoding="utf-8")
    (out / "reports").mkdir(exist_ok=True)
    (out / "reports" / (REPO.replace("/", "__") + ".md")).write_text(render_report(plan, PR.reference, REPO), encoding="utf-8")
    return out

# ---------------------------------------------------------------- the plan

def test_a_removed_class_alone_in_its_file_deletes_the_file(tmp_path: Path):
    """Checks that a class removed in Python, alone in its C# file, becomes one planned delete with the breaking line and the label, and that the clone is not written to.

    Protects the main case: the draft removes the C# of the class, and the file with it.
    """
    plan, repo_root = plan_removal(tmp_path, {"Demo_oM/Door.py": door()})
    hashed = tree_hash(repo_root)

    assert plan.errors == [] and plan.removed == []
    assert [(f.repo, f.path, f.action, f.clr_name) for f in plan.files] == [(REPO, DOOR, "delete", "BH.oM.Demo.Elements.Door")]
    assert plan.files[0].text == "" and plan.files[0].breaking == ["type removed"]
    assert plan.labels() == ["breaking-change"] and plan.repos() == [REPO]
    assert tree_hash(repo_root) == hashed

    report = render_report(plan, "BHoM/BHoM_PythonSchema#9")
    assert f"### `{DOOR}` (file deleted)" in report and "- `BH.oM.Demo.Elements.Door`: type removed" in report
    assert "Removed in Python, but no C# declaration" not in report

def test_a_removed_class_that_shares_its_file_is_removed_from_the_file_only(tmp_path: Path):
    """Checks that removing Alpha, which shares a C# file with Beta, plans a patch that drops Alpha and keeps Beta and the rest of the file.

    Protects the files that declare several types: only the class named by the Python change goes.
    """
    plan, repo_root = plan_removal(tmp_path, {"Demo_oM/Alpha.py": several("Alpha"), "Demo_oM/Beta.py": several("Beta")}, {"Demo_oM/Beta.py": several("Beta")})
    original = (repo_root / SEVERAL).read_text(encoding="utf-8")

    assert plan.errors == [] and plan.removed == []
    planned = plan.files[0]
    assert (planned.path, planned.action, planned.changes) == (SEVERAL, "patch", ["type removed"])
    assert "class Alpha" not in planned.text and "class Beta : IObject" in planned.text
    assert planned.text.count("namespace BH.oM.Demo") == 1 and original.count("namespace BH.oM.Demo") == 2
    assert f"### `{SEVERAL}` (type removed)" in render_report(plan)

def test_a_removed_class_with_no_c_sharp_declaration_is_listed_not_planned(tmp_path: Path):
    """Checks that a class removed in Python that no C# file declares (already removed, or never in this repository) plans nothing and is listed in the report.

    Protects the case where the C# is already in step with the Python.
    """
    plan, _ = plan_removal(tmp_path, {}, {}, drop=["Demo_oM/Mode.py"])
    assert plan.files == [] and plan.removed == [(REPO, "BH.oM.Demo.Mode")]

    report = render_report(plan)
    assert "Removed in Python, but no C# declaration of it was found" in report and "BH.oM.Demo.Mode" in report

def test_a_removal_is_planned_together_with_a_change_to_another_class(tmp_path: Path):
    """Checks that a removed class and a new property on another class in one change give a delete and a patch for the same repository.

    Protects a mixed pull request: the draft carries both, and the breaking section names the removal.
    """
    plan, _ = plan_removal(tmp_path, {"Demo_oM/Door.py": door()}, extra=["ProjectNumber: str = ''"])
    by_type = {f.clr_name: f.action for f in plan.files}

    assert plan.errors == []
    assert by_type == {"BH.oM.Demo.Elements.Door": "delete", "BH.oM.Demo.ProjectInfo": "patch"}
    assert plan.repos() == [REPO]
    assert "- `BH.oM.Demo.Elements.Door`: type removed" in render_report(plan)

def test_a_renamed_class_deletes_the_old_file_and_drafts_the_new_one(tmp_path: Path):
    """Checks that a class removed and another added in one change (a rename) give a delete of the old file and a new file for the new class.

    Protects the rename case, which Python cannot tell from a removal and an addition.
    """
    renamed = module("Gate", "BH.oM.Demo.Elements.Gate", "BH.oM.Demo.Elements", "Demo_oM", body=["Width: float = 0.0"])
    plan, _ = plan_removal(tmp_path, {"Demo_oM/Door.py": door()}, {"Demo_oM/Gate.py": renamed})

    assert plan.errors == []
    assert {(f.clr_name, f.action) for f in plan.files} == {("BH.oM.Demo.Elements.Door", "delete"), ("BH.oM.Demo.Elements.Gate", "new")}

def test_only_the_repository_asked_for_is_planned(tmp_path: Path):
    """Checks that with only_repo a class removed from another repository is left out of the plan, and one of the named repository is planned.

    Protects the linked-PR job, which plans one repository at a time.
    """
    modules = {"Demo_oM/Door.py": door(), "Other_oM/Thing.py": thing()}
    plan, _ = plan_removal(tmp_path, modules, only_repo=REPO)
    assert [(f.clr_name, f.action) for f in plan.files] == [("BH.oM.Demo.Elements.Door", "delete")] and plan.removed == []

    other, _ = plan_removal(tmp_path / "second", modules, only_repo="BHoM/Other_Toolkit")
    assert other.files == [] and other.removed == [("BHoM/Other_Toolkit", "BH.oM.Other.Thing")]

# ---------------------------------------------------------------- the pull request

def remote_with(path: str, plan_text: str = "x") -> Any:
    """Returns a mock GitHub whose develop branch holds the given C# file, as the real repository would before the change."""
    remote = mock_github(REPO)
    remote.repositories[REPO].files[("develop", path)] = plan_text.encode()
    return remote

def test_a_removal_only_plan_raises_a_draft_that_deletes_the_file(tmp_path: Path):
    """Checks that a plan with only a removed class creates the branch, deletes the file on it, opens a labelled draft and comments on the Python PR, and leaves develop alone.

    This is the case that used to be skipped with `no planned files for this repository`.
    """
    plan, _ = plan_removal(tmp_path, {"Demo_oM/Door.py": door()})
    folder = write_plan(plan, tmp_path / "plan")
    remote = remote_with(DOOR)

    result = raise_pr(remote, folder, REPO, PR, python_client=remote)

    assert [c[0] for c in remote.calls] == ["create_branch", "delete_file", "create_pull_request", "add_labels", "upsert_comment"]
    assert ("delete_file", REPO, branch_name(9), DOOR) in remote.calls
    files = remote.repositories[REPO].files
    assert (branch_name(9), DOOR) not in files and ("develop", DOOR) in files
    pull = remote.repositories[REPO].pull_requests[0]
    assert (pull.head, pull.draft, pull.title) == (branch_name(9), True, "Python schema #9: Door")
    assert remote.repositories[REPO].labels[pull.number] == ["breaking-change"]
    assert "(file deleted)" in pull.body
    assert [a.kind for a in result.actions][:2] == ["create branch", "delete file"]

def test_a_dry_run_lists_the_deletion_and_writes_nothing(tmp_path: Path):
    """Checks that a dry run names the file it would delete and makes no call that changes anything.

    Protects the offline preview that people run before pushing.
    """
    plan, _ = plan_removal(tmp_path, {"Demo_oM/Door.py": door()})
    remote = remote_with(DOOR)

    result = raise_pr(remote, write_plan(plan, tmp_path / "plan"), REPO, PR, dry_run=True, python_client=remote)

    assert remote.calls == []
    assert f"delete file {REPO} {DOOR}" in [str(a) for a in result.actions]

def test_running_again_and_pushing_again_delete_nothing_twice(tmp_path: Path):
    """Checks that a second run for the same Python PR finds the file already gone from the branch and does not delete or open anything again.

    Protects the idempotence of a re-run and of a later push to the Python PR.
    """
    plan, _ = plan_removal(tmp_path, {"Demo_oM/Door.py": door()})
    folder = write_plan(plan, tmp_path / "plan")
    remote = remote_with(DOOR)
    raise_pr(remote, folder, REPO, PR, python_client=remote)
    remote.calls.clear()

    again = raise_pr(remote, folder, REPO, PR, python_client=remote)

    # The label is added again (GitHub keeps one) and the comment is updated in place; nothing is deleted or opened twice
    assert [c[0] for c in remote.calls] == ["add_labels", "upsert_comment"]
    assert "unchanged" in [a.kind for a in again.actions] and len(remote.repositories[REPO].pull_requests) == 1

def test_nothing_is_raised_when_the_base_already_lacks_the_file(tmp_path: Path):
    """Checks that a removal whose file is already gone from the default branch (the C# was merged) raises nothing: no branch, no pull request.

    Protects a Python PR whose C# change was merged: GitHub refuses a pull request with no commits.
    """
    plan, _ = plan_removal(tmp_path, {"Demo_oM/Door.py": door()})
    remote = mock_github(REPO)

    result = raise_pr(remote, write_plan(plan, tmp_path / "plan"), REPO, PR, python_client=remote)

    assert remote.calls == [] and [a.kind for a in result.actions] == ["skip"]

def test_a_patch_and_a_delete_in_one_pull_request(tmp_path: Path):
    """Checks that one pull request can carry a patched file and a deleted file: the patch is written and the other file is deleted on the same branch.

    Protects the mixed change of the sync test.
    """
    plan, repo_root = plan_removal(tmp_path, {"Demo_oM/Door.py": door()}, extra=["ProjectNumber: str = ''"])
    folder = write_plan(plan, tmp_path / "plan")
    remote = mock_github(REPO)
    for name in (DOOR, "Demo_oM/AdministrativeInformation/ProjectInfo.cs"):
        remote.repositories[REPO].files[("develop", name)] = (repo_root / name).read_bytes()

    raise_pr(remote, folder, REPO, PR, python_client=remote)

    assert ("put_file", REPO, branch_name(9), "Demo_oM/AdministrativeInformation/ProjectInfo.cs") in remote.calls
    assert ("delete_file", REPO, branch_name(9), DOOR) in remote.calls

def test_the_command_line_plans_a_deletion_without_writing_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    """Checks that `py2cs plan` records a deletion in plan.json without writing a file for it, and that `py2cs pr --dry-run` then says it would delete the file.

    Protects the command line the workflow runs, step by step.
    """
    require_patcher()
    repo_root = csharp_tree(tmp_path / "clones")
    base = package(demo_package(tmp_path / "base").parent, {"Demo_oM/Door.py": door()})
    head = demo_package(tmp_path / "head")
    allowed = tmp_path / "allowed.txt"
    allowed.write_text(f"{REPO}\n", encoding="utf-8")
    out = tmp_path / "plan"

    status = main(["plan", "--base-root", str(base), "--head-root", str(head), "--clones-parent", str(repo_root.parent), "--allowed-repos", str(allowed),
                   "--only-repo", REPO, "--python-pr", "BHoM/BHoM_PythonSchema#9", "--out", str(out)])
    assert status == 0 and "1 files planned in 1 repositories, 0 problems" in capsys.readouterr().out
    entries = json.loads((out / "plan.json").read_text(encoding="utf-8"))["files"]
    assert [(e["path"], e["action"]) for e in entries] == [(DOOR, "delete")]
    assert not (out / REPO.replace("/", "__") / DOOR).exists()

    monkeypatch.delenv("PY2CS_CSHARP_TOKEN", raising=False)
    status = main(["pr", "--plan-dir", str(out), "--repo", REPO, "--python-repo", "BHoM/BHoM_PythonSchema", "--python-pr", "9", "--dry-run"])
    output = capsys.readouterr().out
    assert status == 0 and f"would delete file {REPO} {DOOR}" in output

def test_the_rest_client_deletes_a_file_with_its_sha():
    """Checks that RestClient.delete_file sends a DELETE to the contents endpoint with the message, the blob sha and the branch.

    Protects the one new call that the removal needs from the GitHub API.
    """
    transport = Recorder({("DELETE", "/repos/o/r/contents/a%20b/File.cs"): (200, {})})
    RestClient("tok", transport=transport).delete_file("o/r", "python-schema/pr-9", "a b/File.cs", "message", "blob1")

    method, path, _, body = transport.requests[0]
    assert (method, path) == ("DELETE", "/repos/o/r/contents/a%20b/File.cs")
    assert body == {"message": "message", "sha": "blob1", "branch": "python-schema/pr-9"}
