# C# → Python class conversion: technical research

Purpose: record what we know, what we measured, and what is still open, so a coding plan can be written
from it. Anything marked **[verified]** was
checked by an experiment or by reading the real repos on 2026-10-05 (Python 3.12.10, Pydantic 2.13.5).
Anything marked **[unverified]** is a proposal or assumption that the first spike must confirm.

---

## 1. Scope and decisions already made

| Topic | Decision |
|---|---|
| What the Python package is | Python **class definitions** generated from the C# oM. Nothing else. |
| JSON | **Out of scope.** The Python classes never save or load JSON, and never exchange BHoM-format JSON with C# or `BHoM_JSONSchema`. |
| Base technology | Pydantic v2 (`BaseModel`). |
| Python version | **3.12** minimum (allows `class Group[T: BHoMObject]` generic syntax; verified with Pydantic 2.13.5). |
| Package layout | One C# type per Python file, inside a single wrapper package `bhom_schema` (section 6). |
| Naming | C# PascalCase property names kept exactly as in C#. |
| Metadata | Carry as much C# metadata as possible onto each Python class (section 7). |
| Tooling | Type hints everywhere, checked by Pyright in CI, Pylance in the editor (section 9). |
| C# → Python converter | The important one. It must emit **valid, importable Python**. Lives in this repo under `.ci/generation`. |
| Python → C# converter | Used **only** in the linked-PR flow, to draft C# that is *aligned* with a Python change. It does **not** need to reproduce C# exactly. A human reviews the C# PR. |
| Reuse of existing code | The converter lives here but **references the existing assemblies** (JSONSchema_Toolkit / BHoM engine) for shared reflection helpers. |
| Source of truth | The C# oM (diagram: "C# oM from `<Tool>_Toolkit` and `Python_Toolkit`"). Python is derived from it. |
| Automation | A GitHub Action with org-wide API access raises the linked C# PR, so every Python class must carry enough information to locate its C# home. |

### Pipeline (from the system design diagram)

```
C# oM (source of truth) ──► C# to Python converter ──► BHoM_PythonSchema (this repo)
        │
        └──► C# to JSON converter (weekly) ──► BHoM_JSONSchema     (independent, unchanged)

Python change in this repo ─► PR ─► Python to C# converter ─► PR in the C# repo   (two linked PRs)
```

Because JSON is out of scope, the two output repos only share one thing: the C# oM they both come from.

---

## 2. How the converter will read C# (and why that matters)

The existing generator, [Generate.cs](C:\Github\BHoM_JSONSchema\.ci\Generation\SchemaGeneration\SchemaGeneration\Generate.cs)
and [ToJsonSchema.cs](C:\Github\JSONSchema_Toolkit\JsonSchema_Engine\Convert\ToJsonSchema.cs), does not parse
`.cs` source. It loads the **compiled** `*oM.dll` files from the BHoM folder and uses .NET **reflection**
("ask the compiled code what classes, properties and types it contains"). It already:

- filters to oM types (`IsOmNamespace`), skipping static classes and anything not an enum or `IObject`;
- filters assemblies by organisation (`IsInOrg`);
- finds interface implementers (`Subtypes`);
- reads descriptions and quantity attributes;
- unwraps nullables, arrays, dictionaries, tuples and generic parameters.

We reuse that walk and replace the output side (JSON schema objects) with a Python code emitter.

**Consequence of using reflection:** it only sees what survives compilation. Comments, the order things were
written in, and default-value expressions are not visible (see gotcha 3).

**Language choice:** the C# → Python converter is written in **C#** (reflection is a .NET feature and the
helpers already exist). The Python → C# converter is written in **Python** (it inspects the generated
Pydantic classes). This means the repo has a `dotnet` side and a `pytest` side.

---

## 3. What the real oM looks like (measured)

Counted from the 2,007 schema files in `BHoM_JSONSchema` as a proxy for the oM. These are approximate
(classification is by schema shape); the converter will recount from the DLLs.

