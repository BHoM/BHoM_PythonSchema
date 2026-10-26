"""Command line: python -m py2cs manifest | diff | plan | resolve"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from py2cs.diff import Diff, diff_manifests
from py2cs.model import dump_manifest, load_manifest
from py2cs.plan import make_plan
from py2cs.reader import read_package
from py2cs.report import render_report
from py2cs.resolve import ResolveError, load_listing, resolve_repo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="py2cs", description="Python to C# converter for the BHoM schema")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("manifest", help="read a bhom_schema folder into a manifest file")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("diff", help="what changed between two bhom_schema folders")
    p.add_argument("--base-root", required=True, type=Path)
    p.add_argument("--head-root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("plan", help="draft the C# files for a diff; never writes into the C# checkouts")
    p.add_argument("--base-root", required=True, type=Path)
    p.add_argument("--head-root", required=True, type=Path)
    p.add_argument("--clones-parent", type=Path, help="folder holding one checkout per repository, named after the repository")
    p.add_argument("--listing", type=Path, help="repository listing json; validates the repo of every class")
    p.add_argument("--python-pr", default="", help="reference of the Python pull request, for the report")
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("drafts", help="draft C# for every class of a bhom_schema folder (used by the round trip tests)")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("resolve", help="which repository owns each class")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--listing", type=Path)

    args = parser.parse_args(argv)

    if args.command == "manifest":
        dump_manifest(read_package(args.root), args.out)
        return 0

    if args.command == "diff":
        diff = diff_manifests(read_package(args.base_root), read_package(args.head_root))
        args.out.write_text(json.dumps(diff.to_json(), indent=2) + "\n", encoding="utf-8")
        print(f"{len(diff.changes)} changed types")
        return 0

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

        plan = make_plan(diff, head, base, clone_for, listing)
        args.out.mkdir(parents=True, exist_ok=True)
        for f in plan.files:
            target = args.out / f.repo.replace("/", "__") / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.text, encoding="utf-8", newline="\n")
        (args.out / "plan.json").write_text(json.dumps(plan.summary(), indent=2) + "\n", encoding="utf-8")
        (args.out / "report.md").write_text(render_report(plan, args.python_pr), encoding="utf-8")
        print(f"{len(plan.files)} files planned in {len(plan.repos())} repositories, {len(plan.errors)} problems")
        return 1 if plan.errors else 0

    if args.command == "drafts":
        from py2cs.csharp import emit_new

        manifest = read_package(args.root)
        if args.out.exists():
            import shutil
            shutil.rmtree(args.out)
        for info in manifest.values():
            target = args.out / Path(info.relative_path).with_suffix(".cs")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(emit_new(info, manifest), encoding="utf-8", newline="\n")
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
