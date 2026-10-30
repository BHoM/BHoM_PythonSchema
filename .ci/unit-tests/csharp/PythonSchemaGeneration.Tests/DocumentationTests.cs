using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace PythonSchemaGeneration.Tests
{
    public class DocumentationTests
    {
        /***************************************************/

        private static readonly string[] m_Skipped = { "obj", "bin", ".vs", "_output", "TestResults", "golden", "Fixtures" };

        /***************************************************/

        [Test]
        [Description("Fails with the list of C# methods and constructors that have no Description attribute, so a new method cannot be added without saying what it does.")]
        public void EveryMethodHasADescription()
        {
            List<string> missing = new List<string>();
            string root = Path.Combine(TestPaths.Root, ".ci");
            foreach (string file in Directory.GetFiles(root, "*.cs", SearchOption.AllDirectories).OrderBy(f => f, StringComparer.Ordinal))
            {
                string relative = Path.GetRelativePath(TestPaths.Root, file);
                if (relative.Split(Path.DirectorySeparatorChar).Any(part => m_Skipped.Contains(part)))
                    continue;

                SyntaxNode tree = CSharpSyntaxTree.ParseText(File.ReadAllText(file)).GetRoot();
                foreach (BaseMethodDeclarationSyntax method in tree.DescendantNodes().OfType<BaseMethodDeclarationSyntax>())
                {
                    bool described = method.AttributeLists.SelectMany(l => l.Attributes).Any(a => a.Name.ToString().Split('.').Last() is "Description" or "DescriptionAttribute");
                    if (!described)
                    {
                        int line = method.GetLocation().GetLineSpan().StartLinePosition.Line + 1;
                        missing.Add($"{relative.Replace('\\', '/')}:{line} {Name(method)}");
                    }
                }
            }

            Assert.That(missing, Is.Empty, $"{missing.Count} methods have no Description attribute:\n" + string.Join("\n", missing.Take(60)));
        }

        /***************************************************/

        [Test]
        [Description("Guards the check above against silently looking at nothing, for example after a folder is renamed.")]
        public void TheSearchCoversTheGeneratorThePatcherAndTheTests()
        {
            string root = Path.Combine(TestPaths.Root, ".ci");
            foreach (string name in new[] { "Generator.cs", "FilePatcher.cs", "PatcherTests.cs" })
                Assert.That(Directory.GetFiles(root, name, SearchOption.AllDirectories), Is.Not.Empty, name);
        }

        /***************************************************/

        [Description("The name of a method or constructor, for the list of missing descriptions.")]
        private static string Name(BaseMethodDeclarationSyntax method)
        {
            return method switch
            {
                MethodDeclarationSyntax m => m.Identifier.ValueText,
                ConstructorDeclarationSyntax c => c.Identifier.ValueText + " (constructor)",
                _ => method.Kind().ToString(),
            };
        }

        /***************************************************/
    }
}
