"""The linked C# pull request code, run against an in-memory GitHub: branch names, idempotence, dry runs, closing, the REST calls."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from helpers import csharp_tree, demo_package, module, package, require_patcher
from py2cs.__main__ import main
from py2cs.ci import affected_repos, load_allowed, make_client
from py2cs.diff import diff_manifests
from py2cs.github import FakeGitHub, FakeRepository, GitHubError, RestClient
from py2cs.plan import make_plan
from py2cs.pr import MARKER, PythonPr, branch_name, close_linked, raise_pr
from py2cs.reader import read_package
from py2cs.report import render_report

REPO = "BHoM/Demo_Toolkit"
PYTHON_REPO = "BHoM/BHoM_PythonSchema"
PR = PythonPr(PYTHON_REPO, 7, "https://github.com/BHoM/BHoM_PythonSchema/pull/7")

def written_plan(tmp_path: Path, extra: list[str] | None = None, new_class: bool = False, remove_enum: bool = False) -> Path:
    """Runs make_plan on the demo package and writes it the way `py2cs plan` does; returns the plan folder."""
    require_patcher()
    repo_root = csharp_tree(tmp_path / "clones")
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head", extra if extra is not None else ["ProjectNumber: str = ''"])
    if new_class:
        (head_root / "Demo_oM" / "Fresh.py").write_text(module("Fresh", "BH.oM.Demo.Fresh", "BH.oM.Demo", "Demo_oM", body=["X: float = 0.0"]), encoding="utf-8")
    if remove_enum:
        (head_root / "Demo_oM" / "Mode.py").unlink()
    head = read_package(head_root)
    plan = make_plan(diff_manifests(base, head), head, base, lambda r: repo_root, {REPO: ["Demo_oM"]})
    assert plan.errors == []

    out = tmp_path / "plan"
    for f in plan.files:
        target = out / f.repo.replace("/", "__") / f.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.text, encoding="utf-8-sig" if f.bom else "utf-8", newline="")
    (out / "plan.json").write_text(json.dumps(plan.summary()), encoding="utf-8")
    (out / "reports").mkdir()
    (out / "reports" / (REPO.replace("/", "__") + ".md")).write_text(render_report(plan, PR.reference, REPO), encoding="utf-8")
    return out

def github() -> FakeGitHub:
    return FakeGitHub({REPO: FakeRepository(), PYTHON_REPO: FakeRepository()})

# ---------------------------------------------------------------- raising

def test_branch_is_named_after_the_python_pr():
    assert branch_name(7) == "python-schema/pr-7"

def test_first_run_creates_branch_files_draft_pr_label_and_comment(tmp_path: Path):
    plan = written_plan(tmp_path, ["Count: int = 0"])
    remote = github()
    # Make the planned change breaking, as if the type changed: here a plain addition has no label
    result = raise_pr(remote, plan, REPO, PR, python_client=remote)

    assert [c[0] for c in remote.calls] == ["create_branch", "put_file", "create_pull_request", "upsert_comment"]
    pull = remote.repositories[REPO].pull_requests[0]
    assert (pull.head, pull.base, pull.draft) == ("python-schema/pr-7", "develop", True)
    assert pull.title == "Python schema #7: ProjectInfo"
    assert pull.body.startswith("Depends on BHoM/BHoM_PythonSchema#7")
    assert result.pull_request is not None and result.pull_request.url == "https://github.com/BHoM/Demo_Toolkit/pull/1"
    comment = remote.repositories[PYTHON_REPO].comments[7][0]
    assert MARKER in comment and "https://github.com/BHoM/Demo_Toolkit/pull/1" in comment
    assert b"public virtual int Count" in remote.repositories[REPO].files[("python-schema/pr-7", "Demo_oM/AdministrativeInformation/ProjectInfo.cs")]

def test_running_again_changes_nothing(tmp_path: Path):
    plan = written_plan(tmp_path)
    remote = github()
    raise_pr(remote, plan, REPO, PR, python_client=remote)
    remote.calls.clear()

    again = raise_pr(remote, plan, REPO, PR, python_client=remote)
    assert [c[0] for c in remote.calls] == ["upsert_comment"], "same branch, same files, same PR: only the (updated in place) comment is written"
    assert len(remote.repositories[REPO].pull_requests) == 1
    assert len(remote.repositories[PYTHON_REPO].comments[7]) == 1, "the comment is updated, not repeated"
    assert any(a.kind == "unchanged" for a in again.actions)

def test_a_changed_python_pr_updates_the_same_branch_and_pr(tmp_path: Path):
    remote = github()
    raise_pr(remote, written_plan(tmp_path / "one", ["A: int = 0"]), REPO, PR, python_client=remote)
    remote.calls.clear()

    raise_pr(remote, written_plan(tmp_path / "two", ["A: int = 0", "B: str = ''"]), REPO, PR, python_client=remote)
    assert [c[0] for c in remote.calls] == ["put_file", "update_pull_request", "upsert_comment"]
    assert len(remote.repositories[REPO].pull_requests) == 1
    assert "public virtual string B" in remote.repositories[REPO].files[("python-schema/pr-7", "Demo_oM/AdministrativeInformation/ProjectInfo.cs")].decode()

def test_two_python_prs_get_two_branches(tmp_path: Path):
    plan = written_plan(tmp_path)
    remote = github()
    raise_pr(remote, plan, REPO, PythonPr(PYTHON_REPO, 7))
    raise_pr(remote, plan, REPO, PythonPr(PYTHON_REPO, 8))
    assert sorted(p.head for p in remote.repositories[REPO].pull_requests) == ["python-schema/pr-7", "python-schema/pr-8"]

def test_breaking_changes_label_the_pull_request(tmp_path: Path):
    plan = written_plan(tmp_path, remove_enum=True)
    remote = github()
    raise_pr(remote, plan, REPO, PR)
    pull = remote.repositories[REPO].pull_requests[0]
    assert remote.repositories[REPO].labels[pull.number] == ["breaking-change"]

def test_a_dry_run_writes_nothing_and_lists_what_it_would_do(tmp_path: Path):
    plan = written_plan(tmp_path, new_class=True)
    remote = github()
    result = raise_pr(remote, plan, REPO, PR, dry_run=True, python_client=remote)

    assert remote.calls == []
    kinds = [a.kind for a in result.actions]
    assert kinds[:2] == ["create branch", "write file"] and "open draft pull request" in kinds and "comment on the Python pull request" in kinds
    assert result.pull_request is None

def test_nothing_is_done_for_a_repository_with_no_planned_files(tmp_path: Path):
    plan = written_plan(tmp_path)
    remote = FakeGitHub({"BHoM/Other": FakeRepository()})
    result = raise_pr(remote, plan, "BHoM/Other", PR)
    assert remote.calls == [] and result.actions[0].kind == "skip"

def test_a_repository_the_app_cannot_reach_is_an_error(tmp_path: Path):
    plan = written_plan(tmp_path)
    with pytest.raises(GitHubError, match="not found"):
        raise_pr(FakeGitHub({}), plan, REPO, PR)

# ---------------------------------------------------------------- closing

def test_closing_an_unmerged_python_pr_closes_the_linked_draft_with_a_comment(tmp_path: Path):
    remote = github()
    raise_pr(remote, written_plan(tmp_path), REPO, PR)
    remote.calls.clear()

    close_linked(remote, REPO, PR, merged=False)
    pull = remote.repositories[REPO].pull_requests[0]
    assert pull.state == "closed"
    assert "closed without merging" in remote.repositories[REPO].comments[pull.number][0]

def test_a_merged_python_pr_only_comments(tmp_path: Path):
    remote = github()
    raise_pr(remote, written_plan(tmp_path), REPO, PR)
    close_linked(remote, REPO, PR, merged=True)
    pull = remote.repositories[REPO].pull_requests[0]
    assert pull.state == "open" and "was merged" in remote.repositories[REPO].comments[pull.number][0]

def test_closing_with_no_linked_pr_does_nothing():
    remote = github()
    result = close_linked(remote, REPO, PR, merged=False)
    assert remote.calls == [] and result.actions[0].kind == "skip"

def test_closing_dry_run_writes_nothing(tmp_path: Path):
    remote = github()
    raise_pr(remote, written_plan(tmp_path), REPO, PR)
    remote.calls.clear()
    close_linked(remote, REPO, PR, merged=False, dry_run=True)
    assert remote.calls == [] and remote.repositories[REPO].pull_requests[0].state == "open"

# ---------------------------------------------------------------- allowed repositories

def test_only_listed_repositories_may_get_pull_requests(tmp_path: Path):
    allowed = tmp_path / "allowed.txt"
    allowed.write_text("# comment\n\nBHoM/Other_Toolkit\n", encoding="utf-8")
    base = read_package(demo_package(tmp_path / "base"))
    head = read_package(demo_package(tmp_path / "head", ["ProjectNumber: str = ''"]))

    repos, problems = affected_repos(base, head, load_allowed(allowed))
    assert repos == [] and len(problems) == 1 and "BHoM/Demo_Toolkit is not in the repository listing" in problems[0]

    allowed.write_text("bhom/demo_toolkit\n", encoding="utf-8")
    # The spelling of the list wins, so write it as GitHub does
    assert affected_repos(base, head, load_allowed(allowed)) == (["bhom/demo_toolkit"], [])

def test_command_line_repos_prints_json_and_fails_for_a_repository_that_is_not_allowed(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    demo_package(tmp_path / "base")
    demo_package(tmp_path / "head", ["ProjectNumber: str = ''"])
    allowed = tmp_path / "allowed.txt"
    allowed.write_text("BHoM/Demo_Toolkit\n", encoding="utf-8")
    arguments = ["repos", "--base-root", str(tmp_path / "base" / "bhom_schema"), "--head-root", str(tmp_path / "head" / "bhom_schema")]

    assert main([*arguments, "--allowed-repos", str(allowed)]) == 0
    assert json.loads(capsys.readouterr().out) == ["BHoM/Demo_Toolkit"]

    allowed.write_text("BHoM/Elsewhere\n", encoding="utf-8")
    assert main([*arguments, "--allowed-repos", str(allowed)]) == 1
    assert "not in the repository listing" in capsys.readouterr().err

def test_plan_only_repo_leaves_the_other_repositories_out(tmp_path: Path):
    require_patcher()
    repo_root = csharp_tree(tmp_path / "clones")
    base = read_package(demo_package(tmp_path / "base"))
    head = read_package(demo_package(tmp_path / "head", ["ProjectNumber: str = ''"]))
    diff = diff_manifests(base, head)
    assert make_plan(diff, head, base, lambda r: repo_root, None, None, "BHoM/Elsewhere").files == []
    assert len(make_plan(diff, head, base, lambda r: repo_root, None, None, "bhom/demo_toolkit").files) == 1

# ---------------------------------------------------------------- the command line, offline

def test_command_line_dry_run_without_a_token_is_offline(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    plan = written_plan(tmp_path)
    monkeypatch.delenv("PY2CS_CSHARP_TOKEN", raising=False)
    status = main(["pr", "--plan-dir", str(plan), "--repo", REPO, "--python-repo", PYTHON_REPO, "--python-pr", "7", "--dry-run"])
    out = capsys.readouterr().out
    assert status == 0 and "offline dry run" in out
    assert "would create branch BHoM/Demo_Toolkit python-schema/pr-7 from develop" in out
    assert "would open draft pull request" in out

def test_command_line_without_a_token_and_not_a_dry_run_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    plan = written_plan(tmp_path)
    monkeypatch.delenv("PY2CS_CSHARP_TOKEN", raising=False)
    assert main(["pr", "--plan-dir", str(plan), "--repo", REPO, "--python-repo", PYTHON_REPO, "--python-pr", "7"]) == 2
    assert "holds no token" in capsys.readouterr().err

def test_make_client_reads_the_token_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_TOKEN", "ghs_secret")
    client, offline = make_client("SOME_TOKEN")
    assert isinstance(client, RestClient) and not offline
    assert "ghs_secret" not in repr(client)

# ---------------------------------------------------------------- the REST client

class Recorder:
    """A transport that answers from a table and records every request."""

    def __init__(self, answers: dict[tuple[str, str], tuple[int, Any]]):
        self.answers = answers
        self.requests: list[tuple[str, str, dict[str, str], Any]] = []

    def __call__(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        path = url.removeprefix("https://api.github.com")
        self.requests.append((method, path, headers, json.loads(body) if body else None))
        status, data = self.answers.get((method, path), (404, {"message": "Not Found"}))
        return status, json.dumps(data).encode()

def test_rest_client_calls_the_right_endpoints():
    pull: dict[str, Any] = {"number": 3, "html_url": "https://github.com/o/r/pull/3", "head": {"ref": "python-schema/pr-7"}, "base": {"ref": "develop"}, "title": "t", "body": "b", "draft": True, "state": "open"}
    content = base64.b64encode(b"hello").decode()
    transport = Recorder({
        ("GET", "/repos/o/r"): (200, {"default_branch": "develop"}),
        ("GET", "/repos/o/r/git/ref/heads/develop"): (200, {"object": {"sha": "abc"}}),
        ("POST", "/repos/o/r/git/refs"): (201, {}),
        ("GET", "/repos/o/r/contents/a%20b/File.cs?ref=python-schema%2Fpr-7"): (200, {"sha": "blob1", "content": content}),
        ("PUT", "/repos/o/r/contents/a%20b/File.cs"): (200, {}),
        ("GET", "/repos/o/r/pulls?state=open&head=o%3Apython-schema%2Fpr-7"): (200, [pull]),
        ("POST", "/repos/o/r/pulls"): (201, pull),
        ("PATCH", "/repos/o/r/pulls/3"): (200, pull),
        ("POST", "/repos/o/r/issues/3/labels"): (200, []),
        ("GET", "/repos/o/r/issues/3/comments?per_page=100"): (200, [{"id": 11, "body": f"{MARKER} old"}]),
        ("PATCH", "/repos/o/r/issues/comments/11"): (200, {}),
    })
    client = RestClient("tok", transport=transport)

    assert client.default_branch("o/r") == "develop"
    assert client.branch_sha("o/r", "develop") == "abc"
    assert client.branch_sha("o/r", "missing") is None
    client.create_branch("o/r", "python-schema/pr-7", "abc")
    found = client.get_file("o/r", "python-schema/pr-7", "a b/File.cs")
    assert found is not None and (found.sha, found.content) == ("blob1", b"hello")
    client.put_file("o/r", "python-schema/pr-7", "a b/File.cs", b"new", "message", "blob1")
    existing = client.find_pull_request("o/r", "python-schema/pr-7")
    assert existing is not None and (existing.number, existing.draft) == (3, True)
    assert client.create_pull_request("o/r", "python-schema/pr-7", "develop", "t", "b", True).number == 3
    client.update_pull_request("o/r", 3, "t", "b")
    client.add_labels("o/r", 3, ["breaking-change"])
    client.upsert_comment("o/r", 3, MARKER, f"{MARKER} new")
    client.close_pull_request("o/r", 3)

    by_call = {(m, p): b for m, p, _, b in transport.requests}
    assert by_call[("POST", "/repos/o/r/git/refs")] == {"ref": "refs/heads/python-schema/pr-7", "sha": "abc"}
    put = by_call[("PUT", "/repos/o/r/contents/a%20b/File.cs")]
    assert put == {"message": "message", "content": base64.b64encode(b"new").decode(), "branch": "python-schema/pr-7", "sha": "blob1"}
    assert by_call[("POST", "/repos/o/r/pulls")] == {"title": "t", "head": "python-schema/pr-7", "base": "develop", "body": "b", "draft": True}
    assert by_call[("PATCH", "/repos/o/r/issues/comments/11")] == {"body": f"{MARKER} new"}, "the existing comment is updated"
    assert by_call[("PATCH", "/repos/o/r/pulls/3")] == {"state": "closed"}, "the last call to this pull request closed it"
    assert all(h["Authorization"] == "Bearer tok" for _, _, h, _ in transport.requests)

def test_rest_client_posts_a_new_comment_when_there_is_no_marker():
    transport = Recorder({("GET", "/repos/o/r/issues/3/comments?per_page=100"): (200, [{"id": 1, "body": "someone else"}]), ("POST", "/repos/o/r/issues/3/comments"): (201, {})})
    RestClient("tok", transport=transport).upsert_comment("o/r", 3, MARKER, "text")
    assert transport.requests[-1][:2] == ("POST", "/repos/o/r/issues/3/comments")

def test_rest_errors_name_the_call_but_never_the_token():
    transport = Recorder({("GET", "/repos/o/r"): (403, {"message": "Resource not accessible by integration"})})
    with pytest.raises(GitHubError) as error:
        RestClient("secret-token", transport=transport).default_branch("o/r")
    assert "GET /repos/o/r failed with 403: Resource not accessible by integration" in str(error.value)
    assert "secret-token" not in str(error.value)

def test_a_client_without_a_token_is_refused():
    with pytest.raises(GitHubError):
        RestClient("")
