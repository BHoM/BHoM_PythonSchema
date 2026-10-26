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

        public static string Output(string name) { return Path.Combine(Root, ".ci", "unit-tests", "_output", name); }
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

        //The generated modules import the hand-written support package, so the output folder needs a copy of it
        public static void CopySupport(string package)
        {
            Directory.CreateDirectory(package);
            File.Copy(Path.Combine(TestPaths.SupportPackage, "__init__.py"), Path.Combine(package, "__init__.py"), true);
            string support = Path.Combine(package, "_support");
            Directory.CreateDirectory(support);
            foreach (string file in Directory.GetFiles(Path.Combine(TestPaths.SupportPackage, "_support"), "*.py"))
                File.Copy(file, Path.Combine(support, Path.GetFileName(file)), true);
        }

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
            "BHoM", "Geometry_oM", "Structure_oM", "Graphics_oM", "Acoustic_oM", "Architecture_oM", "Quantities_oM", "dKoP_oM",
            "BHoM_Engine", "Reflection_Engine", "JsonSchema_Engine", "JsonSchema_oM"
        };

        public static List<string> Missing()
        {
            string folder = BHoMAdapter.DefaultAssemblyFolder();
            return Required.Where(a => !File.Exists(Path.Combine(folder, a + ".dll"))).ToList();
        }

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
            "BH.oM.dKoP.ProjectIdentification", "BH.oM.Geometry.Line", "BH.oM.Geometry.ICurve", "BH.oM.Base.BHoMObject",
            "BH.oM.Structure.Elements.Bar", "BH.oM.Graphics.Enums.GradientCenteringOptions", "BH.oM.Base.BHoMGroup`1",
            "BH.oM.Acoustic.Room", "BH.oM.Architecture.Elements.Room", "BH.oM.Graphics.Gradient", "BH.oM.Base.ComparisonConfig"
        };

        private static GenerationResult m_Spike;

        //Generates the spike set from the installed assemblies into _output/spike (including the support package)
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
