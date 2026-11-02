Updated todo list

Searched for files matching `**/Environment_oM/**/Project*.cs`, no matches

Searched for files matching `**/Physical_oM/**/*.cs`, 20 matches

Searched for files matching `**/Structure_oM/**/*.cs`, 20 matches

No matches found. Your search pattern might be excluded completely by either the search.exclude settings or .*ignore files.
If you believe that it should have results, you can check into the .*ignore files and the exclude setting (here are some excluded patterns for reference:[**/node_modules,**/bower_components,**/*.code-search]).
Then if you want to include those files you can call the tool again by setting "includeIgnoredFiles" to true.

Searched for regex `class Storey\b|class Project\b|class Floor\b|class Grid\b"` (`**/Physical_oM/**`), 1 result

Searched for regex `class Column\b|class Beam\b|class Slab\b|class Panel\b|class Foundation\b|class Pile\b|class Material\b|class StructuralSystem\b|class GravitySystem\b|class LateralSystem\b|class ShearWall\b"` (`**/Structure_oM/**`), 2 results

Read 

Read 

Read 

Searched for regex `class Column|class Beam|class IFoundation|class Foundation|class Material|class StructuralSystem|class GravitySystem|class LateralSystem|class ShearWall` (`**/Structure_oM/**`), 1 result

Read 

Read 

No matches found. Your search pattern might be excluded completely by either the search.exclude settings or .*ignore files.
If you believe that it should have results, you can check into the .*ignore files and the exclude setting (here are some excluded patterns for reference:[**/node_modules,**/bower_components,**/*.code-search]).
Then if you want to include those files you can call the tool again by setting "includeIgnoredFiles" to true.

Searched for regex `class.*Storey|class.*Level\b`, 4 results

Read 

Read 

Read 

Searched for regex `class Grid\b|GridLine|class.*Grid`, 5 results

Read 

Read 

Read 

Read 

Read 

Read 

No matches found. Your search pattern might be excluded completely by either the search.exclude settings or .*ignore files.
If you believe that it should have results, you can check into the .*ignore files and the exclude setting (here are some excluded patterns for reference:[**/node_modules,**/bower_components,**/*.code-search]).
Then if you want to include those files you can call the tool again by setting "includeIgnoredFiles" to true.

Searched for regex `GrossFloorArea|FloorArea|RoofArea|StoreysAboveGround|StoreysBelowGround|FloorToFloorHeight`, 3 results

Read 

Searched for regex `ProjectName|ProjectNumber|JobNumber|ProjectID|ProjectId`, 12 results

Read 

No matches found. Your search pattern might be excluded completely by either the search.exclude settings or .*ignore files.
If you believe that it should have results, you can check into the .*ignore files and the exclude setting (here are some excluded patterns for reference:[**/node_modules,**/bower_components,**/*.code-search]).
Then if you want to include those files you can call the tool again by setting "includeIgnoredFiles" to true.

Read 

No matches found. Your search pattern might be excluded completely by either the search.exclude settings or .*ignore files.
If you believe that it should have results, you can check into the .*ignore files and the exclude setting (here are some excluded patterns for reference:[**/node_modules,**/bower_components,**/*.code-search]).
Then if you want to include those files you can call the tool again by setting "includeIgnoredFiles" to true.

Read 

Read 

No matches found. Your search pattern might be excluded completely by either the search.exclude settings or .*ignore files.
If you believe that it should have results, you can check into the .*ignore files and the exclude setting (here are some excluded patterns for reference:[**/node_modules,**/bower_components,**/*.code-search]).
Then if you want to include those files you can call the tool again by setting "includeIgnoredFiles" to true.

Read 

Read , lines 1 to 55

Read , lines 1 to 60

Now I have enough to map the whole document against the existing BHoM object model. Here's the breakdown:

## Summary

The required schema describes **project-level benchmarking/summary metrics** (e.g. "typical column size", "stories above ground", "material volume distribution"). BHoM's existing oM classes instead model **individual geometric/analytical elements** (an actual `Column` with a `Location` and section `Property`, an actual `Panel`/`PadFoundation` with real geometry). Because of this mismatch in level of abstraction, almost none of the requested properties already exist — only a few concepts have a loose, partial analogue.

### Environment_oM → `project`
| Required property | Status |
|---|---|
| `Project_number` | **New** — no `Project` class exists in `Environment_oM`. Closest analogues are `ProjectNumber` in `Audit.cs:74` and `ProjectName` in `LifeCycleAssessmentScope.cs:71`, but neither lives in `Environment_oM` and neither is a dedicated `Project` class with both fields. |
| `Project_name` | **New** (same as above) |

→ You'll need a brand-new `BH.oM.Environment.Elements.Project` class (or similar) with both properties.

### Physical_oM
| Required class/property | Status |
|---|---|
| `Storey` (typical_slab_to_slab_height, stories_above_ground, stories_below_ground) | **New.** No `Storey` class exists in `Physical_oM`. `Level.cs` only models a single elevation plane, not storey counts. |
| `Floor_area` (gross_slab_area_non_roof, roof_area) | **New.** `Floor.cs` is a geometric surface element (`ISurface`), it has no area/roof summary properties. Closest is `FloorArea`/`ConstructedFloorArea` in `IStructEEvaluationConfig.cs:43`, but that's a single generic value, not split gross/roof. |
| `Grid_spacing` (typical_x_spacing_m, typical_y_spacing_m) | **New.** `Grid.cs` models an actual 1D gridline (geometry), not a typical-spacing summary value. |

### Structure_oM (tool-focused)
| Required class/property | Status |
|---|---|
| `Base_structural_element.Is_refurbishment` | **New.** No common base class with this flag exists. |
| `Column` (typical_material/size/count_per_slab/material_distribution) | **Partial reuse of class identity only.** `Column.cs` exists but only has `Location` + `Property` (a real section/material for one physical column) — none of the "typical/aggregate" properties exist. |
| `Beam` (same pattern) | Same as Column — `Beam.cs` exists but lacks these aggregate fields. |
| `Slab` (typical_type/roof_type/size) + depth/ground-slab/material_distribution fields | **Partial reuse.** Slabs are modeled as `Panel.cs` with an `ISurfaceProperty` (e.g. `ConstantThickness.cs` has `Thickness` + `Material` + `PanelType`), which is conceptually close to depth/type/material, but there's no "typical/benchmark" wrapper class matching the doc's flat property list. |
| `Foundation` (foundation_type, pile_count, pile_volume) | **New.** `Pile.cs`, `PadFoundation.cs`, `PileFoundation.cs` model actual individual foundation geometry, not count/volume/type summary stats. |
| `Material` (material_volumes_above/below_ground) | **New.** No such aggregate class exists in `Structure_oM`, `Matter_oM`, or `LifeCycleAssessment_oM`. |
| `Structural_system` → `Gravity_system`, `Lateral_system` (incl. shear wall thickness) | **New.** No `StructuralSystem`, `GravitySystem`, `LateralSystem`, or shear-wall classes exist anywhere in the repo. |

## Conclusion
None of the leaf properties listed in the doc already exist as named properties anywhere in BHoM — they describe early-stage/benchmarking summary data, while existing `Environment_oM`/`Physical_oM`/`Structure_oM` classes describe concrete, individual building elements. You can **reuse the class names/concepts** (`Column`, `Beam`, `Panel`-as-slab, `Pile`/`PadFoundation`-as-foundation) as a naming/semantic starting point, and reuse `BuildingBenchmarkingData`-style patterns (see `BuildingBenchmarkingData.cs`) for the High/Average/Low benchmarking idiom, but every property in your doc will need to be **newly authored**, most likely as a new set of "early-stage benchmarking" classes (e.g. under a new project or inside `LifeCycleAssessment_oM`/`Structure_oM`) rather than by extending the existing geometric element classes directly.

Created 2 todos