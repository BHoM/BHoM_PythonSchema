using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Reporting;

namespace PythonSchemaGeneration
{
    public class GenerationResult
    {
        public int CyclicTypes;
        public int FilesWritten;
        public int AvailableTypes;
        public string BHoMVersion;                          //Major.Minor of the BHoM assemblies that were read, null when BHoM.dll was not among them
        public List<string> FailedTypes = new List<string>();
        public Reporter Reporter = new Reporter();
        public List<RenderedType> Types = new List<RenderedType>();
    }
}
