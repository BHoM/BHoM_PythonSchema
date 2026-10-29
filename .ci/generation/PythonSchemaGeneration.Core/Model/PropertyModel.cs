namespace PythonSchemaGeneration.Model
{
    public class PropertyModel
    {
        public string Name;
        public Type Type;
        public string Description;
        public QuantityModel Quantity;
        public string DisplayText;
        public bool IsDynamic;
        public DefaultValue Default;    //null when no default could be discovered, in which case the field is required
    }
}
