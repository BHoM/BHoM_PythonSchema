# Speeding up the PR checks with a build cache: background

Status: the **plan** is in [Per-Repository-Build-Cache-Plan.md](Per-Repository-Build-Cache-Plan.md) (a build cache per repository, refreshed on `develop` when it
does not have the current state yet). This page keeps the measurements and what exists today. The cache that exists today is described in [Workflows.md](Workflows.md).

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
`JSONSchema_Toolkit` and `CSharpSchema_Test` is **not measured**.

## What exists today

`pr-checks.yml` caches `C:\ProgramData\BHoM\Assemblies` under one key made from the current `develop` commit of all four repositories. On a hit
it skips the clone and the build.

Two limits, which the per-repository plan addresses:

1. **One commit anywhere is a miss.** A new commit in any of the four repositories gives a new key, and everything is rebuilt, including `CSharpSchema_Test`,
   which the loop changes on purpose with every exercise.
2. **A PR's cache is only visible to that PR.** GitHub scopes a cache to the ref that saved it. A PR run can also read caches saved on its base branch,
   but `pr-checks.yml` never runs on `develop`, so nothing is saved there and the first run of every new PR misses.

## Decisions taken since the first version of this page

- A **full per-repository cache** is wanted, not a split into two groups: it works for any list of repositories. `BHoM` does not change that often, and when it does,
  everything is rebuilt anyway.
- A scheduled warm-up on `develop` is not wanted. `develop` is refreshed only when a PR run built something.
- Changing the BHoM installation on the development machine is acceptable for testing.
