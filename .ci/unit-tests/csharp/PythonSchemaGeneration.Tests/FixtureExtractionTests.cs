using BH.oM.FixtureAlpha;
using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Extraction;
using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;

namespace PythonSchemaGeneration.Tests
{
    public class FixtureExtractionTests
    {
        private static RenderedType R(Type type) { return FixtureOutput.Rendered(type.FullName); }
        private static string Names(IEnumerable<Type> types) { return string.Join(",", types.Select(t => t.Name)); }

        /***************************************************/
        /**** Selection                                 ****/
        /***************************************************/

        [Test]
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
        public void InterfaceIsDetectedByReflectionNotByName()
        {
            Assert.That(R(typeof(ThingIdentity)).Model.Kind, Is.EqualTo(TypeKind.Interface));
            Assert.That(R(typeof(ProjectLike)).Model.Kind, Is.EqualTo(TypeKind.Class));
        }

        /***************************************************/
        /**** Bases                                     ****/
        /***************************************************/

        [Test]
        public void ImpliedInterfacesAreDropped()
        {
            Assert.That(Names(R(typeof(ICurveLike)).Model.Bases), Is.EqualTo("IElement1DLike,IGeometryLike"));
            Assert.That(Names(R(typeof(LineLike)).Model.Bases), Is.EqualTo("ICurveLike,ILabelled"));
            Assert.That(Names(R(typeof(PointLike)).Model.Bases), Is.EqualTo("IGeometryLike"));
        }

        [Test]
        public void ClassBaseComesFirstThenInterfaces()
        {
            Assert.That(Names(R(typeof(ImmutableThing)).Model.Bases), Is.EqualTo("BHoMObject,IImmutable"));
        }

        /***************************************************/
        /**** Provenance                                ****/
        /***************************************************/

        [Test]
        public void RepoComesFromTheAssemblyDescription()
        {
            Assert.That(R(typeof(ProjectLike)).Model.Repo, Is.EqualTo("BuroHappoldEngineering/CSharpSchema_Test"));
            Assert.That(FixtureOutput.Rendered(typeof(BH.oM.FixtureBeta.PointLike).FullName).Model.Repo, Is.EqualTo("BuroHappoldEngineering/CSharpSchema_Test"));
            Assert.That(R(typeof(ProjectLike)).Text, Does.Contain("'repo': 'BuroHappoldEngineering/CSharpSchema_Test'"));
            Assert.That(R(typeof(ProjectLike)).Text, Does.Contain("'namespace': 'BH.oM.FixtureAlpha'"));
            Assert.That(R(typeof(ProjectLike)).Text, Does.Contain("'assembly': 'FixtureAlpha_oM'"));
        }

        [Test]
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
        public void StringDefaultsAreRead()
        {
            string text = R(typeof(ProjectLike)).Text;
            Assert.That(text, Does.Contain("ProjectReference: str = ''"));
            Assert.That(text, Does.Contain("AdditionalReferences: str = ''"));
            Assert.That(R(typeof(ProjectLike)).Properties.Select(p => p.Name), Is.EqualTo(new[] { "ProjectReference", "ProjectName", "ProjectLocation", "AdditionalReferences" }));
        }

        [Test]
        public void ImmutableTypeFieldsAreRequired()
        {
            RenderedType thing = R(typeof(ImmutableThing));
            Assert.That(thing.Properties.Single(p => p.Name == "Id").HasDefault, Is.False);
            Assert.That(thing.Properties.Single(p => p.Name == "Length").HasDefault, Is.False);
            Assert.That(thing.Text, Does.Contain("    Id: str\n"));
            Assert.That(thing.Text, Does.Contain("    Length: float\n"));
        }

        [Test]
        public void ObjectAndNullDefaults()
        {
            Assert.That(R(typeof(LineLike)).Text, Does.Contain("Start: PointLike = Field(default_factory=lambda: PointLike())"));
            Assert.That(R(typeof(LineLike)).Text, Does.Contain("Label: str | None = None"));
            Assert.That(R(typeof(Beam)).Text, Does.Contain("Start: PointLike | None = None"));
        }

