using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;

namespace PythonSchemaGeneration.Emission
{
    public class RenderedType
    {
        public TypeModel Model;
        public PyRef Ref;
        public string Text;
        public HashSet<Type> References;          //imported by the module, used to find import cycles
        public HashSet<Type> ClosureReferences;   //everything that has to be generated too
        public List<RenderedProperty> Properties = new List<RenderedProperty>();
        public Dictionary<string, string> RenamedMembers = new Dictionary<string, string>();
    }
}
