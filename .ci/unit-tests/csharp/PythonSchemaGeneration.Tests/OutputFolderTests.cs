using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;

namespace PythonSchemaGeneration.Tests
{
    //What the generator does about files and folders it cannot place, or no longer generates
    public class OutputFolderTests
    {
        private const string FixtureRepo = "BHoM/CSharpSchema_Test";

        /***************************************************/

        [Description("Builds a generated type with only the C# name and the output path, which is all the output writer reads. Used by the file name tests.")]
        private static RenderedType Rendered(string clrName, string relativePath)
        {
            return new RenderedType { Model = new TypeModel { ClrName = clrName }, Ref = new PyRef { RelativePath = relativePath }, Text = "x = 1\n" };
        }

        /***************************************************/

        [Description("Writes a Python file that carries a repository marker into a package folder, as a generated class does. The missing folder tests use it to make an " +
            "assembly folder that the run will not generate.")]
        private static void WriteOldAssembly(string package, string assembly, string repo)
        {
            Directory.CreateDirectory(Path.Combine(package, assembly));
            File.WriteAllText(Path.Combine(package, assembly, "Thing.py"), $"class Thing:\n    __bhom__ = {{\n        'repo': '{repo}',\n    }}\n");
        }

        /***************************************************/

        [Description("Runs the generator over the fixtures and BHoM for the fixture repository into a package folder, with the clean-up option as asked. The missing " +
            "folder tests use it.")]
        private static GenerationResult Run(string package, bool clean)
        {
            return Generator.Run(new GenerationOptions
            {
                Assemblies = new List<System.Reflection.Assembly> { FixtureOutput.Alpha, FixtureOutput.Beta, typeof(BH.oM.Base.BHoMObject).Assembly },
                Repos = new List<string> { FixtureRepo },
                OutputFolder = package,
                CleanMissingAssemblies = clean,
            });
        }

        /***************************************************/

        [Test]
        [Description("Checks that two classes whose file names differ only in upper and lower case stop the run with an error that names both, and write nothing. " +
            "Protects the package from silently losing one of two classes on Windows.")]
        public void ClassesWithTheSameFileNameStopTheRun()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-clash-" + Guid.NewGuid().ToString("N"));
            try
            {
                RenderedType[] clashing = { Rendered("BH.oM.Demo.Panel", "Demo_oM/Panel"), Rendered("BH.oM.Demo.PANEL", "Demo_oM/PANEL") };
                InvalidOperationException error = Assert.Throws<InvalidOperationException>(() => OutputWriter.Write(folder, clashing, true, new PythonSchemaGeneration.Reporting.Reporter()));

                Assert.That(error.Message, Does.Contain("BH.oM.Demo.Panel").And.Contain("BH.oM.Demo.PANEL"));
                Assert.That(Directory.Exists(folder), Is.False);
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }

        /***************************************************/

        [Test]
        [Description("Checks that a full run for a repository warns about an old assembly folder of that repository that it did not generate and keeps its files, while a " +
            "folder of another repository is neither listed nor touched. Protects the weekly run from hiding an assembly whose build failed.")]
        public void AnAssemblyFolderThatWasNotGeneratedIsListed()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-missing-" + Guid.NewGuid().ToString("N"));
            try
            {
                string package = Path.Combine(folder, "bhom_schema");
                WriteOldAssembly(package, "Old_oM", FixtureRepo);
                WriteOldAssembly(package, "Other_oM", "BHoM/Other");

                GenerationResult result = Run(package, false);

                Assert.That(result.Reporter.Warnings, Has.Some.Contain("Old_oM").And.Some.Contain("--clean-missing-assemblies"));
                Assert.That(result.Reporter.Warnings, Has.None.Contain("Other_oM"));
                Assert.That(File.Exists(Path.Combine(package, "Old_oM", "Thing.py")), Is.True);
                Assert.That(File.Exists(Path.Combine(package, "Other_oM", "Thing.py")), Is.True);
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }

        /***************************************************/

        [Test]
        [Description("Checks that --clean-missing-assemblies deletes the old assembly folder of the requested repository and nothing else. Protects the option from " +
            "removing the folders of other repositories or the support package.")]
        public void TheCleanOptionDeletesOnlyTheMissingFoldersOfTheRepository()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-clean-missing-" + Guid.NewGuid().ToString("N"));
            try
            {
                string package = Path.Combine(folder, "bhom_schema");
                WriteOldAssembly(package, "Old_oM", FixtureRepo);
                WriteOldAssembly(package, "Other_oM", "BHoM/Other");
                Directory.CreateDirectory(Path.Combine(package, "_support"));

                GenerationResult result = Run(package, true);

                Assert.That(Directory.Exists(Path.Combine(package, "Old_oM")), Is.False);
                Assert.That(Directory.Exists(Path.Combine(package, "Other_oM")), Is.True);
                Assert.That(Directory.Exists(Path.Combine(package, "_support")), Is.True);
                Assert.That(result.Reporter.Warnings, Has.None.Contain("Old_oM"));
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }

        /***************************************************/

        [Test]
        [Description("Checks that a run for some types only does not list or delete assembly folders. Protects partial runs, which never say what the whole package is.")]
        public void APartialRunNeverListsMissingFolders()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-partial-missing-" + Guid.NewGuid().ToString("N"));
            try
            {
                string package = Path.Combine(folder, "bhom_schema");
                WriteOldAssembly(package, "Old_oM", FixtureRepo);

                GenerationResult result = Generator.Run(new GenerationOptions
                {
                    Assemblies = new List<System.Reflection.Assembly> { FixtureOutput.Alpha, FixtureOutput.Beta, typeof(BH.oM.Base.BHoMObject).Assembly },
                    TypeFilter = new List<string> { "BH.oM.FixtureAlpha.Beam" },
                    OutputFolder = package,
                    CleanMissingAssemblies = true,
                });

                Assert.That(Directory.Exists(Path.Combine(package, "Old_oM")), Is.True);
                Assert.That(result.Reporter.Warnings, Has.None.Contain("Old_oM"));
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }
    }
}
