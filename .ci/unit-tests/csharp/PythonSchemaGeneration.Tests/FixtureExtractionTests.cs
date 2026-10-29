using BH.oM.FixtureAlpha;
using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Extraction;
using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;

namespace PythonSchemaGeneration.Tests
{
    public class FixtureExtractionTests
    {
        [Description("Returns the generated type for a fixture System.Type from the shared fixture run. The tests in this class use it to inspect one type's " +
            "Python text, bases and properties.")]
        private static RenderedType R(Type type) { return FixtureOutput.Rendered(type.FullName); }

        [Description("Joins the simple names of the given types with commas so a type's bases can be compared as one string. Used by the base-type tests.")]
        private static string Names(IEnumerable<Type> types) { return string.Join(",", types.Select(t => t.Name)); }

        /***************************************************/
        /**** Selection                                 ****/
        /***************************************************/

        [Test]
        [Description("Checks that TypeSelector selects oM classes, enums and generic type definitions but not constructed generics or non-oM types. Protects the " +
            "generator's type selection stage.")]
        public void SelectorKeepsOmTypesAndDropsOthers()
        {
            Assert.That(TypeSelector.IsSelected(typeof(PointLike)), Is.True);
            Assert.That(TypeSelector.IsSelected(typeof(SupportKind)), Is.True);
            Assert.That(TypeSelector.IsSelected(typeof(Wrapper<>)), Is.True);
            Assert.That(TypeSelector.IsSelected(typeof(Wrapper<Beam>)), Is.False, "constructed generics are not selected, only the definition");
            Assert.That(TypeSelector.IsSelected(typeof(string)), Is.False);
            Assert.That(TypeSelector.IsSelected(typeof(FixtureOutput)), Is.False);
        }

        [Test]
        [Description("Checks that a type is marked as an interface by reflection and not by an I prefix in its name. Protects the TypeKind that the emitter uses " +
            "to write interface classes.")]
        public void InterfaceIsDetectedByReflectionNotByName()
        {
            Assert.That(R(typeof(ThingIdentity)).Model.Kind, Is.EqualTo(TypeKind.Interface));
            Assert.That(R(typeof(ProjectLike)).Model.Kind, Is.EqualTo(TypeKind.Class));
        }

        /***************************************************/
        /**** Bases                                     ****/
        /***************************************************/

        [Test]
        [Description("Checks that interfaces already implied by another listed base are removed from a type's bases. Protects the base list that extraction hands " +
            "to the emitter.")]
        public void ImpliedInterfacesAreDropped()
        {
            Assert.That(Names(R(typeof(ICurveLike)).Model.Bases), Is.EqualTo("IElement1DLike,IGeometryLike"));
            Assert.That(Names(R(typeof(LineLike)).Model.Bases), Is.EqualTo("ICurveLike,ILabelled"));
            Assert.That(Names(R(typeof(PointLike)).Model.Bases), Is.EqualTo("IGeometryLike"));
        }

        [Test]
        [Description("Checks that a class's own base class is listed first, followed by its interfaces. Protects the Python base order that the generator writes.")]
        public void ClassBaseComesFirstThenInterfaces()
        {
            Assert.That(Names(R(typeof(ImmutableThing)).Model.Bases), Is.EqualTo("BHoMObject,IImmutable"));
        }

        /***************************************************/
        /**** Provenance                                ****/
        /***************************************************/

        [Test]
        [Description("Checks that the repository of a type is read from the GitHub URL in its assembly description and written into the generated class marker. " +
            "Protects the provenance that py2cs later uses to find the owning C# repository.")]
        public void RepoComesFromTheAssemblyDescription()
        {
            Assert.That(R(typeof(ProjectLike)).Model.Repo, Is.EqualTo("BHoM/CSharpSchema_Test"));
            Assert.That(FixtureOutput.Rendered(typeof(BH.oM.FixtureBeta.PointLike).FullName).Model.Repo, Is.EqualTo("BHoM/CSharpSchema_Test"));
            Assert.That(R(typeof(ProjectLike)).Text, Does.Contain("'repo': 'BHoM/CSharpSchema_Test'"));
            Assert.That(R(typeof(ProjectLike)).Text, Does.Contain("'namespace': 'BH.oM.FixtureAlpha'"));
            Assert.That(R(typeof(ProjectLike)).Text, Does.Contain("'assembly': 'FixtureAlpha_oM'"));
        }

