using BH.oM.Base;
using PythonSchemaGeneration.Loading;
using System.ComponentModel;
using System.Reflection;
using System.Runtime.CompilerServices;

namespace PythonSchemaGeneration.Extraction
{
    public static class TypeSelector
    {
        /***************************************************/

        [Description("Returns the oM types to convert from the loaded assemblies, ordered by full name. The generator's type selection stage, run right after the assemblies " +
            "are loaded; it feeds the type registry.")]
        public static List<Type> Select(IEnumerable<Assembly> assemblies)
        {
            List<Type> result = new List<Type>();
            foreach (Assembly assembly in assemblies)
            {
                foreach (Type type in AssemblyLoader.SafeGetTypes(assembly))
                {
                    if (IsSelected(type))
                        result.Add(type);
                }
            }
            return result.OrderBy(x => x.FullName, StringComparer.Ordinal).ToList();
        }

        /***************************************************/

        [Description("Tells whether a type is converted: it is in an oM namespace and is an enum or an IObject implementer, but it is not a static class, compiler " +
            "generated, or a constructed generic type. Applies the same rules as the JSON schema generator, and Select uses it.")]
        public static bool IsSelected(Type type)
        {
            if (type.Namespace == null || !BHoMAdapter.IsOmNamespace(type.Namespace))
                return false;

            if (type.IsAbstract && type.IsSealed)
                return false;

            if (type.IsDefined(typeof(CompilerGeneratedAttribute), false))
                return false;

            if (type.IsGenericType && !type.IsGenericTypeDefinition)
                return false;

            return type.IsEnum || IsIObject(type);
        }

        /***************************************************/

        [Description("Tells whether a type implements IObject, checked by assignability and by interface full name. The name check also recognises a recompiled copy of the " +
            "oM, as the round trip tests use; IsSelected uses it.")]
        public static bool IsIObject(Type type)
        {
            if (typeof(IObject).IsAssignableFrom(type))
                return true;

            return type.FullName == typeof(IObject).FullName || type.GetInterfaces().Any(i => i.FullName == typeof(IObject).FullName);
        }

        /***************************************************/
    }
}
