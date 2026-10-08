using PythonSchemaGeneration.Loading;

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

        public static Type Definition(Type type)
        {
            return type.IsGenericType ? type.GetGenericTypeDefinition() : type;
        }

        /***************************************************/

        public void Add(Type type) { m_Types.Add(Definition(type)); }

        /***************************************************/

        public bool Contains(Type type) { return m_Types.Contains(Definition(type)); }

        /***************************************************/

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
