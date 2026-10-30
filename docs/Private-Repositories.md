# Private C# repositories: what would need to change

**Status: not done. For now the system only works with public C# repositories in the BHoM organisation**
(today that is [BHoM/CSharpSchema_Test](https://github.com/BHoM/CSharpSchema_Test)). This note records what breaks for private
repositories, for example the ones in the BuroHappoldEngineering organisation, and the options, so the work can be picked up later.

## What breaks for private C# repositories

| Part | Why it fails |
|---|---|
| `.github/scripts/Clone-Repositories.ps1` | It clones anonymously over HTTPS |
| The token steps in `linked-csharp-pr.yml` and `linked-csharp-pr-close.yml` | It passes `owner: ${{ github.repository_owner }}`, so it only works for C# repositories in the same organisation as this one. Repositories in another organisation fail |
| Public logs and artifacts | This repository is public, so its Actions logs and uploaded artifacts are public. The weekly generation uploads a report and a manifest that list class names, warnings and build output. Private code built or generated here would be exposed |
| `src/bhom_schema` | Classes generated from a private repository and committed here would be public |

The last two are the real problem. Private classes cannot be generated into, or built inside, the public repository, however the
tokens are arranged.

## Decision 1: where do the private classes live?

| Option | What it means | Verdict |
|---|---|---|
| A. The same public repository | Private classes are generated here | Not acceptable: it leaks them |
| B. A second, private deployment | A private repository (for example `BuroHappoldEngineering/BHoM_PythonSchema-private`) holds the private classes, runs the same workflows, and has its own `Converted-repositories.txt`. This repository keeps the public C# repositories only | **Recommended** |
| C. One private repository for everything | The public BHoM classes are generated in a private repository too | Possible, but the public BHoM Python classes would no longer be public |

**Sharing the code in option B.** Copying the tooling would let the two repositories drift apart. Instead:

- The public repository keeps `py2cs`, the generator and the patcher.
- The three workflows become reusable (`workflow_call`), which a private repository can call, pinned to a commit.
- The private repository holds only its repository lists, its own `src/bhom_schema`, thin workflows that call the public ones, and
  its secrets.

This is a refactor of the workflows, not new logic.

## Decision 2: how do the tokens work?

This applies to every deployment, because each one reads and writes C# repositories with a GitHub App token. One
`actions/create-github-app-token` step makes a token for one owner only.

| Option | How it works | Pros | Cons |
|---|---|---|---|
| 1. One GitHub App, matrix per repository | Take the owner from each repository's `Owner/Name`. Make one token per repository in a matrix leg. | Same GitHub-maintained action. No new secrets in the C# repositories. Small change | The App must be installed in both organisations, and its visibility must be "Any account" (a private App can only be installed in its own organisation). |
| 2. One App per organisation | Same as 1, with one App in BHoM and one in BuroHappoldEngineering. Each deployment holds the secrets of its own App | Strongest separation: nothing crosses organisations. Natural with option B | Two Apps to set up and maintain |
| 3. `py2cs` makes the tokens itself | `py2cs` signs a JWT with the App key and asks GitHub for an installation token per repository. | One step, any number of owners | Needs a JWT/crypto library, and the code that holds the private key grows. Best avoided |
| 4. The C# repositories report their own state | A workflow in each C# repository, on pull request merge or close, tells the Python PR (for example by re-running its alignment check) | Event-driven: no manual re-run, no cross-organisation reads | Needs a workflow and secrets in every C# repository. The public repositories, BHoM/BHoM in particular, cannot be changed yet |
| 5. A personal access token or bot account | One long-lived token that can read the repositories | Simplest | Tied to a person or account, long-lived, and hard to scope across two organisations. Not recommended |

## Recommendation

1. Run private C# in a separate private deployment (option B), and make the public tooling reusable so both share one code base.
2. Use one GitHub App per organisation (token option 2). If a single App is preferred, token option 1 needs it set to "Any account".
3. In both cases:
   - take the owner from each repository's `Owner/Name`;
   - make the cloning script use a token for private repositories;
   - keep uploaded artifacts and verbose logs out of any deployment that handles private code.

Token option 4 is a good later addition for private repositories, because their owners control them. The public BHoM/BHoM cannot have a
workflow added yet.

## Questions to settle before any code

- Is a separate private deployment (option B) acceptable?
- One GitHub App per organisation, or a single App installed in both?

## Where this shows up in the code today

These places assume public repositories in one organisation, and would change:

- `.github/workflows/linked-csharp-pr.yml` and `linked-csharp-pr-close.yml`: `owner: ${{ github.repository_owner }}` in the token steps.
- `.github/scripts/Clone-Repositories.ps1`: anonymous `git clone`.
- `.github/workflows/python-schema-generation.yml`: uploads the report and manifest as a public artifact.
- `Converted-repositories.txt` and `Included-repositories.txt`: one list each, for one deployment.
