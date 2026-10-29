# GitHub workflows

Four workflows run the loop between this repository and the repository that owns the C# classes, and make releases. For now that repository is
[BHoM/CSharpSchema_Test](https://github.com/BHoM/CSharpSchema_Test), a repository made for testing. **No other repository is ever
written to.** BHoM, BHoM_Engine and JSONSchema_Toolkit are only cloned and built (read only) because the generator needs them.

| Workflow | When | What it does |
|---|---|---|
| [python-schema-generation.yml](../.github/workflows/python-schema-generation.yml) | Every Saturday at 4 AM UTC, and by hand | Clones and builds the C# repositories, generates `src/bhom_schema` from the C#, checks it, and commits it straight to `develop`. Not a pull request. If a check fails, nothing is committed |
| [pr-checks.yml](../.github/workflows/pr-checks.yml) | Every pull request to `develop` | Builds the same repositories (`Included-repositories.txt`), clones BHoM_JSONSchema read only as the test oracle for the JSON, then runs `run-all.ps1` (build, NUnit, pytest, Pyright). For a PR that changes `src/bhom_schema` it also runs `py2cs check` and `py2cs align` |
| [linked-csharp-pr.yml](../.github/workflows/linked-csharp-pr.yml) | A pull request that changes `src/bhom_schema`, every hour, and by hand | Raises, updates or closes a linked **draft** pull request in the C# repository, and sets the commit status `linked C# pull request` on the Python PR |
| [release.yml](../.github/workflows/release.yml) | By hand only (dry run by default) | Regenerates with `--release X.Y`, checks, builds the wheel and the release notes; when not a dry run, pushes branch `vX.Y` and tag `vX.Y.0`, creates the GitHub Release and publishes to TestPyPI. See "Making a release" |

## How they fit together

```
 C# repositories (BHoM, BHoM_Engine, JSONSchema_Toolkit: read only; CSharpSchema_Test: the repository that owns the converted classes)
       │                                                            ▲
       │ cloned + built                                             │ draft PR "python-schema/pr-<N>"
       ▼                                                            │
┌──────────────────────────────┐   commit straight to develop   ┌───┴───────────────────────┐
│ python-schema-generation.yml │ ─────────────────────────────► │      linked-csharp-pr.yml │
│ Saturday 4 AM UTC, or manual │                                │ (see below)               │
│ C# ──► src/bhom_schema       │                                └───────────────────────────┘
└──────────────┬───────────────┘
               │ develop (regenerated every week)
               ▼
   a person changes src/bhom_schema on a branch and opens a pull request to develop
               │
               ├────────────────────────────────────────────┐
               ▼                                            ▼
┌──────────────────────────────┐              ┌─────────────────────────────────────────────────┐
│ pr-checks.yml                │              │ linked-csharp-pr.yml                            │
│ on every PR to develop       │              │ on a PR that changes src/bhom_schema            │
│ build, NUnit, pytest,        │              │                                                 │
│ Pyright; py2cs check + align │              │ prepare ─► repos ─► raise ─► status             │
│ (writes nothing)             │              │                    (draft C# PR, and the commit │
└──────────────────────────────┘              │                     status on the Python PR)    │
                                              │ PR closed: prepare ─► repos ─► close            │
                                              │ every hour: sweep (refreshes the status of      │
                                              │             every open Python PR)               │
                                              └─────────────────────┬───────────────────────────┘
                                                                    │ the C# draft is reviewed and merged in C#
                                                                    ▼
                                                  next weekly generation: the C# is the source of truth,
                                                  so src/bhom_schema ends up matching the merged C#

 End of a milestone, by hand:
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ release.yml  (input X.Y, dry run by default)                                                         │
│ job build:  clone + build ─► generate --release X.Y ─► verify + Pyright ─► wheel + notes             │
│             not a dry run: branch vX.Y, tag vX.Y.0, GitHub Release (wheel + notes)                   │
│ job publish-testpypi (not a dry run): the wheel ─► TestPyPI, by trusted publishing                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Order in one line: **generation** (weekly) → a Python **pull request** → **pr-checks** and **linked-csharp-pr** run side by side → the C#
draft is merged → the next **generation** brings the Python back in line → **release** (by hand) freezes it as `vX.Y`.

## What each one reads and writes

| | Reads | Writes |
|---|---|---|
| Generation | `Included-repositories.txt` (what to build), `Converted-repositories.txt` (what to convert), `.ci/generation/warnings-baseline.txt` | `src/bhom_schema` on `develop` |
| PR checks | the same | nothing |
| Linked C# PR | `Converted-repositories.txt` | a branch `python-schema/pr-<N>` and a draft PR in the C# repository, and one comment on the Python PR |

`Converted-repositories.txt` is also the list of repositories a C# pull request may be raised in. A Python class names its own
repository (`__bhom__["repo"]`), so without that list a pull request could aim at any repository the GitHub App can reach. To add
a repository to the loop, add it to both text files (`Included-repositories.txt` so it is built, `Converted-repositories.txt` so it
is converted), and install the App on it.

## One-time setup

Someone with admin rights on the organisation does this once.

1. **A GitHub App** that can push a branch and open pull requests. Permissions: *Contents: read and write*, *Pull requests: read and
   write*, *Metadata: read*. Install it on **BHoM_PythonSchema and CSharpSchema_Test only**. A repository outside the installation
   cannot get a token, so the App cannot write to it.
2. **Credentials** in this repository (Settings, Secrets and variables, Actions): variable `BHOM_APP_ID` and secret
   `BHOM_APP_PRIVATE_KEY` (the whole `.pem` text). If the App already exists for other workflows, reuse its names.
3. **`develop` must accept the weekly commit.** The generation pushes to `develop` with the workflow's own token. If `develop` is
   protected and requires pull requests, allow `github-actions[bot]` (or the App) to bypass that rule.
4. **Actions** are enabled, and the default workflow permissions can stay read-only: each workflow asks for what it needs.

## Running things

The weekly generation can be run by hand from the Actions tab (*Run workflow*). With `dry_run` ticked it generates and checks but
does not commit; the generation report is attached to the run.

The linked pull request can be tried without writing anything:

1. **On a laptop.** In a scratch copy of `src/bhom_schema`, change a class, then (with the C# repository cloned next to this one):

   ```powershell
   $env:PYTHONPATH = ".ci/generation"
   $env:PY2CS_PATCHER = ".ci/generation/PythonSchemaGeneration.Patcher/bin/Release/net8.0/PythonSchemaGeneration.Patcher.dll"
   .venv\Scripts\python -m py2cs plan --base-root <before>/bhom_schema --head-root <after>/bhom_schema --clones-parent C:\Github --allowed-repos Converted-repositories.txt --only-repo BHoM/CSharpSchema_Test --python-pr BHoM/BHoM_PythonSchema#7 --out plan
   .venv\Scripts\python -m py2cs pr --plan-dir plan --repo BHoM/CSharpSchema_Test --python-repo BHoM/BHoM_PythonSchema --python-pr 7 --dry-run
   ```

   Without a token the dry run is offline: it prints the branch, the files, the PR title and the labels, and never calls GitHub. It
   does not write into the clone.
2. **On GitHub, dry run.** Open a Python PR, then run *Linked C# pull request* with its number and `dry_run` ticked (the default). It
   makes the App token for `CSharpSchema_Test` only, which proves the installation and permissions, and prints what it would do.
3. **On GitHub, live.** Run it again with `dry_run` unticked. It pushes `python-schema/pr-<N>` to CSharpSchema_Test and opens a draft
   PR. Run it once more to see that it updates the same branch and PR. When the Python PR is closed without merging, the workflow
   closes the draft with a comment; delete the branch by hand.

## Making a release

Run *Release* from the Actions tab at the end of a milestone, with the BHoM version as `Major.Minor` (for example `10.0`). It is a dry run
by default: it builds the C# repositories, regenerates with `--release 10.0`, checks the result, builds the wheel and writes the release notes,
and attaches them to the run. The generator stops the run when `10.0` is not the assembly version it read from `BHoM.dll` (or from another assembly when that is missing). Untick `dry_run` to:

1. commit the regenerated classes to a new branch `v10.0` and tag `v10.0.0` (a release is never made twice; an existing branch or tag stops the run);
2. create a GitHub Release with the wheel and the release notes (`python -m py2cs notes`: the breaking changes first, then the added, removed and changed classes);
3. publish the wheel to TestPyPI.

TestPyPI is reached with trusted publishing, so no password or token is stored. Set it up once, by an administrator:

- On test.pypi.org, add a pending publisher for the project `bhom-schema` with this repository, the workflow `release.yml` and the environment `testpypi`.
- In the repository settings, create the environment `testpypi` (it can require a reviewer).

Real PyPI is added the same way when BHoM/BHoM is in scope. The branch `v10.0` is left alone afterwards.

## The linked pull request status

Nothing tells this repository when a C# pull request is merged, so `linked-csharp-pr.yml` also sets a commit status on the Python PR
and refreshes it every hour:

| Status | Meaning |
|---|---|
| pending | the C# draft is open: waiting for it to be merged |
| success | the C# pull request is merged (or the Python change needs no C# change) |
| failure | the C# pull request was closed without merging: change the Python, or close it |

To stop a Python PR being merged before its C# PR, make the status `linked C# pull request` a **required check** on `develop`
(Settings, Branches). The hourly run only reads the C# repositories with this repository's own token, so they must be public. A
Python PR with no linked draft gets no status from the hourly run.

## The alignment check

`pr-checks.yml` runs `py2cs align` for a PR that changes `src/bhom_schema`. It generates the Python for the changed classes from
the C# `develop` branches it has just built, and compares it with the PR. So it fails until the linked C# PR is merged, which is the
rule: a Python PR is a proposal and is only merged after its C# PR. After the C# PR is merged, re-run the workflow.

## Safety

- The App token is made for one repository at a time and passed only to the step that needs it, through the environment. It is never
  printed, and error messages never contain it.
- The tooling that holds the token (`py2cs` and the patcher) is taken from the **base** branch, so a pull request cannot change the
  code that runs with the token.
- A pull request from a fork gets no linked pull request, because forks never receive the secrets.
- The linked-PR workflow has no `push` trigger, so the weekly generation commit can never start it.
- `.ci/generation/warnings-baseline.txt` lists the known kinds of generator warning. A new kind fails the weekly run, which means a
  change in BHoM that the generator does not handle yet. Review it, then update the baseline with `--write-baseline`.
