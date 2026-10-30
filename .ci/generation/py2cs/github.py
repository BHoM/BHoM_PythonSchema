"""The GitHub calls py2cs needs, behind a small interface so everything above it can be tested without a network.

RestClient talks to the REST API with urllib (the gh CLI is not needed). MockGitHub keeps repositories in memory, for tests and for
offline dry runs.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

class GitHubError(Exception):
    pass

@dataclass
class PullRequest:
    number: int
    url: str
    head: str
    base: str
    title: str = ""
    body: str = ""
    draft: bool = True
    state: str = "open"
    merged: bool = False

@dataclass
class RemoteFile:
    sha: str
    content: bytes

class GitHubClient(Protocol):
    """What the linked-PR code uses. Every method acts on one repository, named Owner/Name."""

    def default_branch(self, repo: str) -> str:
        """Contract: returns the name of the default branch of the repository (Owner/Name). The linked-PR code uses it as the base of the draft C# pull request.
        """

    def branch_sha(self, repo: str, branch: str) -> str | None:
        """Contract: returns the commit sha at the tip of the branch, or None when the branch does not exist. `pr` uses it to decide whether the branch python-schema/pr-<N> must be created.
        """

    def create_branch(self, repo: str, branch: str, sha: str) -> None:
        """Contract: creates the branch from the given commit sha. `pr` calls it once, the first time a Python PR is linked to a C# repository."""

    def get_file(self, repo: str, ref: str, path: str) -> RemoteFile | None:
        """Contract: returns the sha and bytes of a file at a branch or ref, or None when the file does not exist there. `pr` compares it with the planned file to skip unchanged files.
        """

    def put_file(self, repo: str, branch: str, path: str, content: bytes, message: str, sha: str | None) -> None:
        """Contract: creates or updates one file on a branch with a commit message; the existing blob sha must be given when the file already exists. `pr` writes each planned C# file this way.
        """

    def find_pull_request(self, repo: str, head_branch: str) -> PullRequest | None:
        """Contract: returns the open pull request whose head is the branch, or None. `pr` and `close` use it to find the linked draft C# pull request.
        """

    def create_pull_request(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        """Contract: opens a pull request from head into base and returns it; `draft` says whether it is a draft. `pr` opens the linked C# pull request as a draft.
        """

    def update_pull_request(self, repo: str, number: int, title: str, body: str) -> None:
        """Contract: replaces the title and body of an existing pull request. `pr` calls it when a re-run of the plan changed the report."""

    def add_labels(self, repo: str, number: int, labels: list[str]) -> None:
        """Contract: adds labels to a pull request, keeping the ones it already has. `pr` uses it to add `breaking-change` to the C# pull request."""

    def upsert_comment(self, repo: str, number: int, marker: str, body: str) -> None:
        """Contract: writes a comment on a pull request, replacing the earlier comment that contains the marker text, or adding one when there is none. `pr` and `close` use it so a re-run does not pile up comments.
        """

    def close_pull_request(self, repo: str, number: int) -> None:
        """Contract: closes a pull request without merging it. `close` calls it on the linked C# draft when its Python PR is closed unmerged."""

    def find_linked_pull_request(self, repo: str, head_branch: str) -> PullRequest | None:
        """Contract: returns the newest pull request from the branch whatever its state (open, closed or merged), or None. `status` uses it to see whether the linked C# pull request is merged.
        """

    def set_commit_status(self, repo: str, sha: str, state: str, context: str, description: str, url: str) -> None:
        """Contract: sets a commit status (state, context, description, link) on a commit of the repository. `status` uses it to publish the state of the linked C# pull request on the Python PR.
        """

# ------------------------------------------------------------------------------------------------ real client

Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]

def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    """Sends one HTTP request with urllib and returns the status code and body; an HTTP error status is returned, not raised.

    The default transport of RestClient. Tests replace it with a fake so the client runs without a network.
    """
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

