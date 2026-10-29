"""The GitHub workflows, read as data: what starts them, what they may write to, and where the tokens go."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[4]
WORKFLOWS = REPO / ".github" / "workflows"

def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # YAML reads the key "on" as True
    data["on"] = data.pop(True) if True in data else data.get("on")
    return data

def lines(name: str) -> list[str]:
    return [line.strip() for line in (REPO / name).read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]

def test_all_workflows_are_valid_and_have_the_expected_jobs():
    assert list(load("python-schema-generation.yml")["jobs"]) == ["generate"]
    assert list(load("pr-checks.yml")["jobs"]) == ["checks"]
    assert list(load("linked-csharp-pr.yml")["jobs"]) == ["prepare", "repos", "raise", "close", "status", "sweep"]

def test_the_weekly_generation_commit_cannot_start_the_linked_pr_workflow():
    triggers = load("linked-csharp-pr.yml")["on"]
    assert set(triggers) == {"pull_request", "schedule", "workflow_dispatch"}, "never a push trigger: the weekly commit is a push"
    assert triggers["pull_request"]["paths"] == ["src/bhom_schema/**"]

def test_the_weekly_generation_commits_directly_and_is_not_a_pull_request():
    workflow = load("python-schema-generation.yml")
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    text = (WORKFLOWS / "python-schema-generation.yml").read_text(encoding="utf-8")
    assert "git push origin HEAD:develop" in text
    assert "gh pr create" not in text and "schema-updates" not in text

def test_workflows_start_with_read_only_permissions_and_raise_them_per_job():
    assert load("linked-csharp-pr.yml")["permissions"] == {"contents": "read"}
    assert load("pr-checks.yml")["permissions"] == {"contents": "read"}
    assert load("linked-csharp-pr.yml")["jobs"]["raise"]["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert "permissions" not in load("linked-csharp-pr.yml")["jobs"]["close"]

def test_the_app_token_is_made_for_one_repository_of_the_matrix_only():
    jobs = load("linked-csharp-pr.yml")["jobs"]
    for name in ("raise", "close"):
        step = next(s for s in jobs[name]["steps"] if str(s.get("uses", "")).startswith("actions/create-github-app-token"))
        assert step["with"]["repositories"] == "${{ matrix.name }}"
        assert step["with"]["owner"] == "${{ github.repository_owner }}"

def test_tokens_only_reach_the_steps_that_need_them():
    jobs = load("linked-csharp-pr.yml")["jobs"]
    for job in jobs.values():
        for step in job["steps"]:
            uses_token = "steps.token.outputs.token" in str(step)
            assert not uses_token or step.get("id") == "token" or "PY2CS_CSHARP_TOKEN" in step.get("env", {}) or step.get("with", {}).get("token"), step.get("name")

    plan_step = next(s for s in jobs["raise"]["steps"] if s.get("name") == "Plan the C# changes")
    assert "PY2CS_CSHARP_TOKEN" not in plan_step.get("env", {}), "planning does not need the token"

def test_the_tooling_that_holds_the_token_comes_from_the_base_branch():
    text = (WORKFLOWS / "linked-csharp-pr.yml").read_text(encoding="utf-8")
    assert "PYTHONPATH: base/.ci/generation" in text and "head/.ci/generation" not in text

def test_fork_pull_requests_get_no_linked_pull_request():
    text = (WORKFLOWS / "linked-csharp-pr.yml").read_text(encoding="utf-8")
    assert ".head.repo.full_name" in text and "eligible=false" in text
    jobs = load("linked-csharp-pr.yml")["jobs"]
    assert "eligible == 'true'" in jobs["repos"]["if"]

def test_the_main_bhom_repository_is_never_written_to():
    converted = lines("Converted-repositories.txt")
    assert converted == ["BHoM/CSharpSchema_Test"], "C# pull requests may only be raised in the test repository for now"
    assert "BHoM/BHoM" in lines("Included-repositories.txt"), "BHoM is cloned and built (read only), but never written to"

def test_every_listed_converted_repository_is_also_built():
    built = {r.lower() for r in lines("Included-repositories.txt")}
    assert all(r.lower() in built for r in lines("Converted-repositories.txt"))

def test_the_generation_and_the_checks_build_the_same_repositories():
    for name in ("python-schema-generation.yml", "pr-checks.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "Clone-Repositories.ps1 -List Included-repositories.txt" in text and "Build-Repositories.ps1 -List Included-repositories.txt" in text

def test_the_status_jobs_write_statuses_and_nothing_else():
    jobs = load("linked-csharp-pr.yml")["jobs"]
    assert jobs["status"]["permissions"] == {"contents": "read", "statuses": "write"}
    assert jobs["sweep"]["permissions"] == {"contents": "read", "pull-requests": "read", "statuses": "write"}
    for name in ("prepare", "repos", "raise", "close"):
        assert "statuses" not in jobs[name].get("permissions", {})

    # They read the C# repositories with the workflow's own token, so no GitHub App token is made for them
    for name in ("status", "sweep"):
        assert not any(str(s.get("uses", "")).startswith("actions/create-github-app-token") for s in jobs[name]["steps"])

def test_the_hourly_sweep_runs_only_on_the_schedule_and_the_other_jobs_never_do():
    jobs = load("linked-csharp-pr.yml")["jobs"]
    assert jobs["sweep"]["if"] == "github.event_name == 'schedule'"
    assert jobs["prepare"]["if"] == "github.event_name != 'schedule'"
    assert load("linked-csharp-pr.yml")["on"]["schedule"] == [{"cron": "17 * * * *"}]

def test_a_python_pr_with_no_csharp_change_still_gets_a_status():
    status = load("linked-csharp-pr.yml")["jobs"]["status"]
    assert "needs.repos.outputs.any == 'false'" in status["if"]
    assert "--no-csharp-change" in str(status["steps"])
