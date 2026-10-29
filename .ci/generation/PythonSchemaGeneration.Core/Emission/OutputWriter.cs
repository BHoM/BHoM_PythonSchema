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
            foreach (RenderedType type in rendered)
            {
                string relativePath = type.Ref.RelativePath + ".py";
                if (fileTextByPath.ContainsKey(relativePath))
                {
                    reporter.Warn(type.Model.ClrName, $"output path {relativePath} is already used by another type, skipped");
                    continue;
                }

                fileTextByPath[relativePath] = type.Text;
                string[] segments = relativePath.Split('/');

                for (int i = 1; i < segments.Length; i++)
                {
                    string init = string.Join("/", segments.Take(i)) + "/__init__.py";
                    if (!fileTextByPath.ContainsKey(init))
                        fileTextByPath[init] = "";
                }
            }

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
