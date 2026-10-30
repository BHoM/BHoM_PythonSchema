"""Raising, updating and closing the draft C# pull requests that are linked to a Python pull request.

Only the repositories named by the plan are touched, and every write goes through a GitHubClient, so a dry run changes nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py2cs.github import GitHubClient, PullRequest

BRANCH_PREFIX = "python-schema/pr-"
# Hidden text that marks the comments py2cs writes, so a re-run updates them instead of adding new ones
MARKER = "<!-- py2cs:linked-pr -->"

@dataclass
class PythonPr:
    """The Python pull request the C# pull requests are linked to."""
    repo: str
    number: int
    url: str = ""

    @property
    def reference(self) -> str:
        """Returns the Python pull request as Owner/Name#number. Used in the C# pull request text and in the comments py2cs writes."""
        return f"{self.repo}#{self.number}"

@dataclass
class Action:
    kind: str
    repo: str
    detail: str = ""

    def __str__(self) -> str:
        """Returns the action as one line of kind, repository and detail. `pr`, `close` and the command line print these lines, with `would` in front on a dry run.
        """
        return f"{self.kind} {self.repo} {self.detail}".strip()

@dataclass
class PrResult:
    actions: list[Action] = field(default_factory=lambda: [])
    pull_request: PullRequest | None = None

def branch_name(number: int) -> str:
    """Returns the branch python-schema/pr-<N> that holds the C# draft for Python pull request N. `pr`, `close` and `status` all derive the branch from it.
    """
    return f"{BRANCH_PREFIX}{number}"

def plan_folder(plan_dir: Path, repo: str) -> Path:
    """Returns the folder of a plan directory that holds the files planned for one repository (the slash of Owner/Name becomes a double underscore). Used by `pr` to read the files it pushes.
    """
    return plan_dir / repo.replace("/", "__")

def load_summary(plan_dir: Path) -> dict[str, Any]:
    """Reads plan.json from a plan folder written by `plan`. `pr` uses it to know which files, labels and actions belong to which repository."""
    return json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))

def title_for(python_pr: PythonPr, files: list[dict[str, Any]]) -> str:
    """Builds the C# pull request title from the Python PR number and the class names of the planned files, naming at most three. Used by `pr` when it opens or updates the draft.
    """
    names = sorted({str(f["type"]).rsplit(".", 1)[-1].split("`")[0] for f in files})
    shown = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
    return f"Python schema #{python_pr.number}: {shown}"

def raise_pr(client: GitHubClient, plan_dir: Path, repo: str, python_pr: PythonPr, dry_run: bool = False,
             python_client: GitHubClient | None = None) -> PrResult:
    """Pushes the planned files of one C# repository to the branch python-schema/pr-<N> and opens or updates a draft PR.

    Running it again for the same Python PR updates the same branch and the same PR. With dry_run nothing is written: the
    actions are only listed (the reads that decide them still happen).
    """
    result = PrResult()
    summary = load_summary(plan_dir)
    files = [f for f in summary["files"] if f["repo"].lower() == repo.lower()]
    if not files:
        result.actions.append(Action("skip", repo, "no planned files for this repository"))
        return result

    branch = branch_name(python_pr.number)
    base = client.default_branch(repo)
    # The base already has every planned file (the C# pull request was merged) and no draft is open: there is nothing to propose, and GitHub
    # refuses a pull request with no commits, whether or not the branch exists
    in_sync = all((found := client.get_file(repo, base, e["path"])) is not None and found.content == (plan_folder(plan_dir, repo) / e["path"]).read_bytes() for e in files)
    if in_sync and client.find_pull_request(repo, branch) is None:
        result.actions.append(Action("skip", repo, f"{base} already has the planned files, nothing to raise"))
        return result

    if client.branch_sha(repo, branch) is None:
        base_sha = client.branch_sha(repo, base)
        if base_sha is None:
            raise ValueError(f"{repo} has no branch {base}")
        result.actions.append(Action("create branch", repo, f"{branch} from {base}"))
        if not dry_run:
            client.create_branch(repo, branch, base_sha)

    # In a dry run a new branch does not exist yet, so the files are compared with the base branch it would start from
    read_ref = base if dry_run and _new_branch(result) else branch
    for entry in files:
        data = (plan_folder(plan_dir, repo) / entry["path"]).read_bytes()
        current = client.get_file(repo, read_ref, entry["path"])
        if current is not None and current.content == data:
            result.actions.append(Action("unchanged", repo, entry["path"]))
            continue

        result.actions.append(Action("write file", repo, f"{entry['path']} ({entry['action']})"))
        if not dry_run:
            message = f"Python schema #{python_pr.number}: {entry['action']} {str(entry['type']).rsplit('.', 1)[-1]}"
            client.put_file(repo, branch, entry["path"], data, message, current.sha if current is not None else None)

    report_path = plan_dir / "reports" / (repo.replace("/", "__") + ".md")
    body = report_path.read_text(encoding="utf-8") if report_path.exists() else f"Depends on {python_pr.reference}\n"
    title = title_for(python_pr, files)
    existing = client.find_pull_request(repo, branch)
    if existing is not None:
        result.pull_request = existing
        if existing.body != body or existing.title != title:
            result.actions.append(Action("update pull request", repo, f"#{existing.number}"))
            if not dry_run:
                client.update_pull_request(repo, existing.number, title, body)
    else:
        result.actions.append(Action("open draft pull request", repo, f"{branch} into {base}"))
        if not dry_run:
            result.pull_request = client.create_pull_request(repo, branch, base, title, body, True)

    labels: list[str] = list(summary.get("labels", []))
    if labels:
        result.actions.append(Action("label", repo, ", ".join(labels)))
        if not dry_run and result.pull_request is not None:
            client.add_labels(repo, result.pull_request.number, labels)

    link = result.pull_request.url if result.pull_request is not None else f"(a draft pull request in {repo})"
    result.actions.append(Action("comment on the Python pull request", python_pr.repo, f"#{python_pr.number} links {link}"))
    if not dry_run and python_client is not None and result.pull_request is not None:
        python_client.upsert_comment(python_pr.repo, python_pr.number, MARKER, f"{MARKER}\nDraft C# pull request: {link}\n")
    return result

def _new_branch(result: PrResult) -> bool:
    """Tells whether the actions so far include creating the branch. In a dry run `raise_pr` uses it to compare files with the base branch, which the new branch would start from.
    """
    return any(a.kind == "create branch" for a in result.actions)

def close_linked(client: GitHubClient, repo: str, python_pr: PythonPr, merged: bool, dry_run: bool = False) -> PrResult:
    """When the Python PR is closed: unmerged closes the linked C# PR with a comment, merged only comments on it."""
    result = PrResult()
    found = client.find_pull_request(repo, branch_name(python_pr.number))
    if found is None:
        result.actions.append(Action("skip", repo, f"no open linked pull request for {python_pr.reference}"))
        return result

    result.pull_request = found
    if merged:
        text = f"{MARKER}\n{python_pr.reference} was merged."
        result.actions.append(Action("comment", repo, f"#{found.number}: the Python pull request merged"))
    else:
        text = f"{MARKER}\n{python_pr.reference} was closed without merging, so this draft is closed too."
        result.actions.append(Action("comment", repo, f"#{found.number}: the Python pull request was closed"))
        result.actions.append(Action("close pull request", repo, f"#{found.number}"))

    if not dry_run:
        client.upsert_comment(repo, found.number, MARKER, text)
        if not merged:
            client.close_pull_request(repo, found.number)
    return result
