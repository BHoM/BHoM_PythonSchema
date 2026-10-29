"""The commit status that says whether the linked C# pull request of a Python PR is merged."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from py2cs.__main__ import main
from py2cs.github import FakeGitHub, FakeRepository, PullRequest, RestClient
from py2cs.pr import branch_name
from py2cs.status import CONTEXT, linked_status, update_status

REPO = "BHoM/Demo_Toolkit"
OTHER = "BHoM/Other_Toolkit"
PYTHON_REPO = "BHoM/BHoM_PythonSchema"
SHA = "abc123"

def github(*repos: str) -> FakeGitHub:
    return FakeGitHub({PYTHON_REPO: FakeRepository(), **{r: FakeRepository() for r in repos}})

def linked(remote: FakeGitHub, repo: str, number: int = 7, state: str = "open", merged: bool = False) -> PullRequest:
    pull = remote.create_pull_request(repo, branch_name(number), "develop", "title", "body", True)
    pull.state, pull.merged = state, merged
    return pull

def test_an_open_linked_draft_is_pending():
    remote = github(REPO)
    pull = linked(remote, REPO)
    status = linked_status(remote, [REPO], 7)
    assert status is not None
    assert (status.state, status.description, status.url) == ("pending", f"Waiting for {REPO}#{pull.number} to be merged", pull.url)

def test_a_merged_linked_pr_is_success():
    remote = github(REPO)
    linked(remote, REPO, state="closed", merged=True)
    status = linked_status(remote, [REPO], 7)
    assert status is not None and (status.state, status.description) == ("success", f"Merged: {REPO}#1")

def test_a_linked_pr_closed_without_merging_is_a_failure():
    remote = github(REPO)
    linked(remote, REPO, state="closed", merged=False)
    status = linked_status(remote, [REPO], 7)
    assert status is not None and (status.state, status.description) == ("failure", f"{REPO}#1 was closed without merging")

def test_no_linked_pr_means_no_status():
    assert linked_status(github(REPO), [REPO], 7) is None
    remote = github(REPO)
    linked(remote, REPO, number=8)
    assert linked_status(remote, [REPO], 7) is None, "another Python PR's draft is not this one's"

def test_several_repositories_are_combined():
    remote = github(REPO, OTHER)
    linked(remote, REPO, state="closed", merged=True)
    linked(remote, OTHER)
    status = linked_status(remote, [REPO, OTHER], 7)
    assert status is not None and status.state == "pending" and OTHER in status.description

    remote = github(REPO, OTHER)
    linked(remote, REPO, state="closed", merged=True)
    linked(remote, OTHER, state="closed", merged=True)
    status = linked_status(remote, [REPO, OTHER], 7)
    assert status is not None and status.state == "success"

    remote = github(REPO, OTHER)
    linked(remote, REPO, state="closed", merged=True)
    linked(remote, OTHER, state="closed", merged=False)
    status = linked_status(remote, [REPO, OTHER], 7)
    assert status is not None and status.state == "failure"

def test_the_newest_pr_of_the_branch_counts():
    """An abandoned draft followed by a new one for the same Python PR is pending, not a failure."""
    remote = github(REPO)
    linked(remote, REPO, state="closed", merged=False)
    newer = linked(remote, REPO)
    status = linked_status(remote, [REPO], 7)
    assert status is not None and status.state == "pending" and f"#{newer.number}" in status.description

def test_the_status_is_written_on_the_head_commit_of_the_python_pr():
    remote = github(REPO)
    linked(remote, REPO, state="closed", merged=True)
    update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA)
    assert remote.repositories[PYTHON_REPO].statuses[(SHA, CONTEXT)][0] == "success"
    assert remote.calls[-1] == ("set_commit_status", PYTHON_REPO, SHA, "success")

def test_nothing_is_written_without_a_linked_pr_or_on_a_dry_run():
    remote = github(REPO)
    assert update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA) is None
    assert not any(c[0] == "set_commit_status" for c in remote.calls)

    linked(remote, REPO)
    remote.calls.clear()
    status = update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA, dry_run=True)
    assert status is not None and status.state == "pending" and remote.calls == []

def test_a_python_pr_that_needs_no_csharp_change_is_success():
    remote = github(REPO)
    status = update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA, no_change=True)
    assert status is not None and status.description == "No C# change is needed"
    assert remote.repositories[PYTHON_REPO].statuses[(SHA, CONTEXT)][0] == "success"

def test_a_new_status_replaces_the_old_one_for_the_same_commit():
    remote = github(REPO)
    pull = linked(remote, REPO)
    update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA)
    assert remote.repositories[PYTHON_REPO].statuses[(SHA, CONTEXT)][0] == "pending"

    pull.state, pull.merged = "closed", True
    update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA)
    assert remote.repositories[PYTHON_REPO].statuses[(SHA, CONTEXT)][0] == "success"
    assert len(remote.repositories[PYTHON_REPO].statuses) == 1

# ---------------------------------------------------------------- the command line

def test_command_line_dry_run_without_a_token_is_offline(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PY2CS_PYTHON_TOKEN", raising=False)
    repos = tmp_path / "repos.txt"
    repos.write_text(f"{REPO}\n", encoding="utf-8")
    status = main(["status", "--python-repo", PYTHON_REPO, "--python-pr", "7", "--sha", SHA, "--repos-file", str(repos), "--dry-run"])
    out = capsys.readouterr().out
    assert status == 0 and "offline dry run" in out and "no linked C# pull request: no status" in out

    assert main(["status", "--python-repo", PYTHON_REPO, "--python-pr", "7", "--sha", SHA, "--repos-file", str(repos), "--dry-run", "--no-csharp-change"]) == 0
    assert "would set the status success: No C# change is needed" in capsys.readouterr().out

# ---------------------------------------------------------------- the REST calls

class Recorder:
    def __init__(self, answers: dict[tuple[str, str], tuple[int, object]]):
        self.answers = answers
        self.requests: list[tuple[str, str, object]] = []

    def __call__(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        path = url.removeprefix("https://api.github.com")
        self.requests.append((method, path, json.loads(body) if body else None))
        status, data = self.answers.get((method, path), (404, {"message": "Not Found"}))
        return status, json.dumps(data).encode()

def pull_json(number: int, state: str, merged_at: str | None) -> dict[str, object]:
    return {"number": number, "html_url": f"https://github.com/o/r/pull/{number}", "head": {"ref": "python-schema/pr-7"}, "base": {"ref": "develop"},
            "state": state, "draft": False, "merged_at": merged_at}

def test_rest_client_finds_the_newest_pr_of_a_branch_in_any_state_and_knows_if_it_merged():
    path = "/repos/o/r/pulls?state=all&sort=created&direction=desc&head=o%3Apython-schema%2Fpr-7"
    transport = Recorder({("GET", path): (200, [pull_json(5, "closed", "2026-10-29T10:00:00Z"), pull_json(3, "closed", None)])})
    found = RestClient("tok", transport=transport).find_linked_pull_request("o/r", "python-schema/pr-7")
    assert found is not None and (found.number, found.state, found.merged) == (5, "closed", True)

    transport = Recorder({("GET", path): (200, [pull_json(3, "closed", None)])})
    found = RestClient("tok", transport=transport).find_linked_pull_request("o/r", "python-schema/pr-7")
    assert found is not None and not found.merged

    assert RestClient("tok", transport=Recorder({("GET", path): (200, [])})).find_linked_pull_request("o/r", "python-schema/pr-7") is None

def test_rest_client_sets_a_commit_status_with_a_short_description():
    transport = Recorder({("POST", "/repos/o/r/statuses/abc123"): (201, {})})
    RestClient("tok", transport=transport).set_commit_status("o/r", "abc123", "pending", CONTEXT, "x" * 300, "https://github.com/o/r/pull/3")
    method, path, body = transport.requests[0]
    assert (method, path) == ("POST", "/repos/o/r/statuses/abc123")
    assert isinstance(body, dict) and body["state"] == "pending" and body["context"] == CONTEXT and len(str(body["description"])) == 140
