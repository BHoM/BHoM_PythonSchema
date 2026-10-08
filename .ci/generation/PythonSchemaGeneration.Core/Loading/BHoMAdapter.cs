using System.Reflection;

namespace PythonSchemaGeneration.Loading
{
    //The only place that touches logic referenced from other BHoM repos, so a reference can be swapped in one file
    public static class BHoMAdapter
    {
        /***************************************************/

        public static bool IsOmNamespace(string ns)
        {
            return BH.Engine.Base.Query.IsOmNamespace(ns);
        }

        /***************************************************/

        public static bool IsOmAssembly(Assembly assembly)
        {
            return BH.Engine.Base.Query.IsOmAssembly(assembly);
        }

        /***************************************************/

        public static bool IsInOrg(Assembly assembly, IEnumerable<string> organisations)
        {
            BH.oM.JsonSchema.ConvertConfig config = new BH.oM.JsonSchema.ConvertConfig { OrganisationsToInclude = organisations.ToList() };
            return BH.Engine.JsonSchema.Query.IsInOrg(assembly, config);
        }

        /***************************************************/

        //Same layout rule as the JSON schema repo: Assembly/Namespace/Folders/Name.json. Returned without the extension.
        public static string RelativeTypePath(Type type)
        {
            string path = BH.Engine.JsonSchema.Query.RelativeSchemaId(type);
            if (path == null)
            {
                //the engine only knows types implementing its own copy of IObject
                return LocalRelativeTypePath(type);
            }

            return path.EndsWith(".json") ? path.Substring(0, path.Length - 5) : path;
        }

        /***************************************************/

        private static string LocalRelativeTypePath(Type type)
        {
            //Same rule as BH.Engine.JsonSchema.Query.RelativeSchemaId: Assembly/Namespace folders (without the first segment)/Name
            string fullName = type.FullName.Replace("BH.oM.Adapters.", "").Replace("BH.oM.", "");
            return type.Assembly.GetName().Name + "/" + string.Join("/", fullName.Split('.').Skip(1));
        }

        /***************************************************/

        public static string DefaultAssemblyFolder()
        {
            string folder = null;
            try { folder = BH.Engine.Base.Query.BHoMFolder(); } catch { }

            if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder))
                folder = Path.Combine(Environment.GetEnvironmentVariable("ProgramData") ?? "", "BHoM", "Assemblies");

            return folder;
        }

        /***************************************************/

        public static string AssemblyRepo(Assembly assembly)
        {
            string description = assembly.GetCustomAttribute<AssemblyDescriptionAttribute>()?.Description;
            if (string.IsNullOrWhiteSpace(description))
                return null;

            int idx = description.IndexOf("github.com/", StringComparison.OrdinalIgnoreCase);
            if (idx < 0)
                return null;

            string rest = description.Substring(idx + "github.com/".Length).Trim().TrimEnd('/');
            string[] parts = rest.Split('/');
            if (parts.Length < 2)
                return null;

            string repo = parts[1];
            if (repo.EndsWith(".git", StringComparison.OrdinalIgnoreCase))
                repo = repo.Substring(0, repo.Length - 4);

            return parts[0] + "/" + repo;
        }

        /***************************************************/
    }
}
