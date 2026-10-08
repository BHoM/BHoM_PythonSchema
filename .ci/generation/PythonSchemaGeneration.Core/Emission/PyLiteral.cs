using System.Globalization;
using System.Text;

namespace PythonSchemaGeneration.Emission
{
    //Python source text for C# values, written the way repr()/ast.unparse would write them
    public static class PyLiteral
    {
        /***************************************************/

        public static string Str(string text)
        {
            char quote = text.Contains('\'') && !text.Contains('"') ? '"' : '\'';
            StringBuilder sb = new StringBuilder();
            sb.Append(quote);

            foreach (char c in text)
            {
                if (c == '\\') sb.Append("\\\\");
                else if (c == quote) sb.Append('\\').Append(c);
                else if (c == '\n') sb.Append("\\n");
                else if (c == '\r') sb.Append("\\r");
                else if (c == '\t') sb.Append("\\t");
                else if (c < 0x20 || c == 0x7f) sb.Append("\\x").Append(((int)c).ToString("x2"));
                else if (char.IsSurrogate(c) || char.IsControl(c)) sb.Append("\\u").Append(((int)c).ToString("x4"));
                else sb.Append(c);
            }

            sb.Append(quote);
            return sb.ToString();
        }

        /***************************************************/

        public static string Float(double value)
        {
            if (double.IsNaN(value)) return "float('nan')";
            if (double.IsPositiveInfinity(value)) return "float('inf')";
            if (double.IsNegativeInfinity(value)) return "float('-inf')";

            string text = value.ToString("R", CultureInfo.InvariantCulture).Replace("E", "e");
            if (!text.Contains('.') && !text.Contains('e'))
                text += ".0";

            return text;
        }

        /***************************************************/

        public static string Bool(bool value)
        {
            return value ? "True" : "False";
        }

        /***************************************************/
    }
}
