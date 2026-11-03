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
    assert list(load("build-cache.yml")["jobs"]) == ["gate", "refresh"]

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
    for name in ("linked-csharp-pr.yml", "linked-csharp-pr-close.yml", "pr-checks.yml", "build-cache.yml"):
        assert load(name)["permissions"] == {"contents": "read"}, name

    assert load("linked-csharp-pr.yml")["jobs"]["linked"]["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert "permissions" not in load("linked-csharp-pr-close.yml")["jobs"]["close"]
    assert load("build-cache.yml")["jobs"]["gate"]["permissions"] == {"contents": "read", "actions": "read"}
    assert "permissions" not in load("build-cache.yml")["jobs"]["refresh"]


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
    """Checks that the generation and PR checks workflows build the repositories from the same list, the generation from its own clones and the PR checks through the build cache.

    Protects align, which compares the PR with what the generator would write.
    """
    generation = (WORKFLOWS / "python-schema-generation.yml").read_text(encoding="utf-8")
    assert "Clone-Repositories.ps1 -List Included-repositories.txt" in generation and "Build-Repositories.ps1 -List Included-repositories.txt" in generation
    action = (WORKFLOWS.parent / "actions" / "bhom-assemblies" / "action.yml").read_text(encoding="utf-8")
    assert "Build-Repositories.ps1 -List Included-repositories.txt" in action and 'List = "Included-repositories.txt"' in action

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


def test_the_assemblies_action_plans_restores_builds_and_saves_in_that_order():
    """Checks that the shared assemblies action plans the build first, restores the build cache by its exact key then by its prefix, builds from the saved plan with the cache folder, and saves under the exact key only when an entry was added.

    Protects the speed of the PR checks from a change that rebuilds every time, and the cache from being saved under a key that does not match its content.
    """
    action = yaml.safe_load((WORKFLOWS.parent / "actions" / "bhom-assemblies" / "action.yml").read_text(encoding="utf-8"))
    steps = action["runs"]["steps"]
    by_name = {s.get("name", s.get("uses", "")): s for s in steps}
    order = list(by_name)
    assert order.index("microsoft/setup-msbuild@v2") < order.index("Plan the build"), "the MSBuild version is part of the keys"
    assert order.index("Plan the build") < order.index("Restore the build cache") < order.index("Build the repositories in dependency order") < order.index("Save the build cache")
    assert "-Plan -PlanFile" in by_name["Plan the build"]["run"]
    restore = by_name["Restore the build cache"]
    assert restore["uses"].startswith("actions/cache/restore@")
    assert restore["with"] == {"path": ".build-cache", "key": "${{ steps.plan.outputs.key }}", "restore-keys": "${{ steps.plan.outputs.prefix }}"}
    build = by_name["Build the repositories in dependency order"]["run"]
    assert 'PlanFile = "$env:RUNNER_TEMP/build-plan.json"' in build and 'CacheFolder = ".build-cache"' in build, "the build uses the planned commits"
    save = by_name["Save the build cache"]
    assert save["uses"].startswith("actions/cache/save@") and save["if"] == "steps.build.outputs.added != ''"
    assert save["with"] == {"path": ".build-cache", "key": "${{ steps.plan.outputs.key }}"}

def test_the_alignment_job_waits_for_the_tests_and_still_runs_when_they_fail():
    """Checks that the C# alignment job needs the build and tests job and runs unless the run is cancelled.

    Protects the PR checks from building the same changed C# repository twice, and the alignment result from being skipped when a test fails.
    """
    alignment = load("pr-checks.yml")["jobs"]["alignment"]
    assert alignment["needs"] == "checks"
    assert alignment["if"] == "${{ !cancelled() }}"

def test_the_build_cache_refresh_runs_after_the_pr_checks_and_builds_from_develop():
    """Checks that the refresh workflow starts only after the PR workflow or by hand, that its gate rejects forks and manual runs off develop and looks the current state up on develop, and that the refresh builds from develop.

    Protects the develop cache, which every pull request reads, from what a pull request or a fork built.
    """
    workflow = load("build-cache.yml")
    assert set(workflow["on"]) == {"workflow_run", "workflow_dispatch"}
    assert workflow["on"]["workflow_run"] == {"workflows": ["PR"], "types": ["completed"]}
    assert load("pr-checks.yml")["name"] == "PR"
    assert workflow["concurrency"]["cancel-in-progress"] is False
    gate = workflow["jobs"]["gate"]
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in gate["if"]
    assert "github.ref == 'refs/heads/develop'" in gate["if"]
    assert gate["runs-on"] == "ubuntu-latest"
    assert not any("bhom-assemblies" in str(s.get("uses", "")) or "actions/cache" in str(s.get("uses", "")) for s in gate["steps"]), "the gate writes no cache"
    lookup = next(s for s in gate["steps"] if s.get("id") == "lookup")
    assert "--ref refs/heads/develop" in lookup["run"] and "$env:STATE_PREFIX" in lookup["run"]
    refresh = workflow["jobs"]["refresh"]
    assert refresh["needs"] == "gate" and refresh["if"] == "needs.gate.outputs.refresh == 'true'"
    checkout = next(s for s in refresh["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "develop"
    assert any(s.get("uses") == "./.github/actions/bhom-assemblies" for s in refresh["steps"])

def test_the_release_and_the_generation_build_clean():
    """Checks that the release and generation workflows do not use the build cache yet.

    Protects the published wheel and the weekly commit to develop from a cache that has not proved itself on the PR checks.
    """
    for name in ("release.yml", "python-schema-generation.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "bhom-assemblies" not in text and "actions/cache" not in text and "-CacheFolder" not in text, name

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


def test_the_included_repositories_file_is_tidy():
    """Checks that Included-repositories.txt does not misspell dKoP_Toolkit as dKop_Toolkit and ends with a newline, so that no tool skips its last line.

    Protects the list that the generation and the PR checks clone and build from.
    """
    text = (REPO / "Included-repositories.txt").read_bytes().decode("utf-8")
    assert text.endswith("\n")
    assert "dKop" not in text, "the repository is spelt dKoP_Toolkit"
    assert all(name == name.strip() for name in text.splitlines())

def test_the_alpha_workflow_publishes_only_when_asked_and_only_the_publish_job_gets_an_identity_token():
    """Checks that the alpha workflow starts on a schedule or by hand, is a dry run by default, publishes only when develop moved and not a dry run, gives an identity token to the publish job only, and stores no secret.

    Protects TestPyPI from an unplanned alpha and the identity token from the build job.
    """
    workflow = load("alpha-release.yml")
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True
    assert workflow["permissions"] == {"contents": "read"}
    assert list(workflow["jobs"]) == ["build", "publish-testpypi", "mark"]
    assert "permissions" not in workflow["jobs"]["build"]
    publish = workflow["jobs"]["publish-testpypi"]
    assert publish["permissions"] == {"id-token": "write"} and publish["environment"] == "testpypi-alpha"
    assert publish["if"] == "${{ needs.build.outputs.publish == 'true' && !inputs.dry_run }}"
    assert workflow["jobs"]["mark"]["needs"] == ["build", "publish-testpypi"], "the tag moves only after a publish"
    assert "secrets." not in (WORKFLOWS / "alpha-release.yml").read_text(encoding="utf-8")

def test_the_alpha_stamps_the_version_in_its_own_checkout_and_never_commits_it():
    """Checks that the alpha workflow reads the released tags, stamps with py2cs alpha-version, runs no commit or push of develop, and moves only the tag alpha-latest.

    Protects develop from a commit with a stamped version, and the weekly generation from a conflict with it.
    """
    text = (WORKFLOWS / "alpha-release.yml").read_text(encoding="utf-8")
    assert 'git tag --list "v*.0"' in text and "py2cs alpha-version" in text and "--stamp" in text
    assert "git commit" not in text and "HEAD:develop" not in text
    pushes = [line.strip() for line in text.splitlines() if "git push" in line]
    assert pushes == ["git push --force origin alpha-latest"]

def test_the_workflows_that_write_to_develop_or_its_tags_share_one_concurrency_group():
    """Checks that the generation, the release and the alpha share one concurrency group that never cancels a running one.

    Protects an alpha from packaging a half-pushed develop and from racing a release.
    """
    for name in ("python-schema-generation.yml", "release.yml", "alpha-release.yml"):
        assert load(name)["concurrency"] == {"group": "develop-publishing", "cancel-in-progress": False}, name
