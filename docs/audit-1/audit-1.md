Docs read; now reviewing the remaining docs and the converter code.

Reviewing the Python→C# converter (py2cs) now.

Confirmed a serialization gap with a probe; checking a couple of default-value edge cases next.

## Verdict

**It's partly fit for purpose.** The C#→Python generator works well, but the rest of the Option 2 loop isn't ready yet. The Python→C# return path is weak, Python projects can't easily reuse the output (it doesn't survive JSON), and the CI/PR automation (phase 8) hasn't been started.

**What's already good:**
- It reads the compiled oM by reflection.
- It selects the same types as BHoM_JSONSchema.
- Output is deterministic, and reference cycles are handled.
- The corpus run converts 1,800 of 1,800 types, all import, and Pyright strict is clean.
- The fixture assemblies and the Roslyn round trip are a strong testing approach.
- The docs are thorough.

## Main problems, most serious first

Each was checked with a throwaway probe in the scratchpad against the existing `_output` and your local `dKoP_Toolkit` and `BHoM` clones.

**1. The drafted C# would probably get rejected by BHoM reviewers.** I added one Python field to `Bar`. The full-file replacement of `Structure_oM/Elements/Bar.cs` then:
- dropped both `[DocumentationURL]` attributes;
- removed `IElement1D` and reordered the bases;
- collapsed the multi-line `[Description]` strings;
- dropped `= null` and changed `= 0` to `= 0.0`.

So one line of Python became a ~40-line C# diff that loses information. The Python model doesn't carry every C# attribute, so regenerating the whole file will always lose something. **Fix:** a member-level patch using Roslyn (add, change or remove only the affected members, keeping comments and formatting). Roslyn is already used in the tests. This means revisiting the "full-file replacement" decision in CODING-PLAN §9.

**2. py2cs only understands the generator's own output, but the Python PRs will be written by people.**
- A new class without a hand-written `__bhom__` dict is **silently ignored**. The diff reports no change, so no C# PR would be raised.
- `Stage: int = Field(0, description=...)` (a positional default, which is normal Pydantic) is read as "no default". The draft then made `ProjectIdentification` immutable, with a get-only property and a new constructor. That breaks every `new ProjectIdentification()`.
- `Optional[int]` crashes the whole run with a traceback.

**Fix:**
- Define a small authoring contract and enforce it with a PR check.
- Accept the common idioms (`Optional`, `typing.List`, positional `Field`, `pydantic.Field`).
- Report problems per file instead of crashing.
- Infer the assembly and repo from the folder. Default brand-new types to `Python_Toolkit`, as your diagram suggests.
- Never emit immutable C# from a missing default. Flag it instead.

**3. Python projects can't really reuse the schema yet.** Fields typed with an interface (`ICurve`, `IFragment`, …) are plain `isinstance` checks.
- `Edge.model_validate_json(edge.model_dump_json())` fails.
- `model_json_schema()` fails for **every** `BHoMObject`, because of `Fragments: list[IFragment]`.
- There's no `_t` type marker, so the dump loses which `ICurve` subtype it held.

**Fix:** add a `_t` discriminator to concrete classes, and validate interface-typed fields through a registry keyed on `_t` (or a union of the known implementers). Line this up with the BHoM JSON serialiser. The plan put BHoM JSON out of scope; I'd bring it back, because reuse depends on it, and Python_Toolkit already talks BHoM JSON.

**4. Nothing defines what happens to the two linked PRs over time.** If the Python PR merges and the C# PR is then changed or rejected, the next weekly run silently overwrites or reverts the Python. **Fix:**
- Treat the Python PR as a proposal.
- Add a required "aligned" check: build the linked C# branch, regenerate the affected types, and compare. You already have `compare_manifests` for this.
- Merge (or supersede) the Python PR only after the C# PR merges.
- Flag renames, removals and type changes as breaking. BHoM needs Versioning_Toolkit upgraders for those.

**5. Phase 8 doesn't exist yet.**
- There are no workflows, no `pr.py` or GitHub client, and no generated code committed in `src/bhom_schema`.
- The generator always exits with 0, so CI couldn't gate on failed types or new kinds of warning.
- Input is whatever happens to be in `ProgramData`. **Fix:** build once and emit both JSON and Python from the same weekly build (share the build output, not the logic), or use released BHoM assemblies.

**6. Packaging.**
- The version is fixed at `0.1.0`, and there's no publishing.
- One package holds about 70 oM assemblies, including `UnitTest_oM`, `NUnit_oM` and the attribute classes.

**Fix:** tie the package version to the BHoM release, record it in `__bhom__`, exclude test and attribute types, and consider per-toolkit extras.

**7. Smaller issues:**
- The header hard-codes `2015 - 2026`, so every January all ~2,000 files will change. Drop the year or keep it fixed.
- Clean-up only touches assemblies seen in the current run. A toolkit whose build failed keeps stale files with no warning.
- A case-insensitive path collision drops a type, with only a warning.
- `DateTimeOffset` comes back as `DateTime`.
- `Included-repositories.txt` spells it `dKop_Toolkit` and has no trailing newline.

**8. Docs:**
- `CODING-PLAN.md` still says "plan only, no code written yet" above its own status section.
- `Reusing-oM-Classes.md` is a pasted chat answer and is out of date: it says `Tree_1` fails, which has since been fixed.
- Commands are repeated across three guides.

## Suggested order

Do 2 and 1 first, because they make the loop safe. Then 4, then 5, so the loop actually runs. Do 3 alongside, because it decides whether anyone can use the package. Leave 6 to 8 for last.

I couldn't run `run-all.ps1`: the permission was denied, so I haven't confirmed the test suite currently passes. I can also put this review on a shareable page if you want to pass it on.