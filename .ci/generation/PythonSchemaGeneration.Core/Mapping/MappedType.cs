namespace PythonSchemaGeneration.Mapping
{
    public class MappedType
    {
        public string Expression;   //Python annotation text
        public string DefaultClr;   //The C# type the Python to C# converter would give back when given Expression
        public bool IsValueType;    //Python side value type: gets "?" when nullable
    }
}
