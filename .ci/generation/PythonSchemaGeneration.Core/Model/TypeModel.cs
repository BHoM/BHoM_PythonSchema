namespace PythonSchemaGeneration.Model
{
    public class TypeModel
    {
        public Type Type;   //generic type definition for generic types
        public string ClrName;  //Type.FullName, with the backtick arity for generics
        public string CanonicalName;    //Readable name, for example BH.oM.Base.BHoMGroup<T>
        public string Namespace;
        public string Assembly;
        public string Repo;
        public string Description;
        public TypeKind Kind;
        public bool IsFlags;
        public List<GenericParamModel> GenericParams = new List<GenericParamModel>();
        public List<Type> Bases = new List<Type>();    //class base first, then interfaces
        public List<PropertyModel> Properties = new List<PropertyModel>();
        public List<EnumMemberModel> EnumMembers = new List<EnumMemberModel>();
    }
}
