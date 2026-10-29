using PythonSchemaGeneration.Reporting;

namespace PythonSchemaGeneration.Tests
{
    //The command line and the warning baseline: what lets automation notice a problem instead of ignoring it
    public class CommandLineAndBaselineTests
    {
        /***************************************************/
        /**** Command line                              ****/
        /***************************************************/

        [Test]
        [Description("Checks that CommandLine.Parse reads every supported option into generation options and the baseline paths. Protects the command line that " +
            "the generation workflow calls.")]
        public void KnownOptionsAreRead()
        {
            CommandLine command = CommandLine.Parse(new[]
            {
                "--output", "out", "--assemblies", "dlls", "--org", "BHoM, Other", "--repos", "BHoM/A,BHoM/B", "--types", "X,Y",
                "--manifest", "m.json", "--report", "r.txt", "--baseline-warnings", "base.txt", "--write-baseline", "new.txt",
            });

            Assert.That(command.Error, Is.Null);
            Assert.That(command.Options.OutputFolder, Is.EqualTo("out"));
            Assert.That(command.Options.AssemblyFolder, Is.EqualTo("dlls"));
            Assert.That(command.Options.Organisations, Is.EqualTo(new[] { "BHoM", "Other" }));
            Assert.That(command.Options.Repos, Is.EqualTo(new[] { "BHoM/A", "BHoM/B" }));
            Assert.That(command.Options.TypeFilter, Is.EqualTo(new[] { "X", "Y" }));
            Assert.That(command.Options.ManifestPath, Is.EqualTo("m.json"));
            Assert.That(command.Options.ReportPath, Is.EqualTo("r.txt"));
            Assert.That(command.BaselinePath, Is.EqualTo("base.txt"));
            Assert.That(command.WriteBaselinePath, Is.EqualTo("new.txt"));
        }

        /***************************************************/

        [TestCase(new[] { "--output", "o", "--repo", "BHoM/A" }, "Unknown option --repo")]
        [TestCase(new[] { "--output", "o", "--types" }, "--types needs a value")]
        [TestCase(new[] { "--output", "--types", "A" }, "--output needs a value")]
        [TestCase(new[] { "output", "o" }, "Unexpected argument 'output'")]
        [TestCase(new string[0], "Missing --output")]
        [Description("Checks that unknown options, missing values, stray arguments and a missing output are reported as errors with no options. Protects the " +
            "generator command line so mistakes fail the run.")]
        public void MistakesAreErrorsNotIgnored(string[] args, string expected)
        {
            CommandLine command = CommandLine.Parse(args);
            Assert.That(command.Error, Does.Contain(expected));
            Assert.That(command.Options, Is.Null);
        }

        /***************************************************/
        /**** Warning baseline                          ****/
        /***************************************************/

        [TestCase("[BH.oM.X.Y.Level] default value 0 is not a member of enum BH.oM.X.Sparse, field is required",
                  "default value <n> is not a member of enum <type>, field is required")]
        [TestCase("[BH.oM.X.Y] type System.Collections.Generic.IComparable<System.Int32> has no Python equivalent and is mapped to Any",
                  "type <type> has no Python equivalent and is mapped to Any")]
        [TestCase("[A.B] base type System.Attribute is not an oM type and was dropped", "base type <type> is not an oM type and was dropped")]
        [TestCase("assembly has no github.com URL in its Description, repo is unknown", "assembly has no <type> URL in its Description, repo is unknown")]
        [Description("Checks that WarningBaseline.Kind strips type names and numbers from a warning to give its kind. Protects the warning baseline comparison.")]
        public void TheKindOfAWarningHasNoNamesOrNumbers(string warning, string kind)
        {
            Assert.That(WarningBaseline.Kind(warning), Is.EqualTo(kind));
        }

        /***************************************************/

        [Test]
        [Description("Checks that the same problem in different types counts as one warning kind. Protects the warning baseline from growing for repeated problems.")]
        public void TheSameProblemInAnotherTypeIsTheSameKind()
        {
            string[] warnings =
            {
                "[BH.oM.A.One.Level] default value 0 is not a member of enum BH.oM.A.Sparse, field is required",
                "[BH.oM.B.Two.Size] default value 7 is not a member of enum BH.oM.B.Other, field is required",
            };
            Assert.That(WarningBaseline.Kinds(warnings), Has.Count.EqualTo(1));
        }

        /***************************************************/

        [Test]
        [Description("Checks that Compare returns kinds missing from the baseline as new and baseline kinds no longer seen as gone. Protects the rule that a new " +
            "warning kind fails the run.")]
        public void ANewKindFailsAndAGoneKindIsReported()
        {
            string[] baseline = { "known kind", "kind that no longer occurs" };
            (List<string> newKinds, List<string> goneKinds) = WarningBaseline.Compare(new[] { "[X.Y] known kind", "[X.Y] something new at 3" }, baseline);

            Assert.That(newKinds, Is.EqualTo(new[] { "something new at <n>" }));
            Assert.That(goneKinds, Is.EqualTo(new[] { "kind that no longer occurs" }));
            Assert.That(WarningBaseline.Compare(new[] { "known kind" }, new[] { "known kind" }).New, Is.Empty);
        }

        /***************************************************/

        [Test]
        [Description("Checks that a baseline file is written with a comment header, sorted and de-duplicated, and read back ignoring comments. Protects the " +
            "committed baseline file format.")]
        public void TheBaselineFileRoundTripsAndIgnoresComments()
        {
            string path = Path.Combine(Path.GetTempPath(), "pysg-baseline-" + Guid.NewGuid().ToString("N") + ".txt");
            try
            {
                WarningBaseline.Write(path, new[] { "[A.B] default value 1 is wrong", "[C.D] default value 2 is wrong", "[E.F] another problem" });
                Assert.That(File.ReadAllText(path), Does.StartWith("# "));
                Assert.That(WarningBaseline.Read(path), Is.EqualTo(new[] { "another problem", "default value <n> is wrong" }));
            }
            finally
            {
                File.Delete(path);
            }
        }

        /***************************************************/

        [Test]
        [Description("Checks that a generator run on the fixtures has no warning kinds outside the committed baseline and no failed types. Protects the committed " +
            "baseline against drifting from the generator.")]
        public void TheFixtureWarningsAreInTheCommittedBaseline()
        {
            string baseline = Path.Combine(TestPaths.Root, ".ci", "generation", "warnings-baseline.txt");
            Assert.That(File.Exists(baseline), Is.True, "run the generator with --write-baseline to create it");

            GenerationResult result = Generator.Run(new GenerationOptions
            {
                Assemblies = new List<System.Reflection.Assembly> { FixtureOutput.Alpha, FixtureOutput.Beta, typeof(BH.oM.Base.BHoMObject).Assembly },
                Repos = new List<string> { "BHoM/CSharpSchema_Test" },
            });

            Assert.That(WarningBaseline.Compare(result.Reporter.Warnings, WarningBaseline.Read(baseline)).New, Is.Empty);
            Assert.That(result.FailedTypes, Is.Empty);
        }

        /***************************************************/
    }
}
