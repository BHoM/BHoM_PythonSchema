using System.Reflection;
using System.Runtime.Loader;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using PythonSchemaGeneration;
using PythonSchemaGeneration.Loading;

namespace PythonSchemaGeneration.Tests
{
    //Python to C# round trip: the C# drafted from the generated Python must compile, and reflect back to the same types.
    //The drafts are written by `python -m py2cs drafts` (see run-all.ps1); the comparison with the original manifest is done by pytest.
    [Category("RoundTrip")]
    public class RoundTripTests
    {
        [TestCase("fixtures")]
        [TestCase("spike")]
        public void DraftsCompileAndReflectBack(string set)
        {
            if (set == "spike")
                RealAssemblies.RequireOrSkip();

            string folder = TestPaths.Output(Path.Combine("roundtrip", set));
            if (!Directory.Exists(folder))
            {
                string message = $"No drafts in {folder}: run `python -m py2cs drafts` first";
                if (string.Equals(Environment.GetEnvironmentVariable("CI"), "true", StringComparison.OrdinalIgnoreCase))
                    Assert.Fail(message);
                Assert.Ignore(message);
            }

            List<SyntaxTree> trees = Directory.GetFiles(folder, "*.cs", SearchOption.AllDirectories)
                .OrderBy(f => f, StringComparer.Ordinal)
                .Select(f => CSharpSyntaxTree.ParseText(File.ReadAllText(f), path: f))
                .ToList();
            Assert.That(trees.Count, Is.GreaterThan(10));
            trees.Add(CSharpSyntaxTree.ParseText("[assembly: System.Reflection.AssemblyDescription(\"https://github.com/BHoM/Draft_Toolkit\")]"));

            CSharpCompilation compilation = CSharpCompilation.Create("Draft_oM", trees, References(),
                new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary, nullableContextOptions: NullableContextOptions.Disable));

            using MemoryStream stream = new MemoryStream();
            var result = compilation.Emit(stream);
            List<string> errors = result.Diagnostics.Where(d => d.Severity == DiagnosticSeverity.Error).Select(d => d.ToString()).ToList();
            Assert.That(errors, Is.Empty, string.Join("\n", errors.Take(20)));

            stream.Position = 0;
            AssemblyLoadContext context = new AssemblyLoadContext("draft-" + set, true);
            try
            {
                Assembly draft = context.LoadFromStream(stream);
                string manifest = Path.Combine(folder, "draft-manifest.json");
                GenerationResult generated = Generator.Run(new GenerationOptions
                {
                    Assemblies = new List<Assembly> { draft },
                    ManifestPath = manifest,
                });
                Assert.That(File.Exists(manifest), Is.True);
                Assert.That(generated.Types.Count, Is.EqualTo(trees.Count - 1), "every draft file declares one type that reflects back");
            }
            finally
            {
                context.Unload();
            }
        }

        /***************************************************/

        private static List<MetadataReference> References()
        {
            string[] trusted = ((string)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")).Split(Path.PathSeparator);
            List<string> paths = trusted
                .Where(p => Path.GetFileName(p).StartsWith("System.") || Path.GetFileName(p).StartsWith("Microsoft.") || Path.GetFileName(p) is "netstandard.dll" or "mscorlib.dll")
                .ToList();
            paths.Add(typeof(BH.oM.Base.BHoMObject).Assembly.Location);
            paths.Add(typeof(System.Drawing.Color).Assembly.Location);
            string quantities = Path.Combine(BHoMAdapter.DefaultAssemblyFolder(), "Quantities_oM.dll");
            if (File.Exists(quantities))
                paths.Add(quantities);
            return paths.Distinct().Select(p => (MetadataReference)MetadataReference.CreateFromFile(p)).ToList();
        }
    }
}
