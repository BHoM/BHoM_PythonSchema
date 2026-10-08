using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;
using PythonSchemaGeneration.Reporting;
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

        public DefaultInstanceReader(TypeRegistry registry, Reporter reporter)
        {
            m_Registry = registry;
            m_Reporter = reporter;
        }

        /***************************************************/

        //Returns a default per property name, or an empty dictionary when no instance can be created (all fields are then required)
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

        //Properties of generic type definitions cannot be read; use the same property on the constructed instance type
        private static PropertyInfo Live(PropertyInfo property, object instance)
        {
            if (!property.DeclaringType.ContainsGenericParameters)
                return property;
            Type constructed = instance.GetType();
            while (constructed != null && !(constructed.IsGenericType && constructed.GetGenericTypeDefinition() == property.DeclaringType))
                constructed = constructed.BaseType;
            return constructed?.GetProperty(property.Name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly) ?? property;
        }

        private static bool IsVolatileType(Type type)
        {
            return type == typeof(Guid) || type == typeof(DateTime) || type == typeof(DateTimeOffset);
        }

        /***************************************************/

        //The type to instantiate to read the defaults: the type itself, or for abstract types the first concrete subtype
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

        private static Type Closed(Type type)
        {
            return type.IsGenericTypeDefinition ? null : type;
        }

        /***************************************************/

        private static bool CanInstantiate(Type type)
        {
            if (type.IsAbstract || type.IsInterface)
                return false;

            if (type.IsValueType)
                return true;

            return type.GetConstructor(Type.EmptyTypes) != null;
        }

        /***************************************************/

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
