using BH.oM.Base;
using PythonSchemaGeneration.Loading;
using System.Reflection;
using System.Runtime.CompilerServices;

namespace PythonSchemaGeneration.Extraction
{
    public static class TypeSelector
    {
        /***************************************************/

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

        //Same rules as the JSON schema generator: oM namespace, enums and IObject implementers, no static classes
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

        //By name as well as by type, so a recompiled copy of the oM (as in the round trip tests) is recognised too
        public static bool IsIObject(Type type)
        {
            if (typeof(IObject).IsAssignableFrom(type))
                return true;

            return type.FullName == typeof(IObject).FullName || type.GetInterfaces().Any(i => i.FullName == typeof(IObject).FullName);
        }

        /***************************************************/
    }
}
