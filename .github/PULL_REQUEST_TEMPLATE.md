<!-- PLEASE ENSURE YOU REVIEW THE CONTENT OF EACH PR CAREFULLY, INCLUDING SUBSEQUENT COMMENTS BY YOURSELF OR OTHERS. -->
<!-- IN PARTICULAR PLEASE ENSURE THAT SENSITIVE OR INAPPROPRIATE INFORMATION IS NOT UPLOADED -->

### Issues addressed by this PR
<!-- Add reference(s) to issue(s) solved by this PR. Please use keyword Fixes/Closes as per https://help.github.com/articles/closing-issues-using-keywords/ -->

Closes #

<!-- Add short description of what has been fixed -->


### Python schema changes (only for PRs that change `src/bhom_schema`)
<!-- New to this? Read docs/User-Guide-2-Extending-The-Schema.md. A Python PR is a proposal: the matching C# PR is merged first, this one second. Delete this section if the PR does not change src/bhom_schema -->

**What I added and why** (for example: a `NumberOfLifts` property on `Building`, because my `elements_flat` table has a `number_of_lifts` column that has no home yet):


Tick each box when it is true:

- [ ] Every new class and property has a **description** (what it is, its unit, and `Aliases:` with other names for it) and a **default value**, so Genie Code can map columns to it
- [ ] A **comment with a link to a C# PR** appeared on this PR. Link: 
- [ ] I asked a reviewer to approve the C# PR (see "Get the C# pull request approved" in the user guide), and it is **merged**. If it was closed without merging, I closed this PR with a comment saying why
- [ ] After the C# merge I clicked **Checks** → **Re-run all jobs** on this PR, and the checks are **green**. If one lists differences (first value is the C#, second is this PR), I changed my Python to match the C# and pushed
- [ ] I only **added** things. If I renamed or removed a property, changed a type, or removed an enum member or class, old BHoM files may stop opening


### Test files
<!-- Link to test files to validate the proposed changes -->


### Changelog
<!-- Text to go into changelog if applicable -->
<!-- Please see https://github.com/BHoM/documentation/wiki/changelog for guidelines -->


### Additional comments
<!-- As required -->