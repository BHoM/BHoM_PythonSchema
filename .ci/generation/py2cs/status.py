"""A commit status on the Python pull request that says whether the linked C# pull request is merged.

The C# is the source of truth, so a Python PR is only ready once its C# PR is merged. The status makes that visible on the PR, and
can be made a required check in the branch protection of develop.
"""

from __future__ import annotations

from dataclasses import dataclass

from py2cs.github import GitHubClient, PullRequest
from py2cs.pr import branch_name

CONTEXT = "linked C# pull request"

@dataclass
class Status:
    state: str          # pending | success | failure
    description: str
    url: str = ""

def short(repo: str, pull: PullRequest) -> str:
    return f"{repo}#{pull.number}"

def linked_status(client: GitHubClient, repos: list[str], python_pr: int) -> Status | None:
    """What the linked C# pull requests of one Python pull request say, or None when it has none.

    Merged everywhere is success; any that was closed without merging is a failure (the Python must then change or be closed);
    otherwise it is still pending.
    """
    found: list[tuple[str, PullRequest]] = []
    for repo in repos:
        pull = client.find_linked_pull_request(repo, branch_name(python_pr))
        if pull is not None:
            found.append((repo, pull))

    if not found:
        return None

    url = found[0][1].url
    abandoned = [short(r, p) for r, p in found if p.state == "closed" and not p.merged]
    if abandoned:
        return Status("failure", f"{', '.join(abandoned)} was closed without merging", url)

    waiting = [short(r, p) for r, p in found if not p.merged]
    if waiting:
        return Status("pending", f"Waiting for {', '.join(waiting)} to be merged", url)

    return Status("success", f"Merged: {', '.join(short(r, p) for r, p in found)}", url)

def update_status(csharp_client: GitHubClient, python_client: GitHubClient, repos: list[str], python_repo: str, python_pr: int, sha: str,
                  dry_run: bool = False, no_change: bool = False) -> Status | None:
    """Writes the status on the head commit of the Python PR. Nothing is written when there is no linked pull request.

    With no_change (the Python PR needs no C# change) the status is success, so a required check does not wait for ever.
    """
    status = Status("success", "No C# change is needed") if no_change else linked_status(csharp_client, repos, python_pr)
    if status is not None and not dry_run:
        python_client.set_commit_status(python_repo, sha, status.state, CONTEXT, status.description, status.url)
    return status