        [Test]
        [Description("Checks that every generated class carries the clr_name, namespace, assembly, repo and kind marker entries. Protects the marker that py2cs, " +
            "alignment and verification rely on.")]
        public void EveryGeneratedClassCarriesTheFullMarker()
        {
            foreach (RenderedType type in FixtureOutput.Result.Types)
            {
                Assert.That(type.Text, Does.Contain("'clr_name': '" + type.Model.ClrName + "'"), type.Model.ClrName);
                Assert.That(type.Text, Does.Contain("'namespace':"), type.Model.ClrName);
                Assert.That(type.Text, Does.Contain("'assembly':"), type.Model.ClrName);
                Assert.That(type.Text, Does.Contain("'repo': '"), type.Model.ClrName);
                Assert.That(type.Text, Does.Contain("'kind':"), type.Model.ClrName);
            }
        }

        /***************************************************/
        /**** Defaults and required fields              ****/
        /***************************************************/

        [Test]
        [Description("Checks that string property defaults and the property order are read from a default instance and written to Python. Protects the default " +
            "extraction stage.")]
        public void StringDefaultsAreRead()
        {
            string text = R(typeof(ProjectLike)).Text;
            Assert.That(text, Does.Contain("ProjectReference: str = ''"));
            Assert.That(text, Does.Contain("AdditionalReferences: str = ''"));
            Assert.That(R(typeof(ProjectLike)).Properties.Select(p => p.Name), Is.EqualTo(new[] { "ProjectReference", "ProjectName", "ProjectLocation", "AdditionalReferences" }));
        }

        [Test]
        [Description("Checks that properties of an immutable type are written as required fields with no default. Protects how the Python model reflects " +
            "constructor-initialised C# types.")]
        public void ImmutableTypeFieldsAreRequired()
        {
            RenderedType thing = R(typeof(ImmutableThing));
            Assert.That(thing.Properties.Single(p => p.Name == "Id").HasDefault, Is.False);
            Assert.That(thing.Properties.Single(p => p.Name == "Length").HasDefault, Is.False);
            Assert.That(thing.Text, Does.Contain("    Id: str\n"));
            Assert.That(thing.Text, Does.Contain("    Length: float\n"));
        }

        [Test]
        [Description("Checks that object defaults become default factories and null defaults become None on optional types. Protects default value emission for " +
            "reference-typed properties.")]
        public void ObjectAndNullDefaults()
        {
            Assert.That(R(typeof(LineLike)).Text, Does.Contain("Start: PointLike = Field(default_factory=lambda: PointLike())"));
            Assert.That(R(typeof(LineLike)).Text, Does.Contain("Label: str | None = None"));
            Assert.That(R(typeof(Beam)).Text, Does.Contain("Start: PointLike | None = None"));
        }

        [Test]
        [Description("Checks that dates, GUIDs, decimals, colours, time spans, quoted strings and extreme floats are written as valid Python defaults, and that " +
            "inherited properties are not repeated. Protects PyLiteral and DefaultFormatter output.")]
        public void VolatileAndScalarDefaults()
        {
            string text = R(typeof(Scalars)).Text;
            Assert.That(text, Does.Contain("Created: datetime = Field(default_factory=datetime.now)"));
            Assert.That(text, Does.Contain("Fixed: datetime = datetime(2020, 1, 2, 3, 4, 5, 0)"));
            Assert.That(text, Does.Contain("Key: UUID = UUID(int=0)"));
            Assert.That(text, Does.Contain("Cost: Decimal = Decimal('1.5')"));
            Assert.That(text, Does.Contain("Colour: Color = Field(default_factory=Color)"));
            Assert.That(text, Does.Contain("Duration: timedelta = timedelta(seconds=90.0)"));
            Assert.That(text, Does.Contain("Quote: str = "));
            Assert.That(text, Does.Contain("Big: float = 1.7976931348623157e+308"));
            Assert.That(text, Does.Not.Contain("BHoM_Guid"), "inherited properties are not repeated");
        }

