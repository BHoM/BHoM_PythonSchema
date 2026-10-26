using System.Collections;
using System.Globalization;
using System.Text.RegularExpressions;
using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;
using PythonSchemaGeneration.Reporting;

namespace PythonSchemaGeneration.Emission
{
    public enum DefaultKind { None, Literal, Factory }

    public class DefaultText
    {
        public DefaultKind Kind = DefaultKind.None;
        public string Text;
        public bool IsNull;     //the default is null, so the annotation must allow None
    }

    //Turns the value read from a fresh C# instance into Python source
    public class DefaultFormatter
    {
        private readonly TypeRegistry m_Registry;
        private readonly Reporter m_Reporter;
        private readonly NameTracker m_Scope;
        private readonly string m_Context;
        private readonly HashSet<string> m_TypeParams;

        public DefaultFormatter(TypeRegistry registry, Reporter reporter, NameTracker scope, string context, IEnumerable<string> typeParams)
        {
            m_Registry = registry;
            m_Reporter = reporter;
            m_Scope = scope;
            m_Context = context;
            m_TypeParams = new HashSet<string>(typeParams);
        }

        /***************************************************/

        public DefaultText Format(PropertyModel property, MappedType mapped)
        {
            if (property.Default == null)
                return new DefaultText();

            object value = property.Default.Value;
            if (value == null)
                return new DefaultText { Kind = DefaultKind.Literal, Text = "None", IsNull = true };

            Type vt = value.GetType();
            string member = m_Context + "." + property.Name;

            if (property.Default.NonDeterministic)
            {
                if (vt == typeof(Guid))
                    return Factory(m_Scope.AddStandardName("uuid", "uuid4"));
                return Factory(m_Scope.AddStandardName("datetime", "datetime") + ".now");
            }

            if (vt == typeof(bool)) return Literal(PyLiteral.Bool((bool)value));
            if (vt == typeof(char)) return Literal(PyLiteral.Str(value.ToString()));
            if (vt == typeof(string)) return Literal(PyLiteral.Str((string)value));
            if (vt == typeof(double)) return Literal(PyLiteral.Float((double)value));
            if (vt == typeof(float)) return Literal(PyLiteral.Float(Convert.ToDouble(value.ToString(), CultureInfo.InvariantCulture)));
            if (vt == typeof(decimal))
                return Literal($"{m_Scope.AddStandardName("decimal", "Decimal")}({PyLiteral.Str(((decimal)value).ToString(CultureInfo.InvariantCulture))})");
            if (vt.IsPrimitive)
                return Literal(Convert.ToString(value, CultureInfo.InvariantCulture));

            if (vt.IsEnum)
                return Enum(vt, value, member);

            if (vt == typeof(Guid))
            {
                Guid guid = (Guid)value;
                string uuid = m_Scope.AddStandardName("uuid", "UUID");
                return Literal(guid == Guid.Empty ? $"{uuid}(int=0)" : $"{uuid}({PyLiteral.Str(guid.ToString())})");
            }
            if (vt == typeof(DateTime) || vt == typeof(DateTimeOffset))
            {
                DateTime dt = vt == typeof(DateTime) ? (DateTime)value : ((DateTimeOffset)value).UtcDateTime;
                string datetime = m_Scope.AddStandardName("datetime", "datetime");
                if (dt == DateTime.MinValue)
                    return Literal(datetime + ".min");
                return Literal($"{datetime}({dt.Year}, {dt.Month}, {dt.Day}, {dt.Hour}, {dt.Minute}, {dt.Second}, {(int)((dt.Ticks % TimeSpan.TicksPerSecond) / 10)})");
            }
            if (vt == typeof(TimeSpan))
            {
                TimeSpan ts = (TimeSpan)value;
                string timedelta = m_Scope.AddStandardName("datetime", "timedelta");
                return Literal(ts == TimeSpan.Zero ? $"{timedelta}(0)" : $"{timedelta}(seconds={PyLiteral.Float(ts.TotalSeconds)})");
            }
            if (vt.FullName == "System.Drawing.Color")
                return ColorDefault(value);

            if (value is IEnumerable enumerable)
                return Collection(enumerable, mapped, member);

            if (m_Registry.Contains(vt) && !vt.IsAbstract && (vt.IsValueType || vt.GetConstructor(Type.EmptyTypes) != null))
            {
                //The Python class cannot be created without arguments if one of its own defaults was left out
                if (HasUnwritableEnum(value, 0))
                {
                    m_Reporter.Warn(member, $"default instance of {ClrNames.Format(vt)} cannot be created in Python, field is required");
                    return new DefaultText();
                }

                PyRef pyRef = m_Registry.Ref(vt);
                return Factory($"lambda: {m_Scope.Reference(vt, pyRef, false)}()");
            }

            m_Reporter.Warn(member, $"default value of type {ClrNames.Format(vt)} cannot be written in Python, field is required");
            return new DefaultText();
        }

        /***************************************************/

        private static DefaultText Literal(string text)
        {
            return new DefaultText { Kind = DefaultKind.Literal, Text = text };
        }

        private static DefaultText Factory(string text)
        {
            return new DefaultText { Kind = DefaultKind.Factory, Text = text };
        }

        /***************************************************/

