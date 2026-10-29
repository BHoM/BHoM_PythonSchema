"""Markdown description of a plan, for the body of the C# pull request."""

from __future__ import annotations

from py2cs.plan import Plan

def only(plan: Plan, repo: str) -> Plan:
    """The part of a plan that belongs to one repository."""
    return Plan([f for f in plan.files if f.repo.lower() == repo.lower()], [(r, t) for r, t in plan.removed if r.lower() == repo.lower()], plan.errors)

def render_report(plan: Plan, python_pr: str = "", only_repo: str | None = None) -> str:
    if only_repo is not None:
        plan = only(plan, only_repo)

    lines: list[str] = []
    if python_pr:
        lines.append(f"Depends on {python_pr}")
        lines.append("")
    lines.append("This is a draft generated from the Python classes in BHoM_PythonSchema. It aligns the C# with the Python change, it is not a")
    lines.append("finished implementation: review every file. Existing files are only changed where the Python changed.")

    if plan.labels():
        lines += ["", "## Breaking changes", "",
                  "Some changes below can break existing C# code or objects saved with an earlier version (labelled `breaking-change`).",
                  "Add the matching upgrade in Versioning_Toolkit so old files still open, or confirm none is needed. Nothing here is blocked",
                  "automatically; the reviewer decides.", ""]
        lines += [f"- `{f.clr_name}`: {c}" for f in plan.files for c in f.breaking]
        lines += [f"- `{t}`: type removed" for _, t in plan.removed]

    for repo in plan.repos():
        lines += ["", f"## {repo}"]
        for f in [x for x in plan.files if x.repo == repo]:
            lines += ["", f"### `{f.path}` ({'new file' if f.action == 'new' else 'changes to an existing file'})", f"Type: `{f.clr_name}`"]
            if f.rule:
                lines.append(f"Location: {f.rule}")
            if f.changes:
                lines += ["", "Changes in Python:"] + [f"- {c}" for c in f.changes]
            if f.breaking:
                lines += ["", "Breaking changes:"] + [f"- {c}" for c in f.breaking]
            if f.notes:
                lines += ["", "Notes:"] + [f"- {n}" for n in f.notes]
        removed = [t for r, t in plan.removed if r == repo]
        if removed:
            lines += ["", "Removed in Python (delete or deprecate in C# by hand):"] + [f"- `{t}`" for t in removed]

    unknown = [t for r, t in plan.removed if r == "?"]
    if unknown:
        lines += ["", "## Removed types with an unknown repository"] + [f"- `{t}`" for t in unknown]
    if plan.errors:
        lines += ["", "## Problems"] + [f"- {e}" for e in plan.errors]
    return "\n".join(lines) + "\n"
