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
        public void Setup()
        {
            RealAssemblies.RequireOrSkip();
            m_Result = RealAssemblies.Spike();
        }

        private static RenderedType R(string clrName) { return m_Result.Types.Single(t => t.Model.ClrName == clrName); }
        private static string Names(IEnumerable<Type> types) { return string.Join(",", types.Select(t => t.Name)); }

        /***************************************************/

        [Test]
        public void EverySpikeTypeIsGeneratedWithoutWarnings()
        {
            foreach (string name in RealAssemblies.SpikeTypes)
                Assert.That(m_Result.Types.Any(t => t.Model.ClrName == name), Is.True, name);
            Assert.That(m_Result.Reporter.Warnings, Is.Empty);
        }

        [Test]
        public void ProjectIdentification()
        {
            RenderedType type = R("BH.oM.dKoP.ProjectIdentification");
            Assert.That(type.Model.Kind, Is.EqualTo(TypeKind.Class));
            Assert.That(Names(type.Model.Bases), Is.EqualTo("IdKoPObject"));
            Assert.That(R("BH.oM.dKoP.IdKoPObject").Model.Kind, Is.EqualTo(TypeKind.Interface), "an interface without an I prefix");
            Assert.That(type.Properties.Select(p => p.Name), Is.EqualTo(new[] { "ProjectReference", "ProjectName", "ProjectLocation", "AdditionalReferences" }));
            Assert.That(type.Properties.All(p => p.HasDefault && p.Default == "''"), Is.True);
            Assert.That(type.Model.Repo, Is.EqualTo("BHoM/dKoP_Toolkit"));
            Assert.That(type.Model.Assembly, Is.EqualTo("dKoP_oM"));
            Assert.That(type.Model.Namespace, Is.EqualTo("BH.oM.dKoP"));
            Assert.That(type.Ref.RelativePath, Is.EqualTo("dKoP_oM/ProjectIdentification"), "the source folder AdministrativeInformation/ is not part of the path");
            Assert.That(type.Text, Does.Not.Contain("\"\"\""), "no description, so no docstring");
        }

        [Test]
        public void LineAndTheCurveInterfaceChain()
        {
            Assert.That(Names(R("BH.oM.Geometry.Line").Model.Bases), Is.EqualTo("ICurve"));
            Assert.That(Names(R("BH.oM.Geometry.ICurve").Model.Bases), Is.EqualTo("IElement1D,IGeometry"));
            Assert.That(R("BH.oM.Geometry.Line").Text, Does.Contain("Start: Point = Field(default_factory=lambda: Point())"));
            Assert.That(m_Result.Types.Any(t => t.Model.ClrName == "BH.oM.Geometry.Point"), Is.True, "dependencies are generated too");
            Assert.That(R("BH.oM.Geometry.Line").Ref.RelativePath, Is.EqualTo("Geometry_oM/Line"));
        }

        [Test]
        public void BHoMObjectHasDefaultedFields()
        {
            string text = R("BH.oM.Base.BHoMObject").Text;
            Assert.That(text, Does.Contain("BHoM_Guid: UUID = Field(default_factory=uuid4)"));
            Assert.That(text, Does.Contain("Tags: set[str] = Field(default_factory=set)"));
            Assert.That(text, Does.Contain("CustomData: dict[str, Any] = Field(default_factory=dict)"));
            Assert.That(text, Does.Contain("ClrType('BH.oM.Base.FragmentSet')"));
        }

        [Test]
        public void BarSubclassesBHoMObjectAndCarriesQuantities()
        {
            RenderedType bar = R("BH.oM.Structure.Elements.Bar");
            Assert.That(Names(bar.Model.Bases), Does.StartWith("BHoMObject"));
            Assert.That(bar.Properties.Any(p => p.Quantity != null && p.Quantity.Category == "Angle"), Is.True);
            Assert.That(bar.Text, Does.Contain("Quantity('Angle'"));
        }

        [Test]
        public void EnumWithNoneMember()
        {
            string text = R("BH.oM.Graphics.Enums.GradientCenteringOptions").Text;
            Assert.That(text, Does.Contain("None_ = 0"));
            Assert.That(text, Does.Contain("'renamed_members': {'None_': 'None'}"));
        }

        [Test]
        public void GenericWithConstraint()
        {
            RenderedType group = R("BH.oM.Base.BHoMGroup`1");
            Assert.That(group.Ref.Name, Is.EqualTo("BHoMGroup_1"));
            Assert.That(group.Text, Does.Contain("class BHoMGroup_1[T: IBHoMObject]("));
        }

        [Test]
        public void SameNamedRoomsLiveInDifferentAssemblies()
        {
            Assert.That(R("BH.oM.Acoustic.Room").Ref.RelativePath, Is.EqualTo("Acoustic_oM/Room"));
            Assert.That(R("BH.oM.Architecture.Elements.Room").Ref.RelativePath, Is.EqualTo("Architecture_oM/Elements/Room"));
        }

        [Test]
        public void GradientUsesNonHashableAndSpecialTypes()
        {
            string text = R("BH.oM.Graphics.Gradient").Text;
            Assert.That(text, Does.Contain("dict[Decimal, Color]"));
            Assert.That(text, Does.Contain("from bhom_schema._support import"));
        }

        [Test]
        public void ComparisonConfigHasSetsOfObjects()
        {
            string text = R("BH.oM.Base.BaseComparisonConfig").Text;
            Assert.That(text, Does.Contain("PropertyNumericTolerances: Annotated[list[NamedNumericTolerance], ClrType('System.Collections.Generic.HashSet<BH.oM.Base.NamedNumericTolerance>')]"));
        }

        [Test]
        public void StableTypesMatchGoldenFiles()
        {
            foreach (string name in new[] { "BH.oM.dKoP.ProjectIdentification", "BH.oM.dKoP.IdKoPObject", "BH.oM.Graphics.Enums.GradientCenteringOptions" })
            {
                RenderedType type = R(name);
                GoldenAssert.Matches("spike", type.Ref.RelativePath + ".py", type.Text);
            }
        }

        [Test]
        public void SpikeOutputHasNoReferenceCycles()
        {
            Assert.That(m_Result.CyclicTypes, Is.EqualTo(0));
        }
    }
}