        [Test]
        [Description("Checks that enum defaults are written as members of the generated enum class with a top-level import. Protects default emission and the " +
            "import ordering for enum properties.")]
        public void EnumDefaultsUseTheEnumClass()
        {
            string text = R(typeof(Beam)).Text;
            Assert.That(text, Does.Contain("Support: SupportKind = SupportKind.Pinned"));
            Assert.That(text, Does.Contain("Flags: Options = Options.A"));
            Assert.That(text, Does.Contain("from bhom_schema.FixtureAlpha_oM.SupportKind import SupportKind\n"), "enum defaults need a top level import");
        }

        /***************************************************/
        /**** Type mapping                              ****/
        /***************************************************/

        [Test]
        [Description("Checks that CLR types with no exact Python equivalent (long, float, arrays, enumerables) are kept in a ClrType annotation, while tuples and " +
            "nullables map directly. Protects TypeMapper, which lets the Python round trip back to the same C# types.")]
        public void NonDefaultClrTypesAreKept()
        {
            string beam = R(typeof(Beam)).Text;
            Assert.That(beam, Does.Contain("Count: Annotated[int, ClrType('long')] = 3"));
            Assert.That(beam, Does.Contain("Small: Annotated[float, ClrType('float')] = 0.5"));

            string collections = R(typeof(Collections)).Text;
            Assert.That(collections, Does.Contain("Values: Annotated[list[float], ClrType('double[]')]"));
            Assert.That(collections, Does.Contain("Words: Annotated[list[str], ClrType('System.Collections.Generic.IEnumerable<string>')]"));
            Assert.That(collections, Does.Contain("Pair: tuple[int, str] | None = None"));
            Assert.That(collections, Does.Contain("OptionalCount: int | None = None"));
            Assert.That(collections, Does.Contain("Anything: Any | None = None").Or.Contain("Anything: Any = None"));
        }

        [Test]
        [Description("Checks that sets and dictionaries of hashable items map to set and dict, while unhashable items fall back to lists with the original type " +
            "kept. Protects the TypeMapper hashability rule.")]
        public void SetsAndDictionariesFallBackToListsForUnhashableItems()
        {
            string text = R(typeof(Collections)).Text;
            Assert.That(text, Does.Contain("Names: set[str] = Field(default_factory=set)"));
            Assert.That(text, Does.Contain("Lookup: dict[str, float] = Field(default_factory=dict)"));
            Assert.That(text, Does.Contain("Points: Annotated[list[PointLike], ClrType('System.Collections.Generic.HashSet<BH.oM.FixtureAlpha.PointLike>')]"));
            Assert.That(text, Does.Contain("ByPoint: Annotated[list[tuple[PointLike, str]], ClrType('System.Collections.Generic.Dictionary<BH.oM.FixtureAlpha.PointLike, string>')]"));
        }

        [Test]
        [Description("Checks that TypeMapper.IsHashable accepts strings, enums, GUIDs and tuples of hashable items and rejects oM objects. Protects the rule that " +
            "decides between set or dict and a list.")]
        public void HashableRule()
        {
            Assert.That(TypeMapper.IsHashable(typeof(string)), Is.True);
            Assert.That(TypeMapper.IsHashable(typeof(SupportKind)), Is.True);
            Assert.That(TypeMapper.IsHashable(typeof(Guid)), Is.True);
            Assert.That(TypeMapper.IsHashable(typeof(Tuple<int, string>)), Is.True);
            Assert.That(TypeMapper.IsHashable(typeof(PointLike)), Is.False);
            Assert.That(TypeMapper.IsHashable(typeof(Tuple<int, PointLike>)), Is.False);
        }

