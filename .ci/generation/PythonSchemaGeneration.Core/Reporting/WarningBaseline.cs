using System.ComponentModel;
using System.Text.RegularExpressions;

namespace PythonSchemaGeneration.Reporting
{
    //The known kinds of warning. A warning kind is the message without its [context] and without the names and numbers in it, so the same problem in
    //another type is the same kind. A run fails on a kind that is not in the baseline: a change in BHoM that the generator does not handle yet.
    public static class WarningBaseline
    {
        /***************************************************/

        private static readonly Regex m_Context = new Regex(@"^\[[^\]]*\]\s*");
        private static readonly Regex m_QualifiedName = new Regex(@"\b[A-Za-z_]\w*(?:\.[A-Za-z_][\w`]*)+(?:<[^>]*>)?(?:\[[,\s]*\])*");
        private static readonly Regex m_Number = new Regex(@"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])");

        /***************************************************/

        [Description("Reduces a warning to its kind by removing the leading [context] and replacing type names and numbers with placeholders, so the same problem in another " +
            "type has the same kind. Used by Kinds and the baseline comparison.")]
        public static string Kind(string warning)
        {
            string text = m_Context.Replace(warning ?? "", "");
            text = m_QualifiedName.Replace(text, "<type>");
            return m_Number.Replace(text, "<n>").Trim();
        }

        /***************************************************/

        [Description("Returns the distinct kinds of the given warnings in ordinal order. Used by Write and Compare, and by Program to report the number of kinds.")]
        public static List<string> Kinds(IEnumerable<string> warnings)
        {
            return warnings.Select(Kind).Distinct(StringComparer.Ordinal).OrderBy(k => k, StringComparer.Ordinal).ToList();
        }

        /***************************************************/

        [Description("Reads the committed list of known warning kinds (one per line, blank lines and lines starting with # ignored). Program passes it to Compare to fail a run that has a kind not in the list.")]
        public static List<string> Read(string path)
        {
            return File.ReadAllLines(path).Select(l => l.Trim()).Where(l => l.Length > 0 && !l.StartsWith("#")).ToList();
        }

        /***************************************************/

        [Description("Writes the kinds of the given warnings, with a header, to the baseline file. Program does this for --write-baseline, after a new kind has been reviewed.")]
        public static void Write(string path, IEnumerable<string> warnings)
        {
            string header = "# Known warning kinds of the generator. A kind that is not listed fails the run.\n# Update with --write-baseline after reviewing a new kind.\n";
            File.WriteAllText(path, header + string.Join("\n", Kinds(warnings)) + "\n", new System.Text.UTF8Encoding(false));
        }

        /***************************************************/

        [Description("Compares the warning kinds of a run with the baseline: returns the new kinds, which fail the run, and the listed kinds that no longer occur, which Program reports so the baseline can be trimmed.")]
        public static (List<string> New, List<string> Gone) Compare(IEnumerable<string> warnings, IEnumerable<string> baseline)
        {
            List<string> found = Kinds(warnings);
            HashSet<string> known = new HashSet<string>(baseline, StringComparer.Ordinal);
            return (found.Where(k => !known.Contains(k)).ToList(), known.Where(k => !found.Contains(k)).OrderBy(k => k, StringComparer.Ordinal).ToList());
        }

        /***************************************************/
    }
}