class RestClient:
    """The GitHub REST API. The token is only sent in the Authorization header; it is never written to output or kept in an error."""

    def __init__(self, token: str, api_url: str = "https://api.github.com", transport: Transport | None = None):
        """Creates a client for the GitHub REST API from a token, an optional API base url and an optional transport; raises GitHubError when the token is empty.

        Built by `make_client` in `ci` when a token environment variable is set.
        """
        if not token:
            raise GitHubError("no GitHub token was given")
        self._token = token
        self._api = api_url.rstrip("/")
        self._transport = transport or urllib_transport

    def __repr__(self) -> str:
        """Returns the API base url only, so the token never appears in logs or error output."""
        return f"RestClient({self._api})"

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None, allow_missing: bool = False) -> Any:
        """Sends one authenticated JSON request to the GitHub API and returns the decoded answer.

        A 404 gives None when allow_missing is set; any other status of 400 or more raises GitHubError with the message GitHub sent. Every method of the client goes through it.
        """
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "BHoM_PythonSchema-py2cs"}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        status, content = self._transport(method, self._api + path, headers, data)
        if status == 404 and allow_missing:
            return None
        if status >= 400:
            message = ""
            try:
                data = json.loads(content)
                details = "; ".join(str(e.get("message") or e.get("code") or e) if isinstance(e, dict) else str(e) for e in data.get("errors", []))
                message = str(data.get("message", "")) + (f" ({details})" if details else "")
            except ValueError:
                pass
            raise GitHubError(f"GitHub {method} {path} failed with {status}: {message}")
        return json.loads(content) if content else None

    def default_branch(self, repo: str) -> str:
        """Reads the default branch name of the repository from the GitHub API. Implements the contract for the linked-PR workflow."""
        return str(self._request("GET", f"/repos/{repo}")["default_branch"])

    def branch_sha(self, repo: str, branch: str) -> str | None:
        """Reads the commit sha of a branch from the GitHub API, or returns None when the branch does not exist. Used by `pr` to see whether the linked branch is already there.
        """
        found = self._request("GET", f"/repos/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='/')}", allow_missing=True)
        return None if found is None else str(found["object"]["sha"])

    def create_branch(self, repo: str, branch: str, sha: str) -> None:
        """Creates a branch at a commit sha through the GitHub refs API. Used by `pr` to start the branch python-schema/pr-<N> in a C# repository."""
        self._request("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})

    def get_file(self, repo: str, ref: str, path: str) -> RemoteFile | None:
        """Reads a file at a ref through the GitHub contents API, decoding its base64 content, or returns None when it is missing. Used by `pr` to skip planned files that are already on the branch.
        """
        found = self._request("GET", f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref, safe='')}", allow_missing=True)
        if found is None:
            return None
        return RemoteFile(str(found["sha"]), base64.b64decode(str(found["content"])))

    def put_file(self, repo: str, branch: str, path: str, content: bytes, message: str, sha: str | None) -> None:
        """Creates or updates a file on a branch through the GitHub contents API, sending the old blob sha when the file exists. Used by `pr` to push each planned C# file.
        """
        body: dict[str, Any] = {"message": message, "content": base64.b64encode(content).decode("ascii"), "branch": branch}
        if sha is not None:
            body["sha"] = sha
        self._request("PUT", f"/repos/{repo}/contents/{urllib.parse.quote(path)}", body)

    def find_pull_request(self, repo: str, head_branch: str) -> PullRequest | None:
        """Looks up the open pull request whose head is the given branch of the same owner, or returns None. Used by `pr` and `close` to find the linked C# draft.
        """
        owner = repo.split("/")[0]
        found = self._request("GET", f"/repos/{repo}/pulls?state=open&head={urllib.parse.quote(owner + ':' + head_branch, safe='')}")
        return self._pull_request(found[0]) if found else None

    def create_pull_request(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        """Opens a pull request through the GitHub API and returns it. Used by `pr` to open the linked C# pull request as a draft."""
        return self._pull_request(self._request("POST", f"/repos/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body, "draft": draft}))

    def update_pull_request(self, repo: str, number: int, title: str, body: str) -> None:
        """Replaces the title and body of a pull request through the GitHub API. Used by `pr` when a re-run changes the report."""
        self._request("PATCH", f"/repos/{repo}/pulls/{number}", {"title": title, "body": body})

    def add_labels(self, repo: str, number: int, labels: list[str]) -> None:
        """Adds labels to a pull request through the GitHub issues API. Used by `pr` to mark a C# pull request as a breaking change."""
        self._request("POST", f"/repos/{repo}/issues/{number}/labels", {"labels": labels})

    def upsert_comment(self, repo: str, number: int, marker: str, body: str) -> None:
        """Updates the first comment (among the first 100) that contains the marker, or posts a new comment when none does.

        Used by `pr` and `close` so a re-run keeps one comment instead of adding more.
        """
        existing = self._request("GET", f"/repos/{repo}/issues/{number}/comments?per_page=100") or []
        for comment in existing:
            if marker in str(comment.get("body", "")):
                self._request("PATCH", f"/repos/{repo}/issues/comments/{comment['id']}", {"body": body})
                return
        self._request("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})

    def close_pull_request(self, repo: str, number: int) -> None:
        """Closes a pull request through the GitHub API without merging. Used by `close` on the linked C# draft when the Python PR was closed unmerged.
        """
        self._request("PATCH", f"/repos/{repo}/pulls/{number}", {"state": "closed"})

    def find_linked_pull_request(self, repo: str, head_branch: str) -> PullRequest | None:
        """Looks up the newest pull request from the branch, open, closed or merged, or returns None.

        Used by `status` to find out whether the linked C# pull request is merged.
        """
        owner = repo.split("/")[0]
        found = self._request("GET", f"/repos/{repo}/pulls?state=all&sort=created&direction=desc&head={urllib.parse.quote(owner + ':' + head_branch, safe='')}")
        return self._pull_request(found[0]) if found else None

    def set_commit_status(self, repo: str, sha: str, state: str, context: str, description: str, url: str) -> None:
        """Posts a commit status to the GitHub statuses API, cutting the description to the 140 characters GitHub allows. Used by `status` to show the state of the linked C# pull request on the Python PR.
        """
        body = {"state": state, "context": context, "description": description[:140], "target_url": url}
        self._request("POST", f"/repos/{repo}/statuses/{sha}", body)

    @staticmethod
    def _pull_request(data: dict[str, Any]) -> PullRequest:
        # The list endpoint has merged_at but not merged
        """Converts a pull request object from the GitHub API into a PullRequest.

        It treats a pull request with merged_at as merged, because the list endpoints do not return the merged flag.
        """
        merged = bool(data.get("merged") or data.get("merged_at"))
        return PullRequest(int(data["number"]), str(data["html_url"]), str(data["head"]["ref"]), str(data["base"]["ref"]), str(data.get("title", "")),
                           str(data.get("body") or ""), bool(data.get("draft", False)), str(data.get("state", "open")), merged)

# ------------------------------------------------------------------------------------------------ mock client

@dataclass
class MockRepository:
    default: str = "develop"
    branches: dict[str, str] = field(default_factory=lambda: {"develop": "sha-0"})
    files: dict[tuple[str, str], bytes] = field(default_factory=lambda: {})        # (branch, path) -> content
    pull_requests: list[PullRequest] = field(default_factory=lambda: [])
    labels: dict[int, list[str]] = field(default_factory=lambda: {})
    comments: dict[int, list[str]] = field(default_factory=lambda: {})
    # (sha, context) -> (state, description, url)
    statuses: dict[tuple[str, str], tuple[str, str, str]] = field(default_factory=lambda: {})

class MockGitHub:
    """An in-memory GitHub. `calls` records every call that changes something, so tests can check what was (not) written."""

    def __init__(self, repositories: dict[str, MockRepository] | None = None):
        """Creates an in-memory GitHub from a dictionary of MockRepository by Owner/Name, with an empty log of calls. It stands in for GitHub in tests and offline dry runs.
        """
        self.repositories = repositories if repositories is not None else {}
        self.calls: list[tuple[str, ...]] = []
        self._numbers = 0

    def _repo(self, repo: str) -> MockRepository:
        """Returns the in-memory repository of that name, or raises GitHubError as GitHub does for a repository that is missing or has no App installed.
        """
        if repo not in self.repositories:
            raise GitHubError(f"{repo} was not found (or the App is not installed on it)")
        return self.repositories[repo]

    def default_branch(self, repo: str) -> str:
        """Returns the default branch of the in-memory repository. Stands in for GitHub in tests and offline dry runs."""
        return self._repo(repo).default

    def branch_sha(self, repo: str, branch: str) -> str | None:
        """Returns the sha of a branch of the in-memory repository, or None. Stands in for GitHub in tests and offline dry runs."""
        return self._repo(repo).branches.get(branch)

    def create_branch(self, repo: str, branch: str, sha: str) -> None:
        """Creates a branch at a sha and copies the files of the branch that sha belongs to onto it; the call is logged. Stands in for GitHub in tests and offline dry runs.
        """
        self.calls.append(("create_branch", repo, branch))
        remote = self._repo(repo)
        remote.branches[branch] = sha
        for (source, path), content in list(remote.files.items()):
            if source == self._branch_of_sha(remote, sha):
                remote.files[(branch, path)] = content

    @staticmethod
    def _branch_of_sha(remote: MockRepository, sha: str) -> str:
        """Returns the name of the branch whose tip is the sha. Used by create_branch to copy the files of the branch it starts from."""
        return next(name for name, value in remote.branches.items() if value == sha)

    def get_file(self, repo: str, ref: str, path: str) -> RemoteFile | None:
        """Returns the stored file at a branch with a sha made from its content, or None. Stands in for GitHub in tests and offline dry runs."""
        content = self._repo(repo).files.get((ref, path))
        return None if content is None else RemoteFile(f"blob-{hash(content)}", content)

    def put_file(self, repo: str, branch: str, path: str, content: bytes, message: str, sha: str | None) -> None:
        """Stores a file on a branch and logs the call. Stands in for GitHub in tests and offline dry runs, and lets tests check which files were written.
        """
        self.calls.append(("put_file", repo, branch, path))
        self._repo(repo).files[(branch, path)] = content

    def find_pull_request(self, repo: str, head_branch: str) -> PullRequest | None:
        """Returns the open pull request with that head branch, or None. Stands in for GitHub in tests and offline dry runs."""
        return next((p for p in self._repo(repo).pull_requests if p.head == head_branch and p.state == "open"), None)

    def create_pull_request(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        """Adds a numbered pull request to the repository, logs the call and returns it. Stands in for GitHub in tests and offline dry runs."""
        self.calls.append(("create_pull_request", repo, head))
        self._numbers += 1
        pull = PullRequest(self._numbers, f"https://github.com/{repo}/pull/{self._numbers}", head, base, title, body, draft)
        self._repo(repo).pull_requests.append(pull)
        return pull

    def update_pull_request(self, repo: str, number: int, title: str, body: str) -> None:
        """Replaces title and body of the pull request with that number and logs the call. Stands in for GitHub in tests and offline dry runs."""
        self.calls.append(("update_pull_request", repo, str(number)))
        for pull in self._repo(repo).pull_requests:
            if pull.number == number:
                pull.title, pull.body = title, body

    def add_labels(self, repo: str, number: int, labels: list[str]) -> None:
        """Adds the labels the pull request does not have yet and logs the call. Stands in for GitHub in tests and offline dry runs."""
        self.calls.append(("add_labels", repo, str(number)))
        current = self._repo(repo).labels.setdefault(number, [])
        current += [label for label in labels if label not in current]

    def upsert_comment(self, repo: str, number: int, marker: str, body: str) -> None:
        """Replaces the stored comment that contains the marker, or appends a new one, and logs the call. Stands in for GitHub in tests and offline dry runs.
        """
        self.calls.append(("upsert_comment", repo, str(number)))
        comments = self._repo(repo).comments.setdefault(number, [])
        for i, existing in enumerate(comments):
            if marker in existing:
                comments[i] = body
                return
        comments.append(body)

    def close_pull_request(self, repo: str, number: int) -> None:
        """Marks the pull request with that number as closed and logs the call. Stands in for GitHub in tests and offline dry runs."""
        self.calls.append(("close_pull_request", repo, str(number)))
        for pull in self._repo(repo).pull_requests:
            if pull.number == number:
                pull.state = "closed"

    def find_linked_pull_request(self, repo: str, head_branch: str) -> PullRequest | None:
        """Returns the newest pull request (highest number) from the branch whatever its state, or None. Stands in for GitHub in tests and offline dry runs.
        """
        matches = [p for p in self._repo(repo).pull_requests if p.head == head_branch]
        return max(matches, key=lambda p: p.number) if matches else None

    def set_commit_status(self, repo: str, sha: str, state: str, context: str, description: str, url: str) -> None:
        """Stores the status for the sha and context, cutting the description to 140 characters, and logs the call. Stands in for GitHub in tests and offline dry runs.
        """
        self.calls.append(("set_commit_status", repo, sha, state))
        self._repo(repo).statuses[(sha, context)] = (state, description[:140], url)
