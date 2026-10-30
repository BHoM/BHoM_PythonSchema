"""The linked C# pull request code, run against an in-memory GitHub: branch names, idempotence, dry runs, closing, the REST calls."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from helpers import Recorder, csharp_tree, demo_package, mock_github, module, package, require_patcher
from py2cs.__main__ import main
from py2cs.ci import affected_repos, load_allowed, make_client
from py2cs.diff import diff_manifests
from py2cs.github import MockGitHub, MockRepository, GitHubError, RestClient
from py2cs.plan import make_plan
from py2cs.pr import MARKER, PythonPr, branch_name, close_linked, raise_pr
from py2cs.reader import read_package
from py2cs.report import render_report

REPO = "BHoM/Demo_Toolkit"
PYTHON_REPO = "BHoM/BHoM_PythonSchema"
PR = PythonPr(PYTHON_REPO, 7, "https://github.com/BHoM/BHoM_PythonSchema/pull/7")

def written_plan(tmp_path: Path, extra: list[str] | None = None, new_class: bool = False, remove_enum: bool = False) -> Path:
    """Runs make_plan on the demo package (with the extra fields, a new class or a removed enum as asked), writes the plan folder the way py2cs plan does and returns that folder.

    The raise, close and offline command line tests use it as the input of py2cs pr.
    """
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

# ---------------------------------------------------------------- raising

def test_branch_is_named_after_the_python_pr():
    """Checks that the linked branch is named python-schema/pr-<number> after the Python PR.

    Protects the link that the status, close and sweep jobs use to find the C# PR.
    """
    assert branch_name(7) == "python-schema/pr-7"

def test_first_run_creates_branch_files_draft_pr_label_and_comment(tmp_path: Path):
    """Checks that the first raise_pr run creates the branch, writes the planned file, opens a draft PR with the right title and Depends on text, and comments on the Python PR.

    Protects the linked-PR workflow's raise job.
    """
    plan = written_plan(tmp_path, ["Count: int = 0"])
    remote = mock_github(REPO)
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
    """Checks that running raise_pr again with the same plan writes only the Python PR comment (updated in place) and opens no second PR.

    Protects the raise job from noise when the workflow re-runs.
    """
    plan = written_plan(tmp_path)
    remote = mock_github(REPO)
    raise_pr(remote, plan, REPO, PR, python_client=remote)
    remote.calls.clear()

    again = raise_pr(remote, plan, REPO, PR, python_client=remote)
    assert [c[0] for c in remote.calls] == ["upsert_comment"], "same branch, same files, same PR: only the (updated in place) comment is written"
    assert len(remote.repositories[REPO].pull_requests) == 1
    assert len(remote.repositories[PYTHON_REPO].comments[7]) == 1, "the comment is updated, not repeated"
    assert any(a.kind == "unchanged" for a in again.actions)

def test_nothing_is_raised_when_the_base_already_has_the_planned_files(tmp_path: Path):
    """Checks that raise_pr skips, creating no branch and no pull request, when the default branch already holds every planned file with the same content and no draft is open, also when an empty branch is left over.

    Protects a pushed-to Python PR whose C# pull request was merged and its branch deleted: GitHub refuses a pull request with no commits.
    """
    plan = written_plan(tmp_path)
    remote = mock_github(REPO)
    for path in (plan / REPO.replace("/", "__")).rglob("*.cs"):
        remote.repositories[REPO].files[("develop", path.relative_to(plan / REPO.replace("/", "__")).as_posix())] = path.read_bytes()

    result = raise_pr(remote, plan, REPO, PR, python_client=remote)
    assert remote.calls == []
    assert [a.kind for a in result.actions] == ["skip"]

    # An empty branch left by an earlier run changes nothing: still no pull request
    remote.repositories[REPO].branches[branch_name(7)] = "sha-0"
    assert [a.kind for a in raise_pr(remote, plan, REPO, PR, python_client=remote).actions] == ["skip"]
    assert remote.calls == []


def test_a_changed_python_pr_updates_the_same_branch_and_pr(tmp_path: Path):
    """Checks that a changed plan updates the same branch and the same draft PR instead of opening another.

    Protects the raise job when a developer pushes more commits to the Python PR.
    """
    remote = mock_github(REPO)
    raise_pr(remote, written_plan(tmp_path / "one", ["A: int = 0"]), REPO, PR, python_client=remote)
    remote.calls.clear()

    raise_pr(remote, written_plan(tmp_path / "two", ["A: int = 0", "B: str = ''"]), REPO, PR, python_client=remote)
    assert [c[0] for c in remote.calls] == ["put_file", "update_pull_request", "upsert_comment"]
    assert len(remote.repositories[REPO].pull_requests) == 1
    assert "public virtual string B" in remote.repositories[REPO].files[("python-schema/pr-7", "Demo_oM/AdministrativeInformation/ProjectInfo.cs")].decode()

def test_two_python_prs_get_two_branches(tmp_path: Path):
    """Checks that two Python PRs get two separate branches and draft PRs in the C# repository.

    Protects the link between each Python PR and its C# PR.
    """
    plan = written_plan(tmp_path)
    remote = mock_github(REPO)
    raise_pr(remote, plan, REPO, PythonPr(PYTHON_REPO, 7))
    raise_pr(remote, plan, REPO, PythonPr(PYTHON_REPO, 8))
    assert sorted(p.head for p in remote.repositories[REPO].pull_requests) == ["python-schema/pr-7", "python-schema/pr-8"]

def test_breaking_changes_label_the_pull_request(tmp_path: Path):
    """Checks that a plan with a breaking change puts the breaking-change label on the draft C# PR.

    Protects the label that tells reviewers a change may break users.
    """
    plan = written_plan(tmp_path, remove_enum=True)
    remote = mock_github(REPO)
    raise_pr(remote, plan, REPO, PR)
    pull = remote.repositories[REPO].pull_requests[0]
    assert remote.repositories[REPO].labels[pull.number] == ["breaking-change"]

def test_a_dry_run_writes_nothing_and_lists_what_it_would_do(tmp_path: Path):
    """Checks that a dry run of raise_pr makes no GitHub calls and lists the actions it would do.

    Protects the preview of the raise job.
    """
    plan = written_plan(tmp_path, new_class=True)
    remote = mock_github(REPO)
    result = raise_pr(remote, plan, REPO, PR, dry_run=True, python_client=remote)

    assert remote.calls == []
    kinds = [a.kind for a in result.actions]
    assert kinds[:2] == ["create branch", "write file"] and "open draft pull request" in kinds and "comment on the Python pull request" in kinds
    assert result.pull_request is None

def test_nothing_is_done_for_a_repository_with_no_planned_files(tmp_path: Path):
    """Checks that raise_pr skips a repository the plan has no files for and makes no GitHub calls.

    Protects the raise job's matrix, which runs once per affected repository.
    """
    plan = written_plan(tmp_path)
    remote = MockGitHub({"BHoM/Other": MockRepository()})
    result = raise_pr(remote, plan, "BHoM/Other", PR)
    assert remote.calls == [] and result.actions[0].kind == "skip"

def test_a_repository_the_app_cannot_reach_is_an_error(tmp_path: Path):
    """Checks that raise_pr raises a GitHubError when the repository is not reachable with the token.

    Protects the raise job from silently dropping a C# change.
    """
    plan = written_plan(tmp_path)
    with pytest.raises(GitHubError, match="not found"):
        raise_pr(MockGitHub({}), plan, REPO, PR)

# ---------------------------------------------------------------- closing

def test_closing_an_unmerged_python_pr_closes_the_linked_draft_with_a_comment(tmp_path: Path):
    """Checks that close_linked closes the linked draft PR and comments that the Python PR was closed without merging when it was not merged.

    Protects the close job of the linked-PR workflow.
    """
    remote = mock_github(REPO)
    raise_pr(remote, written_plan(tmp_path), REPO, PR)
    remote.calls.clear()

    close_linked(remote, REPO, PR, merged=False)
    pull = remote.repositories[REPO].pull_requests[0]
    assert pull.state == "closed"
    assert "closed without merging" in remote.repositories[REPO].comments[pull.number][0]

def test_a_merged_python_pr_only_comments(tmp_path: Path):
    """Checks that close_linked leaves the linked C# PR open and only comments that the Python PR was merged.

    Protects the close job, since a person merges the C# PR.
    """
    remote = mock_github(REPO)
    raise_pr(remote, written_plan(tmp_path), REPO, PR)
    close_linked(remote, REPO, PR, merged=True)
    pull = remote.repositories[REPO].pull_requests[0]
    assert pull.state == "open" and "was merged" in remote.repositories[REPO].comments[pull.number][0]

def test_closing_with_no_linked_pr_does_nothing():
    """Checks that close_linked makes no changes and returns a skip action when no linked PR exists.

    Protects the close job for Python PRs that needed no C# change.
    """
    remote = mock_github(REPO)
    result = close_linked(remote, REPO, PR, merged=False)
    assert remote.calls == [] and result.actions[0].kind == "skip"

def test_closing_dry_run_writes_nothing(tmp_path: Path):
    """Checks that a dry run of close_linked leaves the linked PR open and makes no GitHub calls.

    Protects the preview of the close job.
    """
    remote = mock_github(REPO)
    raise_pr(remote, written_plan(tmp_path), REPO, PR)
    remote.calls.clear()
    close_linked(remote, REPO, PR, merged=False, dry_run=True)
    assert remote.calls == [] and remote.repositories[REPO].pull_requests[0].state == "open"

# ---------------------------------------------------------------- allowed repositories

def test_only_listed_repositories_may_get_pull_requests(tmp_path: Path):
    """Checks that affected_repos accepts only repositories in the allowed listing (ignoring comments and blank lines), returns a problem for others, and uses the listing's spelling of the name.

    Protects the repos job, which decides where draft PRs may be raised.
    """
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
    """Checks that py2cs repos prints the affected repositories as JSON and exits 1 with a message when one is not in the allowed listing.

    Protects the repos job, which feeds the matrix of the raise job.
    """
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
    """Checks that make_plan restricted to one repository (matching case-insensitively) leaves the files of other repositories out.

    Protects the raise job, whose matrix plans one repository at a time.
    """
    require_patcher()
    repo_root = csharp_tree(tmp_path / "clones")
    base = read_package(demo_package(tmp_path / "base"))
    head = read_package(demo_package(tmp_path / "head", ["ProjectNumber: str = ''"]))
    diff = diff_manifests(base, head)
    assert make_plan(diff, head, base, lambda r: repo_root, None, None, "BHoM/Elsewhere").files == []
    assert len(make_plan(diff, head, base, lambda r: repo_root, None, None, "bhom/demo_toolkit").files) == 1

# ---------------------------------------------------------------- the command line, offline

def test_command_line_dry_run_without_a_token_is_offline(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    """Checks that py2cs pr --dry-run with no token runs offline and prints what it would do (create the branch, open a draft PR) with exit code 0.

    Lets people preview the linked PR without GitHub access.
    """
    plan = written_plan(tmp_path)
    monkeypatch.delenv("PY2CS_CSHARP_TOKEN", raising=False)
    status = main(["pr", "--plan-dir", str(plan), "--repo", REPO, "--python-repo", PYTHON_REPO, "--python-pr", "7", "--dry-run"])
    out = capsys.readouterr().out
    assert status == 0 and "offline dry run" in out
    assert "would create branch BHoM/Demo_Toolkit python-schema/pr-7 from develop" in out
    assert "would open draft pull request" in out

def test_command_line_without_a_token_and_not_a_dry_run_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    """Checks that py2cs pr without a token and without --dry-run exits with 2 and says no token is held.

    Protects the raise job from a silent pass when the app token is missing.
    """
    plan = written_plan(tmp_path)
    monkeypatch.delenv("PY2CS_CSHARP_TOKEN", raising=False)
    assert main(["pr", "--plan-dir", str(plan), "--repo", REPO, "--python-repo", PYTHON_REPO, "--python-pr", "7"]) == 2
    assert "holds no token" in capsys.readouterr().err

def test_make_client_reads_the_token_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    """Checks that make_client builds a RestClient from the token in the named environment variable and keeps the token out of the client's repr.

    Protects the token handling of the pr, close and status commands.
    """
    monkeypatch.setenv("SOME_TOKEN", "ghs_secret")
    client, offline = make_client("SOME_TOKEN")
    assert isinstance(client, RestClient) and not offline
    assert "ghs_secret" not in repr(client)

# ---------------------------------------------------------------- the REST client

def test_rest_client_calls_the_right_endpoints():
    """Checks that each RestClient method calls the right GitHub REST endpoint with the right body and the bearer token.

    Protects the GitHubClient that the pr, close and status commands use against the real GitHub.
    """
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
    """Checks that upsert_comment posts a new comment when no existing comment has the marker.

    Protects the Python PR comment that links to the draft C# PR.
    """
    transport = Recorder({("GET", "/repos/o/r/issues/3/comments?per_page=100"): (200, [{"id": 1, "body": "someone else"}]), ("POST", "/repos/o/r/issues/3/comments"): (201, {})})
    RestClient("tok", transport=transport).upsert_comment("o/r", 3, MARKER, "text")
    assert transport.requests[-1][:2] == ("POST", "/repos/o/r/issues/3/comments")

def test_rest_errors_name_the_call_but_never_the_token():
    """Checks that a failed REST call raises a GitHubError that names the call and status and does not contain the token.

    Protects the workflow logs from leaking the app token.
    """
    transport = Recorder({("GET", "/repos/o/r"): (403, {"message": "Resource not accessible by integration"})})
    with pytest.raises(GitHubError) as error:
        RestClient("secret-token", transport=transport).default_branch("o/r")
    assert "GET /repos/o/r failed with 403: Resource not accessible by integration" in str(error.value)
    assert "secret-token" not in str(error.value)

def test_a_client_without_a_token_is_refused():
    """Checks that RestClient raises a GitHubError when given an empty token.

    Protects the workflows from running unauthenticated.
    """
    with pytest.raises(GitHubError):
        RestClient("")
