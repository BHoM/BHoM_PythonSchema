using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Extraction;
using PythonSchemaGeneration.Loading;
using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;
using PythonSchemaGeneration.Reporting;
using System.ComponentModel;
using System.Reflection;

namespace PythonSchemaGeneration
{
    public static class Generator
    {
        /***************************************************/

        [Description("Runs the whole C# to Python conversion: loads the oM assemblies, selects and registers the types, applies the --types and --repos filters, renders the " +
            "roots and every oM type they reference, finds reference cycles and renders again, then writes the Python files, the manifest and the report that the " +
            "options ask for. Returns the rendered types, counts and warnings; Program calls it, as do the tests, and it is the orchestrator of the generator " +
            "pipeline.")]
        public static GenerationResult Run(GenerationOptions options)
        {
            GenerationResult result = new GenerationResult();
            Reporter reporter = result.Reporter;

            List<Assembly> assemblies = options.Assemblies;
            if (assemblies == null)
                assemblies = AssemblyLoader.LoadOmAssemblies(options.AssemblyFolder ?? BHoMAdapter.DefaultAssemblyFolder(), options.Organisations, reporter);

            List<Type> selectedTypes = TypeSelector.Select(assemblies);
            result.AvailableTypes = selectedTypes.Count;
            TypeRegistry registry = new TypeRegistry();

            foreach (Type type in selectedTypes)
                registry.Add(type);

            List<Type> roots = FilterByRoots(selectedTypes, options.TypeFilter, reporter);
            HashSet<string> repoAssemblies = null;
            if (options.Repos != null)
            {
                roots = FilterByRepos(roots, options.Repos, reporter, out repoAssemblies);
            }

            TypeExtractor extractor = new TypeExtractor(registry, reporter);
            PythonEmitter emitter = new PythonEmitter(registry, reporter);

            //Render the roots and, transitively, every oM type they reference
            Dictionary<Type, RenderedType> renderedTypesByModelType = new Dictionary<Type, RenderedType>();
            Queue<Type> queue = new Queue<Type>(roots);

            while (queue.Count > 0)
            {
                Type type = TypeRegistry.Definition(queue.Dequeue());
                if (renderedTypesByModelType.ContainsKey(type))
                    continue;

                RenderedType r;
                try
                {
                    r = emitter.Render(extractor.Extract(type));
                }
                catch (Exception e)
                {
                    reporter.Warn(type.FullName, "could not be converted: " + e.Message);
                    result.FailedTypes.Add(type.FullName);
                    renderedTypesByModelType[type] = null;
                    continue;
                }

                renderedTypesByModelType[type] = r;
                foreach (Type reference in r.ClosureReferences.OrderBy(t => t.FullName, StringComparer.Ordinal))
                {
                    if (registry.Contains(reference) && !renderedTypesByModelType.ContainsKey(reference))
                        queue.Enqueue(reference);
                }
            }

            //Imports of types outside a reference cycle are safe before the class; only cyclic ones stay after it. Render again with that knowledge.
            Func<Type, Type, bool> isCycleRef = CycleDetector.DetectFunction(
                renderedTypesByModelType.Where(kv => kv.Value != null).ToDictionary(kv => kv.Key, kv => (IEnumerable<Type>)kv.Value.References));

            //The interfaces list their implementers, which are exactly the types that are generated
            HashSet<Type> generated = new HashSet<Type>(renderedTypesByModelType.Where(kv => kv.Value != null).Select(kv => kv.Key));

            foreach (Type type in renderedTypesByModelType.Keys.ToList())
            {
                if (renderedTypesByModelType[type] == null)
                    continue;

                Type self = type;
                renderedTypesByModelType[type] = emitter.Render(renderedTypesByModelType[type].Model, target => !isCycleRef(self, target), generated);
            }

            result.Types = renderedTypesByModelType.Values
                .Where(rendered => rendered != null)
                .OrderBy(rendered => rendered.Model.ClrName, StringComparer.Ordinal)
                .ToList();

            result.CyclicTypes = renderedTypesByModelType.Keys
                .Count(t => renderedTypesByModelType[t] != null && renderedTypesByModelType[t].References.Any(rendered => rendered != t && isCycleRef(t, rendered)));

            result.BHoMVersion = BHoMAdapter.BHoMVersion(assemblies);
            if (options.ReleaseVersion != null && options.ReleaseVersion != result.BHoMVersion)
                throw new InvalidOperationException($"The release {options.ReleaseVersion} does not match the BHoM version that was read ({result.BHoMVersion ?? "none"}).");

            if (options.OutputFolder != null)
            {
                result.FilesWritten = OutputWriter.Write(options.OutputFolder, result.Types, options.TypeFilter == null, reporter, repoAssemblies);

                //A partial run (--types) does not say what the package is, so it leaves the version file alone
                if (options.TypeFilter == null)
                    result.FilesWritten += WriteVersionFile(options.OutputFolder, result.BHoMVersion, options.ReleaseVersion != null, reporter);
            }

            if (options.ManifestPath != null)
                File.WriteAllText(options.ManifestPath, ManifestWriter.ToJson(result.Types), new System.Text.UTF8Encoding(false));

            if (options.ReportPath != null)
                File.WriteAllText(options.ReportPath, Report(result), new System.Text.UTF8Encoding(false));

            return result;
        }

