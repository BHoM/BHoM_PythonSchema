using PythonSchemaGeneration.Extraction;
using PythonSchemaGeneration.Loading;

namespace PythonSchemaGeneration.Tests
{
    //The version of the package: read from BHoM.dll, written to _version.py, checked by --release
    public class VersionTests
    {
        [Description("Builds options for a full run over the fixture repository and BHoM, with an optional output folder and release. Used by every test in this class.")]
        private static GenerationOptions Options(string output, string release = null)
        {
            return new GenerationOptions
            {
                Assemblies = new List<System.Reflection.Assembly> { FixtureOutput.Alpha, FixtureOutput.Beta, typeof(BH.oM.Base.BHoMObject).Assembly },
                Repos = new List<string> { "BHoM/CSharpSchema_Test" },
                OutputFolder = output,
                ReleaseVersion = release,
            };
        }

        /***************************************************/

        [Test]
        [Description("Checks that a C# attribute class of the BHoM assembly is not selected for the package. Protects the schema from containing markers such as " +
            "DisplayTextAttribute, which are not data.")]
        public void AttributeClassesAreNotSelected()
        {
            Assert.That(TypeSelector.IsSelected(typeof(BH.oM.Base.Attributes.DisplayTextAttribute)), Is.False);
            Assert.That(TypeSelector.Select(new[] { typeof(BH.oM.Base.BHoMObject).Assembly }).Where(t => typeof(Attribute).IsAssignableFrom(t)), Is.Empty);
        }

        /***************************************************/

        [Test]
        [Description("Checks that the BHoM version is read as Major.Minor from the file version of BHoM.dll, and is null without it. Protects the package version from " +
            "following anything but the BHoM release.")]
        public void TheBHoMVersionIsMajorDotMinorOfTheBHoMAssembly()
        {
            string fileVersion = System.Diagnostics.FileVersionInfo.GetVersionInfo(typeof(BH.oM.Base.BHoMObject).Assembly.Location).FileVersion;
            string[] parts = fileVersion.Split('.');

            Assert.That(BHoMAdapter.BHoMVersion(new[] { typeof(BH.oM.Base.BHoMObject).Assembly }), Is.EqualTo(parts[0] + "." + parts[1]));
            Assert.That(BHoMAdapter.BHoMVersion(new[] { FixtureOutput.Alpha }), Is.Null);
        }

        /***************************************************/

        [Test]
        [Description("Checks that a full run writes _version.py with the BHoM version and a dev0 package version, and that a second run leaves the file alone. Protects " +
            "the weekly run from making a commit for nothing.")]
        public void ADevelopRunWritesTheVersionFileOnce()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-version-" + Guid.NewGuid().ToString("N"));
            try
            {
                string package = Path.Combine(folder, "bhom_schema");
                GenerationResult first = Generator.Run(Options(package));
                string text = File.ReadAllText(Path.Combine(package, "_version.py"));

                Assert.That(text, Does.Contain($"__bhom_version__ = \"{first.BHoMVersion}\""));
                Assert.That(text, Does.Contain($"__version__ = \"{first.BHoMVersion}.0.dev0\""));

                DateTime written = File.GetLastWriteTimeUtc(Path.Combine(package, "_version.py"));
                Generator.Run(Options(package));
                Assert.That(File.GetLastWriteTimeUtc(Path.Combine(package, "_version.py")), Is.EqualTo(written));
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }

        /***************************************************/

        [Test]
        [Description("Checks that a release run for the BHoM version gives the plain version, and a release for another version fails and writes nothing. Protects a " +
            "release from being named wrongly.")]
        public void AReleaseMustNameTheBHoMVersionItReads()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-release-" + Guid.NewGuid().ToString("N"));
            try
            {
                string package = Path.Combine(folder, "bhom_schema");
                string bhom = Generator.Run(Options(null)).BHoMVersion;

                Generator.Run(Options(package, bhom));
                Assert.That(File.ReadAllText(Path.Combine(package, "_version.py")), Does.Contain($"__version__ = \"{bhom}.0\""));

                string other = Path.Combine(folder, "other");
                Assert.Throws<InvalidOperationException>(() => Generator.Run(Options(other, "99.9")));
                Assert.That(Directory.Exists(other), Is.False);
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }

        /***************************************************/

        [Test]
        [Description("Checks that a run for some types only does not write _version.py. Protects the version file from being written by a partial run.")]
        public void APartialRunLeavesTheVersionFileAlone()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pysg-partial-" + Guid.NewGuid().ToString("N"));
            try
            {
                GenerationOptions options = Options(Path.Combine(folder, "bhom_schema"));
                options.Repos = null;
                options.TypeFilter = new List<string> { "BH.oM.FixtureAlpha.Beam" };
                Generator.Run(options);

                Assert.That(File.Exists(Path.Combine(folder, "bhom_schema", "_version.py")), Is.False);
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }
    }
}
