using PythonSchemaGeneration.Patcher;

namespace PythonSchemaGeneration.Tests
{
    //The Roslyn patcher: only the members a change names are touched, everything else stays byte for byte
    public class PatcherTests
    {
        private static readonly string Demo = Lf("""
            using BH.oM.Base;
            using System.ComponentModel;

            namespace BH.oM.Demo
            {
                [Description("A demo.")]
                public class Demo : BHoMObject, IThing
                {
                    /***************************************************/
                    /**** Properties                                ****/
                    /***************************************************/

                    [Description("First.")]
                    [DocumentationURL("https://bhom.xyz", DocumentationType.Documentation)]
                    public virtual double Length { get; set; } = 0;

                    // Kept comment
                    public virtual string Name { get; set; } = null;

                    [Length]
                    public virtual double Width { get; set; } = 1.5;

                    /***************************************************/
                }

                public enum Mode
                {
                    Slow,
                    Fast
                }

                public enum Coded
                {
                    A = 1,
                    B = 2,
                }
            }

            """);

        /***************************************************/

        [Test]
        [Description("Checks that patching with no changes returns a real BHoM file and a demo file unchanged. Protects the Roslyn patcher's promise to touch only " +
            "what a change names.")]
        public void NoChangesKeepTheFileByteForByte()
        {
            string bar = File.ReadAllText(TestPaths.Golden("patcher/Bar.cs"));
            Assert.That(Patch(bar, "Bar", "BH.oM.Structure.Elements").Text, Is.EqualTo(bar));
            Assert.That(Patch(Demo, "Demo").Text, Is.EqualTo(Demo));
        }

        /***************************************************/

        [Test]
        [Description("Checks that adding a property to the real Bar class inserts only its attribute and property lines after the named neighbour and adds no " +
            "notes. Protects the add-property change that py2cs sends to the patcher.")]
        public void AddedPropertyOnTheRealBarChangesOnlyItsLines()
        {
            string bar = File.ReadAllText(TestPaths.Golden("patcher/Bar.cs"));
            string nl = bar.Contains("\r\n") ? "\r\n" : "\n";
            string anchor = "        public virtual ISectionProperty SectionProperty { get; set; } = null;" + nl;
            Assert.That(bar, Does.Contain(anchor));

            Change mark = new Change { Kind = "addProperty", Name = "Mark", Type = "string", Initialiser = "\"\"", After = "SectionProperty", Add = { "Description(\"Fabrication mark\")" } };
            PatchResult result = Patch(bar, "Bar", "BH.oM.Structure.Elements", new List<string> { "System.ComponentModel" }, mark);

            string expected = bar.Replace(anchor, anchor + nl + "        [Description(\"Fabrication mark\")]" + nl + "        public virtual string Mark { get; set; } = \"\";" + nl);
            Assert.That(result.Text, Is.EqualTo(expected));
            Assert.That(result.Notes, Is.Empty);
        }

        /***************************************************/