        /***************************************************/

        [Description("Writes bhom_schema/_version.py with the BHoM version the classes come from and the package version: that plus .0 for a release, and that plus .0.dev0 " +
            "for develop, so the weekly run changes the file only when the BHoM version changes. Returns the number of files written (0 when it is unchanged). Run calls it " +
            "after the classes are written; setuptools reads the package version from this file.")]
        private static int WriteVersionFile(string packageRoot, string bhomVersion, bool isRelease, Reporter reporter)
        {
            if (bhomVersion == null)
            {
                reporter.Warn("No assembly was loaded, so _version.py was not written");
                return 0;
            }

            string text = "# Generated by BHoM_PythonSchema from the BHoM assemblies. Do not edit by hand.\n"
                + "# __bhom_version__ is the BHoM version (Major.Minor) of the classes; __version__ is the version of this package.\n\n"
                + $"__bhom_version__ = \"{bhomVersion}\"\n"
                + $"__version__ = \"{bhomVersion}.0{(isRelease ? "" : ".dev0")}\"\n";

            string path = Path.Combine(packageRoot, "_version.py");
            if (File.Exists(path) && File.ReadAllText(path) == text)
                return 0;

            Directory.CreateDirectory(packageRoot);
            File.WriteAllText(path, text, new System.Text.UTF8Encoding(false));
            return 1;
        }

        /***************************************************/

        [Description("Keeps the selected types whose full name, base name or formatted name matches one of the requested names (the --types option) and warns about a name " +
            "that matches nothing. Returns all types when no filter is given; Run uses it to choose the root types.")]
        private static List<Type> FilterByRoots(List<Type> selectedTypes, List<string> filter, Reporter reporter)
        {
            if (filter == null)
                return selectedTypes;

            List<Type> roots = new List<Type>();
            foreach (string name in filter)
            {
                List<Type> matches = selectedTypes.Where(t => t.FullName == name || ClrNames.BaseName(t) == name || ClrNames.Format(t) == name).ToList();
                if (matches.Count == 0)
                    reporter.Warn($"Requested type {name} was not found among the loaded oM types");

                roots.AddRange(matches);
            }
            return roots;
        }

        /***************************************************/

        [Description("Keeps the types of the assemblies that belong to the requested repositories (the --repos option), returns the names of those assemblies for the output " +
            "writer, and warns about a repository with no loaded assembly. Dependencies in other repositories are still generated; Run uses it so a weekly or " +
            "on-demand run can convert chosen repositories.")]
        private static List<Type> FilterByRepos(List<Type> types, List<string> repos, Reporter reporter, out HashSet<string> assemblies)
        {
            HashSet<string> wanted = new HashSet<string>(repos.Select(NormaliseRepo), StringComparer.OrdinalIgnoreCase);
            List<Type> kept = types.Where(t => wanted.Contains(NormaliseRepo(BHoMAdapter.AssemblyRepo(t.Assembly)))).ToList();
            assemblies = new HashSet<string>(kept.Select(t => t.Assembly.GetName().Name), StringComparer.OrdinalIgnoreCase);

            foreach (string repo in wanted.Where(r => !types.Any(t => NormaliseRepo(BHoMAdapter.AssemblyRepo(t.Assembly)).Equals(r, StringComparison.OrdinalIgnoreCase))))
                reporter.Warn($"No loaded oM assembly belongs to the requested repository {repo}");

            return kept;
        }

        /***************************************************/

        [Description("Trims whitespace and slashes from an Owner/Name repository text and turns null into an empty string, so repository names compare equal. Used by FilterByRepos.")]
        private static string NormaliseRepo(string repo)
        {
            return (repo ?? "").Trim().Trim('/');
        }

        /***************************************************/

        [Description("Builds the text of the report file: counts of available types, generated types, types in cycles, files written and warnings, followed by the info " +
            "messages and the sorted warnings. Written by Run when a report path is given.")]
        private static string Report(GenerationResult result)
        {
            List<string> lines = new List<string>
            {
                $"Types available: {result.AvailableTypes}",
                $"Types generated: {result.Types.Count}",
                $"Types in reference cycles: {result.CyclicTypes}",
                $"Files written: {result.FilesWritten}",
                $"Warnings: {result.Reporter.Warnings.Count}",
                ""
            };

            lines.AddRange(result.Reporter.Infos);
            lines.Add("");
            lines.AddRange(result.Reporter.Warnings.OrderBy(w => w, StringComparer.Ordinal));
            return string.Join("\n", lines) + "\n";
        }

        /***************************************************/
    }
}
