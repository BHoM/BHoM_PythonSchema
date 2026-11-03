# GitHub workflows

These workflows run the loop between this repository and the repository that owns the C# classes, and make releases. For now that repository is
[BHoM/CSharpSchema_Test](https://github.com/BHoM/CSharpSchema_Test), a repository made for testing. **No other repository is ever
written to.** BHoM, BHoM_Engine and JSONSchema_Toolkit are only cloned and built (read only) because the generator needs them.

| Workflow | When | What it does |
|---|---|---|
| [python-schema-generation.yml](../.github/workflows/python-schema-generation.yml) | Every Saturday at 4 AM UTC, and by hand | Clones and builds the C# repositories, generates `src/bhom_schema` from the C#, checks it, and commits it straight to `develop`. Not a pull request. If a check fails, nothing is committed |
| [pr-checks.yml](../.github/workflows/pr-checks.yml) | Every pull request to `develop` | Two jobs. **Build and tests**: installs the built assemblies of the repositories in `Included-repositories.txt` (the shared action `.github/actions/bhom-assemblies` keeps a build cache with one entry per repository, keyed by its commit, its dependencies' keys and the build tools, so only a changed repository and what depends on it are rebuilt), clones BHoM_JSONSchema read only as the test oracle for the JSON, runs `run-all.ps1` (build, NUnit, pytest, Pyright) and, for a PR that changes `src/bhom_schema`, `py2cs check`. **C# alignment (fails until the linked C# PR is merged)**: after the first job (so a changed C# repository is built once), and even when its tests fail; for such a PR, builds the generator and runs `py2cs align`; when it fails it explains in the job summary that the linked C# pull request has to be merged first, then the job re-run |
| [build-cache.yml](../.github/workflows/build-cache.yml) | After every run of `pr-checks.yml` from this repository, and by hand on `develop` | A cache saved by a pull request is only visible to that pull request. **Does develop need a refresh?** (ubuntu, a few seconds) plans the build and looks for the current state among the caches of `develop`. When it is missing, **Build and save on develop** clones and builds the changed repositories from `develop`, never from the pull request, and saves the cache where every pull request can read it |
| [linked-csharp-pr.yml](../.github/workflows/linked-csharp-pr.yml) | A pull request that changes `src/bhom_schema`, and by hand | One job, **Raise or update draft**: finds the C# repositories the change touches, raises or updates a linked **draft** pull request in each, and comments on the Python PR with its link. The shared action `.github/actions/linked-pr-context` does the finding |
| [linked-csharp-pr-close.yml](../.github/workflows/linked-csharp-pr-close.yml) | A Python pull request that changes `src/bhom_schema` is closed, and by hand | Closes the linked C# draft with a comment when the Python PR was closed unmerged, or only comments when it was merged. A separate workflow so that nothing of it shows on an open pull request |
| [release.yml](../.github/workflows/release.yml) | By hand only (dry run by default) | Regenerates with `--release X.Y`, checks, builds the wheel and the release notes; when not a dry run, pushes branch `vX.Y` and tag `vX.Y.0`, creates the GitHub Release and publishes to TestPyPI. See "Making a release" |
| [alpha-release.yml](../.github/workflows/alpha-release.yml) | Every day at 6 AM UTC, and by hand (dry run by default) | Publishes `develop` as it is, as the pre-release `X.Y.0aYYMMDDHHmm`, to TestPyPI. No C# build. Skipped when `develop` has not moved since the last alpha. See "Making an alpha release" |

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
│ Pyright; py2cs check;        │              │ one job: raise or update the draft, and add     │
│ C# alignment (own job,       │              │ a comment on the Python PR with its link        │
│ after the tests)             │              │                                                 │
│ writes only the build cache  │              │ PR closed:  linked-csharp-pr-close.yml          │
│ of its own PR                │              │                                                 │
└──────────────┬───────────────┘              │                                                 │
               │ when the run completes       │                                                 │
               ▼                              └─────────────────────┬───────────────────────────┘
┌──────────────────────────────┐                                    │ the C# draft is reviewed and merged in C#
│ build-cache.yml              │                                    ▼
│ gate (ubuntu): is the        │                  next weekly generation: the C# is the source of truth,
│ current state on develop?    │                  so src/bhom_schema ends up matching the merged C#
│ if not, refresh (windows):   │
│ build from develop and save  │
│ the cache on develop, where  │
│ every PR can read it         │
└──────────────────────────────┘

 Every day:
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ alpha-release.yml   develop moved since tag alpha-latest? ─► stamp X.Y.0aYYMMDDHHmm ─► pytest,       │
│                     Pyright ─► wheel ─► TestPyPI (trusted publishing) ─► move tag alpha-latest       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

 End of a milestone, by hand:
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ release.yml  (input X.Y, dry run by default)                                                         │
│ job build:  clone + build ─► generate --release X.Y ─► verify + Pyright ─► wheel + notes             │
│             not a dry run: branch vX.Y, tag vX.Y.0, GitHub Release (wheel + notes)                   │
│ job publish-testpypi (not a dry run): the wheel ─► TestPyPI, by trusted publishing                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Order in one line: **generation** (weekly) → a Python **pull request** → **pr-checks** and **linked-csharp-pr** run side by side → the C#
draft is merged → the next **generation** brings the Python back in line → **release** (by hand) freezes it as `vX.Y`. After each
**pr-checks** run, **build-cache** saves the built C# repositories on `develop` when they changed, so the next pull request does not build them.

## What each one reads and writes

| | Reads | Writes |
|---|---|---|
| Generation | `Included-repositories.txt` (what to build), `Converted-repositories.txt` (what to convert), `.ci/generation/warnings-baseline.txt` | `src/bhom_schema` on `develop` |
| PR checks | the same, and the build cache of its pull request or of `develop` | the build cache of its own pull request, which no other pull request sees |
| Build cache | `Included-repositories.txt`, the `dependencies.txt` of each C# repository, and the caches of `develop` | the build cache on `develop` |
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
2. **Credentials** in this repository (Settings, Secrets and variables, Actions): secrets `BHOM_APP_ID` and
   `BHOM_APP_PRIVATE_KEY` (the whole `.pem` text). The organisation may already hold both under these names for other workflows; a repository secret overrides it.
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
2. **On GitHub, dry run.** Open a Python PR, then run *C# PR* with its number and `dry_run` ticked (the default). It
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

**Right after a release, bump the BHoM version on `develop`** to the next `Major.Minor`. The next weekly generation then writes it into `_version.py`. Until then
the alpha workflow fails on purpose: an alpha of `10.0` would sort below the release `10.0.0`, so `--pre` users would be served the old release.

## Making an alpha release

Alphas are made by `alpha-release.yml` every day at 6 AM UTC (after the Saturday generation has pushed), so nothing is done by hand. Python users install the
latest alpha with `pip install --pre bhom-schema`; without `--pre` they get the release. pip has no `--alpha` option.

- **Source.** `develop` as it is. Nothing is regenerated and no C# is built; `develop` is regenerated weekly and takes pull requests in between.
- **Version.** `python -m py2cs alpha-version` takes the BHoM version from `_version.py` and adds the UTC time: `10.1.0a2611031430`. Several alphas a day are fine, they order by time.
  The version is stamped in the runner's checkout only and never committed, so `develop` keeps `10.1.0.dev0`. It fails when the tag `v10.1.0` already exists (see the bump above).
- **Skip.** The tag `alpha-latest` points at the commit of the last published alpha. When `develop` is still there, the run does nothing, unless *force* is ticked.
- **Checks.** Every module imports, the tests that need no C# assemblies, Pyright, and the wheel carries the stamped version.
- **Publish.** The wheel goes to TestPyPI with trusted publishing, through the environment `testpypi-alpha`; then `alpha-latest` moves to the published commit. There is no GitHub Release and no tag per alpha.

Run it by hand from the Actions tab with `dry_run` ticked (the default) to check and build without publishing, or unticked to publish a merge at once.
It shares one concurrency group with the weekly generation and the release, so it never packages a half-pushed `develop`.

TestPyPI is set up once, by an administrator, for both the release and the alpha. On the repository, create the environments `testpypi` and `testpypi-alpha`
(Settings, Environments). On test.pypi.org, sign in with two-factor authentication, open *Your account*, *Publishing*, and add two pending publishers for the project
`bhom-schema`, owner `BHoM`, repository `BHoM_PythonSchema`: workflow `release.yml` with environment `testpypi`, and workflow `alpha-release.yml` with environment `testpypi-alpha`.
A publisher is bound to one workflow file, so both are needed. After the first upload, check that both are listed under the project's *Publishing* and add the other maintainers as owners.

## When is a Python pull request ready?

A Python PR is a proposal: it is ready once its linked C# pull request is merged. The **C# alignment** job of `pr-checks.yml` is the check for
that. It fails until the Python equals what the C# `develop` generates, and passes after. Nothing tells this repository when a C# PR is merged,
so after the merge **re-run that job by hand** (Re-run jobs on the PR page). The comment that `linked-csharp-pr.yml` leaves on the Python PR links
the C# draft. To stop a Python PR being merged first, make **PR / C# alignment** a required check on `develop` (Settings, Branches).

## The alignment check

`pr-checks.yml` runs `py2cs align` for a PR that changes `src/bhom_schema`. It generates the Python for the changed classes from
the C# `develop` branches it has just built, and compares it with the PR. So it fails until the linked C# PR is merged, which is the
rule: a Python PR is a proposal and is only merged after its C# PR. After the C# PR is merged, re-run the workflow.

## Safety

- The App token is made for one repository at a time and passed only to the step that needs it, through the environment. It is never
  printed, and error messages never contain it.
- The tooling (`py2cs` and the patcher) is taken from the **pull request**, so a fix to it works on the same pull request. That means
  anybody who can push a branch to this repository can run code with the App token, which they could already do by editing the workflow
  file itself; forks get nothing. What keeps this safe is the repository's own access: only trusted people have write access, the App
  token is made for one repository at a time, and the `develop` branch of every C# repository is protected, so the App can open pull requests
  but not push to `develop` (see "Protect the develop branch of the C# repository" in [Testing-On-GitHub.md](Testing-On-GitHub.md)).
  The Python before the change, and the list of repositories a C# pull request may be raised in, still come from the base branch.
- A pull request from a fork gets no linked pull request, because forks never receive the secrets.
- The linked-PR workflow has no `push` trigger, so the weekly generation commit can never start it.
- `.ci/generation/warnings-baseline.txt` lists the known kinds of generator warning. A new kind fails the weekly run, which means a
  change in BHoM that the generator does not handle yet. Review it, then update the baseline with `--write-baseline`.
