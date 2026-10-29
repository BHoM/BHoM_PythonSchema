"""The GitHub calls py2cs needs, behind a small interface so everything above it can be tested without a network.

RestClient talks to the REST API with urllib (the gh CLI is not needed). FakeGitHub keeps repositories in memory, for tests and for
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

@dataclass
class RemoteFile:
    sha: str
    content: bytes

class GitHubClient(Protocol):
    """What the linked-PR code uses. Every method acts on one repository, named Owner/Name."""

    def default_branch(self, repo: str) -> str: ...

    def branch_sha(self, repo: str, branch: str) -> str | None: ...

    def create_branch(self, repo: str, branch: str, sha: str) -> None: ...

    def get_file(self, repo: str, ref: str, path: str) -> RemoteFile | None: ...

    def put_file(self, repo: str, branch: str, path: str, content: bytes, message: str, sha: str | None) -> None: ...

    def find_pull_request(self, repo: str, head_branch: str) -> PullRequest | None: ...

    def create_pull_request(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest: ...

    def update_pull_request(self, repo: str, number: int, title: str, body: str) -> None: ...

    def add_labels(self, repo: str, number: int, labels: list[str]) -> None: ...

    def upsert_comment(self, repo: str, number: int, marker: str, body: str) -> None: ...

    def close_pull_request(self, repo: str, number: int) -> None: ...

# ------------------------------------------------------------------------------------------------ real client

Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]

def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

class RestClient:
    """The GitHub REST API. The token is only sent in the Authorization header; it is never written to output or kept in an error."""

    def __init__(self, token: str, api_url: str = "https://api.github.com", transport: Transport | None = None):
        if not token:
            raise GitHubError("no GitHub token was given")
        self._token = token
        self._api = api_url.rstrip("/")
        self._transport = transport or urllib_transport

    def __repr__(self) -> str:
        return f"RestClient({self._api})"

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None, allow_missing: bool = False) -> Any:
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
                message = str(json.loads(content).get("message", ""))
            except ValueError:
                pass
            raise GitHubError(f"GitHub {method} {path} failed with {status}: {message}")
        return json.loads(content) if content else None

    def default_branch(self, repo: str) -> str:
        return str(self._request("GET", f"/repos/{repo}")["default_branch"])

    def branch_sha(self, repo: str, branch: str) -> str | None:
        found = self._request("GET", f"/repos/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='/')}", allow_missing=True)
        return None if found is None else str(found["object"]["sha"])

    def create_branch(self, repo: str, branch: str, sha: str) -> None:
        self._request("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})

    def get_file(self, repo: str, ref: str, path: str) -> RemoteFile | None:
        found = self._request("GET", f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref, safe='')}", allow_missing=True)
        if found is None:
            return None
        return RemoteFile(str(found["sha"]), base64.b64decode(str(found["content"])))

    def put_file(self, repo: str, branch: str, path: str, content: bytes, message: str, sha: str | None) -> None:
        body: dict[str, Any] = {"message": message, "content": base64.b64encode(content).decode("ascii"), "branch": branch}
        if sha is not None:
            body["sha"] = sha
        self._request("PUT", f"/repos/{repo}/contents/{urllib.parse.quote(path)}", body)

    def find_pull_request(self, repo: str, head_branch: str) -> PullRequest | None:
        owner = repo.split("/")[0]
        found = self._request("GET", f"/repos/{repo}/pulls?state=open&head={urllib.parse.quote(owner + ':' + head_branch, safe='')}")
        return self._pull_request(found[0]) if found else None

    def create_pull_request(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        return self._pull_request(self._request("POST", f"/repos/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body, "draft": draft}))

    def update_pull_request(self, repo: str, number: int, title: str, body: str) -> None:
        self._request("PATCH", f"/repos/{repo}/pulls/{number}", {"title": title, "body": body})

    def add_labels(self, repo: str, number: int, labels: list[str]) -> None:
        self._request("POST", f"/repos/{repo}/issues/{number}/labels", {"labels": labels})

    def upsert_comment(self, repo: str, number: int, marker: str, body: str) -> None:
        existing = self._request("GET", f"/repos/{repo}/issues/{number}/comments?per_page=100") or []
        for comment in existing:
            if marker in str(comment.get("body", "")):
                self._request("PATCH", f"/repos/{repo}/issues/comments/{comment['id']}", {"body": body})
                return
        self._request("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})

    def close_pull_request(self, repo: str, number: int) -> None:
        self._request("PATCH", f"/repos/{repo}/pulls/{number}", {"state": "closed"})

    @staticmethod
    def _pull_request(data: dict[str, Any]) -> PullRequest:
        return PullRequest(int(data["number"]), str(data["html_url"]), str(data["head"]["ref"]), str(data["base"]["ref"]), str(data.get("title", "")),
                           str(data.get("body") or ""), bool(data.get("draft", False)), str(data.get("state", "open")))

# ------------------------------------------------------------------------------------------------ fake client

@dataclass
class FakeRepository:
    default: str = "develop"
    branches: dict[str, str] = field(default_factory=lambda: {"develop": "sha-0"})
    files: dict[tuple[str, str], bytes] = field(default_factory=lambda: {})        # (branch, path) -> content
    pull_requests: list[PullRequest] = field(default_factory=lambda: [])
    labels: dict[int, list[str]] = field(default_factory=lambda: {})
    comments: dict[int, list[str]] = field(default_factory=lambda: {})

class FakeGitHub:
    """An in-memory GitHub. `calls` records every call that changes something, so tests can check what was (not) written."""

    def __init__(self, repositories: dict[str, FakeRepository] | None = None):
        self.repositories = repositories if repositories is not None else {}
        self.calls: list[tuple[str, ...]] = []
        self._numbers = 0

    def _repo(self, repo: str) -> FakeRepository:
        if repo not in self.repositories:
            raise GitHubError(f"{repo} was not found (or the App is not installed on it)")
        return self.repositories[repo]

    def default_branch(self, repo: str) -> str:
        return self._repo(repo).default

    def branch_sha(self, repo: str, branch: str) -> str | None:
        return self._repo(repo).branches.get(branch)

    def create_branch(self, repo: str, branch: str, sha: str) -> None:
        self.calls.append(("create_branch", repo, branch))
        remote = self._repo(repo)
        remote.branches[branch] = sha
        for (source, path), content in list(remote.files.items()):
            if source == self._branch_of_sha(remote, sha):
                remote.files[(branch, path)] = content

    @staticmethod
    def _branch_of_sha(remote: FakeRepository, sha: str) -> str:
        return next(name for name, value in remote.branches.items() if value == sha)

    def get_file(self, repo: str, ref: str, path: str) -> RemoteFile | None:
        content = self._repo(repo).files.get((ref, path))
        return None if content is None else RemoteFile(f"blob-{hash(content)}", content)

    def put_file(self, repo: str, branch: str, path: str, content: bytes, message: str, sha: str | None) -> None:
        self.calls.append(("put_file", repo, branch, path))
        self._repo(repo).files[(branch, path)] = content

    def find_pull_request(self, repo: str, head_branch: str) -> PullRequest | None:
        return next((p for p in self._repo(repo).pull_requests if p.head == head_branch and p.state == "open"), None)

    def create_pull_request(self, repo: str, head: str, base: str, title: str, body: str, draft: bool) -> PullRequest:
        self.calls.append(("create_pull_request", repo, head))
        self._numbers += 1
        pull = PullRequest(self._numbers, f"https://github.com/{repo}/pull/{self._numbers}", head, base, title, body, draft)
        self._repo(repo).pull_requests.append(pull)
        return pull

    def update_pull_request(self, repo: str, number: int, title: str, body: str) -> None:
        self.calls.append(("update_pull_request", repo, str(number)))
        for pull in self._repo(repo).pull_requests:
            if pull.number == number:
                pull.title, pull.body = title, body

    def add_labels(self, repo: str, number: int, labels: list[str]) -> None:
        self.calls.append(("add_labels", repo, str(number)))
        current = self._repo(repo).labels.setdefault(number, [])
        current += [label for label in labels if label not in current]

    def upsert_comment(self, repo: str, number: int, marker: str, body: str) -> None:
        self.calls.append(("upsert_comment", repo, str(number)))
        comments = self._repo(repo).comments.setdefault(number, [])
        for i, existing in enumerate(comments):
            if marker in existing:
                comments[i] = body
                return
        comments.append(body)

    def close_pull_request(self, repo: str, number: int) -> None:
        self.calls.append(("close_pull_request", repo, str(number)))
        for pull in self._repo(repo).pull_requests:
            if pull.number == number:
                pull.state = "closed"
