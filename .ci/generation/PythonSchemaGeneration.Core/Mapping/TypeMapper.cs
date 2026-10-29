using PythonSchemaGeneration.Model;
using PythonSchemaGeneration.Reporting;
using System.ComponentModel;

namespace PythonSchemaGeneration.Mapping
{
    //One table: C# type to Python type. Everything that is not the default C# type for the Python type is kept as a ClrType marker.
    public class TypeMapper
    {
        /***************************************************/

        private readonly string m_Context;
        private readonly Reporter m_Reporter;
        private readonly TypeRegistry m_Registry;
        private readonly NameTracker m_NameTracker;

        private static readonly HashSet<string> m_ListTypes = new HashSet<string>
        {
            "System.Collections.Generic.List`1", "System.Collections.Generic.IList`1", "System.Collections.Generic.ICollection`1",
            "System.Collections.Generic.IEnumerable`1", "System.Collections.Generic.IReadOnlyList`1", "System.Collections.Generic.IReadOnlyCollection`1",
            "System.Collections.ObjectModel.ReadOnlyCollection`1", "System.Collections.ObjectModel.ObservableCollection`1",
            "System.Collections.ObjectModel.Collection`1", "System.Collections.Generic.Queue`1", "System.Collections.Generic.Stack`1",
            "System.Collections.Generic.LinkedList`1"
        };

        private static readonly HashSet<string> m_SetTypes = new HashSet<string>
        {
            "System.Collections.Generic.HashSet`1", "System.Collections.Generic.ISet`1", "System.Collections.Generic.SortedSet`1",
            "System.Collections.Generic.IReadOnlySet`1"
        };

        private static readonly HashSet<string> m_DictionaryTypes = new HashSet<string>
        {
            "System.Collections.Generic.Dictionary`2", "System.Collections.Generic.IDictionary`2", "System.Collections.Generic.SortedDictionary`2",
            "System.Collections.Generic.SortedList`2", "System.Collections.Generic.IReadOnlyDictionary`2",
            "System.Collections.Concurrent.ConcurrentDictionary`2", "System.Collections.ObjectModel.ReadOnlyDictionary`2"
        };

        /***************************************************/

        //When true, referenced oM types are imported before the class is defined (needed for base classes)
        public bool IsSafeForEarlyImport { get; set; }

        /***************************************************/

        [Description("Creates the mapper for one generated module, given the registry, reporter, the module's name tracker and the context text used in warnings. The " +
            "PythonEmitter creates one per type.")]
        public TypeMapper(TypeRegistry registry, Reporter reporter, NameTracker tracker, string context)
        {
            m_Context = context;
            m_Registry = registry;
            m_Reporter = reporter;
            m_NameTracker = tracker;
        }

        /***************************************************/

        [Description("Maps a C# type to a Python type expression plus the C# type the Python to C# converter would give back for it, handling generic parameters, nullables, " +
            "primitives, arrays, oM types, delegates and collections, and mapping anything else to Any with a warning. The central step of the type mapping stage, " +
            "called by the emitter for every property and base.")]
        public MappedType Map(Type type)
        {
            if (type.IsGenericParameter)
                return new MappedType { Expression = type.Name, DefaultClr = type.Name };

            Type underlyingType = Nullable.GetUnderlyingType(type);
            if (underlyingType != null)
            {
                MappedType inner = Map(underlyingType);
                return new MappedType { Expression = inner.Expression + " | None", DefaultClr = inner.DefaultClr + "?" };
            }

            string fullName = type.FullName;
            if (fullName == "BH.oM.Base.FragmentSet")
            {
                Type fragment = type.Assembly.GetType("BH.oM.Base.IFragment");
                MappedType item = fragment != null && m_Registry.Contains(fragment) ? Map(fragment) : Any();
                return new MappedType { Expression = $"list[{item.Expression}]", DefaultClr = ListOf(item.DefaultClr) };
            }

            MappedType primitive = PrimitiveType(type);
            if (primitive != null)
                return primitive;

            if (type.IsArray)
                return ArrayType(type);

            if (m_Registry.Contains(type))
                return OmType(type);

            if (type.IsEnum)
                return UnsupportedType(type);

            if (typeof(Delegate).IsAssignableFrom(type))
            {
                return new MappedType
                {
                    DefaultClr = "System.Delegate",
                    Expression = $"{m_NameTracker.AddStandardName("collections.abc", "Callable")}[..., {m_NameTracker.AddStandardName("typing", "Any")}]",
                };
            }

            MappedType collection = CollectionType(type);
            if (collection != null)
                return collection;

            return UnsupportedType(type);
        }

        /***************************************************/