        [Test]
        [Description("Checks that delegates and System.Type properties are mapped to Any with the original CLR type kept. Protects TypeMapper's fallback for types " +
            "with no Python equivalent.")]
        public void UnsupportedTypesBecomeAnyWithTheOriginalTypeKept()
        {
            string text = R(typeof(Scalars)).Text;
            Assert.That(text, Does.Contain("Callback: Annotated[Callable[..., Any], ClrType('System.Func<double, double>')] | None = None").Or.Contain("Callback: Annotated[Callable[..., Any] | None"));
            Assert.That(text, Does.Contain("TypeRef: Annotated[Any, ClrType('System.Type')]").Or.Contain("TypeRef: Annotated[Any | None, ClrType('System.Type')]"));
        }

        /***************************************************/
        /**** Generics, enums, names                    ****/
        /***************************************************/

        [Test]
        [Description("Checks that a generic oM class is named with its arity, declares its type parameter with its bound and keeps the original CLR name in the " +
            "marker. Protects naming and emission of generics.")]
        public void GenericTypeUsesArityNameAndBound()
        {
            RenderedType wrapper = R(typeof(Wrapper<>));
            Assert.That(wrapper.Ref.Name, Is.EqualTo("Wrapper_1"));
            Assert.That(wrapper.Text, Does.Contain("class Wrapper_1[T: IBHoMObject](BHoMObject):"));
            Assert.That(wrapper.Text, Does.Contain("'clr_name': 'BH.oM.FixtureAlpha.Wrapper`1'"));
            Assert.That(wrapper.Text, Does.Contain("Items: list[T] = Field(default_factory=lambda: [])"));
        }

        [Test]
        [Description("Checks that a generic class referring to itself in a default value uses a lambda default factory. Protects emission of self-referencing " +
            "generic defaults.")]
        public void GenericClassNamingItselfInADefaultUsesALambda()
        {
            RenderedType tree = R(typeof(TreeLike<>));
            Assert.That(tree.Text, Does.Contain("Children: dict[str, TreeLike_1[T]] = Field(default_factory=lambda: {})"));
        }

        [Test]
        [Description("Checks that an enum default that is not a member makes the field required and records a warning. Protects defaults handling and the warning " +
            "that the baseline compares.")]
        public void EnumDefaultThatIsNotAMemberMakesTheFieldRequired()
        {
            Assert.That(R(typeof(SparseHolder)).Text, Does.Contain("    Level: Sparse\n"));
            Assert.That(R(typeof(SparseParent)).Text, Does.Contain("    Holder: SparseHolder\n"));
            Assert.That(FixtureOutput.Result.Reporter.Warnings, Has.Some.Contain("is not a member of enum"));
        }

        [Test]
        [Description("Checks that a two-dimensional array default is written as rows in a default factory, with its dictionary type kept. Protects array default emission.")]
        public void TwoDimensionalArrayDefaultIsWrittenAsRows()
        {
            string text = R(typeof(GridHolder)).Text;
            Assert.That(text, Does.Contain("Field(default_factory=lambda: [[0.0, 0.0], [0.0, 0.0]])"));
            Assert.That(text, Does.Contain("dict[str, float]"));
        }

        [Test]
        [Description("Checks that a generic constraint that refers to another type parameter is written with Any. Protects the Python generic header for " +
            "interfaces with mutually constrained parameters.")]
        public void ConstraintThatNamesATypeParameterGetsAny()
        {
            string text = R(typeof(IPanelLike<,>)).Text;
            Assert.That(text, Does.Contain("class IPanelLike_2[TEdge, TOpening: IOpeningLike_1[Any]]"));
        }

        [Test]
        [Description("Checks that an enum member named None is renamed to None_ and the original name is recorded in the marker, and that flag enums become " +
            "IntFlag. Protects enum emission and the reverse mapping used by py2cs.")]
        public void EnumMemberNamedNoneIsRenamedAndRecorded()
        {
            string text = R(typeof(SupportKind)).Text;
            Assert.That(text, Does.Contain("class SupportKind(Enum):"));
            Assert.That(text, Does.Contain("    None_ = 0"));
            Assert.That(text, Does.Contain("'renamed_members': {'None_': 'None'}"));
            Assert.That(text, Does.Contain("# Fully fixed."));
            Assert.That(R(typeof(Options)).Text, Does.Contain("class Options(IntFlag):"));
        }

