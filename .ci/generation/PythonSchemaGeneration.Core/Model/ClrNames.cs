using System.Text;

namespace PythonSchemaGeneration.Model
{
    //Canonical text form of a C# type, shared with the Python to C# converter (which rebuilds the same strings)
    public static class ClrNames
    {
        /***************************************************/

        private static readonly Dictionary<Type, string> m_Aliases = new Dictionary<Type, string>
        {
            { typeof(bool), "bool" }, { typeof(byte), "byte" }, { typeof(sbyte), "sbyte" },
            { typeof(short), "short" }, { typeof(ushort), "ushort" }, { typeof(int), "int" },
            { typeof(uint), "uint" }, { typeof(long), "long" }, { typeof(ulong), "ulong" },
            { typeof(float), "float" }, { typeof(double), "double" }, { typeof(decimal), "decimal" },
            { typeof(char), "char" }, { typeof(string), "string" }, { typeof(object), "object" },
        };

        /***************************************************/

        public static string Format(Type type)
        {
            if (type.IsGenericParameter)
                return type.Name;

            Type nullable = Nullable.GetUnderlyingType(type);
            if (nullable != null)
                return Format(nullable) + "?";

            if (type.IsArray)
            {
                int rank = type.GetArrayRank();
                return Format(type.GetElementType()) + "[" + new string(',', rank - 1) + "]";
            }

            if (m_Aliases.TryGetValue(type, out string alias))
                return alias;

            string name = BaseName(type);
            if (type.IsGenericType)
            {
                Type[] args = type.GetGenericArguments();
                return name + "<" + string.Join(", ", args.Select(Format)) + ">";
            }
            return name;
        }

        /***************************************************/

        //Full name without generic arity and arguments, nested types separated by dots
        public static string BaseName(Type type)
        {
            Type def = type.IsGenericType ? type.GetGenericTypeDefinition() : type;
            string fullName = def.FullName ?? ((def.Namespace == null ? "" : def.Namespace + ".") + def.Name);

            int tickIndex = fullName.IndexOf('`');
            if (tickIndex >= 0)
                fullName = fullName.Substring(0, tickIndex);

            return fullName.Replace('+', '.');
        }

        /***************************************************/

        public static string Join(IEnumerable<string> items)
        {
            StringBuilder sb = new StringBuilder();
            foreach (string s in items)
            {
                if (sb.Length > 0) sb.Append(", ");
                sb.Append(s);
            }

            return sb.ToString();
        }

        /***************************************************/
    }
}
