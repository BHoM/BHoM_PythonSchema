"""Finding C# files: where an existing type lives, and where a new one should go. Never derived from the namespace alone."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from py2cs.model import TypeInfo

SKIPPED_FOLDERS = {"obj", "bin", ".git", ".vs", "node_modules"}


@dataclass
class Located:
    path: Path | None
    note: str = ""


@dataclass
class Placement:
    path: str          # relative to the repository root, forward slashes
    rule: str


def cs_files(folder: Path) -> list[Path]:
    """Lists the .cs files under a folder, sorted, skipping build and tool folders such as obj, bin and .git. `locate` and `place` search these files.
    """
    return sorted(p for p in folder.rglob("*.cs") if not (SKIPPED_FOLDERS & set(p.relative_to(folder).parts[:-1])))


def read(path: Path) -> str:
    """Reads a C# file as text, dropping a byte order mark and ignoring undecodable bytes. Used by `locate` and `place` to look at declarations and namespaces.
    """
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def assembly_folder(repo_root: Path, assembly: str) -> Path | None:
    """Finds the folder of an assembly directly under the repository root, ignoring case, or returns None. `locate` and `place` search only inside it.
    """
    for child in sorted(repo_root.iterdir()):
        if child.is_dir() and child.name.lower() == assembly.lower():
            return child
    return None


def declaration(name: str) -> re.Pattern[str]:
    """Builds the regular expression that matches a class, interface, enum or struct declaration with that exact name. Used by `locate` to find the file of an existing type.
    """
    return re.compile(rf"\b(?:class|interface|enum|struct)\s+{re.escape(name)}\b")


def namespace_of(text: str) -> str | None:
    """Returns the namespace declared in C# source text, or None. `locate` and `place` use it to prefer files in the same namespace as the type."""
    match = re.search(r"^\s*namespace\s+([\w.]+)", text, re.M)
    return match.group(1) if match else None


def locate(repo_root: Path, info: TypeInfo) -> Located:
    """The existing .cs file declaring a type: file name first, then a search of the assembly folder for the declaration."""
    folder = assembly_folder(repo_root, info.assembly) or repo_root
    pattern = declaration(info.simple_name)

    def matches(files: list[Path]) -> list[Path]:
        """Keeps the files that declare the type, preferring those whose namespace is the type's namespace. Used by `locate` first for files named after the type, then for all files.
        """
        found = [f for f in files if pattern.search(read(f))]
        exact = [f for f in found if namespace_of(read(f)) == info.namespace]
        return exact or found

    files = cs_files(folder)
    found = matches([f for f in files if f.stem == info.simple_name]) or matches(files)
    if not found:
        return Located(None, "no existing declaration found")
    if len(found) > 1:
        return Located(found[0], f"{len(found)} files declare {info.simple_name}: {', '.join(f.name for f in found)}; the first was used")
    return Located(found[0])


def place(repo_root: Path, info: TypeInfo) -> Placement:
    """Where to put the file for a new type, following the conventions already in the assembly folder."""
    folder = assembly_folder(repo_root, info.assembly)
    file_name = f"{info.simple_name}.cs"
    if folder is None:
        return Placement(f"{info.assembly}/{file_name}", f"assembly folder {info.assembly} not found in the repository, placed in a new folder of that name")

    is_enum = info.kind == "enum"
    siblings: list[tuple[Path, bool]] = []
    for path in cs_files(folder):
        text = read(path)
        if namespace_of(text) == info.namespace:
            siblings.append((path, re.search(r"\benum\s+\w+", text) is not None))

    same_kind = [p for p, enum in siblings if enum == is_enum]
    for candidates, label in ((same_kind, "same kind"), ([p for p, _ in siblings], "any kind")):
        if candidates:
            folders = Counter(p.parent for p in candidates)
            best = sorted(folders.items(), key=lambda kv: (-kv[1], len(kv[0].parts), str(kv[0])))[0][0]
            return Placement((best.relative_to(repo_root) / file_name).as_posix(), f"folder of {len(candidates)} existing {label} files in namespace {info.namespace}")

    parts = info.namespace.removeprefix("BH.oM.Adapters.").removeprefix("BH.oM.").split(".")[1:]
    candidate = folder.joinpath(*parts)
    if parts and candidate.is_dir():
        return Placement((candidate.relative_to(repo_root) / file_name).as_posix(), "folder matching the namespace")
    return Placement((folder.relative_to(repo_root) / file_name).as_posix(), "assembly root: no sibling types or matching folder found")