        [Test]
        [Description("Checks that removing a property from the real Bar class also removes its attributes and comment but leaves the class attribute and other " +
            "members. Protects the remove-property change.")]
        public void RemovedPropertyOnTheRealBarTakesItsAttributesAndKeepsTheOthers()
        {
            string bar = File.ReadAllText(TestPaths.Golden("patcher/Bar.cs"));
            string text = Patch(bar, "Bar", "BH.oM.Structure.Elements", null, new Change { Kind = "removeProperty", Name = "OrientationAngle" }).Text;

            Assert.That(text, Does.Not.Contain("OrientationAngle"));
            Assert.That(text, Does.Not.Contain("[Angle]"));
            Assert.That(text, Does.Not.Contain("Controls the local axis orientation"));
            Assert.That(Count(text, "DocumentationURL"), Is.EqualTo(Count(bar, "DocumentationURL") - 1), "the class attribute stays");
            Assert.That(text, Does.Contain("public virtual BarRelease Release { get; set; } = null;"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that a property is added after the last member of a real dKoP class without disturbing anything else. Protects patching of files with " +
            "a different layout.")]
        public void ARealDkopPropertyIsAddedAtTheEnd()
        {
            string source = File.ReadAllText(TestPaths.Golden("patcher/ProjectIdentification.cs"));
            string nl = source.Contains("\r\n") ? "\r\n" : "\n";
            string anchor = "        public virtual string AdditionalReferences { get; set; } = \"\";" + nl;
            string text = Patch(source, "ProjectIdentification", "BH.oM.dKoP", null,
                new Change { Kind = "addProperty", Name = "ProjectNumber", Type = "string", Initialiser = "\"\"", After = "AdditionalReferences" }).Text;

            Assert.That(text, Is.EqualTo(source.Replace(anchor, anchor + nl + "        public virtual string ProjectNumber { get; set; } = \"\";" + nl)));
        }

        /***************************************************/

        [Test]
        [Description("Checks that a property with an anchor is added after it and one without an anchor is added first, with the requested attributes. Protects " +
            "property placement.")]
        public void PropertiesAreAddedAfterTheirNeighbourOrFirst()
        {
            PatchResult result = Patch(Demo, "Demo", "BH.oM.Demo", null,
                new Change { Kind = "addProperty", Name = "Height", Type = "double", Initialiser = "0.0", After = "Width", Add = { "Description(\"H.\")" } },
                new Change { Kind = "addProperty", Name = "Id", Type = "string" });

            string expected = Demo
                .Replace("        public virtual double Width { get; set; } = 1.5;\n",
                         "        public virtual double Width { get; set; } = 1.5;\n\n        [Description(\"H.\")]\n        public virtual double Height { get; set; } = 0.0;\n")
                .Replace("        [Description(\"First.\")]\n", "        public virtual string Id { get; set; }\n\n        [Description(\"First.\")]\n");
            Assert.That(result.Text, Is.EqualTo(expected));
        }

        /***************************************************/

        [Test]
        [Description("Checks that removing a property also removes its leading comment and one blank line. Protects the formatting left behind by the " +
            "remove-property change.")]
        public void RemovedPropertyTakesItsCommentAndOneBlankLine()
        {
            string text = Patch(Demo, "Demo", "BH.oM.Demo", null, new Change { Kind = "removeProperty", Name = "Name" }).Text;
            Assert.That(text, Is.EqualTo(Demo.Replace("        // Kept comment\n        public virtual string Name { get; set; } = null;\n\n", "")));
        }

        /***************************************************/

        [Test]
        [Description("Checks that property types and initialisers are changed in place and that equal defaults such as 0 and 0.0 are left alone. Protects the " +
            "set-type and set-initialiser changes.")]
        public void TypesAndDefaultsChangeInPlace()
        {
            PatchResult result = Patch(Demo, "Demo", "BH.oM.Demo", null,
                new Change { Kind = "setPropertyType", Name = "Width", Type = "float" },
                new Change { Kind = "setPropertyInitialiser", Name = "Width" },
                new Change { Kind = "setPropertyInitialiser", Name = "Length", Initialiser = "0.0" },
                new Change { Kind = "setPropertyInitialiser", Name = "Name", Initialiser = "\"x\"" });

            string expected = Demo
                .Replace("public virtual double Width { get; set; } = 1.5;", "public virtual float Width { get; set; }")
                .Replace("public virtual string Name { get; set; } = null;", "public virtual string Name { get; set; } = \"x\";");
            Assert.That(result.Text, Is.EqualTo(expected), "0 and 0.0 are the same default, so Length is untouched");
        }

        /***************************************************/

        [Test]
        [Description("Checks that descriptions on properties and the class are replaced, added or removed without touching other attributes. Protects the " +
            "set-description change.")]
        public void DescriptionsAreReplacedAddedOrRemovedWithoutTouchingOtherAttributes()
        {
            PatchResult result = Patch(Demo, "Demo", "BH.oM.Demo", null,
                new Change { Kind = "setDescription", Name = "Length", Description = "\"Changed.\"" },
                new Change { Kind = "setDescription", Name = "Name", Description = "\"N.\"" },
                new Change { Kind = "setDescription" });

            string expected = Demo
                .Replace("[Description(\"First.\")]", "[Description(\"Changed.\")]")
                .Replace("        // Kept comment\n", "        // Kept comment\n        [Description(\"N.\")]\n")
                .Replace("    [Description(\"A demo.\")]\n", "");
            Assert.That(result.Text, Is.EqualTo(expected));
            Assert.That(result.Text, Does.Contain("DocumentationURL"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that attributes are removed and added by name and that removing an absent attribute produces a note. Protects the set-attributes " +
            "change for quantities and display text.")]
        public void AttributesAreSwappedByName()
        {
            PatchResult result = Patch(Demo, "Demo", "BH.oM.Demo", null,
                new Change { Kind = "setAttributes", Name = "Width", Remove = { "Length" }, Add = { "Area" } },
                new Change { Kind = "setAttributes", Name = "Length", Add = { "DisplayText(\"L\")" } },
                new Change { Kind = "setAttributes", Name = "Name", Remove = { "DisplayText" } });

            string expected = Demo
                .Replace("        [Length]\n", "        [Area]\n")
                .Replace("DocumentationType.Documentation)]\n", "DocumentationType.Documentation)]\n        [DisplayText(\"L\")]\n");
            Assert.That(result.Text, Is.EqualTo(expected));
            Assert.That(result.Notes, Has.One.Contains("DisplayText was not found"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that base types are added and removed by name and that a missing base produces a note. Protects the set-bases change.")]
        public void BasesAreAddedAndRemovedByName()
        {
            PatchResult result = Patch(Demo, "Demo", "BH.oM.Demo", null, new Change { Kind = "setBases", Remove = { "IThing", "IMissing" }, Add = { "IOther", "BH.oM.Base.BHoMObject" } });
            Assert.That(result.Text, Is.EqualTo(Demo.Replace("public class Demo : BHoMObject, IThing", "public class Demo : BHoMObject, IOther")));
            Assert.That(result.Notes, Has.One.Contains("IMissing"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that a member added to an enum without explicit values goes at the end with a note, so existing values do not shift. Protects the " +
            "add-enum-member change.")]
        public void EnumMembersWithoutValuesOnlyGrowAtTheEnd()
        {
            PatchResult result = Patch(Demo, "Mode", "BH.oM.Demo", null, new Change { Kind = "addEnumMember", Name = "Medium", Value = "2", After = "Slow" });
            Assert.That(result.Text, Is.EqualTo(Demo.Replace("        Slow,\n        Fast\n", "        Slow,\n        Fast,\n        Medium\n")));
            Assert.That(result.Notes, Has.One.Contains("added at the end"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that enum members with explicit values are added, removed and renumbered in place, with descriptions. Protects the enum member changes.")]
        public void EnumMembersWithValuesAreAddedRemovedAndRenumbered()
        {
            PatchResult result = Patch(Demo, "Coded", "BH.oM.Demo", new List<string> { "System.ComponentModel" },
                new Change { Kind = "addEnumMember", Name = "C", Value = "3", After = "B", Description = "\"Third.\"" },
                new Change { Kind = "removeEnumMember", Name = "A" },
                new Change { Kind = "setEnumValue", Name = "B", Value = "5" });

            Assert.That(result.Text, Is.EqualTo(Demo.Replace("        A = 1,\n        B = 2,\n", "        B = 5,\n        [Description(\"Third.\")]\n        C = 3,\n")));
            Assert.That(result.Notes, Is.Empty);
        }

        /***************************************************/

        [Test]
        [Description("Checks that missing using directives are added once and existing ones are not duplicated. Protects the usings that the changes require.")]
        public void MissingUsingsAreAddedOnce()
        {
            string text = Patch(Demo, "Demo", "BH.oM.Demo", new List<string> { "System.ComponentModel", "BH.oM.Quantities.Attributes" },
                new Change { Kind = "addProperty", Name = "Depth", Type = "double", After = "Width", Add = { "Length" } }).Text;
            Assert.That(text, Does.StartWith("using BH.oM.Base;\nusing System.ComponentModel;\nusing BH.oM.Quantities.Attributes;\n\nnamespace"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that a property added to an immutable class is get-only and produces a note about the constructor. Protects patching of immutable types.")]
        public void GetOnlyClassesGetGetOnlyPropertiesAndANote()
        {
            string source = Lf("""
                namespace BH.oM.Demo
                {
                    public class Fixed : IImmutable
                    {
                        public virtual string Id { get; }

                        public Fixed(string id)
                        {
                            Id = id;
                        }
                    }
                }

                """);
            PatchResult result = Patch(source, "Fixed", "BH.oM.Demo", null, new Change { Kind = "addProperty", Name = "Extra", Type = "string", After = "Id" });
            Assert.That(result.Text, Is.EqualTo(source.Replace("        public virtual string Id { get; }\n", "        public virtual string Id { get; }\n\n        public virtual string Extra { get; }\n")));
            Assert.That(result.Notes, Has.One.Contains("constructor"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that properties are added to interfaces without a modifier and inside regions in the right place. Protects patching of interfaces and " +
            "region-structured files.")]
        public void InterfacesAndRegionsKeepTheirShape()
        {
            string source = Lf("""
                namespace BH.oM.Demo
                {
                    public interface IThing : IObject
                    {
                        string Label { get; set; }
                    }

                    public class Regioned : BHoMObject
                    {
                        #region Properties

                        public virtual int A { get; set; } = 0;

                        #endregion
                    }
                }

                """);
            string inInterface = Patch(source, "IThing", "BH.oM.Demo", null, new Change { Kind = "addProperty", Name = "Count", Type = "int", Initialiser = "3", After = "Label" }).Text;
            Assert.That(inInterface, Is.EqualTo(source.Replace("        string Label { get; set; }\n", "        string Label { get; set; }\n\n        int Count { get; set; }\n")));

            string inRegion = Patch(source, "Regioned", "BH.oM.Demo", null, new Change { Kind = "addProperty", Name = "B", Type = "int", Initialiser = "0", After = "A" }).Text;
            Assert.That(inRegion, Is.EqualTo(source.Replace("        public virtual int A { get; set; } = 0;\n", "        public virtual int A { get; set; } = 0;\n\n        public virtual int B { get; set; } = 0;\n")));
        }

        /***************************************************/

        [Test]
        [Description("Checks that patching a CRLF file adds only CRLF line endings. Protects files that use Windows line endings from mixed endings.")]
        public void WindowsLineEndingsAreKept()
        {
            string source = Demo.Replace("\n", "\r\n");
            string text = Patch(source, "Demo", "BH.oM.Demo", null, new Change { Kind = "addProperty", Name = "Height", Type = "double", After = "Width" }).Text;
            Assert.That(text.Replace("\r\n", ""), Does.Not.Contain("\n"));
            Assert.That(text, Does.Contain("= 1.5;\r\n\r\n        public virtual double Height { get; set; }\r\n"));
        }

        /***************************************************/

        [Test]
        [Description("Checks that a missing type throws and a missing member leaves the file unchanged with a note. Protects the patcher from guessing when the C# " +
            "differs from what py2cs expected.")]
        public void AMissingTypeOrMemberIsReportedNotGuessed()
        {
            Assert.Throws<InvalidOperationException>(() => Patch(Demo, "Nowhere"));
            PatchResult result = Patch(Demo, "Demo", "BH.oM.Demo", null, new Change { Kind = "removeProperty", Name = "Ghost" });
            Assert.That(result.Text, Is.EqualTo(Demo));
            Assert.That(result.Notes, Has.One.Contains("Ghost was not found"));
        }

        /***************************************************/

        [Description("Builds a file job for the given type, namespace, usings and changes and runs the patcher on the source, returning the patched text and " +
            "notes. Used by every test in this class.")]
        private static PatchResult Patch(string source, string type, string ns = "BH.oM.Demo", List<string> usings = null, params Change[] changes)
        {
            FileJob job = new FileJob { Type = type, Namespace = ns, Usings = usings ?? new List<string>(), Changes = changes.ToList() };
            return FilePatcher.Patch(source, job);
        }

        /***************************************************/

        [Description("Converts line endings of the text to LF so raw-string sources are the same on every platform. Used for the demo sources in this class.")]
        private static string Lf(string text)
        {
            return text.Replace("\r\n", "\n");
        }

        /***************************************************/

        [Description("Counts how many times a part occurs in a text. Used to check how many DocumentationURL attributes remain after a removal.")]
        private static int Count(string text, string part)
        {
            return (text.Length - text.Replace(part, "").Length) / part.Length;
        }

        /***************************************************/
    }
}
