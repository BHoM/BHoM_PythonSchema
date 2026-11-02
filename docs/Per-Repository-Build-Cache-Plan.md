# Plan: a build cache per repository

Status: **implemented**, except the later step 7 (generation). It replaces the "two groups" recommendation of [Build-Cache-Plan.md](Build-Cache-Plan.md), which stays as the
background (where the time goes, what exists today).

## Goal

Rebuild only the C# repositories whose own commit, or whose dependencies' commits, changed since the last build. It must work for any list in
`Included-repositories.txt`, not just today's four, so adding `BHoM/BHoM` or a toolkit needs no change to the cache.

It is adopted in steps (see "Where it is used"): `pr-checks.yml` first, `python-schema-generation.yml` once the cache has proved itself, and
`release.yml` keeps a clean build.

## What we corrected from the earlier notes

| Earlier note | Now |
|---|---|
| "`BHoM` changes most often, so a per-repository cache helps little" | `BHoM` does not change that often. When it does, everything is rebuilt (as today). In between, a change in a dependent repository rebuilds only that repository and what depends on it |
| "It cannot be tested locally without changing the BHoM installation" | Changing the installation on the development machine is acceptable, so the scripts can be tested for real. Note that some projects write to a fixed `C:\ProgramData\BHoM\Assemblies` (for example `BHoM_Engine`), so redirecting `%ProgramData%` would not isolate a test |
| "Add a warm-up workflow on `develop`" | Not as a schedule. A refresh runs on `develop` only when `develop` does not have the current state (see "Refreshing `develop`") |
| "The last PR that builds updates the cache and the next PR uses it" | GitHub scopes a cache to the ref that saved it: a PR can read its own caches and those of its base branch (`develop`), but not another PR's. A cache saved by a PR run is therefore invisible to the next PR. That is why a run on `develop` is needed to share it |

## What we know about the builds

- A repository's build installs its assemblies into `C:\ProgramData\BHoM\Assemblies` through a post-build `xcopy`, and creates the empty folders
  `Datasets`, `Upgrades`, `Settings` and `Developer` next to it. `BHoM_Engine` also copies `DeepCloner.dll`.
- Later repositories read the earlier ones' assemblies from there (`HintPath` `$(ProgramData)\BHoM\Assemblies\...`). That is the dependency that matters.
- The dependencies are listed in each repository's `dependencies.txt`, one `Owner/Name` per line: `BHoM` has none, `BHoM_Engine` lists `BHoM`,
  `JSONSchema_Toolkit` lists `BHoM` and `BHoM_Engine`. `Build-Repositories.ps1` already orders the build with them, among the listed repositories only.
- Nothing after the build reads the C# sources in `.repos`: the generator and the tests use the installed assemblies, and the generation commit
  message uses `.repos/commits.txt`. So a repository that is restored from the cache does not need to be cloned.
- All assemblies on the development machine are 145 MB in 567 files. The four repositories of CI are a fraction of that, so the entries stay small.
  To be measured on a runner.

## Design

### 1. One key per repository

```
source(R) = sha256( "v1" | runner OS | R | commit(R) | sorted [ source(D) for D in dependencies(R) that are in the list ] )
key(R)    = sha256( source(R) | tools )
```

- `commit(R)` is the head of `develop` (else `main`, else `master`), the same choice as `Clone-Repositories.ps1`, read with `git ls-remote`.
- Because `source(D)` is part of `source(R)`, a change in a dependency changes every key that depends on it, and nothing else. This is the table of the
  earlier notes: a `CSharpSchema_Test` commit rebuilds one repository, a `BHoM_Engine` commit rebuilds it and `JSONSchema_Toolkit`, a `BHoM` commit rebuilds all.
- `tools` is the hash of `.github/workflows/build.ps1`, the MSBuild major.minor version and the .NET SDK feature band (`10.0.4xx`). A change to
  how the repositories are built, or a new MSBuild on the runner image, then gives new keys without anybody having to remember it. Patch versions
  are left out: during an image rollout two attempts of the same run can land on runners a patch apart, which with exact versions rebuilt
  everything on a re-run. The plan logs the runner image next to the tools. The tools are kept out of `source(R)` because only
  the Windows runner knows them, and the refresh gate runs on ubuntu (see "Refreshing `develop`").
