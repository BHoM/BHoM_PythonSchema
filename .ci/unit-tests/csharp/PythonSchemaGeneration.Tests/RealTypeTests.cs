using PythonSchemaGeneration;
using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Model;

namespace PythonSchemaGeneration.Tests
{
    //Tier 2: the real oM assemblies installed in ProgramData\BHoM\Assemblies. Fails in CI, ignored locally when something is missing.
    [Category("RealTypes")]
    public class RealTypeTests
    {
        private static GenerationResult m_Result;

        [OneTimeSetUp]
        [Description("Skips or fails the fixture when the real BHoM assemblies are missing and otherwise generates the spike set once. Prepares the shared result " +
            "for the tests in this class.")]
        public void Setup()
        {
            RealAssemblies.RequireOrSkip();
            m_Result = RealAssemblies.Spike();
        }

        [Description("Returns the generated spike type with the given CLR name. The tests in this class use it to inspect real BHoM types.")]
        private static RenderedType R(string clrName) { return m_Result.Types.Single(t => t.Model.ClrName == clrName); }

        [Description("Joins the simple names of the given types with commas so a type's bases can be compared as one string. Used by the base-type tests.")]
        private static string Names(IEnumerable<Type> types) { return string.Join(",", types.Select(t => t.Name)); }

        /***************************************************/

        [Test]
        [Description("Checks that every spike type is generated from the real assemblies and that the run produces no warnings. Protects the generator against " +
            "real oM types.")]
        public void EverySpikeTypeIsGeneratedWithoutWarnings()
        {
            foreach (string name in RealAssemblies.SpikeTypes)
                Assert.That(m_Result.Types.Any(t => t.Model.ClrName == name), Is.True, name);
            Assert.That(m_Result.Reporter.Warnings, Is.Empty);
        }

        [Test]
        [Description("Checks that Line and ICurve get the expected bases, that Line's defaults, dependencies and path are generated. Protects the base and default " +
            "handling on a real geometry type.")]
        public void LineAndTheCurveInterfaceChain()
        {
            Assert.That(Names(R("BH.oM.Geometry.Line").Model.Bases), Is.EqualTo("ICurve"));
            Assert.That(Names(R("BH.oM.Geometry.ICurve").Model.Bases), Is.EqualTo("IElement1D,IGeometry"));
            Assert.That(R("BH.oM.Geometry.Line").Text, Does.Contain("Start: Point = Field(default_factory=lambda: Point())"));
            Assert.That(m_Result.Types.Any(t => t.Model.ClrName == "BH.oM.Geometry.Point"), Is.True, "dependencies are generated too");
            Assert.That(R("BH.oM.Geometry.Line").Ref.RelativePath, Is.EqualTo("Geometry_oM/Line"));
        }

        [Test]
        [Description("Checks that BHoMObject gets its GUID, tags, custom data and fragment fields with the expected defaults and CLR types. Protects the base " +
            "class that most generated types inherit.")]
        public void BHoMObjectHasDefaultedFields()
        {
            string text = R("BH.oM.Base.BHoMObject").Text;
            Assert.That(text, Does.Contain("BHoM_Guid: UUID = Field(default_factory=uuid4)"));
            Assert.That(text, Does.Contain("Tags: set[str] = Field(default_factory=set)"));
            Assert.That(text, Does.Contain("CustomData: dict[str, Any] = Field(default_factory=dict)"));
            Assert.That(text, Does.Contain("ClrType('BH.oM.Base.FragmentSet')"));
        }

        [Test]
        [Description("Checks that Bar derives from BHoMObject and carries quantity metadata for angle properties. Protects quantity extraction on a real structural type.")]
        public void BarSubclassesBHoMObjectAndCarriesQuantities()
        {
            RenderedType bar = R("BH.oM.Structure.Elements.Bar");
            Assert.That(Names(bar.Model.Bases), Does.StartWith("BHoMObject"));
            Assert.That(bar.Properties.Any(p => p.Quantity != null && p.Quantity.Category == "Angle"), Is.True);
            Assert.That(bar.Text, Does.Contain("Quantity('Angle'"));
        }

        [Test]
        [Description("Checks that a real enum with a None member is renamed to None_ and records the original name. Protects enum emission on a real type.")]
        public void EnumWithNoneMember()
        {
            string text = R("BH.oM.Graphics.Enums.GradientCenteringOptions").Text;
            Assert.That(text, Does.Contain("None_ = 0"));
            Assert.That(text, Does.Contain("'renamed_members': {'None_': 'None'}"));
        }

        [Test]
        [Description("Checks that the real generic BHoMGroup is named with its arity and keeps its type parameter bound. Protects generics handling on a real type.")]
        public void GenericWithConstraint()
        {
            RenderedType group = R("BH.oM.Base.BHoMGroup`1");
            Assert.That(group.Ref.Name, Is.EqualTo("BHoMGroup_1"));
            Assert.That(group.Text, Does.Contain("class BHoMGroup_1[T: IBHoMObject]("));
        }

        [Test]
        [Description("Checks that the two Room types from different assemblies get different module paths. Protects TypeRegistry placement of same-named real types.")]
        public void SameNamedRoomsLiveInDifferentAssemblies()
        {
            Assert.That(R("BH.oM.Acoustic.Room").Ref.RelativePath, Is.EqualTo("Acoustic_oM/Room"));
            Assert.That(R("BH.oM.Architecture.Elements.Room").Ref.RelativePath, Is.EqualTo("Architecture_oM/Elements/Room"));
        }

        [Test]
        [Description("Checks that Gradient's dictionary of decimal to colour is written with special types imported from the support package. Protects TypeMapper " +
            "and imports for special types.")]
        public void GradientUsesNonHashableAndSpecialTypes()
        {
            string text = R("BH.oM.Graphics.Gradient").Text;
            Assert.That(text, Does.Contain("dict[Decimal, Color]"));
            Assert.That(text, Does.Contain("from bhom_schema._support import"));
        }

        [Test]
        [Description("Checks that a hash set of oM objects is written as a list with the original type kept. Protects the hashable fallback on a real type.")]
        public void ComparisonConfigHasSetsOfObjects()
        {
            string text = R("BH.oM.Base.BaseComparisonConfig").Text;
            Assert.That(text, Does.Contain("PropertyNumericTolerances: Annotated[list[NamedNumericTolerance], ClrType('System.Collections.Generic.HashSet<BH.oM.Base.NamedNumericTolerance>')]"));
        }

        [Test]
        [Description("Checks that the spike types considered stable match their committed golden files. Protects the exact output for real types.")]
        public void StableTypesMatchGoldenFiles()
        {
            foreach (string name in new[] { "BH.oM.Graphics.Enums.GradientCenteringOptions" })
            {
                RenderedType type = R(name);
                GoldenAssert.Matches("spike", type.Ref.RelativePath + ".py", type.Text);
            }
        }

        [Test]
        [Description("Checks that the spike set contains no cyclic references between generated types. Protects the CycleDetector result for the spike set.")]
        public void SpikeOutputHasNoReferenceCycles()
        {
            Assert.That(m_Result.CyclicTypes, Is.EqualTo(0));
        }
    }
}
