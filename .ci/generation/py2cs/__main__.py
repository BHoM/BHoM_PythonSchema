"""Command line: python -m py2cs check | manifest | diff | align | repos | plan | pr | close | status | verify | drafts | resolve"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from py2cs.align import AlignError, align, changed_types, generate
from py2cs.check import check_package
from py2cs.ci import affected_repos, load_allowed, make_client, verify_package
from py2cs.csharp import emit_new
from py2cs.diff import diff_manifests
from py2cs.model import dump_manifest
from py2cs.patch import FilePatch, PatchResult, run_patcher
from py2cs.plan import Patcher, make_plan
from py2cs.pr import PythonPr, close_linked, raise_pr
from py2cs.status import update_status
from py2cs.reader import ReadErrors, read_package
from py2cs.report import render_report
from py2cs.resolve import ResolveError, load_listing, resolve_repo
from py2cs.github import GitHubError

def main(argv: list[str] | None = None) -> int:
    """Builds the argument parser with every command and its options, parses the arguments, runs them and turns failures into exit codes (1 for Python read errors, 2 for GitHub, alignment and value errors).

    It is the entry point of `python -m py2cs`, used by the workflows and the tests.
    """
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
    p.add_argument("--work", type=Path, help="folder for the generated Python (default: a temporary one)")

    p = sub.add_parser("repos", help="the repositories a Python change touches, as a json list (for the workflow matrix)")
    p.add_argument("--base-root", required=True, type=Path)
    p.add_argument("--head-root", required=True, type=Path)
    p.add_argument("--allowed-repos", type=Path, help="text file with the repositories C# pull requests may be raised in")

    p = sub.add_parser("plan", help="draft the C# files for a diff; never writes into the C# checkouts")
    p.add_argument("--base-root", required=True, type=Path)
    p.add_argument("--head-root", required=True, type=Path)
    p.add_argument("--clones-parent", type=Path, help="folder holding one checkout per repository, named after the repository")
    p.add_argument("--listing", type=Path, help="repository listing json; validates the repo of every class")
    p.add_argument("--python-pr", default="", help="reference of the Python pull request, for the report")
    p.add_argument("--patcher", type=Path, help="PythonSchemaGeneration.Patcher.dll, when not in its build folder")
    p.add_argument("--allowed-repos", type=Path, help="text file with the repositories C# pull requests may be raised in; others are errors")
    p.add_argument("--only-repo", help="plan only the classes of this repository (the linked-PR job has one checkout per repository)")
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("pr", help="push a plan to the C# repository and open or update the draft pull request")
    p.add_argument("--plan-dir", required=True, type=Path)
    p.add_argument("--repo", required=True, help="the C# repository, Owner/Name")
    p.add_argument("--python-repo", required=True, help="this repository, Owner/Name")
    p.add_argument("--python-pr", required=True, type=int)
    p.add_argument("--python-url", default="")
    p.add_argument("--token-env", default="PY2CS_CSHARP_TOKEN", help="environment variable with the token for the C# repository only")
    p.add_argument("--python-token-env", default="PY2CS_PYTHON_TOKEN", help="environment variable with the token that comments on the Python pull request")
    p.add_argument("--dry-run", action="store_true", help="write nothing; list what would be done (offline when there is no token)")

    p = sub.add_parser("close", help="when the Python PR is closed: close the linked C# draft (unmerged) or comment on it (merged)")
    p.add_argument("--repo", required=True)
    p.add_argument("--python-repo", required=True)
    p.add_argument("--python-pr", required=True, type=int)
    p.add_argument("--merged", action="store_true")
    p.add_argument("--token-env", default="PY2CS_CSHARP_TOKEN")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("status", help="set the commit status of a Python PR to whether its linked C# pull request is merged")
    p.add_argument("--python-repo", required=True)
    p.add_argument("--python-pr", required=True, type=int)
    p.add_argument("--sha", required=True, help="head commit of the Python pull request")
    p.add_argument("--no-csharp-change", action="store_true", help="the Python pull request needs no C# change: the status is success")
    p.add_argument("--repos-file", required=True, type=Path, help="text file with the repositories C# pull requests are raised in")
    p.add_argument("--token-env", default="PY2CS_PYTHON_TOKEN", help="environment variable with a token that can read the C# repositories and write statuses here")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("verify", help="every module of a generated package imports, and it reads back as the C# manifest says")
    p.add_argument("--package", required=True, type=Path)
    p.add_argument("--manifest", type=Path)

    p = sub.add_parser("drafts", help="draft C# for every class of a bhom_schema folder (used by the round trip tests)")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)

    p = sub.add_parser("resolve", help="which repository owns each class")
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--listing", type=Path)

    args = parser.parse_args(argv)
    try:
        return run(args)
    except ReadErrors as e:
        for error in e.errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"{len(e.errors)} problems in the Python files", file=sys.stderr)
        return 1
    # After ReadErrors, which is a ValueError too
    except (GitHubError, AlignError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

def run(args: argparse.Namespace) -> int:
    """Dispatcher of the commands: runs the command named in the arguments (check, manifest, diff, align, repos, plan, pr, close, status, verify, drafts or resolve), prints its result and returns the exit code.

    Each branch wires the py2cs modules together for one workflow step; unknown commands return 2.
    """
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
                generate(changed + removed, args.assemblies, output, args.generator)
                generated = read_package(output)

        result = align(base, head, generated)
        for problem in result.problems:
            print(f"difference: {problem}")
        print(f"{len(result.checked)} classes compared, {len(result.problems)} differences" + ("" if result.ok else " (first value: the C#, second: this PR)"))
        return 0 if result.ok else 1

    if args.command == "plan":
        base, head = read_package(args.base_root), read_package(args.head_root)
        diff = diff_manifests(base, head)
        listing = load_listing(args.listing) if args.listing else load_allowed(args.allowed_repos) if args.allowed_repos else None

        def clone_for(repo: str) -> Path | None:
            """Finds the local checkout of a C# repository under the clones folder, by the repository name and ignoring case, or returns None. Passed to `make_plan` by the `plan` command.
            """
            if args.clones_parent is None:
                return None
            path = args.clones_parent / repo.split("/")[-1]
            if path.is_dir():
                return path
            matches = [c for c in args.clones_parent.iterdir() if c.name.lower() == repo.split("/")[-1].lower()] if args.clones_parent.is_dir() else []
            return matches[0] if matches else None

        def patch_with(patches: list[FilePatch]) -> list[PatchResult]:
            """Runs the C# patcher with the dll path given on the command line. Passed to `make_plan` by the `plan` command when --patcher is set."""
            return run_patcher(patches, args.patcher)

        patcher: Patcher | None = patch_with if args.patcher else None
        plan = make_plan(diff, head, base, clone_for, listing, patcher, args.only_repo)
        args.out.mkdir(parents=True, exist_ok=True)
        for f in plan.files:
            target = args.out / f.repo.replace("/", "__") / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            # newline="" keeps the line endings of the existing file
            target.write_text(f.text, encoding="utf-8-sig" if f.bom else "utf-8", newline="")
        (args.out / "plan.json").write_text(json.dumps(plan.summary(), indent=2) + "\n", encoding="utf-8")
        (args.out / "report.md").write_text(render_report(plan, args.python_pr), encoding="utf-8")
        (args.out / "reports").mkdir(exist_ok=True)
        for repo in plan.repos():
            (args.out / "reports" / (repo.replace("/", "__") + ".md")).write_text(render_report(plan, args.python_pr, repo), encoding="utf-8")
        print(f"{len(plan.files)} files planned in {len(plan.repos())} repositories, {len(plan.errors)} problems")
        return 1 if plan.errors else 0

    if args.command == "repos":
        listing = load_allowed(args.allowed_repos) if args.allowed_repos else None
        repos, problems = affected_repos(read_package(args.base_root), read_package(args.head_root), listing)
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        print(json.dumps(repos))
        return 1 if problems else 0

    if args.command == "pr":
        client, offline = make_client(args.token_env, [args.repo] if args.dry_run else None)
        python_client = None if offline else make_client(args.python_token_env)[0] if os.environ.get(args.python_token_env) else None
        if offline:
            print("no token: offline dry run, nothing is read from or written to GitHub")
        python_pr = PythonPr(args.python_repo, args.python_pr, args.python_url)
        outcome = raise_pr(client, args.plan_dir, args.repo, python_pr, args.dry_run, python_client)
        for action in outcome.actions:
            print(("would " if args.dry_run else "") + str(action))
        if outcome.pull_request is not None:
            print(f"pull request: {outcome.pull_request.url}")
        return 0

    if args.command == "close":
        client, offline = make_client(args.token_env, [args.repo] if args.dry_run else None)
        outcome = close_linked(client, args.repo, PythonPr(args.python_repo, args.python_pr), args.merged, args.dry_run)
        for action in outcome.actions:
            print(("would " if args.dry_run else "") + str(action))
        return 0

    if args.command == "status":
        repos = list(load_allowed(args.repos_file))
        client, offline = make_client(args.token_env, repos if args.dry_run else None)
        if offline:
            print("no token: offline dry run, nothing is read from or written to GitHub")
        status = update_status(client, client, repos, args.python_repo, args.python_pr, args.sha, args.dry_run, args.no_csharp_change)
        if status is None:
            print(f"{args.python_repo}#{args.python_pr} has no linked C# pull request: no status")
        else:
            print(("would set " if args.dry_run else "set ") + f"the status {status.state}: {status.description}")
        return 0

    if args.command == "verify":
        count, problems = verify_package(args.package, args.manifest)
        for problem in problems:
            print(f"error: {problem}")
        print(f"{count} modules imported, {len(problems)} problems")
        return 1 if problems else 0

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