- The leading `v1` is a manual salt: bump it to throw every cache away, for example after a change to the cache scripts themselves.
- Only the dependencies that are in the list count. A dependency through a repository that is not listed (A depends on an unlisted X, which depends on
  a listed B) is not seen, so `key(A)` ignores B. `Build-Repositories.ps1` has the same limitation today.

### 2. Reading the dependencies before cloning

The keys are needed before any clone, so each `dependencies.txt` is fetched alone, at the commit just read, from
`https://raw.githubusercontent.com/<repo>/<commit>/dependencies.txt`. A missing file means no dependencies. This is one small request per repository,
and a hit then needs no clone at all.

The repositories are public, so no token is needed. A private repository would need a GitHub App token like the one `linked-csharp-pr.yml` makes,
because the workflow token can only read this repository.

A failed `git ls-remote` or fetch is retried a few times, then fails the run. It never falls back to a partial plan.

### 3. What one repository's entry holds

A folder `<repo>-<key prefix>/` holding the files the repository's build added or changed under `%ProgramData%\BHoM`, with paths relative to that
folder. It is a plain folder, not a zip: `actions/cache` already compresses the whole cache, and copying a folder is faster than `Expand-Archive`.

- The files are found by a snapshot of the `BHoM` folder (relative path, size, last write time) before and after that repository's build.
  Comparing size and time is enough and fast; no hashing of 567 files.
- Restoring is copying the folder into `%ProgramData%\BHoM` (`robocopy`), in build order and overwriting, so a later repository's version of a
  shared file wins, as in a real build. The four empty folders are always created.