        private DefaultText Enum(Type type, object value, string member)
        {
            if (!m_Registry.Contains(type))
                return Literal(PyLiteral.Str(value.ToString()));

            string local = m_Scope.Reference(type, m_Registry.Ref(type), true);
            if (System.Enum.IsDefined(type, value))
                return Literal($"{local}.{Naming.Identifier(value.ToString())}");

            //A plain Python Enum rejects a value that is not a member, so only flags enums can carry one
            if (!type.IsDefined(typeof(FlagsAttribute), false))
            {
                m_Reporter.Warn(member, $"default value {value:D} is not a member of enum {ClrNames.Format(type)}, field is required");
                return new DefaultText();
            }

            object raw = Convert.ChangeType(value, System.Enum.GetUnderlyingType(type));
            return Literal($"{local}({Convert.ToString(raw, CultureInfo.InvariantCulture)})");
        }

        private DefaultText ColorDefault(object value)
        {
            Type t = value.GetType();
            int a = Convert.ToInt32(t.GetProperty("A").GetValue(value));
            int r = Convert.ToInt32(t.GetProperty("R").GetValue(value));
            int g = Convert.ToInt32(t.GetProperty("G").GetValue(value));
            int b = Convert.ToInt32(t.GetProperty("B").GetValue(value));
            string color = m_Scope.AddStandardName("bhom_schema._support", "Color");
            if (a == 0 && r == 0 && g == 0 && b == 0)
                return Factory(color);
            return Factory($"lambda: {color}(A={a}, R={r}, G={g}, B={b})");
        }

        /***************************************************/

        private DefaultText Collection(IEnumerable enumerable, MappedType mapped, string member)
        {
            string expr = mapped.Expression.Replace(" | None", "");
            string head = expr.Split('[')[0];
            List<object> items = enumerable.Cast<object>().ToList();

            //Containers that mention a type parameter need the subscripted form so the factory stays typed
            if (head != "list" && head != "set" && head != "dict")
            {
                m_Reporter.Warn(member, $"default collection mapped to {expr} is not supported, field is required");
                return new DefaultText();
            }

            //A lambda is evaluated after the class exists, so it can name the class itself or a type parameter
            bool generic = m_TypeParams.Any(p => Regex.IsMatch(expr, $@"\b{Regex.Escape(p)}\b"));
            string factory = generic ? (head == "set" ? "lambda: set()" : head == "dict" ? "lambda: {}" : "lambda: []") : head;

            if (enumerable is Array array && array.Rank == 2)
                return Matrix(array, factory, member);

            if (items.Count == 0)
                return Factory(factory);

            List<string> literals = new List<string>();
            foreach (object item in items)
            {
                string text = SimpleLiteral(item);
                if (text == null)
                {
                    m_Reporter.Warn(member, "default collection holds complex items, an empty collection is used instead");
                    return Factory(factory);
                }
                literals.Add(text);
            }
            if (head == "dict")
            {
                m_Reporter.Warn(member, "non-empty default dictionary is not written, an empty dictionary is used instead");
                return Factory(factory);
            }
            string body = string.Join(", ", literals);
            return Factory(head == "set" ? $"lambda: {{{body}}}" : $"lambda: [{body}]");
        }

        private bool HasUnwritableEnum(object value, int depth)
        {
            if (value == null || depth > 4)
                return false;

            Type type = value.GetType();
            foreach (System.Reflection.PropertyInfo property in type.GetProperties())
            {
                if (property.GetIndexParameters().Length > 0 || !property.CanRead)
                    continue;

                object item;
                try { item = property.GetValue(value); }
                catch { continue; }

                if (item == null)
                    continue;

                Type itemType = item.GetType();
                if (itemType.IsEnum && m_Registry.Contains(itemType))
                {
                    if (!System.Enum.IsDefined(itemType, item) && !itemType.IsDefined(typeof(FlagsAttribute), false))
                        return true;
                }
                else if (m_Registry.Contains(itemType) && !itemType.IsEnum && HasUnwritableEnum(item, depth + 1))
                    return true;
            }

            return false;
        }

        private DefaultText Matrix(Array array, string emptyFactory, string member)
        {
            List<string> rows = new List<string>();
            for (int row = array.GetLowerBound(0); row <= array.GetUpperBound(0); row++)
            {
                List<string> cells = new List<string>();
                for (int column = array.GetLowerBound(1); column <= array.GetUpperBound(1); column++)
                {
                    string text = SimpleLiteral(array.GetValue(row, column));
                    if (text == null)
                    {
                        m_Reporter.Warn(member, "default array holds complex items, an empty collection is used instead");
                        return Factory(emptyFactory);
                    }

                    cells.Add(text);
                }

                rows.Add("[" + string.Join(", ", cells) + "]");
            }

            if (rows.Count == 0)
                return Factory(emptyFactory);

            return Factory("lambda: [" + string.Join(", ", rows) + "]");
        }

        private static string SimpleLiteral(object item)
        {
            switch (item)
            {
                case null: return "None";
                case bool b: return PyLiteral.Bool(b);
                case string s: return PyLiteral.Str(s);
                case double d: return PyLiteral.Float(d);
                case float f: return PyLiteral.Float(f);
            }
            if (item.GetType().IsPrimitive)
                return Convert.ToString(item, CultureInfo.InvariantCulture);
            return null;
        }
    }
}
