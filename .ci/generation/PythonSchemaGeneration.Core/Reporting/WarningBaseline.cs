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

        public static string Kind(string warning)
        {
            string text = m_Context.Replace(warning ?? "", "");
            text = m_QualifiedName.Replace(text, "<type>");
            return m_Number.Replace(text, "<n>").Trim();
        }

        /***************************************************/

        public static List<string> Kinds(IEnumerable<string> warnings)
        {
            return warnings.Select(Kind).Distinct(StringComparer.Ordinal).OrderBy(k => k, StringComparer.Ordinal).ToList();
        }

        /***************************************************/

        [Description("One kind per line. Blank lines and lines starting with # are comments.")]
        public static List<string> Read(string path)
        {
            return File.ReadAllLines(path).Select(l => l.Trim()).Where(l => l.Length > 0 && !l.StartsWith("#")).ToList();
        }

        /***************************************************/

        public static void Write(string path, IEnumerable<string> warnings)
        {
            string header = "# Known warning kinds of the generator. A kind that is not listed fails the run.\n# Update with --write-baseline after reviewing a new kind.\n";
            File.WriteAllText(path, header + string.Join("\n", Kinds(warnings)) + "\n", new System.Text.UTF8Encoding(false));
        }

        /***************************************************/

        [Description("The kinds in the warnings that the baseline does not list, and the listed kinds that no longer occur.")]
        public static (List<string> New, List<string> Gone) Compare(IEnumerable<string> warnings, IEnumerable<string> baseline)
        {
            List<string> found = Kinds(warnings);
            HashSet<string> known = new HashSet<string>(baseline, StringComparer.Ordinal);
            return (found.Where(k => !known.Contains(k)).ToList(), known.Where(k => !found.Contains(k)).OrderBy(k => k, StringComparer.Ordinal).ToList());
        }

        /***************************************************/
    }
}