        [Description("Returns the mapping to Python's Any (importing it through the name tracker) with object as the C# type. The fallback of Map for types with no Python equivalent.")]
        private MappedType Any()
        {
            return new MappedType { Expression = m_NameTracker.AddStandardName("typing", "Any"), DefaultClr = "object" };
        }

        /***************************************************/

        [Description("Maps a type with no Python equivalent to Any and warns about it, except for object, System.Type and System.Enum, which are mapped silently. Used by Map.")]
        private MappedType UnsupportedType(Type type)
        {
            if (type != typeof(object) && type.FullName != "System.Type" && type.FullName != "System.Enum")
                m_Reporter.Warn(m_Context, $"type {ClrNames.Format(type)} has no Python equivalent and is mapped to Any");

            return Any();
        }

        /***************************************************/

        [Description("Returns the C# type text of a List of the given item type. Used to give the default C# type of Python lists.")]
        private static string ListOf(string item)
        {
            return $"System.Collections.Generic.List<{item}>";
        }

        /***************************************************/

        [Description("Maps the built-in C# types (bool, integers, floats, decimal, char, string, object, Guid, date and time types, Color, Type, Enum) to Python types and " +
            "their default C# types, or returns null when the type is not one of them. Used by Map.")]
        private MappedType PrimitiveType(Type type)
        {
            if (type == typeof(bool))
                return new MappedType { Expression = "bool", DefaultClr = "bool", IsValueType = true };

            if (type == typeof(byte) || type == typeof(sbyte) || type == typeof(short) || type == typeof(ushort) ||
                type == typeof(int) || type == typeof(uint) || type == typeof(long) || type == typeof(ulong))
                return new MappedType { Expression = "int", DefaultClr = "int", IsValueType = true };

            if (type == typeof(float) || type == typeof(double))
                return new MappedType { Expression = "float", DefaultClr = "double", IsValueType = true };

            if (type == typeof(decimal))
                return new MappedType { Expression = m_NameTracker.AddStandardName("decimal", "Decimal"), DefaultClr = "decimal", IsValueType = true };

            if (type == typeof(char) || type == typeof(string))
                return new MappedType { Expression = "str", DefaultClr = "string", IsValueType = type == typeof(char) };

            if (type == typeof(object))
                return Any();

            if (type == typeof(Guid))
                return new MappedType { Expression = m_NameTracker.AddStandardName("uuid", "UUID"), DefaultClr = "System.Guid", IsValueType = true };

            if (type == typeof(DateTime) || type == typeof(DateTimeOffset))
                return new MappedType { Expression = m_NameTracker.AddStandardName("datetime", "datetime"), DefaultClr = "System.DateTime", IsValueType = true };

            if (type == typeof(TimeSpan))
                return new MappedType { Expression = m_NameTracker.AddStandardName("datetime", "timedelta"), DefaultClr = "System.TimeSpan", IsValueType = true };

            if (type.FullName == "System.Drawing.Color")
                return new MappedType { Expression = m_NameTracker.AddStandardName("bhom_schema._support", "Color"), DefaultClr = "System.Drawing.Color", IsValueType = true };

            if (type.FullName == "System.Type" || type.FullName == "System.Enum")
                return Any();

            return null;
        }

        /***************************************************/

        [Description("Maps a C# array to nested Python lists, one level per dimension of the array rank. Used by Map.")]
        private MappedType ArrayType(Type type)
        {
            MappedType item = Map(type.GetElementType());
            string expr = item.Expression;
            string clr = item.DefaultClr;

            for (int i = 0; i < type.GetArrayRank(); i++)
            {
                expr = $"list[{expr}]";
                clr = ListOf(clr);
            }

            return new MappedType { Expression = expr, DefaultClr = clr };
        }

        /***************************************************/

        [Description("Maps a generated oM type to its imported Python class name, with its mapped type arguments in brackets when it is generic, and marks enums and structs " +
            "as value types. Registers the reference through the name tracker; used by Map.")]
        private MappedType OmType(Type type)
        {
            PyRef pyRef = m_Registry.Ref(type);
            string local = m_NameTracker.Reference(type, pyRef, IsSafeForEarlyImport);
            Type def = TypeRegistry.Definition(type);
            bool valueType = def.IsEnum || def.IsValueType;

            if (!type.IsGenericType)
                return new MappedType { Expression = local, DefaultClr = ClrNames.Format(type), IsValueType = valueType };

            List<MappedType> args = type.GetGenericArguments().Select(Map).ToList();
            return new MappedType
            {
                Expression = $"{local}[{string.Join(", ", args.Select(a => a.Expression))}]",
                DefaultClr = $"{ClrNames.BaseName(type)}<{string.Join(", ", args.Select(a => a.DefaultClr))}>",
                IsValueType = valueType
            };
        }

