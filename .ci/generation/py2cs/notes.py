"""The release notes: what a Python user must know before upgrading to a new release."""

from __future__ import annotations

from py2cs.diff import Diff


def render_notes(diff: Diff, version: str, previous: str | None) -> str:
    """Returns Markdown release notes for a version: a Breaking changes section first, then the added, removed and modified classes.

    The release workflow writes it from the diff between the previous release and the new classes and attaches it to the GitHub Release.
    """
    since = f"since {previous}" if previous else "(the first release)"
    lines = [f"# BHoM schema {version}", "", f"Changes {since}.", ""]

    breaking = [(change.clr_name, item) for change in diff.changes for item in change.breaking]
    lines.append("## Breaking changes")
    lines.append("")
    if breaking:
        lines.append("Update your code for these before upgrading.")
        lines.append("")
        lines.extend(f"- `{name}`: {item}" for name, item in breaking)
    else:
        lines.append("None.")
    lines.append("")

    for kind, title in (("added", "Added classes"), ("removed", "Removed classes"), ("modified", "Changed classes")):
        changes = [change for change in diff.changes if change.kind == kind]
        if not changes:
            continue

        lines.append(f"## {title}")
        lines.append("")
        for change in changes:
            if kind == "modified":
                lines.append(f"- `{change.clr_name}`")
                lines.extend(f"  - {detail}" for detail in change.details)
            else:
                lines.append(f"- `{change.clr_name}`")

        lines.append("")

    return "\n".join(lines)
