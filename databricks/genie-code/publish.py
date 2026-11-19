# Databricks notebook source
# MAGIC %md
# MAGIC # Publish the BHoM skills and instructions for Genie Code
# MAGIC
# MAGIC Run by a **workspace admin**, from a Databricks Git folder of the BHoM_PythonSchema repository, after a change to the skills or the instructions has been merged and pulled.
# MAGIC
# MAGIC - Every skill folder of `databricks/genie-code/skills/` is copied into `<workspace>/.assistant/skills/`, replacing the folder of the same name and nothing else.
# MAGIC - The BHoM section of `workspace-instructions.md` is written into `<workspace>/.assistant_workspace_instructions.md` between two marker lines; everything else in that file is kept.
# MAGIC
# MAGIC With `dry_run` set to `yes` (the default) nothing is written: the cell lists what would be done. Start a new Genie Code chat afterwards and check that `@bhom-mapping` is listed.

# COMMAND ----------

import shutil
from pathlib import Path

START = "<!-- bhom-schema: start -->"
END = "<!-- bhom-schema: end -->"
INSTRUCTIONS_FILE = ".assistant_workspace_instructions.md"
SKILLS_FOLDER = ".assistant/skills"
LIMIT = 20000

def skill_folders(source: Path) -> list[Path]:
    """Returns the skill folders of the source: the folders of `skills/` that hold a SKILL.md, sorted by name."""
    return sorted(folder for folder in (source / "skills").iterdir() if (folder / "SKILL.md").is_file())

def section_of(source: Path) -> str:
    """Returns the BHoM section of the instructions, between its two marker lines, ready to be put in the instructions file."""
    text = (source / "workspace-instructions.md").read_text(encoding="utf-8").strip("\n")
    return f"{START}\n{text}\n{END}"

def merged(existing: str, section: str) -> str:
    """Returns the instructions file with the BHoM section in it: the section between the markers is replaced, or added at the end when there is none, and all other text is kept.

    Raises ValueError when only one of the two markers is there, because the file would then be guessed at.
    """
    first, last = existing.find(START), existing.find(END)
    if first == -1 and last == -1:
        return (existing.rstrip("\n") + "\n\n" if existing.strip() else "") + section + "\n"

    if first == -1 or last == -1 or last < first:
        raise ValueError(f"the instructions file has one of the markers {START!r} and {END!r}, or has them in the wrong order; repair it by hand")

    return existing[:first] + section + existing[last + len(END):]

def publish(source: Path, workspace: Path, dry_run: bool = True) -> list[str]:
    """Publishes the skills and the instructions of the source folder (`databricks/genie-code`) into a workspace folder, and returns the lines that say what was done (or would be, with `dry_run`).

    A skill folder of the source replaces the folder of the same name in the workspace, so a file removed from the source goes too; other skill folders are not touched. Raises ValueError, before
    writing anything, when the instructions file would be longer than Genie Code reads (20,000 characters), or has a damaged marker.
    """
    actions: list[str] = []
    target = workspace / INSTRUCTIONS_FILE
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    result = merged(existing, section_of(source))
    if len(result) > LIMIT:
        raise ValueError(f"the instructions would be {len(result)} characters; Genie Code reads at most {LIMIT}. Shorten the instructions of the other teams or of this section")

    for folder in skill_folders(source):
        destination = workspace / SKILLS_FOLDER / folder.name
        actions.append(f"{'would copy' if dry_run else 'copied'} skill {folder.name} to {destination}")
        if not dry_run:
            if destination.exists():
                shutil.rmtree(destination)

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(folder, destination)

    if result == existing:
        actions.append(f"instructions in {target} are up to date")
    else:
        actions.append(f"{'would write' if dry_run else 'wrote'} the BHoM section of the instructions in {target} ({len(result)} characters)")
        if not dry_run:
            target.write_text(result, encoding="utf-8", newline="\n")

    return actions

# COMMAND ----------

if __name__ == "__main__":
    dbutils.widgets.text("repository_folder", "/Workspace/Shared/admin/BHoM_PythonSchema", "Git folder of BHoM_PythonSchema")  # noqa: F821
    dbutils.widgets.text("workspace_folder", "/Workspace", "Workspace root of .assistant")  # noqa: F821
    dbutils.widgets.dropdown("dry_run", "yes", ["yes", "no"], "Dry run (write nothing)")  # noqa: F821

    for line in publish(
            Path(dbutils.widgets.get("repository_folder")) / "databricks" / "genie-code",  # noqa: F821
            Path(dbutils.widgets.get("workspace_folder")),  # noqa: F821
            dbutils.widgets.get("dry_run") == "yes"):  # noqa: F821
        print(line)
