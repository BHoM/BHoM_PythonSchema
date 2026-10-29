using System.ComponentModel;
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

        [Description("Tells whether a name is a Python keyword. Identifier uses it to decide whether a trailing underscore is needed.")]
        public static bool IsKeyword(string name) { return m_Keywords.Contains(name); }

        /***************************************************/

        [Description("Turns any text into a valid Python identifier: invalid characters become underscores, a leading digit gets an underscore in front, and a Python " +
            "keyword gets a trailing underscore. Used for field, enum member, folder and module names throughout the emission stage.")]
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

        [Description("Returns the Python class name of a C# type, turning the generic arity marker into an underscore (Output`1 becomes Output_1) and making the result a " +
            "valid identifier. The TypeRegistry uses it to build the module reference of each type.")]
        public static string TypeName(Type definition)
        {
            return Identifier(definition.Name.Replace('`', '_'));
        }

        /***************************************************/
    }
}
