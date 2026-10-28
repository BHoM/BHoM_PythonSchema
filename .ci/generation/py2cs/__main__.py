"""Command line: python -m py2cs check | manifest | diff | align | plan | drafts | resolve"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from py2cs.align import AlignError, align, changed_types, generate
from py2cs.check import check_package
from py2cs.csharp import emit_new
from py2cs.diff import diff_manifests
from py2cs.model import dump_manifest
from py2cs.patch import FilePatch, PatchResult, run_patcher
from py2cs.plan import Patcher, make_plan
from py2cs.reader import ReadErrors, read_package
from py2cs.report import render_report
from py2cs.resolve import ResolveError, load_listing, resolve_repo

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="py2cs", description="Python to C# converter for the BHoM schema")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="read a bhom_schema folder strictly and list every problem; drafts nothing")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--base-root", type=Path, help="the folder before the change; new classes and fields are then checked for descriptions")

    p = sub.add_parser("manifest", help="read a bhom_schema folder into a manifest file")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("diff", help="what changed between two bhom_schema folders")
    p.add_argument("--base-root", required=True, type=Path)
    p.add_argument("--head-root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("align", help="compare the changed classes of a Python PR with the Python generated from the merged C#")
    p.add_argument("--base-root", required=True, type=Path)
    p.add_argument("--head-root", required=True, type=Path)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--assemblies", type=Path, help="folder with the built oM dlls of the merged C#; the generator is run for the changed classes")
    source.add_argument("--generated-root", type=Path, help="a bhom_schema folder that was already generated from the merged C#")
    p.add_argument("--generator", type=Path, help="PythonSchemaGeneration.dll, when not in its build folder")
    p.add_argument("--org", help="organisations whose assemblies are read, for example BHoM,BuroHappoldEngineering (default: BHoM)")
    p.add_argument("--work", type=Path, help="folder for the generated Python (default: a temporary one)")

    p = sub.add_parser("plan", help="draft the C# files for a diff; never writes into the C# checkouts")
    p.add_argument("--base-root", required=True, type=Path)
    p.add_argument("--head-root", required=True, type=Path)
    p.add_argument("--clones-parent", type=Path, help="folder holding one checkout per repository, named after the repository")
    p.add_argument("--listing", type=Path, help="repository listing json; validates the repo of every class")
    p.add_argument("--python-pr", default="", help="reference of the Python pull request, for the report")
    p.add_argument("--patcher", type=Path, help="PythonSchemaGeneration.Patcher.dll, when not in its build folder")
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("drafts", help="draft C# for every class of a bhom_schema folder (used by the round trip tests)")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("resolve", help="which repository owns each class")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--listing", type=Path)

    args = parser.parse_args(argv)
    try:
        return run(args)
    except AlignError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ReadErrors as e:
        for error in e.errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"{len(e.errors)} problems in the Python files", file=sys.stderr)
        return 1

def run(args: argparse.Namespace) -> int:
    if args.command == "check":
        result = check_package(args.root, args.base_root)
        for error in result.errors:
            print(f"error: {error}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        print(f"{len(result.errors)} errors, {len(result.warnings)} warnings")
        return 1 if result.errors else 0

    if args.command == "manifest":
        dump_manifest(read_package(args.root), args.out)
        return 0

    if args.command == "diff":
        diff = diff_manifests(read_package(args.base_root), read_package(args.head_root))
        args.out.write_text(json.dumps(diff.to_json(), indent=2) + "\n", encoding="utf-8")
        print(f"{len(diff.changes)} changed types")
        return 0

    if args.command == "align":
        base, head = read_package(args.base_root), read_package(args.head_root)
        changed, removed = changed_types(base, head)
        if not changed and not removed:
            print("no changed classes, nothing to compare")
            return 0

        if args.generated_root is not None:
            generated = read_package(args.generated_root)
        else:
            with tempfile.TemporaryDirectory() as scratch:
                output = (args.work or Path(scratch)) / "bhom_schema"
                if output.exists():
                    shutil.rmtree(output)
                generate(changed + removed, args.assemblies, output, args.generator, args.org)
                generated = read_package(output)

        result = align(base, head, generated)
        for problem in result.problems:
            print(f"difference: {problem}")
        print(f"{len(result.checked)} classes compared, {len(result.problems)} differences" + ("" if result.ok else " (first value: the C#, second: this PR)"))
        return 0 if result.ok else 1

    if args.command == "plan":
        base, head = read_package(args.base_root), read_package(args.head_root)
        diff = diff_manifests(base, head)
        listing = load_listing(args.listing) if args.listing else None

        def clone_for(repo: str) -> Path | None:
            if args.clones_parent is None:
                return None
            path = args.clones_parent / repo.split("/")[-1]
            if path.is_dir():
                return path
            matches = [c for c in args.clones_parent.iterdir() if c.name.lower() == repo.split("/")[-1].lower()] if args.clones_parent.is_dir() else []
            return matches[0] if matches else None

        def patch_with(patches: list[FilePatch]) -> list[PatchResult]:
            return run_patcher(patches, args.patcher)

        patcher: Patcher | None = patch_with if args.patcher else None
        plan = make_plan(diff, head, base, clone_for, listing, patcher)
        args.out.mkdir(parents=True, exist_ok=True)
        for f in plan.files:
            target = args.out / f.repo.replace("/", "__") / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            # newline="" keeps the line endings of the existing file
            target.write_text(f.text, encoding="utf-8-sig" if f.bom else "utf-8", newline="")
        (args.out / "plan.json").write_text(json.dumps(plan.summary(), indent=2) + "\n", encoding="utf-8")
        (args.out / "report.md").write_text(render_report(plan, args.python_pr), encoding="utf-8")
        print(f"{len(plan.files)} files planned in {len(plan.repos())} repositories, {len(plan.errors)} problems")
        return 1 if plan.errors else 0

    if args.command == "drafts":
        manifest = read_package(args.root)
        if args.out.exists():
            shutil.rmtree(args.out)
        for info in manifest.values():
            target = args.out / Path(info.relative_path).with_suffix(".cs")
            target.parent.mkdir(parents=True, exist_ok=True)
            # The generated types keep their C# shape: fields without a default come from immutable types
            target.write_text(emit_new(info, manifest, read_only_required=True), encoding="utf-8", newline="\n")
        print(f"{len(manifest)} drafts written")
        return 0

    if args.command == "resolve":
        listing = load_listing(args.listing) if args.listing else None
        status = 0
        for clr_name, info in sorted(read_package(args.root).items()):
            try:
                resolution = resolve_repo(info, listing)
                print(f"{clr_name}\t{resolution.repo}\t{resolution.source}")
            except ResolveError as e:
                print(f"{clr_name}\tERROR\t{e}")
                status = 1
        return status

    return 2

if __name__ == "__main__":
    sys.exit(main())
