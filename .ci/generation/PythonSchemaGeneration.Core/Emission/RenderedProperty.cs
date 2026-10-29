using PythonSchemaGeneration.Model;

namespace PythonSchemaGeneration.Emission
{
    public class RenderedProperty
    {
        public string Name;
        public string PyName;
        public string ClrType;
        public string PyType;
        public bool HasDefault;
        public string Default;
        public string Description;
        public QuantityModel Quantity;
        public string DisplayText;
        public bool IsDynamic;
    }
}
