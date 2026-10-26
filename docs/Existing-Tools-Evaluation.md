# Could an existing package do the conversion? Evaluation (2026-10-26)

Question: can public packages replace the core logic of our two converters (C# to Python, and Python to C#)? The answer after
research and tests is **no** for the core logic. The reasons are below, with what was tested and what was not.

## 1. What the converters must do

| Need | Why it matters |
|---|---|
| Keep the class hierarchy and interfaces | `ProjectIdentification` derives from `IdKoPObject`; BHoM relies on `IObject`, `IBHoMObject`, `IFragment`, and so on |
| Keep enum member names (including `None`, written `None_`) | The member name is the contract; the number is not |
| Keep generics and their constraints | `BHoMGroup<T>`, `Tree<T>` |
| Keep C# defaults, descriptions, quantities and display text | Needed for faithful Python and for drafting C# back |
| Carry provenance (C# full name, assembly, repo) | Needed to route the linked PR to the right repository and file |
| Read the **compiled** types | The oM can be built from many repos; reflection already knows every type, base and default |
| Produce **declaration-level** C# (types, properties, enums), not translated method bodies | The oM has no logic, only data shapes |

## 2. Candidates, by direction

### Python to C#

| Candidate | Found | Verdict |
|---|---|---|
| **py2many** (v0.9 installed, repo updated Oct 2026) | `--help` lists C++, Rust, Julia, Kotlin, Lean, Nim, Mojo, D, Dart, Go, V, Zig, SMT. **No C#.** | Not an option. Tested: the installed CLI has no C# switch. |
| **pytocs** (uxmal, Apache-2.0) | Last commit Feb 2023. README examples are Python 2 (`print "Hello"`). Output types are all `object` (listed on its own roadmap). The parser reads annotated assignments (`x: str = ''`) but nothing under `Core/Translate` uses the annotation, so field types would not reach the C#. No PEP 695 generics. Targets `net6.0`. | Statement-level translator of method bodies; wrong tool for typed data shapes. Source reviewed; **not built or run** (see section 4). |
| **cs2python** (isukces) | Last commit Feb 2018, "early stage". C# to Python, simple loops. | Abandoned. |
| **Pydantic JSON Schema, then NJsonSchema/quicktype to C#** | Pydantic side tested (below). C# generator side **not run** (section 4). | Loses the information we need before C# is even reached. |
| **LLM-based** (py2many `--llm`) | Not deterministic. | Not suitable for a CI step that must be reproducible. |

### C# to Python

| Candidate | Found | Verdict |
|---|---|---|
| **datamodel-code-generator** (v0.86 installed) | Excellent JSON Schema/OpenAPI to Pydantic generator. It cannot read .NET types, so C# would first have to be exported to a schema. Tested on the real `BHoM_JSONSchema` files: see below. | Fails our needs; would also make the JSON repo a dependency, which we decided against. |
| **NJsonSchema / NSwag** | C# to schema and schema to C#. Same schema-level loss as above. | Not run. |
| **PythonNetStubGenerator, pythonstubs, clr-stubs** | Produce `.pyi` stubs so Python can *call* .NET through pythonnet. | Wrong purpose: stubs for calling .NET, not Pydantic data classes. |
| **Roslyn-based transpilers** (Rosetta, Transpose) | Target TypeScript and JavaScript. | No Python target. |
| **Reflection to Pydantic** | A blog shows exactly our approach for Java. No packaged .NET equivalent found. | Confirms writing our own reflection generator is the standard route. |

## 3. Tests that were run

### 3.1 Pydantic to JSON Schema (the first half of any schema route to C#)

Using a probe model file shaped like our generated output (base interface, `None_` enum member, generic, `Annotated` quantity,
`ClassVar` provenance marker):

| Information | After `model_json_schema()` |
|---|---|
| Base class `IdKoPObject` | **Lost** (plain `object` schema) |
| `__bhom__` provenance (C# name, repo) | **Lost** |
| Enum `None_ = 0`, `Center = 1`, `Edge = 2` | **Names lost**, only `enum: [0, 1, 2]` remains |
| `Group[T]` generic | **Lost** (`items: {}`) |
| `Quantity` marker | **Lost** |
| `Tags: list[str]` default factory | Default dropped |

Any C# generated from that schema would be a flat property bag with no hierarchy, no enum names and no repo to send the PR to.

### 3.2 JSON Schema to Pydantic (the C# to Python schema route)

`datamodel-codegen` on the real `BHoM_JSONSchema/dKoP_oM/ProjectIdentification.json` and `Graphics_oM/Enums/GradientCenteringOptions.json`:

- `ProjectIdentification`: no base class `IdKoPObject`, no defaults (every field `str | None` and required), and BHoM-JSON noise
  fields (`_t`, `_bhomVersion`).
- `GradientCenteringOptions`: produced **two copies of the enum plus a `System.Enum`/`System.Type` wrapper model** and a `RootModel`
  union, because the schema describes the BHoM-JSON wire format, not the type.

It is a tool for wire formats; our target is the type model.

## 4. What could not be tested, and why

The sandbox blocked building the cloned pytocs (`dotnet build` of an unreviewed third-party repository), and I did not work
around that. The same applies to running NJsonSchema or quicktype, which would also be downloaded third-party code. The verdicts
for those rest on reading their source and documentation, plus the schema tests above (which show the loss happens before they
run). To run them anyway, the user can approve the build and I will repeat the probe: `python probe/probe_models.py` through
`pytocs` (expect `object`-typed output and no field types), and the Pydantic schema through NJsonSchema.

## 5. Conclusion

1. No existing package converts Python to C# with typed declarations, and none targets C# from a Python class model.
2. The only maintained broad transpiler (py2many) does not have a C# backend.
3. The only existing C# target (pytocs) is aimed at method bodies and produces untyped `object` code.
4. Every schema-based route drops hierarchy, enum names, generics and provenance, so it cannot meet the requirements.
5. For C# to Python, reflection over the compiled oM is the standard method and no package replaces it.

So the core logic stays ours. What we **do** reuse already: BHoM's own helpers (`IsOmNamespace`, `IsInOrg`, `RelativeSchemaId`,
`BHoMFolder`), Pydantic for the model classes, Roslyn for compiling the C# in the tests, and Pyright for checking the output.
