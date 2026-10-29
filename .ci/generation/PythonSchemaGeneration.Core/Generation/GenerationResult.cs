using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Reporting;

namespace PythonSchemaGeneration
{
    public class GenerationResult
    {
        public int CyclicTypes;
        public int FilesWritten;
        public int AvailableTypes;
        public string BHoMVersion;                          //Major.Minor of the assembly version of BHoM.dll (or of another loaded assembly when it is missing), null when no assembly was loaded
        public List<string> FailedTypes = new List<string>();
        public Reporter Reporter = new Reporter();
        public List<RenderedType> Types = new List<RenderedType>();
    }
}
