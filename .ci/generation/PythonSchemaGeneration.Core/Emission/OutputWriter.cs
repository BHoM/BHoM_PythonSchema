using PythonSchemaGeneration.Reporting;
using System.Text;

namespace PythonSchemaGeneration.Emission
{
    public static class OutputWriter
    {
        /***************************************************/

        private static readonly UTF8Encoding m_Utf8 = new UTF8Encoding(false);

        /***************************************************/

        //Writes the rendered modules under <packageRoot>. With cleanRedundant=True, existing files of written assemblies that are no longer generated are removed.
        //Only folders of assemblies in this run are touched, so the hand-written support package is never affected.
        public static int Write(string packageRoot, IEnumerable<RenderedType> rendered, bool cleanRedundant, Reporter reporter)
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
                CleanRedundantExistingFiles(packageRoot, fileTextByPath);

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

        private static void CleanRedundantExistingFiles(string packageRoot, Dictionary<string, string> fileTextByPath)
        {
            foreach (string assembly in fileTextByPath.Keys.Select(k => k.Split('/')[0]).Distinct())
            {
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

        private static void RemoveEmptyDirectories(string folder)
        {
            foreach (string dir in Directory.GetDirectories(folder))
            {
                RemoveEmptyDirectories(dir);
                if (!Directory.EnumerateFileSystemEntries(folder).Any())
                    Directory.Delete(folder);
            }
        }

        /***************************************************/
    }
}
