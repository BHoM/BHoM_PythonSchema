namespace PythonSchemaGeneration.Patcher
{
    //The job file written by py2cs: one entry per existing C# file to change
    public class PatchJob
    {
        public List<FileJob> Files { get; set; } = new List<FileJob>();
    }

    /***************************************************/

    public class FileJob
    {
        public string Path { get; set; }

        public string Output { get; set; }

        //Simple name of the type to change, without namespace or generic arity
        public string Type { get; set; }

        public string Namespace { get; set; }

        public List<string> Usings { get; set; } = new List<string>();

        public List<Change> Changes { get; set; } = new List<Change>();
    }

    /***************************************************/

    //One member-level change. Kind is one of addProperty, removeProperty, setPropertyType, setPropertyInitialiser, setDescription,
    //setAttributes, setBases, addEnumMember, removeEnumMember, setEnumValue. Texts are C# source, ready to be written.
    public class Change
    {
        public string Kind { get; set; }

        //Member name; empty for changes to the type itself
        public string Name { get; set; }

        public string Type { get; set; }

        public string Initialiser { get; set; }

        //C# string literal, quotes included; empty to remove the description
        public string Description { get; set; }

        public string Value { get; set; }

        //The existing member after which a new one goes; empty to put it first
        public string After { get; set; }

        //Attributes (without brackets) or base types to add
        public List<string> Add { get; set; } = new List<string>();

        //Attribute names or base types to remove
        public List<string> Remove { get; set; } = new List<string>();
    }

    /***************************************************/

    public class FileResult
    {
        public string Output { get; set; }

        public List<string> Notes { get; set; } = new List<string>();

        public string Error { get; set; }
    }

    /***************************************************/

    public class PatchResult
    {
        public string Text { get; set; }

        public List<string> Notes { get; set; } = new List<string>();
    }
}
