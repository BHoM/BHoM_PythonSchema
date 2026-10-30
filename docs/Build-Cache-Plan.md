# Speeding up the PR checks with a build cache (for later)

Status: **not implemented**. This records what we learned and what to do if the PR checks need to be faster. The cache that exists today is
described in [Workflows.md](Workflows.md).

## Where the time goes

`pr-checks.yml` takes about 2m 46s. The slow part is building the C# repositories (`Included-repositories.txt`) on every run:

| Step | Time |
|---|---|
| Build the repositories in dependency order | 1m 02s |
| Build and test (`run-all.ps1`) | 36s |
| Clone the repositories | 13s |
| Create the virtual environment | 16s (now cached with pip) |
| setup-dotnet | 24s (removed) |

The log of the build step shows `BHoM` alone restoring about 30 projects (`Geometry_oM`, `Structure_oM`, and so on) before compiling
`BHoM.dll`. The log we have stops there and has no per-repository timings, so how the minute splits between `BHoM`, `BHoM_Engine`,
`JSONSchema_Toolkit` and `CSharpSchema_Test` is **not measured**. `BHoM` is probably most of it.

## What exists today

`pr-checks.yml` caches `C:\ProgramData\BHoM\Assemblies` under one key made from the current `develop` commit of all four repositories. On a hit
it skips the clone and the build.

Two limits:

1. **One commit anywhere is a miss.** A new commit in any of the four repositories gives a new key, and everything is rebuilt. That includes
   `CSharpSchema_Test`, which the loop changes on purpose with every exercise, although it is small and nothing depends on it.
2. **A PR's cache is only visible to that PR.** GitHub scopes a cache to the ref that saved it, and a PR run can also read caches saved on its base
   branch. `pr-checks.yml` never runs on `develop`, so nothing is saved there and the first run of every new PR misses.

## A cache per repository

The idea is to cache each repository's build separately, so that a change in `BHoM_Engine` rebuilds one repository, not four.

This needs a dependency rule. A repository is compiled against the assemblies of the ones it depends on (`dependencies.txt`), so its key must
contain its own commit **and** the keys of everything it depends on:

| What changes | What must be rebuilt |
|---|---|
| `CSharpSchema_Test` | only itself |
| `JSONSchema_Toolkit` | only itself |
| `BHoM_Engine` | itself and `JSONSchema_Toolkit` |
| `BHoM` | all four |

`BHoM` is the biggest repository and changes most often, and any change there rebuilds everything. A full per-repository cache therefore helps less
than it first appears. It would also need real work in `Build-Repositories.ps1`: snapshot what each build adds to `%ProgramData%\BHoM`, zip it
per repository under its key, restore in dependency order, and clone only the repositories that must be rebuilt. It cannot be tested locally without
changing the BHoM installation on the machine, because the repositories' post-build step copies into `%ProgramData%`.

## Recommendation: two groups

Split the cache in two and leave the rest alone:

1. **Upstream group** (`BHoM`, `BHoM_Engine`, `JSONSchema_Toolkit`): cached together, keyed by their three commits. This is the slow part and
   it changes least.
2. **`CSharpSchema_Test`**: not cached. It is built on top of the restored assemblies on every run. It is a leaf repository that is small and is the
   one the loop changes, so a merge there no longer invalidates the cache.

How to do it:

- Make a second list file containing only `BHoM/CSharpSchema_Test` (for example `Leaf-repositories.txt`), and make the upstream list the other three.
  `Build-Repositories.ps1` orders only among the listed repositories, so building the leaf list uses what is already installed. The generation and
  release workflows can keep building from `Included-repositories.txt`.
- In `pr-checks.yml`, compute the cache key from the upstream list only, restore, build the upstream list on a miss and save, then always clone and
  build the leaf list.
- Keep the key's version prefix (`bhom-assemblies-v1-`) so the cache can be reset by changing it.

## Warm-up on `develop`

To make the first run of a new PR hit, add a workflow that runs on `develop` (on a schedule such as daily, and by hand) and does only the
restore, build and save steps with the same key logic. A PR can restore caches saved on `develop`.

- It hits only while none of the cached repositories has moved since the last warm-up. `BHoM` changes often, so expect partial hit rates.
- GitHub deletes caches unused for 7 days and limits a repository to 10 GB. The assemblies folder should be far below that.
- A restore from an older key (a prefix fallback with `restore-keys`) would give hits more often, but would restore assemblies built from other
  commits and rebuild on top of them. Do not do that without a check that the result equals a clean build.

## Before doing any of this

1. Get per-repository build times from a run (a `Building <name>...` line is printed for each, but the log needs timestamps; step timing can be
   switched on in the run's log settings). If `BHoM` is nearly all of the minute, the two-group split gains little for ordinary PRs and the warm-up is
   the better investment. If `CSharpSchema_Test` takes a noticeable part, the split pays off on every loop exercise.
2. Check how often `BHoM` really changes in a week, since that sets the hit rate of any cache.
3. Check the first run after a change: a cache saved by the run itself never shows a saving on that run. Compare the second run.
