namespace PythonSchemaGeneration
{
    //The command line of the generator. Options that are not known are an error, so a misspelt one is not silently ignored.
    public class CommandLine
    {
        /***************************************************/

        private static readonly string[] m_Known = { "output", "assemblies", "org", "repos", "types", "manifest", "report", "baseline-warnings", "write-baseline" };

        public const string Usage = "Usage: PythonSchemaGeneration --output <bhom_schema folder> [--assemblies <folder>] [--org BHoM,Other] [--repos BHoM/BHoM,BHoM/Other_Toolkit] "
            + "[--types A,B] [--manifest <file>] [--report <file>] [--baseline-warnings <file>] [--write-baseline <file>]";

        public GenerationOptions Options { get; private set; }

        //Known warning kinds; a run with a kind that is not in this file fails
        public string BaselinePath { get; private set; }

        //Writes the kinds of this run's warnings to this file
        public string WriteBaselinePath { get; private set; }

        public string Error { get; private set; }

        /***************************************************/

        public static CommandLine Parse(string[] args)
        {
            CommandLine result = new CommandLine();
            Dictionary<string, string> arguments = new Dictionary<string, string>();
            for (int i = 0; i < args.Length; i++)
            {
                if (!args[i].StartsWith("--"))
                    return result.Fail($"Unexpected argument '{args[i]}'.");

                string name = args[i].Substring(2);
                if (!m_Known.Contains(name))
                    return result.Fail($"Unknown option --{name}.");

                if (i + 1 >= args.Length || args[i + 1].StartsWith("--"))
                    return result.Fail($"Option --{name} needs a value.");

                arguments[name] = args[++i];
            }

            if (!arguments.ContainsKey("output"))
                return result.Fail("Missing --output <path to the bhom_schema package folder>.");

            result.Options = new GenerationOptions
            {
                OutputFolder = arguments["output"],
                ReportPath = arguments.GetValueOrDefault("report"),
                ManifestPath = arguments.GetValueOrDefault("manifest"),
                AssemblyFolder = arguments.GetValueOrDefault("assemblies"),
            };

            if (arguments.TryGetValue("org", out string orgs))
                result.Options.Organisations = Split(orgs);

            if (arguments.TryGetValue("repos", out string repos))
                result.Options.Repos = Split(repos);

            if (arguments.TryGetValue("types", out string types))
                result.Options.TypeFilter = Split(types);

            result.BaselinePath = arguments.GetValueOrDefault("baseline-warnings");
            result.WriteBaselinePath = arguments.GetValueOrDefault("write-baseline");
            return result;
        }

        /***************************************************/

        private CommandLine Fail(string message)
        {
            Error = message;
            return this;
        }

        /***************************************************/

        private static List<string> Split(string text)
        {
            return text.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim()).ToList();
        }

        /***************************************************/
    }
}
