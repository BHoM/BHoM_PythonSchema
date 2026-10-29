using System.ComponentModel;
using System.Reflection;
using System.Text.RegularExpressions;

namespace PythonSchemaGeneration.Loading
{
    public static class AssemblyLoader
    {
        /***************************************************/

        [Description("Loads every oM assembly of the requested organisations from the BHoM folder, in file name order, and reports each one loaded, skipped or failed. The " +
            "generator's first stage: only these assemblies are searched for types to convert.")]
        public static List<Assembly> LoadOmAssemblies(string folder, IEnumerable<string> organisations, Reporting.Reporter reporter)
        {
            List<Assembly> result = new List<Assembly>();
            Regex regex = new Regex(@"oM$");

            foreach (string file in Directory.GetFiles(folder, "*.dll", SearchOption.TopDirectoryOnly).OrderBy(x => x, StringComparer.OrdinalIgnoreCase))
            {
                string name = Path.GetFileNameWithoutExtension(file);
                if (!regex.IsMatch(name) && name != "BHoM")
                    continue;

                try
                {
                    Assembly loaded = Assembly.LoadFrom(file);
                    if (loaded != null && BHoMAdapter.IsOmAssembly(loaded) && BHoMAdapter.IsInOrg(loaded, organisations))
                    {
                        result.Add(loaded);
                        reporter?.Info($"Loaded assembly {name}");
                    }
                    else
                        reporter?.Info($"Skipped assembly {name} (not an oM assembly of the requested organisations)");
                }
                catch (Exception e)
                {
                    reporter?.Warn($"Could not load assembly {name}: {e.Message}");
                }
            }

            return result;
        }

        /***************************************************/

        [Description("Returns the types of an assembly, or only the types that loaded when some of them fail to load. The TypeSelector uses it so one broken dependency does not stop the run.")]
        public static Type[] SafeGetTypes(Assembly assembly)
        {
            try
            {
                return assembly.GetTypes();
            }
            catch (ReflectionTypeLoadException e)
            {
                return e.Types.Where(x => x != null).ToArray();
            }
        }

        /***************************************************/
    }
}
