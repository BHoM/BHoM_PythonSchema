using PythonSchemaGeneration.Loading;
using System.ComponentModel;

namespace PythonSchemaGeneration.Mapping
{
    //The set of C# types that get a Python class, and where each one lives
    public class TypeRegistry
    {
        /***************************************************/

        public const string RootPackage = "bhom_schema";
        private readonly HashSet<Type> m_Types = new HashSet<Type>();
        private readonly Dictionary<Type, PyRef> m_Refs = new Dictionary<Type, PyRef>();

        /***************************************************/

        public IEnumerable<Type> Types { get { return m_Types; } }

        /***************************************************/

        [Description("Returns the generic type definition of a constructed generic type, or the type itself. Used wherever a generic type must be treated as one generated class.")]
        public static Type Definition(Type type)
        {
            return type.IsGenericType ? type.GetGenericTypeDefinition() : type;
        }

        /***************************************************/

        [Description("Adds the definition of a type to the set of types that get a Python class. The Generator fills the registry with the selected types before extraction starts.")]
        public void Add(Type type) { m_Types.Add(Definition(type)); }

        /***************************************************/

        [Description("Tells whether the type, or its generic definition, gets a Python class. The extractor and type mapper use it to decide whether a type is a generated oM type.")]
        public bool Contains(Type type) { return m_Types.Contains(Definition(type)); }

        /***************************************************/

        [Description("Returns the Python name, relative path and module of the class generated for a type, built from the same path layout as the JSON schema and cached per " +
            "type. Used by the mapper to write imports and by the output writer to place files.")]
        public PyRef Ref(Type type)
        {
            Type def = Definition(type);
            if (m_Refs.TryGetValue(def, out PyRef pyRef))
                return pyRef;

            string path = BHoMAdapter.RelativeTypePath(def);
            string[] segments = path.Split('/').Select(Naming.Identifier).ToArray();
            segments[segments.Length - 1] = Naming.TypeName(def);

            pyRef = new PyRef
            {
                Name = segments[segments.Length - 1],
                RelativePath = string.Join("/", segments),
                Module = RootPackage + "." + string.Join(".", segments),
            };

            m_Refs[def] = pyRef;
            return pyRef;
        }

        /***************************************************/
    }
}
