using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;
using PythonSchemaGeneration.Reporting;
using System.ComponentModel;
using System.Reflection;

namespace PythonSchemaGeneration.Extraction
{
    //Reflection cannot see property initialisers, so defaults are read from freshly created instances
    public class DefaultInstanceReader
    {
        /***************************************************/

        private readonly Reporter m_Reporter;
        private readonly TypeRegistry m_Registry;
        private readonly Dictionary<Type, Type> m_InstantiableSource = new Dictionary<Type, Type>();

        /***************************************************/

        [Description("Creates the reader that finds the default value of each property of a type, using the registry to pick a concrete subtype for abstract types and the " +
            "reporter for warnings. Created once by the TypeExtractor in the generator's extraction stage.")]
        public DefaultInstanceReader(TypeRegistry registry, Reporter reporter)
        {
            m_Registry = registry;
            m_Reporter = reporter;
        }

        /***************************************************/

        [Description("Reads the default value of every readable property by creating two instances of the type (or of its first concrete subtype) and reading each property " +
            "from both, flagging values such as Guid and DateTime that differ between the two as non-deterministic. Returns an empty dictionary when no instance " +
            "can be created, so every field is then required; the TypeExtractor calls it for each class and struct to fill the defaults of the type model.")]
        public Dictionary<string, DefaultValue> Read(Type definition, IEnumerable<PropertyInfo> properties)
        {
            Dictionary<string, DefaultValue> result = new Dictionary<string, DefaultValue>();
            Type source = InstantiableSource(definition);

            if (source == null)
                return result;

            object first = Instance(source);
            object second = Instance(source);
            if (first == null || second == null)
                return result;

            foreach (PropertyInfo property in properties)
            {
                if (property.GetMethod == null || !property.GetMethod.IsPublic)
                    continue;
                try
                {
                    PropertyInfo live = Live(property, first);
                    object v1 = live.GetValue(first);
                    object v2 = live.GetValue(second);
                    bool volatileValue = v1 != null && v2 != null && IsVolatileType(v1.GetType()) && !v1.Equals(v2);
                    result[property.Name] = new DefaultValue { Value = v1, NonDeterministic = volatileValue };
                }
                catch (Exception e)
                {
                    m_Reporter.Warn(definition.FullName + "." + property.Name, "default value could not be read (" + (e.InnerException ?? e).Message + "), field is required");
                }
            }
            return result;
        }

        /***************************************************/

        [Description("Returns the property to read on a live instance: for a property declared on a generic type definition, the same property on the constructed type in " +
            "the instance's base chain. Used by Read because properties of open generic types cannot be read.")]
        private static PropertyInfo Live(PropertyInfo property, object instance)
        {
            if (!property.DeclaringType.ContainsGenericParameters)
                return property;
            Type constructed = instance.GetType();
            while (constructed != null && !(constructed.IsGenericType && constructed.GetGenericTypeDefinition() == property.DeclaringType))
                constructed = constructed.BaseType;
            return constructed?.GetProperty(property.Name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly) ?? property;
        }

        [Description("Tells whether a type (Guid, DateTime, DateTimeOffset) gets a new value on every instantiation. Read uses it to mark such defaults as non-deterministic " +
            "so they are not written into the generated Python.")]
        private static bool IsVolatileType(Type type)
        {
            return type == typeof(Guid) || type == typeof(DateTime) || type == typeof(DateTimeOffset);
        }

        /***************************************************/

        [Description("Finds the type to instantiate to read the defaults of a definition: the type itself when it has a usable constructor, otherwise the first concrete " +
            "subtype in the registry by full name for an abstract class. Returns null for interfaces, enums and types with no instantiable subtype, and caches the " +
            "answer; used by Read.")]
        private Type InstantiableSource(Type definition)
        {
            if (definition.IsInterface || definition.IsEnum)
                return null;

            if (m_InstantiableSource.TryGetValue(definition, out Type cached))
                return cached;

            Type source = null;
            if (CanInstantiate(definition))
                source = definition;
            else if (definition.IsAbstract)
            {
                source = m_Registry.Types
                    .Where(t => !t.IsAbstract && !t.IsInterface && !t.IsEnum && t != definition && definition.IsAssignableFrom(Closed(t) ?? t) && CanInstantiate(t))
                    .OrderBy(t => t.FullName, StringComparer.Ordinal)
                    .FirstOrDefault();
            }

            m_InstantiableSource[definition] = source;
            return source;
        }

        /***************************************************/

        [Description("Returns the type itself, or null when it is an open generic type definition that cannot be assigned to another type. InstantiableSource uses it when " +
            "it searches the registry for a concrete subtype.")]
        private static Type Closed(Type type)
        {
            return type.IsGenericTypeDefinition ? null : type;
        }

        /***************************************************/

        [Description("Tells whether an instance can be created without arguments: any value type, or a non-abstract class with a public parameterless constructor. Used by " +
            "InstantiableSource to choose the type to instantiate.")]
        private static bool CanInstantiate(Type type)
        {
            if (type.IsAbstract || type.IsInterface)
                return false;

            if (type.IsValueType)
                return true;

            return type.GetConstructor(Type.EmptyTypes) != null;
        }

        /***************************************************/

        [Description("Creates one instance of a type with Activator, closing a generic type definition over its constraint types (or object) first. Returns null and reports " +
            "a warning when creation fails; Read calls it twice to compare the values.")]
        private object Instance(Type type)
        {
            try
            {
                if (type.IsGenericTypeDefinition)
                {
                    Type[] args = type.GetGenericArguments().Select(a =>
                    {
                        Type constraint = a.GetGenericParameterConstraints().FirstOrDefault(c => !c.IsGenericType && !c.IsValueType);
                        return constraint ?? typeof(object);
                    }).ToArray();

                    type = type.MakeGenericType(args);
                }

                return Activator.CreateInstance(type);
            }
            catch (Exception e)
            {
                m_Reporter.Warn(type.FullName, "could not be instantiated to read defaults (" + (e.InnerException ?? e).Message + ")");
                return null;
            }
        }

        /***************************************************/
    }
}
