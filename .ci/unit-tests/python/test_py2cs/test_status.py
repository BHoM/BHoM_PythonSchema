"""The commit status that says whether the linked C# pull request of a Python PR is merged."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from py2cs.__main__ import main
from py2cs.github import MockGitHub, MockRepository, PullRequest, RestClient
from py2cs.pr import branch_name
from py2cs.status import CONTEXT, linked_status, update_status

REPO = "BHoM/Demo_Toolkit"
OTHER = "BHoM/Other_Toolkit"
PYTHON_REPO = "BHoM/BHoM_PythonSchema"
SHA = "abc123"

def github(*repos: str) -> MockGitHub:
    """Returns an in-memory MockGitHub holding an empty Python repository and an empty repository for each name given.

    The status tests use it in place of the real GitHub.
    """
    return MockGitHub({PYTHON_REPO: MockRepository(), **{r: MockRepository() for r in repos}})

def linked(remote: MockGitHub, repo: str, number: int = 7, state: str = "open", merged: bool = False) -> PullRequest:
    """Creates a draft PR on the linked branch of a Python PR in the given repository and sets its state and merged flag; returns it.

    The status tests use it to stand for a linked C# PR in each state.
    """
    pull = remote.create_pull_request(repo, branch_name(number), "develop", "title", "body", True)
    pull.state, pull.merged = state, merged
    return pull

def test_an_open_linked_draft_is_pending():
    """Checks that an open linked draft PR gives a pending status that names the PR and links to it.

    Protects the commit status that tells reviewers the C# PR is not merged yet.
    """
    remote = github(REPO)
    pull = linked(remote, REPO)
    status = linked_status(remote, [REPO], 7)
    assert status is not None
    assert (status.state, status.description, status.url) == ("pending", f"Waiting for {REPO}#{pull.number} to be merged", pull.url)

def test_a_merged_linked_pr_is_success():
    """Checks that a merged linked PR gives a success status.

    Protects the commit status that allows the Python PR to merge once the C# is merged.
    """
    remote = github(REPO)
    linked(remote, REPO, state="closed", merged=True)
    status = linked_status(remote, [REPO], 7)
    assert status is not None and (status.state, status.description) == ("success", f"Merged: {REPO}#1")

def test_a_linked_pr_closed_without_merging_is_a_failure():
    """Checks that a linked PR closed without merging gives a failure status.

    Protects the commit status from passing a Python PR whose C# was abandoned.
    """
    remote = github(REPO)
    linked(remote, REPO, state="closed", merged=False)
    status = linked_status(remote, [REPO], 7)
    assert status is not None and (status.state, status.description) == ("failure", f"{REPO}#1 was closed without merging")

def test_no_linked_pr_means_no_status():
    """Checks that linked_status returns nothing when no linked PR exists, including when only another Python PR has a draft.

    Protects the status job from reporting on unrelated PRs.
    """
    assert linked_status(github(REPO), [REPO], 7) is None
    remote = github(REPO)
    linked(remote, REPO, number=8)
    assert linked_status(remote, [REPO], 7) is None, "another Python PR's draft is not this one's"

def test_several_repositories_are_combined():
    """Checks that the statuses of several repositories combine into pending if any is open, success if all are merged and failure if any was closed without merging.

    Protects the status of a Python PR that changes classes of several C# repositories.
    """
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
    """Checks that an abandoned draft followed by a new one for the same Python PR gives pending, not failure.

    Protects the status when a developer reopens the linked work.
    """
    remote = github(REPO)
    linked(remote, REPO, state="closed", merged=False)
    newer = linked(remote, REPO)
    status = linked_status(remote, [REPO], 7)
    assert status is not None and status.state == "pending" and f"#{newer.number}" in status.description

def test_the_status_is_written_on_the_head_commit_of_the_python_pr():
    """Checks that update_status writes the status with the right context on the head commit of the Python PR.

    Protects the status job of the linked-PR workflow.
    """
    remote = github(REPO)
    linked(remote, REPO, state="closed", merged=True)
    update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA)
    assert remote.repositories[PYTHON_REPO].statuses[(SHA, CONTEXT)][0] == "success"
    assert remote.calls[-1] == ("set_commit_status", PYTHON_REPO, SHA, "success")

def test_nothing_is_written_without_a_linked_pr_or_on_a_dry_run():
    """Checks that update_status writes no status when there is no linked PR, and also none on a dry run, which still returns the status.

    Protects the status job from noise and the dry-run preview.
    """
    remote = github(REPO)
    assert update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA) is None
    assert not any(c[0] == "set_commit_status" for c in remote.calls)

    linked(remote, REPO)
    remote.calls.clear()
    status = update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA, dry_run=True)
    assert status is not None and status.state == "pending" and remote.calls == []

def test_a_python_pr_that_needs_no_csharp_change_is_success():
    """Checks that update_status sets a success status saying no C# change is needed when no_change is given.

    Protects the status job for Python PRs that need no linked C# PR.
    """
    remote = github(REPO)
    status = update_status(remote, remote, [REPO], PYTHON_REPO, 7, SHA, no_change=True)
    assert status is not None and status.description == "No C# change is needed"
    assert remote.repositories[PYTHON_REPO].statuses[(SHA, CONTEXT)][0] == "success"

def test_a_new_status_replaces_the_old_one_for_the_same_commit():
    """Checks that a new status of the same context on the same commit replaces the old one, from pending to success.

    Protects the status job when the C# PR is merged later.
    """
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
    """Checks that py2cs status --dry-run with no token runs offline and prints the status it would set, including with --no-csharp-change.

    Lets people preview the status command without GitHub access.
    """
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
        """Stores the canned answers keyed by (method, path) and starts an empty request log."""
        self.answers = answers
        self.requests: list[tuple[str, str, object]] = []

    def __call__(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        """Acts as the RestClient transport: records the request (method, path, parsed body) and returns the canned status and JSON, or 404 Not Found."""
        path = url.removeprefix("https://api.github.com")
        self.requests.append((method, path, json.loads(body) if body else None))
        status, data = self.answers.get((method, path), (404, {"message": "Not Found"}))
        return status, json.dumps(data).encode()

def pull_json(number: int, state: str, merged_at: str | None) -> dict[str, object]:
    """Builds the JSON of a pull request as the GitHub API returns it, for the given number, state and merged_at.

    The REST client tests use it to make canned answers.
    """
    return {"number": number, "html_url": f"https://github.com/o/r/pull/{number}", "head": {"ref": "python-schema/pr-7"}, "base": {"ref": "develop"},
            "state": state, "draft": False, "merged_at": merged_at}

def test_rest_client_finds_the_newest_pr_of_a_branch_in_any_state_and_knows_if_it_merged():
    """Checks that find_linked_pull_request returns the newest PR of the branch in any state, knows whether it merged, and returns nothing when there is none.

    Protects the GitHubClient that the status job and the sweep use.
    """
    path = "/repos/o/r/pulls?state=all&sort=created&direction=desc&head=o%3Apython-schema%2Fpr-7"
    transport = Recorder({("GET", path): (200, [pull_json(5, "closed", "2026-10-29T10:00:00Z"), pull_json(3, "closed", None)])})
    found = RestClient("tok", transport=transport).find_linked_pull_request("o/r", "python-schema/pr-7")
    assert found is not None and (found.number, found.state, found.merged) == (5, "closed", True)

    transport = Recorder({("GET", path): (200, [pull_json(3, "closed", None)])})
    found = RestClient("tok", transport=transport).find_linked_pull_request("o/r", "python-schema/pr-7")
    assert found is not None and not found.merged

    assert RestClient("tok", transport=Recorder({("GET", path): (200, [])})).find_linked_pull_request("o/r", "python-schema/pr-7") is None

def test_rest_client_sets_a_commit_status_with_a_short_description():
    """Checks that set_commit_status posts to the commit status endpoint and cuts the description to 140 characters, the GitHub limit.

    Protects the status job from rejected API calls.
    """
    transport = Recorder({("POST", "/repos/o/r/statuses/abc123"): (201, {})})
    RestClient("tok", transport=transport).set_commit_status("o/r", "abc123", "pending", CONTEXT, "x" * 300, "https://github.com/o/r/pull/3")
    method, path, body = transport.requests[0]
    assert (method, path) == ("POST", "/repos/o/r/statuses/abc123")
    assert isinstance(body, dict) and body["state"] == "pending" and body["context"] == CONTEXT and len(str(body["description"])) == 140