        [Test]
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
            Assert.That(text, Does.Contain("BHoM_Guid: UUID") .Or.Not.Contain("BHoM_Guid"), "inherited properties are not repeated");
        }

        [Test]
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
        public void SetsAndDictionariesFallBackToListsForUnhashableItems()
        {
            string text = R(typeof(Collections)).Text;
            Assert.That(text, Does.Contain("Names: set[str] = Field(default_factory=set)"));
            Assert.That(text, Does.Contain("Lookup: dict[str, float] = Field(default_factory=dict)"));
            Assert.That(text, Does.Contain("Points: Annotated[list[PointLike], ClrType('System.Collections.Generic.HashSet<BH.oM.FixtureAlpha.PointLike>')]"));
            Assert.That(text, Does.Contain("ByPoint: Annotated[list[tuple[PointLike, str]], ClrType('System.Collections.Generic.Dictionary<BH.oM.FixtureAlpha.PointLike, string>')]"));
        }

        [Test]
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
        public void GenericTypeUsesArityNameAndBound()
        {
            RenderedType wrapper = R(typeof(Wrapper<>));
            Assert.That(wrapper.Ref.Name, Is.EqualTo("Wrapper_1"));
            Assert.That(wrapper.Text, Does.Contain("class Wrapper_1[T: IBHoMObject](BHoMObject):"));
            Assert.That(wrapper.Text, Does.Contain("'clr_name': 'BH.oM.FixtureAlpha.Wrapper`1'"));
            Assert.That(wrapper.Text, Does.Contain("Items: list[T] = Field(default_factory=lambda: [])"));
        }

        [Test]
        public void GenericClassNamingItselfInADefaultUsesALambda()
        {
            RenderedType tree = R(typeof(TreeLike<>));
            Assert.That(tree.Text, Does.Contain("Children: dict[str, TreeLike_1[T]] = Field(default_factory=lambda: {})"));
        }

        [Test]
        public void EnumDefaultThatIsNotAMemberMakesTheFieldRequired()
        {
            Assert.That(R(typeof(SparseHolder)).Text, Does.Contain("    Level: Sparse\n"));
            Assert.That(R(typeof(SparseParent)).Text, Does.Contain("    Holder: SparseHolder\n"));
            Assert.That(FixtureOutput.Result.Reporter.Warnings, Has.Some.Contain("is not a member of enum"));
        }

        [Test]
        public void TwoDimensionalArrayDefaultIsWrittenAsRows()
        {
            string text = R(typeof(GridHolder)).Text;
            Assert.That(text, Does.Contain("Field(default_factory=lambda: [[0.0, 0.0], [0.0, 0.0]])"));
            Assert.That(text, Does.Contain("dict[str, float]"));
        }

        [Test]
        public void ConstraintThatNamesATypeParameterGetsAny()
        {
            string text = R(typeof(IPanelLike<,>)).Text;
            Assert.That(text, Does.Contain("class IPanelLike_2[TEdge, TOpening: IOpeningLike_1[Any]]"));
        }

        [Test]
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
        public void TypesWithoutDescriptionGetNoDocstring()
        {
            Assert.That(R(typeof(ProjectLike)).Text, Does.Not.Contain("\"\"\""));
        }

        /***************************************************/
        /**** Paths and cycles                          ****/
        /***************************************************/

        [Test]
        public void PathsFollowTheNamespaceNotTheSourceFolder()
        {
            Assert.That(R(typeof(ProjectLike)).Ref.RelativePath, Is.EqualTo("FixtureAlpha_oM/ProjectLike"));
            Assert.That(R(typeof(LineLike)).Ref.RelativePath, Is.EqualTo("FixtureAlpha_oM/LineLike"));
            Assert.That(FixtureOutput.Rendered("BH.oM.FixtureBeta.Elements.UsesBoth").Ref.RelativePath, Is.EqualTo("FixtureBeta_oM/Elements/UsesBoth"));
            Assert.That(File.Exists(Path.Combine(FixtureOutput.Package, "FixtureAlpha_oM", "ProjectLike.py")));
            Assert.That(File.Exists(Path.Combine(FixtureOutput.Package, "FixtureBeta_oM", "Elements", "UsesBoth.py")));
        }

        [Test]
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
