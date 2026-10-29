using PythonSchemaGeneration.Emission;

namespace PythonSchemaGeneration.Tests
{
    //--repos: convert the assemblies of some repositories, plus what they depend on in other repositories
    public class RepoFilterTests
    {
        private const string FixtureRepo = "BHoM/CSharpSchema_Test";

        /***************************************************/

        [Description("Builds generator options for the fixture and BHoM assemblies limited to one repository, with an optional output folder. Used by every test " +
            "in this class.")]
        private static GenerationOptions Options(string repo, string output = null)
        {
            return new GenerationOptions
            {
                Assemblies = new List<System.Reflection.Assembly> { FixtureOutput.Alpha, FixtureOutput.Beta, typeof(BH.oM.Base.BHoMObject).Assembly },
                Repos = new List<string> { repo },
                OutputFolder = output,
            };
        }

        /***************************************************/

        [Test]
        [Description("Checks that a repository run converts that repository's types plus only the base classes it depends on in other repositories. Protects the " +
            "--repos filter of the generator.")]
        public void OnlyTheRequestedRepositoryIsConvertedPlusItsDependencies()
        {
            GenerationResult result = Generator.Run(Options(FixtureRepo));
            List<RenderedType> others = result.Types.Where(t => !t.Model.ClrName.StartsWith("BH.oM.Fixture")).ToList();

            Assert.That(result.Types.Count(t => t.Model.ClrName.StartsWith("BH.oM.Fixture")), Is.GreaterThan(20));
            Assert.That(others.Select(t => t.Model.Assembly).Distinct(), Is.EqualTo(new[] { "BHoM" }), "only base classes from BHoM, nothing else");
            Assert.That(others.Any(t => t.Model.ClrName == "BH.oM.Base.BHoMObject"), Is.True);
            Assert.That(others.Count, Is.LessThan(20), "the rest of the BHoM assembly is not converted");
        }

        /***************************************************/

        [Test]
        [Description("Checks that the repository filter matches names regardless of case. Protects the --repos option against capitalisation differences.")]
        public void RepositoryNamesAreMatchedWithoutRegardToCase()
        {
            Assert.That(Generator.Run(Options("bhom/csharpschema_test")).Types.Any(t => t.Model.ClrName == "BH.oM.FixtureAlpha.Beam"), Is.True);
        }

        /***************************************************/

        [Test]
        [Description("Checks that a repository with no assembly produces a warning and converts no types. Protects the --repos option from silently doing nothing.")]
        public void ARepositoryWithNoAssemblyIsReportedAndConvertsNothing()
        {
            GenerationResult result = Generator.Run(Options("BHoM/Nowhere"));
            Assert.That(result.Types, Is.Empty);
            Assert.That(result.Reporter.Warnings, Has.Some.Contain("BHoM/Nowhere"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that stale files are removed only for the requested repository's assemblies, files of other repositories stay and needed base classes " +
            "are written. Protects OutputWriter in per-repository runs.")]
        public void CleanUpOnlyTouchesTheAssembliesOfTheRequestedRepository()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-repos-" + Guid.NewGuid().ToString("N"));
            try
            {
                string package = Path.Combine(folder, "bhom_schema");
                Directory.CreateDirectory(Path.Combine(package, "FixtureAlpha_oM"));
                Directory.CreateDirectory(Path.Combine(package, "BHoM"));
                File.WriteAllText(Path.Combine(package, "FixtureAlpha_oM", "Stale.py"), "x = 1\n");
                File.WriteAllText(Path.Combine(package, "BHoM", "FromAnotherRun.py"), "x = 1\n");

                Generator.Run(Options(FixtureRepo, package));

                Assert.That(File.Exists(Path.Combine(package, "FixtureAlpha_oM", "Stale.py")), Is.False, "stale file of the requested repository is removed");
                Assert.That(File.Exists(Path.Combine(package, "BHoM", "FromAnotherRun.py")), Is.True, "files of the dependency's own repository stay");
                Assert.That(File.Exists(Path.Combine(package, "BHoM", "BHoMObject.py")), Is.True, "the base class that the fixtures import is written");
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }

        /***************************************************/
    }
}
