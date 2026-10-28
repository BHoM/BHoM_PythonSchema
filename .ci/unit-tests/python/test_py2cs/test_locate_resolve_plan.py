from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from helpers import demo_package, module, package, require_patcher
from py2cs.__main__ import main
from py2cs.diff import diff_manifests
from py2cs.locate import locate, place
from py2cs.plan import make_plan
from py2cs.reader import read_package
from py2cs.report import render_report
from py2cs.resolve import ResolveError, build_listing, load_listing, resolve_repo

LISTING = Path(__file__).resolve().parents[2] / "github-fixtures" / "repo-listing.json"


def cs(namespace: str, declaration: str) -> str:
    return f"using System;\n\nnamespace {namespace}\n{{\n    {declaration}\n    {{\n    }}\n}}\n"


def csharp_tree(root: Path) -> Path:
    """A repository whose folders do not follow the namespaces, like many real ones."""
    repo = root / "Demo_Toolkit"
    files = {
        "Demo_oM/AdministrativeInformation/ProjectInfo.cs": cs("BH.oM.Demo", "public class ProjectInfo : IdentityBase"),
        "Demo_oM/AdministrativeInformation/IdentityBase.cs": cs("BH.oM.Demo", "public interface IdentityBase : IObject"),
        "Demo_oM/Enums/Colour.cs": cs("BH.oM.Demo", "public enum Colour"),
        "Demo_oM/Enums/Shade.cs": cs("BH.oM.Demo", "public enum Shade"),
        "Demo_oM/Enums/Elements/Wall.cs": cs("BH.oM.Demo.Elements", "public class Wall : IObject"),
        "Demo_oM/Misc/Several.cs": cs("BH.oM.Demo", "public class Alpha : IObject") + cs("BH.oM.Demo", "public class Beta : IObject"),
        "Demo_oM/Curves/Line.cs": cs("BH.oM.Demo", "public class Line : IObject"),
        "Demo_oM/Other/Line.cs": cs("BH.oM.Other", "public class Line : IObject"),
        "Demo_oM/Elements/Door.cs": cs("BH.oM.Demo.Elements", "public class Door : IObject"),
        "Demo_oM/obj/Debug/Ghost.cs": cs("BH.oM.Demo", "public class Ghost : IObject"),
        "Other_oM/Thing.cs": cs("BH.oM.Other", "public class Thing : IObject"),
    }
    for relative, text in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return repo


def info(tmp_path: Path, clr: str, ns: str, kind: str = "class", asm: str = "Demo_oM", repo: str | None = "BHoM/Demo_Toolkit"):
    name = clr.rsplit(".", 1)[-1]
    pkg = package(tmp_path / f"pkg_{asm}_{name}_{repo is None}", {f"{asm}/{name}.py": module(name, clr, ns, asm, repo=repo, kind=kind)})
    return read_package(pkg)[clr]


# ---------------------------------------------------------------- locate

