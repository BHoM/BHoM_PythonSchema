using System.Text;

namespace PythonSchemaGeneration.Mapping
{
    public static class Naming
    {
        /***************************************************/

        private static readonly HashSet<string> m_Keywords = new HashSet<string>
        {
            "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del",
            "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
            "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"
        };

        /***************************************************/

        public static bool IsKeyword(string name) { return m_Keywords.Contains(name); }

        /***************************************************/

        //Makes any name a valid Python identifier. Keywords get a trailing underscore.
        public static string Identifier(string name)
        {
            StringBuilder sb = new StringBuilder();
            foreach (char c in name)
                sb.Append(char.IsLetterOrDigit(c) || c == '_' ? c : '_');

            if (sb.Length == 0 || char.IsDigit(sb[0]))
                sb.Insert(0, '_');

            string id = sb.ToString();
            return IsKeyword(id) ? id + "_" : id;
        }

        /***************************************************/

        //Python class name for a C# type: the generic arity marker becomes an underscore (Output`1 -> Output_1)
        public static string TypeName(Type definition)
        {
            return Identifier(definition.Name.Replace('`', '_'));
        }

        /***************************************************/
    }
}