        [Test]
        [Description("Checks that two types with the same name from different assemblies are imported under distinct aliases in one generated file. Protects " +
            "NameTracker and import generation.")]
        public void SameNamedTypesGetAliasesInOneFile()
        {
            string text = FixtureOutput.Rendered("BH.oM.FixtureBeta.Elements.UsesBoth").Text;
            Assert.That(text, Does.Contain("import PointLike as FixtureAlpha_oM_PointLike").Or.Contain("PointLike as FixtureBeta_oM_PointLike"));
            Assert.That(text, Does.Contain("FromAlpha:"));
            Assert.That(text, Does.Contain("Local:"));
        }

        /***************************************************/
        /**** Metadata                                  ****/
        /***************************************************/

        [Test]
        [Description("Checks that descriptions, quantity category and unit, and display text from C# attributes are carried into the model and the generated " +
            "Python. Protects MetadataReader output.")]
        public void DescriptionsQuantityAndDisplayTextAreCarried()
        {
            RenderedType beam = R(typeof(Beam));
            RenderedProperty span = beam.Properties.Single(p => p.Name == "Span");
            Assert.That(span.Quantity.Category, Is.EqualTo("Length"));
            Assert.That(span.Quantity.Unit, Is.EqualTo("m"));
            Assert.That(span.DisplayText, Is.EqualTo("Span length"));
            Assert.That(beam.Text, Does.Contain("Span: Annotated[float, Quantity('Length', 'm'), DisplayText('Span length')] = Field(default=1.5, description='Distance between the supports.')"));
            Assert.That(R(typeof(LineLike)).Text, Does.Contain("\"\"\"A straight segment between two points.\"\"\""));
        }

        [Test]
        [Description("Checks that a type with no description is written without a docstring. Protects emission of class documentation.")]
        public void TypesWithoutDescriptionGetNoDocstring()
        {
            Assert.That(R(typeof(ProjectLike)).Text, Does.Not.Contain("\"\"\""));
        }

        /***************************************************/
        /**** Paths and cycles                          ****/
        /***************************************************/

        [Test]
        [Description("Checks that module paths and written files follow the namespace of each type, relative to its assembly folder. Protects TypeRegistry and " +
            "OutputWriter placement.")]
        public void PathsFollowTheNamespaceNotTheSourceFolder()
        {
            Assert.That(R(typeof(ProjectLike)).Ref.RelativePath, Is.EqualTo("FixtureAlpha_oM/ProjectLike"));
            Assert.That(R(typeof(LineLike)).Ref.RelativePath, Is.EqualTo("FixtureAlpha_oM/LineLike"));
            Assert.That(FixtureOutput.Rendered("BH.oM.FixtureBeta.Elements.UsesBoth").Ref.RelativePath, Is.EqualTo("FixtureBeta_oM/Elements/UsesBoth"));
            Assert.That(File.Exists(Path.Combine(FixtureOutput.Package, "FixtureAlpha_oM", "ProjectLike.py")));
            Assert.That(File.Exists(Path.Combine(FixtureOutput.Package, "FixtureBeta_oM", "Elements", "UsesBoth.py")));
        }

        [Test]
        [Description("Checks that mutually referencing types import each other after the class and call model_rebuild, while other types do not, and that the " +
            "cycle count is reported. Protects CycleDetector and the emitted import placement.")]
        public void CyclicReferencesUseBottomImports()
        {
            string a = R(typeof(CycleA)).Text;
            string b = R(typeof(CycleB)).Text;
            Assert.That(a, Does.Contain("CycleA.model_rebuild()"));
            Assert.That(b, Does.Contain("CycleB.model_rebuild()"));
            Assert.That(a.IndexOf("from bhom_schema.FixtureAlpha_oM.CycleB import CycleB"), Is.GreaterThan(a.IndexOf("class CycleA")));
            Assert.That(R(typeof(PointLike)).Text, Does.Not.Contain("model_rebuild"), "types outside a cycle do not need a rebuild");
            Assert.That(FixtureOutput.Result.CyclicTypes, Is.EqualTo(2));
        }
    }
}
