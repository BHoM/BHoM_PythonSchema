using PythonSchemaGeneration.Patcher;
using System.Text;
using System.Text.Json;

//Usage: PythonSchemaGeneration.Patcher <job.json>
//Changes existing C# files member by member as the job lists, writes each result to its output path, and prints the notes as json.
if (args.Length != 1)
{
    Console.Error.WriteLine("Usage: PythonSchemaGeneration.Patcher <job.json>");
    return 2;
}

Console.OutputEncoding = new UTF8Encoding(false);
JsonSerializerOptions options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true };
PatchJob job = JsonSerializer.Deserialize<PatchJob>(File.ReadAllText(args[0]), options);
List<FileResult> results = new List<FileResult>();

foreach (FileJob file in job.Files)
{
    FileResult result = new FileResult { Output = file.Output };
    try
    {
        //Keep the byte order mark of the existing file, if it has one
        byte[] bytes = File.ReadAllBytes(file.Path);
        bool bom = bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF;
        string source = new UTF8Encoding(false).GetString(bytes, bom ? 3 : 0, bytes.Length - (bom ? 3 : 0));
        PatchResult patched = FilePatcher.Patch(source, file);
        File.WriteAllText(file.Output, patched.Text, new UTF8Encoding(bom));
        result.Notes = patched.Notes;
    }
    catch (Exception e)
    {
        result.Error = e.Message;
    }

    results.Add(result);
}

Console.WriteLine(JsonSerializer.Serialize(new { Files = results }, options));
return 0;