- A file that two repositories copy with the same size and time (a third-party DLL keeps its package's timestamp through `xcopy`) is only in the
  entry of the first one built. That is fine while both are in the list, but see "Risks" for removing a repository.

### 4. Where the entries are stored: one folder, one GitHub cache entry

GitHub's `actions/cache` is a workflow step and cannot be called from a loop over a list read at run time, so one step per repository is not possible for
a list-driven design. Instead the entries live together in one folder, `.build-cache/`, which is one GitHub cache entry:

| Step | Key |
|---|---|
| Restore | exact key `bhom-build-cache-v1-<OS>-<state>-<tools>`, where `<state>` hashes every `source(R)` and `<tools>` the tools; if that misses, `restore-keys` prefix `bhom-build-cache-v1-<OS>-`, which brings the most recent folder in scope |
| Save | the exact key above, only when it was not an exact hit and an entry was added |

- An exact hit means nothing changed: nothing is built and nothing is saved.
- A prefix hit gives the folder of an earlier state. The script then finds, repository by repository, whether `<repo>-<key>/` is in it.
- Cache keys are immutable, so a second save of the same key fails harmlessly when two runs race.
- Before saving, entries whose key is not among this run's keys are deleted. The current heads of the repositories are the only ones a run can need, so
  the folder never grows beyond one entry per repository.

### 5. The run, in order

1. **Plan:** read the list, the commits and the dependencies, compute every key, order the repositories (existing topological order). Print a table of
   repository, commit, entry, hit or miss. A `-Plan` mode stops here and writes the plan to a file, which the build then reads, so the build uses
   the commits the key was made from. It takes the OS and the tools as parameters, so it also runs on ubuntu.
2. **Restore** the folder (exact key, then prefix).
3. **For each repository in order:** on a hit, copy its entry. On a miss, clone it at the planned commit (`git init`, `git fetch --depth 1 origin <commit>`,
   `git checkout FETCH_HEAD`; GitHub allows fetching a commit by its hash), snapshot, build, snapshot, copy the difference into the folder. Cloning the
   planned commit instead of the branch head means a push during the run cannot make the build differ from its key. A build that fails stops the
   run, so a failed build never becomes an entry.
4. **Write** `.repos/commits.txt` from the plan, in the same format as `Clone-Repositories.ps1`.
5. **Save** the folder under the exact key when something was built.

Hits skip the clone as well, so a run with every repository cached does not clone anything.

### 6. Refreshing `develop`

A PR run saves under the PR's own ref. For the next PR to benefit, the same state must be saved on `develop`. A new workflow `build-cache.yml` does this
only when `develop` does not have it yet:

| Part | Detail |
|---|---|
| Trigger | `workflow_run` when the `PR` workflow completes, plus `workflow_dispatch`. A `workflow_run` workflow runs on the default branch, so what it saves is visible to every PR |
| Job 1, `gate` (ubuntu, a few seconds, `actions: read`) | Continues only if the PR comes from this repository, not a fork (`github.event.workflow_run.head_repository.full_name`), or for a manual run on `develop`. Then runs `-Plan` for Windows and looks for the state prefix `bhom-build-cache-v1-Windows-<state>-` on `develop` (`gh cache list --ref refs/heads/develop --key <prefix>`). Continues only if it is not there, or for a manual run |
| Job 2, `refresh` (windows) | Runs the same action: plan, restore, build the misses, save. It builds from the trusted code on `develop`, never from the PR |
| Concurrency | One group, `cancel-in-progress: false`: the running refresh finishes, and a newer pending one replaces an older pending one. This avoids building the same state twice in parallel |

The gate asks `develop` directly rather than whether the PR run built something. A PR's second push can hit the PR's own cache after a refresh failed
or was cancelled, and would then never trigger a new one.

Why it rebuilds, instead of passing the PR's entries over: an entry from a PR run is code that the PR built. Putting it in the `develop` cache would let
one branch affect every later run, and forks could do the same. The rebuild costs one extra build per change in an upstream repository, not one per PR,
and the next PR hits.

Alternatives that were rejected:

| Alternative | Why not |
|---|---|
| A scheduled warm-up | Not event-driven: it either wastes runs or leaves a window with misses |
| The PR run dispatches the refresh with `gh workflow run` | Needs `actions: write` in the PR job, which also runs the PR's own code |
| Run on `push` to `develop` | A push to this repository does not happen when only an upstream repository changed |
| Pass the PR's entries as an artifact | The poisoning risk above |
| Gate on an artifact the PR run uploads when it built something | Misses the case above, where a PR run hits its own cache but `develop` was never refreshed |

The gate cannot see the tools, so after a new MSBuild on the runner image `develop` keeps its entry of the old tools until a repository changes
(or a manual run of `build-cache.yml`); in between, pull requests rebuild everything, as before this cache.

Until the generation workflow adopts the cache, nothing else refreshes `develop`. If no PR runs for 7 days, GitHub deletes the unused entry and the next
PR builds everything once (about 1 min 15 s), then the refresh restores it.

### 7. Where it is used

The composite action `.github/actions/bhom-assemblies` is rewritten for this. It is adopted in steps, because a wrong cache does very different harm depending on where
it is used:

| Workflow | When | Why |
|---|---|---|
| `pr-checks.yml`, both jobs | First change | A wrong cache gives a wrong test result on a pull request. It is seen, re-run with `-NoCache`, and nothing is published |
| `python-schema-generation.yml` | After about four weekly runs without a discrepancy | It commits straight to `develop`, with no pull request. The worst failure is silent: a stale entry gives Python that matches the old C#, `py2cs verify` and Pyright pass, and `commits.txt` names the new commits |
| `release.yml` | Not adopted: it keeps a clean build | It publishes a wheel and runs a few times a year, so saving a minute is worth nothing. A `workflow_dispatch` run can also read the caches of the ref it was dispatched from, so a release dispatched from a branch could use what that branch built |

In `pr-checks.yml`, the alignment job waits for the unit-test job (`needs: checks`, `if: ${{ !cancelled() }}`), so a miss is built once: the unit-test
job saves the cache right after the build, and the alignment job then hits it. Alignment still runs when the tests fail, and re-running only the
alignment job after the C# merge still works, because a single-job re-run does not re-run its `needs`. The price is an alignment result that comes
after the tests instead of beside them.

While generation still builds clean, it can also restore the cache and compare the two `Assemblies` folders (file list, sizes and assembly versions),
writing the differences to the step summary without using the cache. That makes the waiting period a real test.

## What it should cost, to be measured

| Situation | Today (one key) | Per repository |
|---|---|---|
| Nothing changed | restore, about 20 s | plan (a few requests) + restore + copy every entry, expected 30 to 45 s |
| `CSharpSchema_Test` changed | rebuild all, about 1 min 15 s | build one repository |
| `BHoM_Engine` changed | rebuild all | build it and `JSONSchema_Toolkit` |
| `BHoM` changed | rebuild all | rebuild all, as today |
| First run of a new PR | miss: only PR refs save the cache today, and a PR cannot read another PR's | hit, once `develop` has the cache |

These are estimates. The per-repository build times are not measured yet (the earlier log has no timings), so the second row onward is only as good as
that measurement.

## Risks and how they are handled

| Risk | Handling |
|---|---|
| A stale entry is used | The key contains the commit, the dependencies' keys, the OS, the build script and the MSBuild and .NET SDK versions. The `v1` salt (`-Salt` of `Build-Repositories.ps1`) covers the rest |
| A build fails but its files are cached | `Build-Repositories.ps1` stops at the first build that exits with an error, before the entry is complete and before the save |
| A file shared by two repositories is only in the first one's entry | Fine while both are listed, since every run installs every listed repository. After removing a repository from the list, bump the salt |
| A build has side effects outside `%ProgramData%\BHoM` | None known. The plan checks this by comparing the folder before and after on a real run |
| Two jobs build the same repository at once | Avoided in `pr-checks.yml` by `needs`. Elsewhere, wasted time, not a wrong result: the second save of the same key fails harmlessly |
| The cache grows or is evicted | One entry per repository, pruned on every save. Unused entries are deleted after 7 days and the repository limit is 10 GB, far above this |
| `git ls-remote` or a `dependencies.txt` fetch fails | Retried, then the run fails. It never builds from a partial plan |
| A fork spams the refresh workflow | The gate rejects runs whose head repository is not this repository, and runs on an ubuntu runner for a few seconds |
| The script is wrong and builds from stale assemblies | `-NoCache` ignores the cache completely, and bumping the salt resets it; both are one-line changes. Generation adopts the cache only after a comparison period, and release never does |

## Implementation steps

Steps 1 to 6 are done.

1. **Planning script.** Add `-Plan` to `Build-Repositories.ps1`: commits, dependencies, keys, order, hit or miss. A `-CommitsFile`
   parameter replaces `git ls-remote` and `-DependenciesRoot` the fetch of `dependencies.txt`, so tests need no network.
2. **Build with the folder.** `-CacheFolder` for `Build-Repositories.ps1`: copy on a hit, clone at the planned commit and build on a miss, snapshot, copy the
   difference, prune, write `.repos/commits.txt`. `-NoCache` for the old behaviour.
3. **Composite action.** Plan, restore (exact then prefix), build, save when something was built; outputs which repositories were built.
4. **Use it** in `pr-checks.yml`, with the alignment job waiting for the unit-test job.
5. **`build-cache.yml`** with the gate and refresh jobs above.
6. **Tests and docs**, listed below, then update [Workflows.md](Workflows.md) and mark [Build-Cache-Plan.md](Build-Cache-Plan.md) as superseded.
7. **Later, a separate change:** the comparison in `python-schema-generation.yml`, then the switch to the cache once it has shown no difference.

## How we will test it

- **The plan logic, with no network and no build:** a test that feeds `-Plan` a fake commits file and fake `dependencies.txt` files and checks the keys: a change in one
  repository changes exactly its own key and those that depend on it, the order is topological, and the salt, the OS and the tools change every key. NUnit or pytest can start `pwsh`.
- **Restore, on a real machine:** run the build twice on the development machine (the installation may be changed): the second run must copy everything and build
  nothing; change one commit (or a fake commit file) and check that only that repository and its dependents are rebuilt; compare the resulting `Assemblies` folder with a
  clean build by file list, sizes and assembly versions (the builds are not byte-for-byte deterministic).
- **Workflow structure tests** (the style of `test_workflows.py`): the action restores before building and saves after; the alignment job needs the unit-test job and
  runs unless cancelled; the refresh workflow triggers only on `workflow_run` and manual runs; the gate checks the head repository and looks the key up on `develop`;
  only the refresh job writes to the `develop` cache; `release.yml` does not use the action.
- **On GitHub:** a first run that builds and saves, a second that restores everything, then a PR that touches one upstream repository's commit (or a fake) and rebuilds only that one,
  and a check that the refresh run makes the next PR hit.

The plan logic and the restore are tested in `test_build_plan.py`, and the workflow structure in `test_workflows.py`. The run on the development
machine with real builds and the runs on GitHub are still to do.

## Still to measure

1. Build time per repository from a real run (the `Building <name>...` lines with timestamps), to confirm the expected gain.
