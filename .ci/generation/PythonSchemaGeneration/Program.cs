using PythonSchemaGeneration;
using PythonSchemaGeneration.Reporting;

//Exit codes: 0 done, 1 a type could not be converted or a warning kind is not in the baseline, 2 wrong command line
CommandLine command = CommandLine.Parse(args);
if (command.Error != null)
{
    Console.Error.WriteLine(command.Error);
    Console.Error.WriteLine(CommandLine.Usage);
    return 2;
}

GenerationResult result = Generator.Run(command.Options);

Console.WriteLine($"Generated {result.Types.Count} of {result.AvailableTypes} types, wrote {result.FilesWritten} files, {result.Reporter.Warnings.Count} warnings.");

foreach (string warning in result.Reporter.Warnings.Take(25))
    Console.WriteLine("  warning: " + warning);

int exitCode = 0;
foreach (string type in result.FailedTypes)
{
    Console.Error.WriteLine($"error: {type} could not be converted");
    exitCode = 1;
}

if (command.WriteBaselinePath != null)
{
    WarningBaseline.Write(command.WriteBaselinePath, result.Reporter.Warnings);
    Console.WriteLine($"Wrote {WarningBaseline.Kinds(result.Reporter.Warnings).Count} warning kinds to {command.WriteBaselinePath}");
}

if (command.BaselinePath != null)
{
    (List<string> newKinds, List<string> goneKinds) = WarningBaseline.Compare(result.Reporter.Warnings, WarningBaseline.Read(command.BaselinePath));
    foreach (string kind in goneKinds)
        Console.WriteLine($"note: the warning kind '{kind}' no longer occurs; remove it from the baseline");

    foreach (string kind in newKinds)
    {
        Console.Error.WriteLine($"error: new warning kind not in the baseline: {kind}");
        exitCode = 1;
    }
}

return exitCode;
