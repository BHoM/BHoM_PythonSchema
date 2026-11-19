# Databricks notebook source
# MAGIC %md
# MAGIC # Publish the BHoM skills and instructions for Genie Code
# MAGIC
# MAGIC Run by a **workspace admin**, from a Databricks Git folder of the BHoM_PythonSchema repository, after a change to the skills or the instructions has been merged and pulled.
# MAGIC
# MAGIC - Every skill folder of `databricks/genie-code/skills/` is copied into `<workspace>/.assistant/skills/`, replacing the folder of the same name and nothing else.
# MAGIC - The BHoM section of `workspace-instructions.md` is written into `<workspace>/.assistant_workspace_instructions.md` between two marker lines; everything else in that file is kept.
# MAGIC
# MAGIC The workspace is written through the Workspace API (the Databricks SDK, which notebooks have), because the file system of a notebook cannot create files in the root of the workspace.
# MAGIC With `dry_run` set to `yes` (the default) nothing is written: the cell lists what would be done. Start a new Genie Code chat afterwards and check that `@bhom-mapping` is listed.

# COMMAND ----------

import io
import shutil
from pathlib import Path, PurePath

START = "<!-- bhom-schema: start -->"
END = "<!-- bhom-schema: end -->"
INSTRUCTIONS_FILE = ".assistant_workspace_instructions.md"
SKILLS_FOLDER = ".assistant/skills"
LIMIT = 20000

class FileStore:
    """Writes to a folder through the file system: for a folder you may write to, and for the tests."""

    def read(self, path: PurePath) -> str | None:
        """Returns the text of a file, or None when it does not exist."""
        file = Path(path)
        return file.read_text(encoding="utf-8") if file.is_file() else None

    def write(self, path: PurePath, text: str) -> None:
        """Writes a text file, making its folder."""
        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8", newline="\n")

    def replace_folder(self, destination: PurePath, source: Path) -> None:
        """Makes the destination folder a copy of the source folder, removing what was there."""
        target = Path(destination)
        if target.exists():
            shutil.rmtree(target)

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)

class WorkspaceStore:
    """Writes to the workspace through the Workspace API (the Databricks SDK), which is how the root of the workspace can be written: the file system of a notebook cannot create files in the root.

    `client` is a `databricks.sdk.WorkspaceClient`, `not_found` the exception its calls raise for a missing path, and `auto_format` the value `ImportFormat.AUTO`. A path under `/Workspace` is given
    to the API without that prefix.
    """

    def __init__(self, client, not_found, auto_format) -> None:
        """Keeps the client and the two values taken from the SDK."""
        self.client = client
        self.not_found = not_found
        self.auto_format = auto_format

    @staticmethod
    def api_path(path: PurePath) -> str:
        """Returns the path as the Workspace API writes it: `/Workspace/.assistant/skills` is `/.assistant/skills`."""
        text = path.as_posix()
        if text.startswith("/Workspace"):
            return text[len("/Workspace"):] or "/"

        return text

    def read(self, path: PurePath) -> str | None:
        """Returns the text of a workspace file, or None when it does not exist."""
        try:
            return self.client.workspace.download(self.api_path(path)).read().decode("utf-8")
        except self.not_found:
            return None

    def write(self, path: PurePath, text: str) -> None:
        """Writes a workspace file, replacing it, making its folder."""
        self.client.workspace.mkdirs(self.api_path(path.parent))
        self.client.workspace.upload(self.api_path(path), io.BytesIO(text.encode("utf-8")), format=self.auto_format, overwrite=True)

    def replace_folder(self, destination: PurePath, source: Path) -> None:
        """Makes the destination folder of the workspace a copy of the source folder: it is deleted, then every file of the source is uploaded."""
        target = self.api_path(destination)
        try:
            self.client.workspace.delete(target, recursive=True)
        except self.not_found:
            pass

        self.client.workspace.mkdirs(target)
        for file in sorted(source.rglob("*")):
            if not file.is_file():
                continue

            relative = file.relative_to(source).as_posix()
            if "/" in relative:
                self.client.workspace.mkdirs(target + "/" + relative.rpartition("/")[0])

            self.client.workspace.upload(target + "/" + relative, io.BytesIO(file.read_bytes()), format=self.auto_format, overwrite=True)

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

def publish(source: Path, workspace: PurePath, dry_run: bool = True, store=None) -> list[str]:
    """Publishes the skills and the instructions of the source folder (`databricks/genie-code`) into a workspace folder, and returns the lines that say what was done (or would be, with `dry_run`).

    A skill folder of the source replaces the folder of the same name in the workspace, so a file removed from the source goes too; other skill folders are not touched. Raises ValueError, before
    writing anything, when the instructions file would be longer than Genie Code reads (20,000 characters), or has a damaged marker. `store` is where to write: the file system by default, or a
    WorkspaceStore.
    """
    store = store if store is not None else FileStore()
    actions: list[str] = []
    target = workspace / INSTRUCTIONS_FILE
    existing = store.read(target) or ""
    result = merged(existing, section_of(source))
    if len(result) > LIMIT:
        raise ValueError(f"the instructions would be {len(result)} characters; Genie Code reads at most {LIMIT}. Shorten the instructions of the other teams or of this section")

    for folder in skill_folders(source):
        destination = workspace / SKILLS_FOLDER / folder.name
        actions.append(f"{'would copy' if dry_run else 'copied'} skill {folder.name} to {destination.as_posix()}")
        if not dry_run:
            store.replace_folder(destination, folder)

    if result == existing:
        actions.append(f"instructions in {target.as_posix()} are up to date")
    else:
        actions.append(f"{'would write' if dry_run else 'wrote'} the BHoM section of the instructions in {target.as_posix()} ({len(result)} characters)")
        if not dry_run:
            store.write(target, result)

    return actions

# COMMAND ----------

if __name__ == "__main__":
    from pathlib import PurePosixPath

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import NotFound
    from databricks.sdk.service.workspace import ImportFormat

    dbutils.widgets.text("repository_folder", "/Workspace/Shared/admin/BHoM_PythonSchema", "Git folder of BHoM_PythonSchema")  # noqa: F821
    dbutils.widgets.text("workspace_folder", "/Workspace", "Workspace root of .assistant")  # noqa: F821
    dbutils.widgets.dropdown("dry_run", "yes", ["yes", "no"], "Dry run (write nothing)")  # noqa: F821

    # The source is read as files; the workspace is written through the Workspace API, because the root of the workspace cannot be written through the file system of a notebook
    for line in publish(
            Path(dbutils.widgets.get("repository_folder")) / "databricks" / "genie-code",  # noqa: F821
            PurePosixPath(dbutils.widgets.get("workspace_folder")),  # noqa: F821
            dbutils.widgets.get("dry_run") == "yes",  # noqa: F821
            WorkspaceStore(WorkspaceClient(), NotFound, ImportFormat.AUTO)):
        print(line)
