using System.Reflection;
using System.Text.RegularExpressions;

namespace PythonSchemaGeneration.Loading
{
    public static class AssemblyLoader
    {
        /***************************************************/

        //Loads every oM assembly of the given organisations from the BHoM folder
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
