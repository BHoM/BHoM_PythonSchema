namespace PythonSchemaGeneration.Mapping
{
    public class ImportEntry
    {
        public string Module;
        public string Name;
        public string Local;
        public bool IsSafeForEarlyImport;        //must be imported before the class is defined
        public bool IsOm;       //a generated oM module (imported after the class when not Top)
        public Type OmType;
    }
}
