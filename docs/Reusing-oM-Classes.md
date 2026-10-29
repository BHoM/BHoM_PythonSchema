I've checked the oM for a direct project → building → storey → slab containment chain but found none, so I'm now looking into generic container classes and cross-discipline models instead.

The corpus has no ready-made project → building → storey → slab chain. The oM has no `Project`, `Site` or `Storey` container. `Level` and `Building` exist, but no other class has a property of those types, so none of them are nested in anything.

Containment between levels would come from composing the classes below. In `bhom_schema`, paths follow `<Assembly>/<namespace after BH.oM>/<Type>.py`.

## What exists at each level

| Level | Candidates | Notes |
|---|---|---|
| **Project** | `LifeCycleAssessment_oM/LifeCycleAssessment/ProjectLifeCycleAssessment` | The only class with a project-to-elements link: `LCAScope` (project name, area, building lifespan, `Location`) plus `Elements: List[IElementM]`. |
| | `dKoP_oM/dKoP/ProjectIdentification`, `ProjectTeam` | Reference, name and location strings; client, architect and engineer contact details. |
| | `LifeCycleAssessmentScope`, `Inspection_oM/Audit`, `MidasCivil_oM/Metadata` | Project number or name as loose fields. |
| **Site** | `Environment_oM/Climate/Location`, `Ground_oM` (`Borehole`, `Stratum`), `OpenStreetMap_oM` | Only site context; no site container. |
| **Building** | `Environment_oM/Elements/Building` | `Location`, `Elevation`, `Type`. Holds no reference to spaces or panels. |
| **Storey** | `Spatial_oM/SettingOut/Level` (`Name`, `Elevation`), `Spatial_oM/SettingOut/Grid` | `Level` is the only real storey class. Nothing references it. |
| | `dKoP_oM/dKoP/SettingOut.BuildingLevel` | A string. |
| | `ETABS_oM/ETABSId.Story` and `Revit_oM/ViewPlan.LevelName` | Adapter-specific strings. |
| **Space / room** | `Environment_oM/Elements/Space`, `Zone`; `Architecture_oM/Elements/Room`, `Ceiling` | Perimeter plus location. `Space.Zones` holds names. |
| **Slab / floor** | `Physical_oM/Elements/Floor` | Surface location, `Construction`, `Openings`. |
| | `Structure_oM/Elements/Panel`, `Surface` | `Property` is an `ISurfaceProperty`. The slab types are `ConstantThickness`, `Ribbed`, `Waffle`, `HollowCore`, `SlabOnDeck`, `ToppedSlab`, `Layered` and others under `Structure_oM/SurfaceProperties`. |
| | `dKoP_oM/dKoP/UpperFloor` | A product data sheet for a floor, not a model object. |
| **Other elements** | `Physical`: `Wall`, `Roof`, `Column`, `Beam`, `Bracing`, `Door`, `Window`, `Void`, `Pile`, `PadFoundation`. `Structure`: `Bar`, `Node`, `RetainingWall`. `Facade`: `CurtainWall`, `Panel`. `MEP`: `Duct`, `Pipe`, `AirHandlingUnit`, fixtures. | |
| **Below element** | `Physical/Constructions/Construction` → `Layer` → `Material`; `Physical/Materials/MaterialComposition` | |

## Routes (hierarchies that actually exist)

- **Route A, Physical (building model).**
  - `Floor`/`Wall`/`Roof` → `Openings: List[IOpening]` (`Door`, `Window`, `Void`) → `Construction` → `Layer` → `Material`.
  - `Column`, `Beam`, `Bracing` and `Pile` sit beside them. `Level`, `Grid` and `Room` are not wired in.
  - This is the closest to "slab etc.", and these classes are the most reusable.
- **Route B, Environment (energy and analysis model).**
  - `Building` (+`Location`) and `Space` (+`Perimeter`) are separate.
  - `Panel` → `Opening` → `Edge` carries `ConnectedSpaces`, a list of strings.
  - Containment is by name, not by object.
- **Route C, Structure (analytical model).**
  - `Panel` or `Surface` → `ISurfaceProperty` → `Material`.
  - `Bar` → `Node`.
  - `RetainingWall` → `Stem` + `PadFoundation`.
  - Groups use `BHoMGroup[T]`; `DesignGroup` holds member ids.
  - A structural slab is a `Panel` with a slab property.
- **Route D, Facade.** `CurtainWall` → `Panel` → `Opening` → `FrameEdge`.
- **Route E, dKoP (product data).**
  - Every part type (`UpperFloor`, `FlatRoof`, `ExternalWall`, `Window` and others) carries `AdministrativeInformation`, which holds `ProjectIdentification` and `ProjectTeam`.
  - `PartIdentification.BuildingReference` and `SettingOut.BuildingLevel` link parts to a building and level as strings.
  - It is the only model that names project, building and level together, but it is one document per part.
- **Route F, LCA.** `ProjectLifeCycleAssessment` → `Elements: List[IElementM]`. `IElementM` is the interface for anything with a material, which covers all of Physical and Structure.
- **Route G, generic nesting.**
  - `BHoMGroup[T]` (`Elements`), `Tree[T]` (`Name`, `Value`, `Children`), `DomainTree[T]` and `Graph[T]`.
  - Every `BHoMObject` also has `Fragments`, `Tags` and `CustomData`.
  - `Tree[Level|Floor|…]` gives project > building > storey > slab directly.
  - `Tree_1` and `DomainTree_1` currently fail to import because of the generic self-reference bug in the phase 7 list.

I found nothing else useful. `Planning_oM` has `ConstructionPhase` and `IPhase` (start and end times), but its other classes (`Issue`, `PullRequest`, `Repository`) are GitHub concepts.

## Recommendation

The BHoM oM doesn't model a project tree itself. Use `Building`, `Level`, `Floor`, `Wall`, `Room` and `Opening` for the nodes. For the tree, either add a thin new layer or use `Tree[T]` or `BHoMGroup[T]` once the generic bug is fixed.

If you want a concrete skeleton (a `Project`, `Building` and `Storey` mapped onto these classes with `Level` linked to `Floor`), I can draft it. It would need either new C# oM classes or a Python-only layer, and that choice is yours.