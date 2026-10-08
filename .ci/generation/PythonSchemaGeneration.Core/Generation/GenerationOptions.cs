using System.Reflection;

namespace PythonSchemaGeneration
{
    public class GenerationOptions
    {
        public string AssemblyFolder;                       //folder with the oM dlls (used when Assemblies is null)

        public List<Assembly> Assemblies;                   //already loaded assemblies, for tests

        public List<string> Organisations = new List<string> { "BHoM" };

        public string OutputFolder;                         //the bhom_schema package folder; null to render only

        public List<string> TypeFilter;                     //full names of root types; their dependencies are generated too. Null generates everything.

        public string ManifestPath;

        public string ReportPath;
    }
}
