using System.Reflection;
using BH.oM.Base;
using PythonSchemaGeneration;
using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Extraction;
using PythonSchemaGeneration.Loading;

namespace PythonSchemaGeneration.Tests
{
    public static class TestPaths
    {
        public static string Root
        {
            get
            {
                string dir = AppContext.BaseDirectory;
                while (dir != null && !Directory.Exists(Path.Combine(dir, ".ci")))
                    dir = Path.GetDirectoryName(dir);
                return dir ?? throw new InvalidOperationException("Repository root (folder containing .ci) not found");
            }
        }

        [Description("Returns the path of a file or folder inside .ci/unit-tests/_output, where the NUnit tests write the generated Python and manifests that the " +
            "pytest suites read.")]
        public static string Output(string name) { return Path.Combine(Root, ".ci", "unit-tests", "_output", name); }

        [Description("Returns the path of a file inside .ci/unit-tests/golden, which holds the expected generator output and the patcher input files used by " +
            "GoldenAssert and PatcherTests.")]
        public static string Golden(string name) { return Path.Combine(Root, ".ci", "unit-tests", "golden", name); }

        public static string SupportPackage { get { return Path.Combine(Root, "src", "bhom_schema"); } }
    }

    //Generates the Python package for the fixture assemblies once, into _output/fixtures, where the pytest tests pick it up
    public static class FixtureOutput
    {
        private static readonly object m_Lock = new object();
        private static GenerationResult m_Result;

        public static Assembly Alpha { get { return typeof(BH.oM.FixtureAlpha.PointLike).Assembly; } }
        public static Assembly Beta { get { return typeof(BH.oM.FixtureBeta.PointLike).Assembly; } }

        public static string Folder { get { return TestPaths.Output("fixtures"); } }
        public static string Package { get { return Path.Combine(Folder, "bhom_schema"); } }

        public static GenerationResult Result
        {
            get
            {
                lock (m_Lock)
                {
                    if (m_Result == null)
                        m_Result = Generate(Folder, true);
                    return m_Result;
                }
            }
        }

        [Description("Recreates the folder, copies the hand-written support package into it and runs the generator over the fixture assemblies, optionally writing " +
            "the manifest and report. FixtureOutput.Result uses it for the output the pytest suites read, and the determinism test uses it for two " +
            "throw-away runs.")]
        public static GenerationResult Generate(string folder, bool withManifest)
        {
            if (Directory.Exists(folder))
                Directory.Delete(folder, true);
            Directory.CreateDirectory(folder);
            CopySupport(Path.Combine(folder, "bhom_schema"));

            List<Assembly> assemblies = new List<Assembly> { Alpha, Beta, typeof(BHoMObject).Assembly };
            GenerationOptions options = new GenerationOptions
            {
                Assemblies = assemblies,
                OutputFolder = Path.Combine(folder, "bhom_schema"),
                TypeFilter = TypeSelector.Select(new[] { Alpha, Beta }).Select(t => t.FullName).ToList(),
                ManifestPath = withManifest ? Path.Combine(folder, "manifest.json") : null,
                ReportPath = withManifest ? Path.Combine(folder, "report.txt") : null,
            };
            return Generator.Run(options);
        }

        [Description("Copies the hand-written bhom_schema __init__, _version and _support modules into the given package folder, because the generated modules import them. " +
            "Every test that generates Python into a folder calls it first.")]
        public static void CopySupport(string package)
        {
            Directory.CreateDirectory(package);
            File.Copy(Path.Combine(TestPaths.SupportPackage, "__init__.py"), Path.Combine(package, "__init__.py"), true);
            File.Copy(Path.Combine(TestPaths.SupportPackage, "_version.py"), Path.Combine(package, "_version.py"), true);
            string support = Path.Combine(package, "_support");
            Directory.CreateDirectory(support);
            foreach (string file in Directory.GetFiles(Path.Combine(TestPaths.SupportPackage, "_support"), "*.py"))
                File.Copy(file, Path.Combine(support, Path.GetFileName(file)), true);
        }

        [Description("Returns the generated type with the given CLR name from the shared fixture run. The fixture extraction tests use it to inspect the Python " +
            "text and properties of one type.")]
        public static RenderedType Rendered(string clrName)
        {
            return Result.Types.Single(t => t.Model.ClrName == clrName);
        }
    }

    //Real BHoM assemblies: the tests fail in CI and are ignored locally when an assembly is missing
    public static class RealAssemblies
    {
        public static readonly string[] Required =
        {
            "BHoM", "Geometry_oM", "Structure_oM", "Graphics_oM", "Acoustic_oM", "Architecture_oM", "Quantities_oM",
            "BHoM_Engine", "Reflection_Engine", "JsonSchema_Engine", "JsonSchema_oM"
        };

        [Description("Lists the required real BHoM assemblies that are not in the default BHoM assembly folder. RequireOrSkip uses it to decide whether the " +
            "real-type tests can run.")]
        public static List<string> Missing()
        {
            string folder = BHoMAdapter.DefaultAssemblyFolder();
            return Required.Where(a => !File.Exists(Path.Combine(folder, a + ".dll"))).ToList();
        }

        [Description("Returns when all required real BHoM assemblies are installed; otherwise fails the test when the CI environment variable is true and ignores " +
            "it locally, with a message naming the missing assemblies. The real-type and spike round-trip tests call it so CI never skips them silently.")]
        public static void RequireOrSkip()
        {
            List<string> missing = Missing();
            if (missing.Count == 0)
                return;
            string message = "Missing BHoM assemblies in " + BHoMAdapter.DefaultAssemblyFolder() + ": " + string.Join(", ", missing);
            if (string.Equals(Environment.GetEnvironmentVariable("CI"), "true", StringComparison.OrdinalIgnoreCase))
                Assert.Fail(message);
            Assert.Ignore(message);
        }

        public static readonly string[] SpikeTypes =
        {
            "BH.oM.Geometry.Line", "BH.oM.Geometry.ICurve", "BH.oM.Base.BHoMObject",
            "BH.oM.Structure.Elements.Bar", "BH.oM.Graphics.Enums.GradientCenteringOptions", "BH.oM.Base.BHoMGroup`1",
            "BH.oM.Acoustic.Room", "BH.oM.Architecture.Elements.Room", "BH.oM.Graphics.Gradient", "BH.oM.Base.ComparisonConfig"
        };

        private static GenerationResult m_Spike;

        [Description("Generates the Python (with support package, manifest and report) for the fixed set of real BHoM spike types from the installed assemblies " +
            "into _output/spike, once, and returns the cached result. RealTypeTests and the pytest spike suite read it.")]
        public static GenerationResult Spike()
        {
            if (m_Spike != null)
                return m_Spike;
            string folder = TestPaths.Output("spike");
            if (Directory.Exists(folder))
                Directory.Delete(folder, true);
            Directory.CreateDirectory(folder);
            FixtureOutput.CopySupport(Path.Combine(folder, "bhom_schema"));
            m_Spike = Generator.Run(new GenerationOptions
            {
                AssemblyFolder = BHoMAdapter.DefaultAssemblyFolder(),
                OutputFolder = Path.Combine(folder, "bhom_schema"),
                TypeFilter = SpikeTypes.ToList(),
                ManifestPath = Path.Combine(folder, "manifest.json"),
                ReportPath = Path.Combine(folder, "report.txt"),
            });
            return m_Spike;
        }
    }
}
