using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Reporting;

namespace PythonSchemaGeneration
{
    public class GenerationResult
    {
        public int CyclicTypes;
        public int FilesWritten;
        public int AvailableTypes;
        public Reporter Reporter = new Reporter();
        public List<RenderedType> Types = new List<RenderedType>();
    }
}
