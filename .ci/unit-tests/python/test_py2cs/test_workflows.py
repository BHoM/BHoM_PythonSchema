"""The GitHub workflows, read as data: what starts them, what they may write to, and where the tokens go."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[4]
WORKFLOWS = REPO / ".github" / "workflows"

def load(name: str) -> dict[str, Any]:
    """Reads one workflow file as YAML and returns it with the on key (read by YAML as True) put back under on.

    Every test here uses it to check workflows as data.
    """
    data: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # YAML reads the key "on" as True
    data["on"] = data.pop(True) if True in data else data.get("on")
    return data

def lines(name: str) -> list[str]:
    """Returns the stripped non-blank, non-comment lines of a text file at the repository root.

    The tests use it to read the repository lists.
    """
    return [line.strip() for line in (REPO / name).read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]

def test_all_workflows_are_valid_and_have_the_expected_jobs():
    """Checks that the workflows are valid YAML with the expected jobs.

    Protects the generation, PR checks and linked C# PR workflows from broken edits.
    """
    assert list(load("python-schema-generation.yml")["jobs"]) == ["generate"]
    assert list(load("pr-checks.yml")["jobs"]) == ["checks", "alignment"]
    assert list(load("linked-csharp-pr.yml")["jobs"]) == ["linked"], "one job, so the pull request page shows one line"
    assert list(load("linked-csharp-pr-close.yml")["jobs"]) == ["close"]

def test_the_weekly_generation_commit_cannot_start_the_linked_pr_workflow():
    """Checks that neither linked-PR workflow has a push or schedule trigger, that they run for pull requests only on src/bhom_schema paths, and that only the close workflow reacts to a closed pull request.

    Protects against the weekly generation commit, which is a push, starting a linked C# PR, and the open pull request page from showing jobs that only matter on closing.
    """
    raised = load("linked-csharp-pr.yml")["on"]
    assert set(raised) == {"pull_request", "workflow_dispatch"}, "never a push trigger: the weekly commit is a push"
    assert raised["pull_request"]["paths"] == ["src/bhom_schema/**"]
    assert "closed" not in raised["pull_request"]["types"]

    closed = load("linked-csharp-pr-close.yml")["on"]
    assert set(closed) == {"pull_request", "workflow_dispatch"}
    assert closed["pull_request"]["types"] == ["closed"] and closed["pull_request"]["paths"] == ["src/bhom_schema/**"]

    assert "schedule" not in raised and "schedule" not in closed, "nothing polls: the C# alignment is re-run by hand after the C# merge"


def test_the_weekly_generation_commits_directly_and_is_not_a_pull_request():
    """Checks that the generation workflow runs on schedule or on demand and pushes straight to develop without opening a PR.

    Protects the weekly generation design.
    """
    workflow = load("python-schema-generation.yml")
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    text = (WORKFLOWS / "python-schema-generation.yml").read_text(encoding="utf-8")
    assert "git push origin HEAD:develop" in text
    assert "gh pr create" not in text and "schema-updates" not in text

def test_workflows_start_with_read_only_permissions_and_raise_them_per_job():
    """Checks that the workflows default to read-only contents and that only the jobs that need more raise their permissions.

    Protects the token permissions of the workflows.
    """
    for name in ("linked-csharp-pr.yml", "linked-csharp-pr-close.yml", "pr-checks.yml"):
        assert load(name)["permissions"] == {"contents": "read"}, name

    assert load("linked-csharp-pr.yml")["jobs"]["linked"]["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert "permissions" not in load("linked-csharp-pr-close.yml")["jobs"]["close"]


def test_the_app_token_is_made_only_for_the_repositories_the_change_touches():
    """Checks that the raise and close jobs make the GitHub App token only for the repositories that the change touches (a subset of the allowed list) and the owner.

    Protects the C# repositories from a token with wider reach.
    """
    for name, job in (("linked-csharp-pr.yml", "linked"), ("linked-csharp-pr-close.yml", "close")):
        step = next(s for s in load(name)["jobs"][job]["steps"] if str(s.get("uses", "")).startswith("actions/create-github-app-token"))
        assert step["with"]["repositories"] == "${{ steps.ctx.outputs.names }}"
        assert step["with"]["owner"] == "${{ github.repository_owner }}"

    action = yaml.safe_load((WORKFLOWS.parent / "actions" / "linked-pr-context" / "action.yml").read_text(encoding="utf-8"))
    repos_step = next(s for s in action["runs"]["steps"] if s.get("id") == "repos")
    assert "--allowed-repos base/Converted-repositories.txt" in repos_step["run"], "the touched repositories are always checked against the allowed list"


def test_tokens_only_reach_the_steps_that_need_them():
    """Checks that the app token reaches only steps that create it or need it, and not the planning step.

    Protects the token from the steps that run code from the PR.
    """
    for name in ("linked-csharp-pr.yml", "linked-csharp-pr-close.yml"):
        for job in load(name)["jobs"].values():
            for step in job["steps"]:
                uses_token = "steps.token.outputs.token" in str(step)
                assert not uses_token or step.get("id") == "token" or "PY2CS_CSHARP_TOKEN" in step.get("env", {}) or step.get("with", {}).get("token"), step.get("name")

    plan_step = next(s for s in load("linked-csharp-pr.yml")["jobs"]["linked"]["steps"] if s.get("name") == "Plan the C# changes")
    assert "PY2CS_CSHARP_TOKEN" not in plan_step.get("env", {}), "planning does not need the token"


def test_the_tooling_comes_from_the_pull_request_and_the_allowed_repositories_from_the_base():
    """Checks that the linked-PR workflows run py2cs and the patcher from the PR head checkout, and read the list of repositories a C# pull request may be raised in from the base.

    Protects the choice that a fix to the tooling works on its own pull request, and the list of where the App may write from being changed by that pull request.
    """
    action = (WORKFLOWS.parent / "actions" / "linked-pr-context" / "action.yml").read_text(encoding="utf-8")
    text = "".join((WORKFLOWS / name).read_text(encoding="utf-8") for name in ("linked-csharp-pr.yml", "linked-csharp-pr-close.yml")) + action
    assert "PYTHONPATH: head/.ci/generation" in text and "PYTHONPATH: base/.ci/generation" not in text
    assert "PY2CS_PATCHER: head/.ci/generation/" in text
    assert "base/Converted-repositories.txt" in text and "head/Converted-repositories.txt" not in text


def test_fork_pull_requests_get_no_linked_pull_request():
    """Checks that the shared action marks pull requests from forks as not eligible, and that every step of the raise and close jobs that uses a secret or writes waits for the gate of that action.

    Protects the secrets of the workflows from fork PRs.
    """
    action = (WORKFLOWS.parent / "actions" / "linked-pr-context" / "action.yml").read_text(encoding="utf-8")
    assert ".head.repo.full_name" in action and "eligible=false" in action

    for name, job, gate in (("linked-csharp-pr.yml", "linked", "raise"), ("linked-csharp-pr-close.yml", "close", "close")):
        for step in load(name)["jobs"][job]["steps"]:
            if step.get("id") == "ctx" or str(step.get("uses", "")).startswith("actions/checkout"):
                continue
            assert f"steps.ctx.outputs.{gate} == 'true'" in step["if"], step.get("name")


def test_the_main_bhom_repository_is_never_written_to():
    """Checks that the list of converted repositories holds only the test repository and that BHoM is in the build list.

    Protects the main BHoM repository from C# PRs while the process is tested.
    """
    converted = lines("Converted-repositories.txt")
    assert converted == ["BHoM/CSharpSchema_Test"], "C# pull requests may only be raised in the test repository for now"
    assert "BHoM/BHoM" in lines("Included-repositories.txt"), "BHoM is cloned and built (read only), but never written to"

def test_every_listed_converted_repository_is_also_built():
    """Checks that every converted repository is also in the list of built repositories (compared without case).

    Protects the generator, which needs each converted repository to be built.
    """
    built = {r.lower() for r in lines("Included-repositories.txt")}
    assert all(r.lower() in built for r in lines("Converted-repositories.txt"))

def test_the_generation_and_the_checks_build_the_same_repositories():
    """Checks that the generation and PR checks workflows clone and build the repositories from the same list.

    Protects align, which compares the PR with what the generator would write.
    """
    for path in (WORKFLOWS / "python-schema-generation.yml", WORKFLOWS.parent / "actions" / "bhom-assemblies" / "action.yml"):
        text = path.read_text(encoding="utf-8")
        assert "Clone-Repositories.ps1 -List Included-repositories.txt" in text and "Build-Repositories.ps1 -List Included-repositories.txt" in text

def test_the_release_workflow_is_manual_and_only_the_publish_job_gets_an_identity_token():
    """Checks that the release workflow starts only by hand, that contents are read-only by default, and that only the TestPyPI job can ask for an identity token.

    Protects the release from an unplanned trigger and TestPyPI from a token held by the build job.
    """
    workflow = load("release.yml")
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True
    assert workflow["permissions"] == {"contents": "read"}
    assert list(workflow["jobs"]) == ["build", "publish-testpypi"]
    assert workflow["jobs"]["build"]["permissions"] == {"contents": "write"}
    assert workflow["jobs"]["publish-testpypi"]["permissions"] == {"id-token": "write"}
    assert workflow["jobs"]["publish-testpypi"]["environment"] == "testpypi"


def test_the_release_workflow_stores_no_secret_and_nothing_is_published_in_a_dry_run():
    """Checks that the release workflow reads no repository secret, passes --release to the generator, and keeps every push, release and publish step behind not dry run.

    Protects the release from a stored password and from publishing when only a check was asked for.
    """
    workflow = load("release.yml")
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "secrets." not in text
    assert '--release "${{ inputs.version }}"' in text
    assert workflow["jobs"]["publish-testpypi"]["if"] == "${{ !inputs.dry_run }}"
    publishing = [s for s in workflow["jobs"]["build"]["steps"] if "git push" in s.get("run", "") or "gh release" in s.get("run", "")]
    assert publishing and all(s["if"] == "${{ !inputs.dry_run }}" for s in publishing)


def test_the_pr_checks_build_only_when_the_cache_of_assemblies_misses():
    """Checks that the shared assemblies action caches the built BHoM assemblies under a key made from the current commits, builds only on a cache miss, and saves the cache right after the build.

    Protects the speed of the PR checks from a change that rebuilds every time, and the cache from becoming stale.
    """
    action = yaml.safe_load((WORKFLOWS.parent / "actions" / "bhom-assemblies" / "action.yml").read_text(encoding="utf-8"))
    steps = action["runs"]["steps"]
    by_name = {s.get("name", s.get("uses", "")): s for s in steps}
    restore = by_name["Restore the built BHoM assemblies"]
    assert restore["with"]["key"] == "${{ steps.commits.outputs.key }}"
    for name in ("Clone the repositories", "Build the repositories in dependency order", "Save the built BHoM assemblies"):
        assert by_name[name]["if"] == "steps.assemblies.outputs.cache-hit != 'true'"
    assert "git ls-remote" in by_name["Find the current commit of each repository"]["run"]
    order = [s.get("name", "") for s in steps]
    assert order.index("Build the repositories in dependency order") < order.index("Save the built BHoM assemblies")


def test_the_alignment_check_is_its_own_job_with_a_name_that_says_what_is_pending():
    """Checks that the C# alignment runs as its own job of pr-checks, named after the linked C# PR, using the shared assemblies action and explaining a failure in the job summary, and that the main job no longer runs align.

    Protects the pull request page from showing an unexplained failure while the C# pull request is still open.
    """
    jobs = load("pr-checks.yml")["jobs"]
    assert "linked C# PR" in jobs["alignment"]["name"]
    assert any(s.get("uses") == "./.github/actions/bhom-assemblies" for s in jobs["alignment"]["steps"])
    assert any(s.get("name") == "Explain the failure" and "GITHUB_STEP_SUMMARY" in s["run"] for s in jobs["alignment"]["steps"])
    assert not any("align" in s.get("run", "") for s in jobs["checks"]["steps"])
    assert any("py2cs check" in s.get("run", "") for s in jobs["checks"]["steps"])