| Fact | Count / finding | Why it matters |
|---|---|---|
| Total types | 2,007 | Import time and file count (gotcha 10) |
| Enums | 317 | Straightforward `Enum` classes |
| Interfaces + abstract classes | 227 | Need a representation (gotchas 6 and 9) |
| Concrete classes/structs | ~1,463 | The bulk |
| Assemblies (top-level folders) | ~70 | Package layout, provenance |
| Folder depth below an assembly | 0–3 levels of namespace | Package nesting |
| Generic types (name has a backtick, e.g. ``Output`10``) | 34 | Names are not valid Python (gotcha 5) |
| Enum members named `None` | 12 | Python keyword (gotcha 7) |
| Property names that are Python keywords | **0** | Keyword problem is limited to enums |
| Property names that clash with Pydantic's own attributes | **0** | Pydantic risk is low |
| Properties named like builtins | 3 (`type` ×2, `Warning`) | Minor (gotcha 7) |
| Type names that are the **same** in different assemblies/namespaces | 64 (e.g. `Panel` ×4, `ISurface` ×3) | Big: names are **not** unique (gotcha 8) |
| Type names equal to a Python builtin or `typing` name | 0 | Good |
| Type names equal (ignoring case) to a stdlib module | 5 (`Time`, `Select`, `Profile`, `Encodings`, `UnitTest`) | Low risk if everything is inside our own package |
| Reference cycles if interfaces list their implementers (the JSON-schema way) | 15 groups, largest has 25 types (e.g. `IGeometry` ↔ `CompositeGeometry`) | These **disappear** with the ABC interface design (gotcha 6) |
| Reference cycles between concrete classes + interfaces, interfaces treated as dead ends | **0** | Circular imports look much smaller than feared (gotcha 9). Abstract classes could not be measured from schemas; re-measure from the DLLs |
| `HashSet<T>` properties where `T` is a BHoM object | 6 properties in 3 types (`ComparisonConfig`, `RevitComparisonConfig`, ...). The other ~750 `HashSet`s are `HashSet<string>` (`Tags`) | Hashability issue is narrow (gotcha 11) |
| Dictionaries with non-string keys (stored as `k`/`v` arrays) | 11 types, keys include `Frequency` (a class), `Guid`, `decimal` | Same |
| Properties documented with a quantity (length, stress, ...) | 348 types | Metadata worth carrying (section 7) |
| oM `.cs` files whose folder differs from the namespace-derived folder | 625 of 1,460 (43%) in the local clones | Never derive a C# path from a namespace (gotcha 14) |
| oM projects whose `AssemblyDescription` is the repo URL | 41 of 41 local projects | Repo can be recorded at generation time (gotcha 12) |

---

## 4. Gotchas

Each item: what C# does, what Python does, why it matters here, the plan, and the evidence.

### 1. The type systems don't match

C# has `int`, `long`, `short`, `byte`, `float`, `double`, `decimal`, `char`, and many collection types
(`T[]`, `List<T>`, `IList<T>`, `IEnumerable<T>`, `HashSet<T>`). Python has one `int`, one `float`, and mostly
`list`, `set`, `tuple`, `dict`.

Why it matters: after conversion, `int` and `long` are both `int`, and `T[]`, `List<T>`, `IList<T>` are all
`list[T]`. The Python→C# PR draft would not know which one to write.

Plan: one mapping table (section 5) is the only place types are translated. Record the original C# type on
each field with `typing.Annotated`, so the Python→C# converter can read it back. Python does not enforce it.

### 2. Nullability

`int?` can be null; plain `int` cannot. Reference types can usually be null. Python needs `X | None`.
Follow the existing `type.IsNullable()` / `Nullable.GetUnderlyingType` logic so the rule matches the JSON
schema generator. Getting it wrong either rejects valid objects or accepts invalid ones.

### 3. Default values are invisible to reflection

C# source can say `public List<Point> Points { get; set; } = new List<Point>();`. After compilation that
expression is buried in constructor code.

Plan:
- Classes with a parameterless constructor: create an instance and read each property to learn its default.
  Mutable defaults (lists, dicts) become `Field(default_factory=...)`.
- "Immutable" classes (constructor arguments required): fields are required, no default. The existing JSON
  generator treats them the same way (`RequiredProperties`, which uses the constructor with most parameters).

Evidence **[verified]**: Pydantic copies mutable defaults per instance (two objects with `Items: list[int] = []`
do not share the list). Still emit `default_factory` for clarity.

### 4. Inheritance and field order

Plain Python `dataclasses` refuse a required field after a defaulted one, even across inheritance. Almost
every BHoM object inherits from `BHoMObject` (defaulted `Name`, `Tags`, ...) and adds required fields.

Evidence **[verified]**: a plain dataclass subclass failed with `non-default argument 'l' follows default
argument`; the equivalent Pydantic subclass worked. This is a main reason for choosing Pydantic.

### 5. Names that are not valid Python (generics and backticks)

The compiled name of a generic is ``Output`1``, ``Output`2`` ... ``Output`10``. 34 such types exist.

Evidence **[verified]**: a class can be *created* with a backtick name at runtime, but `class Output`1:` is a
syntax error, so it cannot appear in source or be imported by name.

Plan **[unverified]**: emit `Output_1`, `Output_2`... as the Python names (arity suffix; two classes of the
same base name and different arity must not collide) and keep the real CLR name in the provenance marker
(gotcha 12). Python `Generic[T]` + `TypeVar` carry the generic parameters.

Related, Python can't express: multiple constraints (`where T : IA, IB`), `new()`, `struct`, `class`
constraints. Plan: bind to the first constraint, note the rest in the docstring/metadata. Looser typing,
but still valid code.

Evidence **[verified]**: `Group(BaseModel, Generic[T])` with `T = TypeVar(bound=BHoMObject)` works, and
`Group[Child]` rejects a plain `BHoMObject` element.

### 6. Interfaces, and the MRO error

C# lets a class list interfaces in any order, even redundantly (`class X : IFoo, IBar` where `IBar : IFoo`).
Python computes lookup order (the **MRO**) and rejects an inconsistent one. Reflection also returns a
**flattened** list of all interfaces, not what was declared.

Evidence **[verified]**: `class M(IFoo, IBar)` where `IBar(IFoo)` raised `TypeError: Cannot create a
consistent method resolution order`; `class M(IBar, IFoo)` worked.

Plan: from the flattened list, drop any interface already implied by another one in the list, then order
most-specific first (topological sort).

Representation **[verified]**: model each C# interface (and abstract-only type) as a plain `abc.ABC` class,
and set `model_config = ConfigDict(arbitrary_types_allowed=True)` on models that have fields typed as an
interface. Then:
- a field typed `IGeometry` accepts any implementing instance and **keeps its real subclass** (a `Point`
  stays a `Point`);
- it rejects a non-implementer (`Input should be an instance of IGeometry`).

Because JSON is out of scope, this removes the need for giant discriminated unions of every implementer
(`IObject` has ~1,469). That is a large simplification.

**In plain words.** In C#, a property can be declared as an *interface*, a promise like "anything that is
a geometry":

```csharp
public interface IGeometry { }
public class Point : IGeometry { ... }
public class Line  : ICurve   { ... }       // ICurve itself extends IGeometry

public class Holder { public IGeometry Geo { get; set; } }   // can hold a Point, a Line, ...
```

Python has no `interface` keyword. We need *something* that says "this class counts as an IGeometry", and
a way to make a field accept "any IGeometry". There were two ways to do it:

| | Option A: list every implementer | Option B (chosen): abstract base class |
|---|---|---|
| Python type of the field | `Point \| Line \| Arc \| ... \| (1,469 classes)` | `IGeometry` |
| What `IGeometry` is | a huge union type | an empty class `class IGeometry(ABC): ...` |
| Needs to know all implementers? | Yes, so the interface file must import every implementer | No, implementers import the interface, never the reverse |
| Cost | Slow imports, circular imports | Almost free |

Option B in code:

```python
from abc import ABC

class IGeometry(ABC): ...                   # the "interface": just a marker class
class ICurve(IGeometry): ...                # interfaces can extend interfaces

class Point(BaseModel, IGeometry):          # "Point implements IGeometry" = Point inherits from it
    X: float
    ...

class Holder(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)   # see below
    Geo: IGeometry                                            # accepts anything that inherits IGeometry
```

What the two bullet points mean:
- **"Keeps its real subclass":** `Holder(Geo=Point(...)).Geo` is still a `Point` with `X`, `Y`, `Z`.
  Pydantic does not convert it into a generic `IGeometry` or throw its fields away. (With some validation
  designs it would; this one does not.)
- **"Rejects a non-implementer":** `Holder(Geo=3)` fails with `Input should be an instance of IGeometry`,
  so a wrong object cannot slip in.

`arbitrary_types_allowed=True` is needed because `IGeometry` is a plain Python class, not a Pydantic model.
By default Pydantic only knows how to validate its own models and built-in types; this setting tells it
"for classes you don't recognise, just check `isinstance`". That check is exactly what we want here.

Limitation: it checks *what the object is*, not what is inside a dict. `Holder(Geo={"X": 1})` would be
rejected because Pydantic can't know which implementer to build. That is acceptable, because the classes
never load from JSON or dictionaries by design.

Pyright also understands this: `Holder(Geo=3)` is flagged in the editor before the code runs (section 9).

### 7. Reserved words and shadowed names

- Enum members called `None`: `None = 0` is a syntax error. Evidence **[verified]**: the functional form
  `Enum("E", {"None": 0})` works (`E["None"]`, and `getattr(E, "None")`) but `E.None` cannot be written in
  source. The suffix form `None_ = 0` works and is what users would type. Only the 12 `None` members were
  found, so a keyword check (`keyword.iskeyword`) plus `_` suffix is enough. Keep the original name in the
  metadata.
- Enum members called `name` / `value`: **[verified]** they work on Python 3.12, so no special handling,
  but still worth a lint check on older versions.
- Properties named `type` (2) and `Warning` (1): Pydantic accepts them **[verified]**. However, a field named
  `type` shadows the builtin **inside the class body**, so a later annotation like `type[int]` in the same
  class breaks (**[verified]**: `TypeError: string indices must be integers`). Plan: emit annotations that
  can't be affected (e.g. `builtins.type[...]`) or rename on collision.
- Properties are PascalCase, so no clash with Pydantic's lowercase attributes was found (0 of 16,153).

### 8. Type names are not unique

64 simple names appear in more than one place (`Panel` in Acoustic, Environment, Facade, Structure;
`ISurface` in three assemblies; ...).

Consequences:
- Package layout must include assembly and namespace; a flat module is impossible.
- Generated annotations and imports must never rely on a bare class name being unique. Where two
  same-named classes are both needed in one file, import with an alias.
- A single global "name → class" lookup used to resolve forward references would be ambiguous (see gotcha 9).

### 9. Circular references

C# classes reference each other freely. Python modules run top-to-bottom, so `a.py` importing `b.py` which
imports `a.py` can fail.

How common is it here? **[verified from the schemas]** If interfaces had to list all their implementers
there would be 15 groups of types that reference each other, the biggest with 25 types (for example
`IGeometry` lists `CompositeGeometry`, and `CompositeGeometry` has a list of `IGeometry`). With the ABC
design (gotcha 6) an interface file points at nothing, and the same analysis found **zero** cycles among
concrete classes. Caveat: abstract classes carry real properties in Python but show up as interfaces in the
schemas, so the true count must be re-measured from the DLLs. Keep the safe pattern below anyway, because a
single cycle appearing in a future C# change must not break the whole package.

Evidence **[verified]** (two-class cycle `Panel`↔`Opening` in separate packages):
- Using `from __future__ import annotations` + `if TYPE_CHECKING:` imports **alone is fragile**. It happened
  to work only when the calling code had both classes in scope; when user code imported just `Panel`, creating
  one failed with `Panel is not fully defined; you should define Opening, then call Panel.model_rebuild()`.
- Putting the cross-import at the **bottom of each module** (after the class) and calling `Model.model_rebuild()`
  there worked in both import orders.
- A central `model_rebuild(_types_namespace=...)` also works but needs a name→class dictionary, which clashes
  with gotcha 8.

Recommended **[unverified at scale]**: bottom-of-module runtime imports with an explicit `model_rebuild()` per
model, using import aliases to disambiguate duplicate names. The spike must test deep chains and larger
cycles, not just a pair.

### 10. Scale and import time

Evidence **[verified, synthetic]**: 2,000 generated models (8 fields each, cross-package references,
inheritance depth up to ~29) imported in about 3–4 seconds cold with Pydantic 2.13.5, one file per model.
This test used deferred references and did not exercise full rebuild of long reference chains, so the real
number needs the spike. Options if it is too slow: lazy loading via module `__getattr__`, or fewer, larger
modules.

### 11. Types with no Python twin

`DateTime`, `Guid`, `Color`, `Type`, delegates, `DataTable`, `Bitmap`, `object`, tuples, `IComparable`.
Start from the special cases already in `SystemSchemas.cs`. Unknown or unsupported types become `Any` and
are written to a warning list in the converter output, so each gap is visible and can be handled later.

**Hashability: why `set[T]` and some dictionaries can't hold BHoM objects.**

A Python `set`, and the *keys* of a `dict`, can only contain **hashable** values. "Hashable" means the object
can produce a fixed number (a hash) that Python uses to find it quickly and detect duplicates. Strings,
numbers, tuples and enums are hashable. A normal mutable object is not: if its contents can change, its hash
could change, and Python would lose track of it.

Pydantic models are mutable, so by default they are **not hashable** **[verified]**:

```python
class P(BaseModel):
    X: float = 0

{P()}          # TypeError: unhashable type: 'P'
{P(): 1}       # TypeError: unhashable type: 'P'
```

C# has no such restriction: `HashSet<Point>` and `Dictionary<Frequency, double>` are fine there. If we
translated them literally to `set[Point]` or `dict[Frequency, float]`, the generated class would fail the
moment someone tried to put an object in.

How much does this matter? **[verified from the schemas]** Very little: of ~750 `HashSet` properties, nearly
all are `HashSet<string>` (the `Tags` property inherited from `BHoMObject`), which is fine as `set[str]`.
Only 6 properties are sets of BHoM objects (`ComparisonConfig` and `RevitComparisonConfig`), and 11 types
have dictionaries with non-string keys (for example `Acoustic_oM/Panel` keyed by `Frequency`, a class;
`Gradient` keyed by `decimal`, which is fine; `Graph` keyed by `Guid`, also fine. Only class keys are a problem).

Rule for the converter:
- element/key type is a string, number, enum, `Guid`, date or tuple of those → `set[T]` / `dict[K, V]`;
- element/key type is a BHoM object → use `list[T]` for the set, and `list[tuple[K, V]]` for the dictionary,
  and record the original C# type in metadata so the uniqueness/key meaning is not lost.

(The alternative, making every model `frozen=True` so it is hashable, would stop users changing any field
after creation, so we don't do it.)

### 12. Provenance and finding the right C# repo

Every generated class carries a class-level, non-field marker **[verified: a `ClassVar` named `__bhom__` is
excluded from `model_fields`]**:

```python
class ProjectIdentification(SchemaModel, IdKoPObject):
    __bhom__: ClassVar[dict[str, str]] = {
        "clr_name": "BH.oM.dKoP.ProjectIdentification",   # real C# full name (backticks and all)
        "namespace": "BH.oM.dKoP",
        "assembly": "dKoP_oM",
        "repo": "BHoM/dKoP_Toolkit",                      # from the assembly's Description attribute
    }
```

**The repo is available straight from the compiled assembly [verified].** Every oM project sets
`<Description>https://github.com/BHoM/<Repo></Description>` in its `.csproj`, which the compiler stores as the
assembly's `AssemblyDescription` attribute (the existing `IsInOrg` helper already reads it). In the local clones this
holds for **all 41 oM projects**: `Geometry_oM`, `Structure_oM` and most others → `BHoM/BHoM`, `dKoP_oM` →
`BHoM/dKoP_Toolkit`, `Revit_oM` → `BHoM/Revit_Toolkit`, `CodeCompliance_oM` → `BHoM/Test_Toolkit`, `Adapter_oM` →
`BHoM/BHoM_Adapter`, `Python_oM` → `BHoM/Python_Toolkit`, and so on. The converter therefore records `repo` at
generation time. This replaces the earlier idea of scanning every repository to build an `assembly → repo` map, and it
also resolves the known exceptions (the `BHoM` assembly and `CodeCompliance_oM`) without special cases.

The Action still **validates** the recorded repo (it exists and the App can reach it) and falls back to the folder
scan only if `repo` is missing, for example on a hand-written class. Compare repository names case-insensitively
(`Included-repositories.txt` says `dKop_Toolkit`, the real name is `dKoP_Toolkit`).

### 13. The output is a snapshot

The Python reflects one build of the C# oM. If a toolkit DLL is not present when the converter runs, its
classes silently do not exist, and references to them fall back to `Any`. The converter must print which
assemblies were loaded, which types were skipped and why, and every fallback to `Any`.

### 14. C# folders do not follow namespaces (locating and placing `.cs` files)

The generated Python path comes from the **namespace** (same rule as the JSON repo: drop `BH.oM.`, drop the first
segment, the rest become folders). The C# file path comes from wherever the developer put the file, and the two often
disagree. Example **[verified]** from the spike type `ProjectIdentification`:

| | Path |
|---|---|
| C# file | `dKoP_oM/AdministrativeInformation/ProjectIdentification.cs` (namespace `BH.oM.dKoP`) |
| Generated Python | `bhom_schema/dKoP_oM/ProjectIdentification.py` |

How common: in the local clones **625 of 1,460 oM files (43%)** sit in a folder that differs from the namespace-derived
folder. Often it is a harmless convention (enums in an `Enums/` subfolder, `Curve/` for types in `BH.oM.Geometry`), but
`dKoP_oM` (108 files), `LifeCycleAssessment_oM` (90), `Structure_oM` (65), `Environment_oM` (51) and `Geometry_oM` (44)
show it heavily.

Consequences for the Python → C# side:
- **Never derive an existing C# file path from the namespace.** Find the file by searching the assembly folder of the
  resolved repo for the declaration (`class|interface|enum|struct <Name>`), using the file name as a first guess.
- **New types:** a placement rule is needed. Proposed order: (1) the folder of existing sibling types in the same
  namespace (using the most common one), (2) an `Enums/` subfolder for enums when siblings do that, (3) the
  namespace-derived folder, (4) the assembly root. Always mention the choice in the PR so a reviewer can move the file.
- **Generics and nested types:** search for the declaration, don't trust the file name.
- Interface names don't always start with `I`: `IdKoPObject` is an **interface** (`ProjectIdentification : IdKoPObject`).
  Never classify types by name; use reflection (`IsInterface`) on the C# side and the abstract-class marker on the
  Python side.

---

## 5. Proposed type mapping **[unverified: to confirm in the spike]**

| C# | Python | Notes |
|---|---|---|
| `bool` | `bool` | |
| `byte/sbyte/short/ushort/int/uint/long/ulong` | `int` | CLR type kept in `Annotated` metadata |
| `float/double` | `float` | CLR type kept in metadata |
| `decimal` | `decimal.Decimal` | No JSON wrapper needed (JSON is out of scope) |
| `char`, `string` | `str` | |
| `DateTime`, `DateTimeOffset` | `datetime.datetime` | |
| `TimeSpan` | `datetime.timedelta` | |
| `Guid` | `uuid.UUID` | |
| `enum` | `enum.Enum` subclass | `None` → `None_` with original name recorded |
| `T?` / nullable reference | `T \| None` | |
| `T[]`, `List<T>`, `IList<T>`, `IEnumerable<T>`, `ICollection<T>` | `list[T]` | Multi-dimensional arrays → nested lists |
| `HashSet<T>`, `ISet<T>` | `set[T]` or `list[T]` | `list` if `T` is not hashable |
| `Dictionary<K,V>`, `IDictionary` | `dict[K, V]` | |
| `Tuple<...>` | `tuple[...]` | |
| `object`, generic parameter with no constraint | `Any` | |
| Interface | `abc.ABC` subclass | See gotcha 6 |
| Abstract class | `BaseModel` + `ABC` | |
| `System.Drawing.Color` | small hand-written `Color` model (A, R, G, B) | Lives in a support module |
| `Type` | `type[Any]` or `str` | Decide in spike |
| `DataTable`, `Bitmap`, delegates | `Any` / `Callable[..., Any]` | Warn in converter output |
| Generic `Foo<T>` | `class Foo_1(BaseModel, Generic[T])` | Real name in `__bhom__` |

---

## 6. Design decisions (resolved)

| # | Decision | Outcome |
|---|---|---|
| 1 | Granularity | **One C# type per Python file.** Mirrors the JSON repo and the C# folders, gives clean diffs, and lets the PR Action map class ↔ file 1:1. Revisit only if import time (gotcha 10) is a problem. |
| 2 | Package | A single wrapper package **`bhom_schema`** that contains the assembly folders: `bhom_schema/Geometry_oM/Curve/Line.py`, used as `from bhom_schema.Geometry_oM.Curve.Line import Line`. Avoids `Geometry_oM`, `Structure_oM`... becoming global import names. |
| 3 | Python version | **3.12** minimum. Lets generated generics use `class Group[T: BHoMObject]` (verified), `X \| None` and other modern syntax with no fallbacks. Anyone on older Python can't use the package. |
| 4 | Property names | Keep C# **PascalCase** unchanged. No mapping layer. |
| 5 | Metadata | Carry as much C# metadata as practical (section 7). |
| 6 | Python → C# "aligned" | Agreed: loose, structural alignment (section 8). |

Still to settle during the spike: how to render `System.Type` (`type[Any]` or `str`), and whether `Quantity`
metadata is a custom `Annotated` marker or a plain description string (leaning marker, see section 7).

---

## 7. Metadata to carry from C#

Goal: each Python class should say as much about its C# original as possible, so people (and tools such as the
Python → C# converter) get the same meaning, not just the same shape. What the oM actually uses
(attribute lines counted in the local `BHoM` clone, so approximate):

| C# attribute | Uses | Proposed Python carrier |
|---|---|---|
| `[Description("...")]` | ~3,570 | Class docstring for types; `Field(description="...")` for properties; docstring/comment for enum members |
| Quantity attributes (`[Length]`, `[Stress]`, `[Ratio]`, `[Angle]`, `[Area]`, `[YoungsModulus]`, `[Density]`, ... about 25 kinds) | ~1,000+ | `Annotated[float, Quantity("Length", "m")]` using a small marker type in a support module. The existing generator already reads `QuantityAttribute.SIUnit` and writes "measured in [unit]" into the description, so the data is easy to get |
| `[DisplayText("...")]` | ~195 | `Annotated[..., DisplayText("...")]` or `Field(title="...")` |
| `[DynamicProperty]` | ~54 | Marker on the field, plus a note in the class docstring (these are properties the JSON generator treats specially) |
| Original C# type of a field (`long`, `IList<T>`, `T[]`, ...) | all fields | `Annotated[..., ClrType("long")]` (gotcha 1) |
| Full C# name, namespace, assembly, repo (from `AssemblyDescription`) | all types | `__bhom__` class marker (gotcha 12) |
| Generic parameters and constraints | 34 types | `TypeVar` bounds, with extra constraints listed in `__bhom__` |
| Interfaces / base type | all types | Real Python bases, in a safe order (gotcha 6) |
| Obsolete / version attributes | not in the top 25; check in the spike | `__bhom__["obsolete"]` if present |

Keep the marker types (`Quantity`, `ClrType`, `DisplayText`) in one small hand-written support module, so the
converter and the Python → C# converter agree on them. Because they are plain `Annotated` metadata, Pydantic
ignores them at runtime and Pyright is unaffected.

Note on inheritance: the JSON schemas list every inherited property again on each type, because they come
from reflection with inherited members included. In Python, emit **only the properties declared on the class
itself** and let inheritance supply the rest. That is how Python and Pydantic expect it.

---

## 8. Python → C# converter (looser scope)

Input: the generated and hand-edited Pydantic classes. It reads, via `model_fields`, `typing.get_type_hints`,
the `Annotated` markers (section 7) and `__bhom__`.

Output: draft C# for the linked PR. "Aligned" means: same type name, namespace and assembly; same base types
and interfaces; same property names and (as far as the metadata allows) types; same enum members; descriptions
and quantities carried across as attributes. It does not reproduce comments, ordering, headers, constructors or
default expressions. A reviewer finishes the PR.

Because it is looser, most of gotchas 3, 4, 5, 6 do not apply in this direction. Gotchas 1 and 12 do.

---

## 9. Tooling: type hints, Pyright, Pylance, Pydantic

Someone suggested three practices. Recommendation on each:

**Type hints everywhere: yes.** The generated classes are fully typed by nature (every field has a type). The
hand-written Python in this repo (the Python → C# converter, support module, tests) should also be fully
typed, and CI should enforce it.

**Pyright / Pylance: use both; they are not alternatives.**
- **Pyright** is the open-source type checker. It is a command-line tool, so it runs in CI, in pre-commit, or
  from a test. It is the one that can *fail a build*.
- **Pylance** is Microsoft's VS Code extension. It is built on Pyright's engine and adds editor features
  (autocomplete, hover docs, quick fixes, import suggestions). It is free to use but closed source, and works
  in VS Code only.
- So: developers use Pylance in the editor (if they use VS Code); CI runs Pyright as the gate. Commit a
  `pyrightconfig.json` so both use the same rules, and pin the Pyright version in the dev requirements so
  results don't change under you.
- If a team member uses PyCharm or another editor, Pyright (or its language server) still works for them.
  mypy would also work but gains nothing here and understands Pydantic less directly.

**Pydantic for external inputs: yes, with a precise meaning here.** Our generated classes *are* the Pydantic
models, which gives construction-time validation (wrong field types, missing required fields, wrong interface
implementer are all rejected). In the converter tooling, any structured input it reads (for example config
files or an internal type-list file used by tests) should also be validated through Pydantic models rather than
raw dictionaries. That internal test file is just tooling data; it has nothing to do with BHoM JSON.

**Evidence [verified]** (Pyright 1.1.414, strict mode, Python 3.12, Pydantic 2.13.5):
- Pyright understands Pydantic constructors. On sample generated-style classes it flagged, with no extra
  plugin: a string passed to a `float` field, a missing required argument, an object that isn't an
  `IGeometry` passed to an `IGeometry` field, and a misspelled attribute (`.Strt`).
- Generated-style code (ABC interfaces, `ClassVar` marker, `arbitrary_types_allowed`) passed strict mode.
- A class `class Group[T: BHoMObject]` was understood: `Group[W](...).Elements` is `list[W]`.
- One strict-mode warning to design around: `Field(default_factory=list)` inside a generic class reads as
  `list[Unknown]`. The generator should emit a typed factory for those, and the spike should confirm strict
  mode stays clean over the generated sample.
- Speed on 2,000 files is **not** yet measured; add it to the spike.

---

## 10. Testing approach (no JSON anywhere)

1. **Generated package imports cleanly:** import every generated module, call `model_rebuild()` on every
   model, fail on any `PydanticUserError` or `NameError`. This catches gotchas 5, 7, 8, 9 and 10.
2. **Type-check the generated package:** run Pyright (strict, section 9) over `bhom_schema`. This catches
   invalid hints, wrong imports and missing names that the import test can miss.
3. **Structural check against C#:** the converter also dumps a language-neutral list of types (name,
   namespace, assembly, base, interfaces, properties with CLR types). A pytest compares each Python class's
   `model_fields` and `__bhom__` to that list.
4. **Converter unit tests:** the spike types in section 11 as fixtures.
5. **Python → C# alignment test:** generate C# from the Python, compile it with Roslyn, and compare the same
   structural list with the original (loose comparison, per section 8).
6. **Build step (required by repo policy):** the plan must end with building the C# converter projects and
   running the Python test suite.

---

## 11. First spike: ten real test types

Chosen by scanning `BHoM_JSONSchema` (and checking the C# source for inheritance). Together they cover every
gotcha above. Ten slots; slot 8 is a pair, so eleven types, plus the types they depend on (`Point`, `IGeometry`, ...)
which are generated and import-tested automatically.

| # | Type | Why it is in the spike |
|---|---|---|
| 1 | `dKoP_oM/ProjectIdentification` (C#: `dKoP_Toolkit/dKoP_oM/AdministrativeInformation/ProjectIdentification.cs`) | The new baseline: a flat class of four `virtual string` properties with `= ""` defaults, no `[Description]`, implementing an interface (`IdKoPObject : IObject`, an interface whose name has no `I` prefix) rather than deriving from `BHoMObject`. It also exercises what no other spike type does: a **toolkit repo** (`BHoM/dKoP_Toolkit`, so provenance and repo resolution matter), and a C# folder (`AdministrativeInformation/`) that differs from the namespace folder (`BH.oM.dKoP`, so the Python path is `dKoP_oM/ProjectIdentification.py`) (gotchas 12, 14). It replaces `Point` as the "simplest realistic class": the two have the same shape (flat, interface-only, no `BHoMObject` base), and `Point` is still generated and checked as the type of `Line.Start` and `Line.End`. |
| 2 | `Geometry_oM/Line` | Class referencing another class (`Start`, `End` of type `Point`), implements an interface, has a required `bool` (`Infinite`). Its C# file lives in `Curve/` while the namespace is `BH.oM.Geometry` (gotcha 14). |
| 3 | `Geometry_oM/ICurve` (+ its parents `IGeometry`, `IElement1D`, `IObject`) | Interface chain. `ICurve : IGeometry, IElement1D` is a real multi-interface case for the MRO ordering (gotcha 6), and `IGeometry` has 37 implementers in the schema. Add `Line` as a second implementer in the same test. |
| 4 | `BHoM/BHoMObject` | Base class with defaulted fields (`Name`, `Tags` as `HashSet<string>`, `CustomData` dictionary, `Fragments`). Checks gotchas 3 and 4. |
| 5 | `Structure_oM/Elements/Bar` | Subclass of `BHoMObject` with required fields (`Start`, `End`, `SectionProperty`, ...) after defaulted base fields, plus a quantity-annotated property (`OrientationAngle`) for metadata (section 7). |
| 6 | `Graphics_oM/Enums/GradientCenteringOptions` | Enum with a member named `None` (gotcha 7). |
| 7 | ``BHoM/BHoMGroup`1`` | Generic with a type constraint; the backtick name (gotcha 5). |
| 8 | `Acoustic_oM/Room` **and** `Architecture_oM/Elements/Room` | Same simple name in two assemblies (gotcha 8). Counted as one slot; they are tested together. |
| 9 | `Graphics_oM/Gradient` | A dictionary whose key is a `decimal`, and `System.Drawing.Color` values (gotcha 11, type-mapping table). |
| 10 | `BHoM/ComparisonConfig` | `HashSet` of BHoM objects (`PropertyNumericTolerances`) and several dictionaries, the hashability case (gotcha 11). |

Optional extra if time allows: `BHoM/UsageLogEntry` (a `DateTime` field, `$date` in the schema) for the
`DateTime` → `datetime` mapping.

No true reference cycle exists among concrete classes in this set (consistent with the 0 measured in
section 3), so the spike should add one hand-written cyclic fixture pair to exercise the bottom-of-module
import pattern from gotcha 9.

**Success criteria:** the generated package imports; every model rebuilds; Pyright strict is clean (apart from
agreed exceptions); the structural check passes against the C# type list; the Python → C# draft compiles;
timing for the import and Pyright runs is recorded so the full 2,000-type run can be estimated.

---

## Appendix: experiment log

Run in a throw-away virtual environment, not part of the repo.

| Experiment | Result |
|---|---|
| Pydantic subclass with required field after defaulted base | Works |
| Plain dataclass, same shape | `TypeError: non-default argument follows default argument` |
| Interface as `ABC`, field typed with it | Accepts implementers, keeps subclass, rejects others |
| `class M(IFoo, IBar)` with `IBar(IFoo)` | `TypeError` (inconsistent MRO) |
| `class M(IBar, IFoo)` | Works |
| `Enum("E", {"None": 0})` | Works, access via `E["None"]` |
| Enum members `name`, `value` | Work on 3.12 |
| `ClassVar` `__bhom__` on a model | Not treated as a field |
| Mutable list default | Not shared between instances |
| `Generic[T]` model with bound `TypeVar` | Works; wrong element type rejected |
| Field named `type`, then annotation `type[int]` | `TypeError` |
| Class named ``Output`1`` created dynamically / written in source | Works dynamically / `SyntaxError` in source |
| Cross-package cycle with `TYPE_CHECKING` only | Works only if caller has both names in scope; otherwise "not fully defined" |
| Cross-package cycle with bottom-of-module imports + `model_rebuild()` | Works in both import orders |
| 2,000 synthetic models imported | about 3–4 s cold |
| Name clash scan over all 2,007 types and 16,153 properties | Findings in section 3 |
| Python-level reference cycles (interfaces as dead ends), from the schemas | 0 groups |
| Same cycles if interfaces list their implementers | 15 groups, largest 25 types |
| `set` / `dict` keyed by a Pydantic model | `TypeError: unhashable type` |
| `frozen=True` model | Hashable (not adopted) |
| PEP 695 generic `class Group[T: BHoMObject](BaseModel)` | Works on 3.12 |
| Pyright 1.1.414 strict on generated-style code | Clean; flagged bad argument type, missing argument, wrong interface, typo attribute |
| Pyright strict, `Field(default_factory=list)` in a generic class | `list[Unknown]` warning |
