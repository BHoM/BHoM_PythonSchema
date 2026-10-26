using System.Text;
using PythonSchemaGeneration;
using PythonSchemaGeneration.Emission;

namespace PythonSchemaGeneration.Tests
{
    public static class GoldenAssert
    {
        //Set UPDATE_GOLDEN=1 to rewrite the expected files after an intended change, then review the diff
        public static void Matches(string goldenFolder, string relativePath, string actual)
        {
            string path = Path.Combine(TestPaths.Golden(goldenFolder), relativePath.Replace('/', Path.DirectorySeparatorChar));
            actual = actual.Replace("\r\n", "\n");
            if (Environment.GetEnvironmentVariable("UPDATE_GOLDEN") == "1")
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllText(path, actual, new UTF8Encoding(false));
                return;
            }
            Assert.That(File.Exists(path), Is.True, $"missing golden file {path} (run with UPDATE_GOLDEN=1 to create it)");
            Assert.That(actual, Is.EqualTo(File.ReadAllText(path).Replace("\r\n", "\n")), $"golden file {relativePath} differs");
        }
    }

    public class GoldenTests
    {
        [Test]
        public void FixtureOutputMatchesGoldenFiles()
        {
            foreach (RenderedType type in FixtureOutput.Result.Types.Where(t => t.Ref.RelativePath.StartsWith("Fixture")))
                GoldenAssert.Matches("fixtures", type.Ref.RelativePath + ".py", type.Text);
        }

        [Test]
        public void FixtureManifestMatchesGolden()
        {
            GoldenAssert.Matches("fixtures", "manifest.json", File.ReadAllText(Path.Combine(FixtureOutput.Folder, "manifest.json")));
        }
    }

    public class WorkflowTests
    {
        [Test]
        public void OutputIsDeterministic()
        {
            string a = Path.Combine(Path.GetTempPath(), "pysg-a-" + Guid.NewGuid().ToString("N"));
            string b = Path.Combine(Path.GetTempPath(), "pysg-b-" + Guid.NewGuid().ToString("N"));
            try
            {
                FixtureOutput.Generate(a, false);
                FixtureOutput.Generate(b, false);
                string[] filesA = Directory.GetFiles(a, "*.py", SearchOption.AllDirectories).Select(f => Path.GetRelativePath(a, f)).OrderBy(x => x, StringComparer.Ordinal).ToArray();
                string[] filesB = Directory.GetFiles(b, "*.py", SearchOption.AllDirectories).Select(f => Path.GetRelativePath(b, f)).OrderBy(x => x, StringComparer.Ordinal).ToArray();
                Assert.That(filesA, Is.EqualTo(filesB));
                foreach (string file in filesA)
                    Assert.That(File.ReadAllBytes(Path.Combine(a, file)), Is.EqualTo(File.ReadAllBytes(Path.Combine(b, file))), file);
                Assert.That(File.ReadAllText(Path.Combine(a, "bhom_schema", "FixtureAlpha_oM", "PointLike.py")), Does.Not.Contain("\r"));
            }
            finally
            {
                if (Directory.Exists(a)) Directory.Delete(a, true);
                if (Directory.Exists(b)) Directory.Delete(b, true);
            }
        }

        [Test]
        public void RegenerationRemovesStaleFilesButNeverTheSupportPackage()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-clean-" + Guid.NewGuid().ToString("N"));
            try
            {
                string package = Path.Combine(folder, "bhom_schema");
                FixtureOutput.CopySupport(package);
                Directory.CreateDirectory(Path.Combine(package, "FixtureAlpha_oM", "Old", "Deeper"));
                File.WriteAllText(Path.Combine(package, "FixtureAlpha_oM", "Stale.py"), "x = 1\n");
                File.WriteAllText(Path.Combine(package, "FixtureAlpha_oM", "Old", "Deeper", "Gone.py"), "x = 1\n");
                File.WriteAllText(Path.Combine(package, "_support", "keep_me.py"), "x = 1\n");

                //Whole assembly run (no type filter) so the clean-up is active
                GenerationResult result = Generator.Run(new GenerationOptions
                {
                    Assemblies = new List<System.Reflection.Assembly> { FixtureOutput.Alpha, typeof(BH.oM.Base.BHoMObject).Assembly },
                    OutputFolder = package,
                    TypeFilter = null,
                });

                Assert.That(File.Exists(Path.Combine(package, "FixtureAlpha_oM", "Stale.py")), Is.False);
                Assert.That(Directory.Exists(Path.Combine(package, "FixtureAlpha_oM", "Old")), Is.False, "empty folders are removed");
                Assert.That(File.Exists(Path.Combine(package, "_support", "keep_me.py")), Is.True);
                Assert.That(File.Exists(Path.Combine(package, "FixtureAlpha_oM", "PointLike.py")), Is.True);
                Assert.That(result.Types.Count, Is.GreaterThan(10));
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }

        [Test]
        public void FilteredRunDoesNotDeleteAnything()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-partial-" + Guid.NewGuid().ToString("N"));
            try
            {
                string package = Path.Combine(folder, "bhom_schema");
                Directory.CreateDirectory(Path.Combine(package, "FixtureAlpha_oM"));
                File.WriteAllText(Path.Combine(package, "FixtureAlpha_oM", "Other.py"), "x = 1\n");
                Generator.Run(new GenerationOptions
                {
                    Assemblies = new List<System.Reflection.Assembly> { FixtureOutput.Alpha, typeof(BH.oM.Base.BHoMObject).Assembly },
                    OutputFolder = package,
                    TypeFilter = new List<string> { "BH.oM.FixtureAlpha.PointLike" },
                });
                Assert.That(File.Exists(Path.Combine(package, "FixtureAlpha_oM", "Other.py")), Is.True);
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }

        [Test]
        public void UnknownRequestedTypeIsReportedNotFatal()
        {
            GenerationResult result = Generator.Run(new GenerationOptions
            {
                Assemblies = new List<System.Reflection.Assembly> { FixtureOutput.Alpha },
                TypeFilter = new List<string> { "BH.oM.Nope.DoesNotExist", "BH.oM.FixtureAlpha.PointLike" },
            });
            Assert.That(result.Reporter.Warnings.Any(w => w.Contains("DoesNotExist")), Is.True);
            Assert.That(result.Types.Any(t => t.Model.ClrName == "BH.oM.FixtureAlpha.PointLike"), Is.True);
        }

        [Test]
        public void GeneratorHasNoDependencyOnTheJsonSchemaRepo()
        {
            string generation = Path.Combine(TestPaths.Root, ".ci", "generation");
            foreach (string file in Directory.GetFiles(generation, "*.cs*", SearchOption.AllDirectories).Where(f => !f.Contains(Path.DirectorySeparatorChar + "obj" + Path.DirectorySeparatorChar) && !f.Contains(Path.DirectorySeparatorChar + "bin" + Path.DirectorySeparatorChar)))
            {
                string text = File.ReadAllText(file);
                Assert.That(text, Does.Not.Contain("BHoM_JSONSchema"), file);
            }
        }

        [Test]
        public void HandWrittenSupportPackageIsNotGenerated()
        {
            Assert.That(FixtureOutput.Result.Types.Any(t => t.Ref.Module.StartsWith("bhom_schema._support")), Is.False);
        }
    }
}
