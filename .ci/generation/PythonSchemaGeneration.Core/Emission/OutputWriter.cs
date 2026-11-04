using System.ComponentModel;
using PythonSchemaGeneration.Reporting;
using System.Text;

namespace PythonSchemaGeneration.Emission
{
    public static class OutputWriter
    {
        /***************************************************/

        private static readonly UTF8Encoding m_Utf8 = new UTF8Encoding(false);

        /***************************************************/

        [Description("Writes the rendered modules (and empty __init__.py files for their folders) under the package root, skipping files whose text is unchanged, "
            + "and returns the number of files written. With cleanRedundant it first deletes stale .py files in the folders of the written assemblies (only "
            + "those in cleanAssemblies when given), so the hand-written support package is never touched. The generator's last file-writing stage.")]
        public static int Write(string packageRoot, IEnumerable<RenderedType> rendered, bool cleanRedundant, Reporter reporter, ISet<string> cleanAssemblies = null)
        {
            Dictionary<string, string> fileTextByPath = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            Dictionary<string, string> typeByPath = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            List<string> clashes = new List<string>();
            foreach (RenderedType type in rendered)
            {
                string relativePath = type.Ref.RelativePath + ".py";
                if (fileTextByPath.ContainsKey(relativePath))
                {
                    clashes.Add($"{typeByPath[relativePath]} and {type.Model.ClrName} would both be written to {relativePath}");
                    continue;
                }

                fileTextByPath[relativePath] = type.Text;
                typeByPath[relativePath] = type.Model.ClrName;
                string[] segments = relativePath.Split('/');

                for (int i = 1; i < segments.Length; i++)
                {
                    string init = string.Join("/", segments.Take(i)) + "/__init__.py";
                    if (!fileTextByPath.ContainsKey(init))
                        fileTextByPath[init] = "";
                }
            }

            //File names ignore upper and lower case on Windows, so one of the two classes would silently be lost
            if (clashes.Count > 0)
                throw new InvalidOperationException("Two classes would be written to the same file:" + Environment.NewLine + string.Join(Environment.NewLine, clashes));

            if (cleanRedundant)
                CleanRedundantExistingFiles(packageRoot, fileTextByPath, cleanAssemblies);

            int written = 0;
            foreach (KeyValuePair<string, string> file in fileTextByPath.OrderBy(f => f.Key, StringComparer.Ordinal))
            {
                string path = Path.Combine(packageRoot, file.Key.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                string text = file.Value.Replace("\r\n", "\n");

                if (File.Exists(path) && File.ReadAllText(path, m_Utf8) == text)
                    continue;

                File.WriteAllText(path, text, m_Utf8);
                written++;
            }

            return written;
        }

        /***************************************************/

        [Description("Lists the assembly folders of the package that this run did not generate: folders of the package root, other than the support, tables and hidden ones, that " +
            "no rendered type belongs to. With repos (a run for some repositories) only the folders whose Python files name one of those repositories count, so the " +
            "folders of other repositories are left alone. Generator calls it after a full run, so a failed build of an assembly is noticed instead of leaving its old files behind.")]
        public static List<string> MissingAssemblyFolders(string packageRoot, IEnumerable<RenderedType> rendered, IEnumerable<string> repos)
        {
            HashSet<string> generated = new HashSet<string>(rendered.Select(r => r.Ref.RelativePath.Split('/')[0]), StringComparer.OrdinalIgnoreCase);
            List<string> missing = new List<string>();
            if (!Directory.Exists(packageRoot))
                return missing;

            foreach (string folder in Directory.GetDirectories(packageRoot).Select(Path.GetFileName).OrderBy(name => name, StringComparer.Ordinal))
            {
                if (folder.StartsWith("_") || folder.StartsWith(".") || folder == "tables" || generated.Contains(folder))
                    continue;

                if (repos != null && !repos.Contains(RepoOfFolder(Path.Combine(packageRoot, folder)), StringComparer.OrdinalIgnoreCase))
                    continue;

                missing.Add(folder);
            }

            return missing;
        }

        /***************************************************/

        [Description("Reads the repository that the generated Python files of a folder name in their marker, or null when no file has one. MissingAssemblyFolders uses it to " +
            "tell which repository a folder that was not generated belongs to.")]
        private static string RepoOfFolder(string folder)
        {
            const string key = "'repo': '";
            foreach (string file in Directory.EnumerateFiles(folder, "*.py", SearchOption.AllDirectories))
            {
                foreach (string line in File.ReadLines(file, m_Utf8))
                {
                    int start = line.IndexOf(key, StringComparison.Ordinal);
                    if (start < 0)
                        continue;

                    start += key.Length;
                    int end = line.IndexOf('\'', start);
                    return end < 0 ? null : line.Substring(start, end - start);
                }
            }

            return null;
        }

        /***************************************************/

        [Description("Deletes .py files in the folders of the written assemblies that are no longer generated, then removes the empty folders. Write calls it when "
            + "stale output must be cleaned; cleanAssemblies limits it to the assemblies of the requested repositories.")]
        private static void CleanRedundantExistingFiles(string packageRoot, Dictionary<string, string> fileTextByPath, ISet<string> cleanAssemblies)
        {
            foreach (string assembly in fileTextByPath.Keys.Select(k => k.Split('/')[0]).Distinct())
            {
                if (cleanAssemblies != null && !cleanAssemblies.Contains(assembly))
                    continue;

                string folder = Path.Combine(packageRoot, assembly);
                if (!Directory.Exists(folder))
                    continue;

                foreach (string file in Directory.EnumerateFiles(folder, "*.py", SearchOption.AllDirectories))
                {
                    string relative = Path.GetRelativePath(packageRoot, file).Replace('\\', '/');
                    if (!fileTextByPath.ContainsKey(relative))
                        File.Delete(file);
                }

                RemoveEmptyDirectories(folder);
            }
        }

        /***************************************************/

        [Description("Recursively deletes the empty folders under a folder. CleanRedundantExistingFiles calls it after removing stale files.")]
        private static void RemoveEmptyDirectories(string folder)
        {
            foreach (string dir in Directory.GetDirectories(folder))
            {
                RemoveEmptyDirectories(dir);
                if (!Directory.EnumerateFileSystemEntries(dir).Any())
                    Directory.Delete(dir);
            }
        }

        /***************************************************/
    }
}
