using PythonSchemaGeneration;

//Usage: PythonSchemaGeneration --output <bhom_schema folder> [--assemblies <folder>] [--org BHoM,Other] [--types A,B] [--manifest <file>] [--report <file>]
Dictionary<string, string> arguments = new Dictionary<string, string>();
for (int i = 0; i < args.Length; i++)
{
    if (args[i].StartsWith("--") && i + 1 < args.Length)
        arguments[args[i].Substring(2)] = args[++i];
}

if (!arguments.ContainsKey("output"))
{
    Console.Error.WriteLine("Missing --output <path to the bhom_schema package folder>");
    return 2;
}

GenerationOptions options = new GenerationOptions
{
    OutputFolder = arguments["output"],
    ReportPath = arguments.GetValueOrDefault("report"),
    ManifestPath = arguments.GetValueOrDefault("manifest"),
    AssemblyFolder = arguments.GetValueOrDefault("assemblies"),
};

if (arguments.TryGetValue("org", out string orgs))
    options.Organisations = orgs.Split(',', StringSplitOptions.RemoveEmptyEntries).ToList();

if (arguments.TryGetValue("types", out string types))
    options.TypeFilter = types.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim()).ToList();

GenerationResult result = Generator.Run(options);

Console.WriteLine($"Generated {result.Types.Count} of {result.AvailableTypes} types, wrote {result.FilesWritten} files, {result.Reporter.Warnings.Count} warnings.");

foreach (string warning in result.Reporter.Warnings.Take(25))
    Console.WriteLine("  warning: " + warning);

return 0;
