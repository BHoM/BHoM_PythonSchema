using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using PythonSchemaGeneration;
using PythonSchemaGeneration.Emission;

namespace PythonSchemaGeneration.Tests
{
    public static class GoldenAssert
    {
        [Description("Compares generated text with the golden file of the same name, or rewrites the golden file when UPDATE_GOLDEN is 1, normalising line " +
            "endings. Used by the golden tests to pin the exact generator output.")]
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
        //One fixture class per situation the generator must handle. Classes added to the fixture repository later are not compared, so a merged
        //C# change does not break these tests; add a class here only when it covers a situation that no listed class covers.
        private static readonly string[] m_PinnedClasses =
        {
            "FixtureAlpha_oM/Beam",
            "FixtureAlpha_oM/Collections",
            "FixtureAlpha_oM/CycleA",
            "FixtureAlpha_oM/CycleB",
            "FixtureAlpha_oM/GeometryHolder",
            "FixtureAlpha_oM/GridHolder",
            "FixtureAlpha_oM/ICurveLike",
            "FixtureAlpha_oM/IElement1DLike",
            "FixtureAlpha_oM/IGeometryLike",
            "FixtureAlpha_oM/ILabelled",
            "FixtureAlpha_oM/IOpeningLike_1",
            "FixtureAlpha_oM/IPanelLike_2",
            "FixtureAlpha_oM/ImmutableThing",
            "FixtureAlpha_oM/LineLike",
            "FixtureAlpha_oM/Options",
            "FixtureAlpha_oM/PointLike",
            "FixtureAlpha_oM/ProjectLike",
            "FixtureAlpha_oM/Scalars",
            "FixtureAlpha_oM/Sparse",
            "FixtureAlpha_oM/SparseHolder",
            "FixtureAlpha_oM/SparseParent",
            "FixtureAlpha_oM/SupportKind",
            "FixtureAlpha_oM/ThingIdentity",
            "FixtureAlpha_oM/TreeLike_1",
            "FixtureAlpha_oM/Wrapper_1",
            "FixtureBeta_oM/Elements/UsesBoth",
            "FixtureBeta_oM/PointLike"
        };

        /***************************************************/

        [Test]
        [Description("Checks that the Python generated for each pinned fixture class is identical to its committed golden file. Protects the exact output of the " +
            "generator against unintended changes, without depending on the other classes of the fixture repository.")]
        public void FixtureOutputMatchesGoldenFiles()
        {
            List<RenderedType> pinned = FixtureOutput.Result.Types.Where(t => m_PinnedClasses.Contains(t.Ref.RelativePath)).ToList();
            Assert.That(pinned.Select(t => t.Ref.RelativePath).OrderBy(x => x, StringComparer.Ordinal), Is.EqualTo(m_PinnedClasses), "every pinned class must still be generated");

            foreach (RenderedType type in pinned)
                GoldenAssert.Matches("fixtures", type.Ref.RelativePath + ".py", type.Text);
        }

        /***************************************************/

        [Test]
        [Description("Checks that the entries of the pinned fixture classes in the manifest written for the fixture run are identical to the committed golden manifest. " +
            "Protects the language-neutral manifest that py2cs and alignment read.")]
        public void FixtureManifestMatchesGolden()
        {
            JsonNode manifest = JsonNode.Parse(File.ReadAllText(Path.Combine(FixtureOutput.Folder, "manifest.json")));
            JsonArray types = manifest["types"].AsArray();
            List<JsonNode> kept = types.Where(t => m_PinnedClasses.Contains(((string)t["relativePath"]).Replace(".py", ""))).ToList();
            types.Clear();
            foreach (JsonNode type in kept)
                types.Add(type.DeepClone());

            string text = manifest.ToJsonString(new JsonSerializerOptions { WriteIndented = true, Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }) + '\n';
            GoldenAssert.Matches("fixtures", "manifest.json", text);
        }
    }

    public class WorkflowTests
    {
        [Test]
        [Description("Checks that two generator runs produce identical files with LF line endings. Protects the weekly generation workflow from committing noise.")]
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
        [Description("Checks that a whole-assembly run deletes stale generated files and empty folders but keeps the hand-written support package. Protects " +
            "OutputWriter's clean-up in the weekly generation.")]
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
        [Description("Checks that a run limited by a type filter does not delete existing files. Protects OutputWriter so partial runs cannot remove other " +
            "generated modules.")]
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
        [Description("Checks that an unknown name in the type filter is reported as a warning while the other requested types are still generated. Protects " +
            "Generator's handling of the --types option.")]
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
        [Description("Checks that no file of the generator mentions the BHoM_JSONSchema repository. Protects the generator's independence from that repository.")]
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
        [Description("Checks that no generated type is placed in the hand-written support package. Protects TypeRegistry from overwriting support modules.")]
        public void HandWrittenSupportPackageIsNotGenerated()
        {
            Assert.That(FixtureOutput.Result.Types.Any(t => t.Ref.Module.StartsWith("bhom_schema._support")), Is.False);
        }
    }
}