        /***************************************************/

        [Description("Maps generic and non-generic collection types to Python list, set, dict or tuple (a set or dictionary with unhashable keys becomes a list), including " +
            "any other IEnumerable of T as a list. Returns null for a type that is not a collection; used by Map.")]
        private MappedType CollectionType(Type type)
        {
            if (type.IsGenericType)
            {
                Type def = type.GetGenericTypeDefinition();
                string name = def.FullName;
                Type[] args = type.GetGenericArguments();

                if (m_ListTypes.Contains(name))
                {
                    MappedType itemType = Map(args[0]);
                    return new MappedType
                    {
                        Expression = $"list[{itemType.Expression}]",
                        DefaultClr = ListOf(itemType.DefaultClr)
                    };
                }

                if (m_SetTypes.Contains(name))
                {
                    MappedType itemType = Map(args[0]);
                    if (IsHashable(args[0]))
                        return new MappedType
                        {
                            Expression = $"set[{itemType.Expression}]",
                            DefaultClr = $"System.Collections.Generic.HashSet<{itemType.DefaultClr}>"
                        };

                    return new MappedType { Expression = $"list[{itemType.Expression}]", DefaultClr = ListOf(itemType.DefaultClr) };
                }

                if (m_DictionaryTypes.Contains(name))
                {
                    MappedType keyType = Map(args[0]);
                    MappedType valueType = Map(args[1]);

                    if (IsHashable(args[0]))
                        return new MappedType
                        {
                            Expression = $"dict[{keyType.Expression}, {valueType.Expression}]",
                            DefaultClr = $"System.Collections.Generic.Dictionary<{keyType.DefaultClr}, {valueType.DefaultClr}>"
                        };

                    return new MappedType
                    {
                        Expression = $"list[tuple[{keyType.Expression}, {valueType.Expression}]]",
                        DefaultClr = ListOf($"System.Tuple<{keyType.DefaultClr}, {valueType.DefaultClr}>")
                    };
                }

                if (name.StartsWith("System.Tuple`") || name.StartsWith("System.ValueTuple`") || name == "System.Collections.Generic.KeyValuePair`2")
                {
                    List<MappedType> itemTypes = args.Select(Map).ToList();
                    return new MappedType
                    {
                        Expression = $"tuple[{string.Join(", ", itemTypes.Select(i => i.Expression))}]",
                        DefaultClr = $"System.Tuple<{string.Join(", ", itemTypes.Select(i => i.DefaultClr))}>"
                    };
                }

                Type enumerable = type.GetInterfaces().FirstOrDefault(i => i.IsGenericType && i.GetGenericTypeDefinition() == typeof(IEnumerable<>));
                if (enumerable != null && type != typeof(string))
                {
                    MappedType itemType = Map(enumerable.GetGenericArguments()[0]);
                    return new MappedType
                    {
                        Expression = $"list[{itemType.Expression}]",
                        DefaultClr = ListOf(itemType.DefaultClr)
                    };
                }

                return null;
            }

            string fullName = type.FullName;
            if (fullName == "System.Collections.IDictionary" || fullName == "System.Collections.Hashtable")
            {
                string any = m_NameTracker.AddStandardName("typing", "Any");
                return new MappedType
                {
                    Expression = $"dict[{any}, {any}]",
                    DefaultClr = "System.Collections.Generic.Dictionary<object, object>"
                };
            }

            if (fullName == "System.Collections.IEnumerable" || fullName == "System.Collections.IList" || fullName == "System.Collections.ArrayList" || fullName == "System.Collections.ICollection")
                return new MappedType
                {
                    Expression = $"list[{m_NameTracker.AddStandardName("typing", "Any")}]",
                    DefaultClr = ListOf("object")
                };

            return null;
        }

        /***************************************************/

        [Description("Tells whether values of a type can be Python set members or dictionary keys: primitives, strings, decimals, enums, object, Guid, date and time types " +
            "and tuples of those. Pydantic models are not hashable, so CollectionType turns such sets and dictionaries into lists.")]
        public static bool IsHashable(Type type)
        {
            Type underlying = Nullable.GetUnderlyingType(type);
            if (underlying != null)
                type = underlying;

            if (type.IsPrimitive || type == typeof(string) || type == typeof(decimal) || type.IsEnum || type == typeof(object))
                return true;

            if (type == typeof(Guid) || type == typeof(DateTime) || type == typeof(DateTimeOffset) || type == typeof(TimeSpan))
                return true;

            if (type.IsGenericType && type.FullName != null && type.FullName.StartsWith("System.Tuple`"))
                return type.GetGenericArguments().All(IsHashable);

            return false;
        }

        /***************************************************/
    }
}
