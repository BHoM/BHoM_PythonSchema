using System.ComponentModel;
using System.Reflection;

namespace PythonSchemaGeneration.Loading
{
    //The only place that touches logic referenced from other BHoM repos, so a reference can be swapped in one file
    public static class BHoMAdapter
    {
        /***************************************************/

        [Description("Tells whether a namespace is an oM namespace, by asking the BHoM Engine. Used by the TypeSelector.")]
        public static bool IsOmNamespace(string ns)
        {
            return BH.Engine.Base.Query.IsOmNamespace(ns);
        }

        /***************************************************/

        [Description("Tells whether an assembly is an oM assembly, by asking the BHoM Engine. Used by the AssemblyLoader.")]
        public static bool IsOmAssembly(Assembly assembly)
        {
            return BH.Engine.Base.Query.IsOmAssembly(assembly);
        }

        /***************************************************/

        [Description("Tells whether an assembly belongs to one of the given GitHub organisations, by asking the JSON schema engine. The AssemblyLoader uses it to filter " +
            "assemblies by organisation.")]
        public static bool IsInOrg(Assembly assembly, IEnumerable<string> organisations)
        {
            BH.oM.JsonSchema.ConvertConfig config = new BH.oM.JsonSchema.ConvertConfig { OrganisationsToInclude = organisations.ToList() };
            return BH.Engine.JsonSchema.Query.IsInOrg(assembly, config);
        }

        /***************************************************/

        [Description("Returns the path of a type relative to the output package, in the form Assembly/Namespace folders/Name without extension, using the JSON schema " +
            "engine's layout rule and falling back to the local rule for types the engine does not know. The TypeRegistry uses it to place each generated file.")]
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

        [Description("Builds the relative type path locally from the assembly name and the type's namespace, mirroring the JSON schema engine rule. RelativeTypePath uses it " +
            "for recompiled copies of the oM that the engine does not recognise.")]
        private static string LocalRelativeTypePath(Type type)
        {
            //Same rule as BH.Engine.JsonSchema.Query.RelativeSchemaId: Assembly/Namespace folders (without the first segment)/Name
            string fullName = type.FullName.Replace("BH.oM.Adapters.", "").Replace("BH.oM.", "");
            return type.Assembly.GetName().Name + "/" + string.Join("/", fullName.Split('.').Skip(1));
        }

        /***************************************************/

        [Description("Returns the folder with the BHoM assemblies: the BHoM folder reported by the engine when it exists, otherwise ProgramData BHoM Assemblies. The " +
            "generator uses it when no assembly folder is given, and the tests use it to find the oM dlls.")]
        public static string DefaultAssemblyFolder()
        {
            string folder = null;
            try { folder = BH.Engine.Base.Query.BHoMFolder(); } catch { }

            if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder))
                folder = Path.Combine(Environment.GetEnvironmentVariable("ProgramData") ?? "", "BHoM", "Assemblies");

            return folder;
        }

        /***************************************************/

        [Description("Reads the GitHub repository (Owner/Name) from the github.com address in an assembly's description attribute, or returns null when there is none. The " +
            "TypeExtractor stores it as the provenance repository of each type, and it drives the --repos filter.")]
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
