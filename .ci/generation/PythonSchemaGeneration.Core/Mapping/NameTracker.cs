namespace PythonSchemaGeneration.Mapping
{

    //Tracks the names used inside one generated module so imports never collide with fields or each other
    public class NameTracker
    {
        /***************************************************/

        private readonly Type m_Self;
        private readonly string m_SelfName;
        private readonly HashSet<string> m_ReservedNames;
        private readonly Dictionary<string, ImportEntry> m_ImportByLocal = new Dictionary<string, ImportEntry>();
        private readonly Dictionary<string, ImportEntry> m_ImportBySource = new Dictionary<string, ImportEntry>();

        /***************************************************/

        public HashSet<Type> References { get; } = new HashSet<Type>();

        //Types that must be generated because a marker mentions them, but that are not imported by this module
        public HashSet<Type> MentionedOnly { get; } = new HashSet<Type>();

        //Types that can be imported before the class is defined without risking a circular import
        public Func<Type, bool> IsSafeForEarlyImport { get; set; }

        /***************************************************/

        public NameTracker(Type self, string selfName, IEnumerable<string> reserved)
        {
            m_Self = self;
            m_SelfName = selfName;
            m_ReservedNames = new HashSet<string>(reserved) { selfName };
        }

        /***************************************************/

        public IEnumerable<ImportEntry> Imports { get { return m_ImportByLocal.Values; } }

        /***************************************************/

        public void Reserve(string name) { m_ReservedNames.Add(name); }

        /***************************************************/

        //Import of a standard or support name, for example AddStandardName("typing", "Any")
        public string AddStandardName(string module, string name)
        {
            return Add(module, name, name, false, false, null);
        }

        /***************************************************/

        //Reference to a generated oM type. top: the name is needed while the class is being defined (bases, enum defaults).
        public string Reference(Type type, PyRef pyRef, bool isSafeForEarlyImport)
        {
            Type def = TypeRegistry.Definition(type);
            References.Add(def);

            if (def == m_Self)
                return m_SelfName;

            string assembly = pyRef.RelativePath.Split('/')[0];
            isSafeForEarlyImport |= IsSafeForEarlyImport != null && IsSafeForEarlyImport(def);
            return Add(pyRef.Module, pyRef.Name, pyRef.Name, isSafeForEarlyImport, true, def, assembly);
        }

        /***************************************************/

        private string Add(string module, string name, string preferredName, bool isSafeForEarlyImport, bool isOm, Type omType, string assembly = null)
        {
            string key = module + ":" + name;
            if (m_ImportBySource.TryGetValue(key, out ImportEntry existing))
            {
                existing.IsSafeForEarlyImport |= isSafeForEarlyImport;
                return existing.Local;
            }

            string localName = preferredName;
            if (IsTaken(localName) && assembly != null)
                localName = assembly + "_" + preferredName;

            while (IsTaken(localName))
                localName += "_";

            ImportEntry entry = new ImportEntry { Module = module, Name = name, Local = localName, IsSafeForEarlyImport = isSafeForEarlyImport, IsOm = isOm, OmType = omType };
            m_ImportByLocal[localName] = entry;
            m_ImportBySource[key] = entry;
            return localName;
        }

        /***************************************************/

        private bool IsTaken(string local)
        {
            return m_ReservedNames.Contains(local) || m_ImportByLocal.ContainsKey(local);
        }

        /***************************************************/
    }
}
