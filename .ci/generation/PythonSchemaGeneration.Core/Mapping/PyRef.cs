namespace PythonSchemaGeneration.Mapping
{
    public class PyRef
    {
        public string RelativePath;   //Assembly/Folders/Name, valid Python names, forward slashes
        public string Module;         //bhom_schema.Assembly.Folders.Name
        public string Name;           //Class name, identical to the last module segment
    }
}