def test_existing_file_is_found_although_the_folder_does_not_match_the_namespace(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    found = locate(repo, info(tmp_path, "BH.oM.Demo.ProjectInfo", "BH.oM.Demo"))
    assert found.path is not None and found.path.relative_to(repo).as_posix() == "Demo_oM/AdministrativeInformation/ProjectInfo.cs"


def test_locate_uses_the_namespace_to_choose_between_same_named_files(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    found = locate(repo, info(tmp_path, "BH.oM.Other.Line", "BH.oM.Other"))
    assert found.path is not None and found.path.relative_to(repo).as_posix() == "Demo_oM/Other/Line.cs"


def test_locate_finds_a_type_declared_in_a_differently_named_file(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    found = locate(repo, info(tmp_path, "BH.oM.Demo.Beta", "BH.oM.Demo"))
    assert found.path is not None and found.path.name == "Several.cs"


def test_locate_reports_missing_types_and_ignores_build_folders(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    assert locate(repo, info(tmp_path, "BH.oM.Demo.Nope", "BH.oM.Demo")).path is None
    assert locate(repo, info(tmp_path, "BH.oM.Demo.Ghost", "BH.oM.Demo")).path is None


@pytest.mark.skipif(not Path("C:/Github/dKoP_Toolkit/dKoP_oM").is_dir(), reason="dKoP_Toolkit is not cloned")
def test_real_dkop_project_identification_is_found_under_administrative_information(tmp_path: Path):
    found = locate(Path("C:/Github/dKoP_Toolkit"), info(tmp_path, "BH.oM.dKoP.ProjectIdentification", "BH.oM.dKoP", asm="dKoP_oM", repo="BHoM/dKoP_Toolkit"))
    assert found.path is not None
    assert found.path.relative_to("C:/Github/dKoP_Toolkit").as_posix() == "dKoP_oM/AdministrativeInformation/ProjectIdentification.cs"


# ---------------------------------------------------------------- place

def test_place_enum_next_to_sibling_enums(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    placement = place(repo, info(tmp_path, "BH.oM.Demo.Size", "BH.oM.Demo", kind="enum"))
    assert placement.path == "Demo_oM/Enums/Size.cs" and "same kind" in placement.rule


def test_place_class_next_to_sibling_classes_of_the_namespace(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    placement = place(repo, info(tmp_path, "BH.oM.Demo.Elements.Window", "BH.oM.Demo.Elements"))
    assert placement.path == "Demo_oM/Elements/Window.cs"


def test_place_falls_back_to_namespace_folder_then_assembly_root(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    (repo / "Demo_oM" / "Loads").mkdir()
    assert place(repo, info(tmp_path, "BH.oM.Demo.Loads.Point", "BH.oM.Demo.Loads")).path == "Demo_oM/Loads/Point.cs"
    root = place(repo, info(tmp_path, "BH.oM.Demo.Brand.New", "BH.oM.Demo.Brand"))
    assert root.path == "Demo_oM/New.cs" and "assembly root" in root.rule


def test_place_in_an_unknown_assembly_creates_a_folder_named_after_it(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    assert place(repo, info(tmp_path, "BH.oM.Fresh.Thing", "BH.oM.Fresh", asm="Fresh_oM")).path == "Fresh_oM/Thing.cs"


# ---------------------------------------------------------------- resolve

def test_repo_from_the_marker_is_validated_case_insensitively(tmp_path: Path):
    listing = {"BHoM/dKoP_Toolkit": ["dKoP_oM"], "BHoM/BHoM": ["Geometry_oM"]}
    assert resolve_repo(info(tmp_path, "BH.oM.A.X", "BH.oM.A", repo="https://github.com/BHoM/dkop_toolkit"), listing).repo == "BHoM/dKoP_Toolkit"
    assert resolve_repo(info(tmp_path, "BH.oM.A.Y", "BH.oM.A", repo="BHoM/BHoM")).source == "marker"


def test_repo_missing_from_the_listing_is_an_error(tmp_path: Path):
    with pytest.raises(ResolveError, match="GitHub App"):
        resolve_repo(info(tmp_path, "BH.oM.A.X", "BH.oM.A", repo="BHoM/Hidden"), {"BHoM/BHoM": []})


def test_scan_fallback_finds_the_assembly_folder(tmp_path: Path):
    listing = {"BHoM/BHoM": ["Geometry_oM"], "BHoM/Revit_Toolkit": ["Revit_oM"]}
    found = resolve_repo(info(tmp_path, "BH.oM.Revit.X", "BH.oM.Revit", asm="Revit_oM", repo=None), listing)
    assert (found.repo, found.source) == ("BHoM/Revit_Toolkit", "scan")


def test_scan_fallback_errors_are_clear(tmp_path: Path):
    with pytest.raises(ResolveError, match="no repository has a folder"):
        resolve_repo(info(tmp_path, "BH.oM.A.X", "BH.oM.A", asm="Nowhere_oM", repo=None), {"BHoM/BHoM": ["Geometry_oM"]})
    with pytest.raises(ResolveError, match="several repositories"):
        resolve_repo(info(tmp_path, "BH.oM.A.X", "BH.oM.A", asm="Dup_oM", repo=None), {"A/A": ["Dup_oM"], "B/B": ["dup_oM"]})
    with pytest.raises(ResolveError, match="no repo recorded"):
        resolve_repo(info(tmp_path, "BH.oM.A.X", "BH.oM.A", repo=None))


def test_recorded_listing_resolves_the_real_assemblies(tmp_path: Path):
    listing = load_listing(LISTING)
    for assembly, repo in [("dKoP_oM", "BHoM/dKoP_Toolkit"), ("Geometry_oM", "BHoM/BHoM"), ("BHoM", "BHoM/BHoM"), ("Revit_oM", "BHoM/Revit_Toolkit"),
                           ("Python_oM", "BHoM/Python_Toolkit"), ("Adapter_oM", "BHoM/BHoM_Adapter")]:
        assert resolve_repo(info(tmp_path / assembly, f"BH.oM.X.{assembly}T", "BH.oM.X", asm=assembly, repo=None), listing).repo == repo
    assert resolve_repo(info(tmp_path, "BH.oM.X.Y", "BH.oM.X", asm="dKoP_oM", repo="BHoM/dKop_Toolkit"), listing).repo == "BHoM/dKoP_Toolkit"


def test_listing_can_be_built_from_clones(tmp_path: Path):
    repo = csharp_tree(tmp_path)
    assert build_listing({"BHoM/Demo_Toolkit": repo}) == {"BHoM/Demo_Toolkit": ["Demo_oM", "Other_oM"]}


# ---------------------------------------------------------------- plan

def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_plan_for_a_modified_new_and_removed_type(tmp_path: Path):
    require_patcher()
    clones = tmp_path / "clones"
    repo = csharp_tree(clones)
    before = tree_hash(clones)

    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head", ["ProjectNumber: str = ''"])
    (head_root / "Demo_oM" / "Mode.py").unlink()
    (head_root / "Demo_oM" / "Fresh.py").write_text(module("Fresh", "BH.oM.Demo.Fresh", "BH.oM.Demo", "Demo_oM", body=["X: float = 0.0"]), encoding="utf-8")
    head = read_package(head_root)

    plan = make_plan(diff_manifests(base, head), head, base, lambda r: repo if r == "BHoM/Demo_Toolkit" else None, {"BHoM/Demo_Toolkit": ["Demo_oM"]})
    assert plan.errors == []
    by_type = {f.clr_name: f for f in plan.files}
    modified = by_type["BH.oM.Demo.ProjectInfo"]
    assert (modified.action, modified.path) == ("patch", "Demo_oM/AdministrativeInformation/ProjectInfo.cs")
    assert modified.text == cs("BH.oM.Demo", "public class ProjectInfo : IdentityBase").replace("    {\n    }", "    {\n        public virtual string ProjectNumber { get; set; } = \"\";\n    }")
    assert "public virtual string ProjectNumber { get; set; } = \"\";" in modified.text
    new = by_type["BH.oM.Demo.Fresh"]
    assert (new.action, new.path) == ("new", "Demo_oM/AdministrativeInformation/Fresh.cs")
    assert plan.removed == [("BHoM/Demo_Toolkit", "BH.oM.Demo.Mode")]
    assert tree_hash(clones) == before, "planning must never write into the C# checkouts"

    report = render_report(plan, "BHoM/BHoM_PythonSchema#7")
    assert report.startswith("Depends on BHoM/BHoM_PythonSchema#7")
    assert "## BHoM/Demo_Toolkit" in report and "property added: string ProjectNumber" in report and "BH.oM.Demo.Mode" in report


def test_plan_reports_problems_instead_of_guessing(tmp_path: Path):
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head", ["ProjectNumber: str = ''"])
    head = read_package(head_root)
    no_clone = make_plan(diff_manifests(base, head), head, base, lambda r: None, None)
    assert no_clone.files == [] and "no checkout of BHoM/Demo_Toolkit" in no_clone.errors[0]
    not_installed = make_plan(diff_manifests(base, head), head, base, lambda r: None, {"BHoM/Elsewhere": []})
    assert "GitHub App" in not_installed.errors[0]


def test_command_line_plan_writes_files_into_the_output_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    require_patcher()
    clones = tmp_path / "clones"
    csharp_tree(clones)
    before = tree_hash(clones)
    demo_package(tmp_path / "base")
    demo_package(tmp_path / "head", ["ProjectNumber: str = ''"])
    listing = tmp_path / "listing.json"
    listing.write_text(json.dumps({"BHoM/Demo_Toolkit": ["Demo_oM"]}))
    out = tmp_path / "out"

    status = main(["plan", "--base-root", str(tmp_path / "base" / "bhom_schema"), "--head-root", str(tmp_path / "head" / "bhom_schema"),
                   "--clones-parent", str(clones), "--listing", str(listing), "--python-pr", "BHoM/BHoM_PythonSchema#7", "--out", str(out)])
    assert status == 0
    assert (out / "BHoM__Demo_Toolkit" / "Demo_oM" / "AdministrativeInformation" / "ProjectInfo.cs").exists()
    assert json.loads((out / "plan.json").read_text())["files"][0]["action"] == "patch"
    assert "Depends on BHoM/BHoM_PythonSchema#7" in (out / "report.md").read_text()
    assert tree_hash(clones) == before
    assert "1 files planned" in capsys.readouterr().out


def test_command_line_diff_resolve_and_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    demo_package(tmp_path / "base")
    demo_package(tmp_path / "head", ["ProjectNumber: str = ''"])
    assert main(["diff", "--base-root", str(tmp_path / "base" / "bhom_schema"), "--head-root", str(tmp_path / "head" / "bhom_schema"), "--out", str(tmp_path / "d.json")]) == 0
    assert json.loads((tmp_path / "d.json").read_text())["changes"][0]["kind"] == "modified"
    assert main(["manifest", "--root", str(tmp_path / "head" / "bhom_schema"), "--out", str(tmp_path / "m.json")]) == 0
    capsys.readouterr()
    assert main(["resolve", "--root", str(tmp_path / "head" / "bhom_schema")]) == 0
    assert "BH.oM.Demo.ProjectInfo\tBHoM/Demo_Toolkit\tmarker" in capsys.readouterr().out


@pytest.mark.skipif(not Path("C:/Github/dKoP_Toolkit/dKoP_oM").is_dir(), reason="dKoP_Toolkit is not cloned")
def test_rehearsal_adding_a_property_to_project_identification(tmp_path: Path):
    """The dry run planned for the real dKoP_Toolkit: a new Python property becomes a one line C# change, clone untouched."""
    require_patcher()
    def project_identification(root: Path, extra: list[str]) -> Path:
        return package(root, {"dKoP_oM/IdKoPObject.py": module("IdKoPObject", "BH.oM.dKoP.IdKoPObject", "BH.oM.dKoP", "dKoP_oM", repo="BHoM/dKoP_Toolkit", kind="interface", bases="ABC",
                                                                imports=["from abc import ABC"]),
                              "dKoP_oM/ProjectIdentification.py": module(
            "ProjectIdentification", "BH.oM.dKoP.ProjectIdentification", "BH.oM.dKoP", "dKoP_oM", repo="BHoM/dKoP_Toolkit", bases="SchemaModel, IdKoPObject",
            imports=["from bhom_schema.dKoP_oM.IdKoPObject import IdKoPObject"],
            body=["ProjectReference: str = ''", "ProjectName: str = ''", "ProjectLocation: str = ''", "AdditionalReferences: str = ''", *extra])})

    clone = Path("C:/Github/dKoP_Toolkit")
    before = tree_hash(clone / "dKoP_oM" / "AdministrativeInformation")
    base = read_package(project_identification(tmp_path / "base", []))
    head = read_package(project_identification(tmp_path / "head", ["ProjectNumber: str = ''"]))
    plan = make_plan(diff_manifests(base, head), head, base, lambda r: clone, load_listing(LISTING))
    assert plan.errors == [] and [f.clr_name for f in plan.files] == ["BH.oM.dKoP.ProjectIdentification"]
    planned = plan.files[0]
    assert planned.repo == "BHoM/dKoP_Toolkit" and planned.path == "dKoP_oM/AdministrativeInformation/ProjectIdentification.cs"
    original = (clone / planned.path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    added = [line for line in planned.text.splitlines() if line not in original.splitlines()]
    assert [line.strip() for line in added if line.strip()] == ["public virtual string ProjectNumber { get; set; } = \"\";"]
    assert tree_hash(clone / "dKoP_oM" / "AdministrativeInformation") == before
    assert os.path.exists(clone / planned.path)
