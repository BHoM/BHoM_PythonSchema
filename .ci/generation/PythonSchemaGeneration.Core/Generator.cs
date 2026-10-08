using PythonSchemaGeneration.Emission;
using PythonSchemaGeneration.Extraction;
using PythonSchemaGeneration.Loading;
using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;
using PythonSchemaGeneration.Reporting;
using System.Reflection;

namespace PythonSchemaGeneration
{
    public static class Generator
    {
        /***************************************************/

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

            foreach (Type type in renderedTypesByModelType.Keys.ToList())
            {
                if (renderedTypesByModelType[type] == null)
                    continue;

                Type self = type;
                renderedTypesByModelType[type] = emitter.Render(renderedTypesByModelType[type].Model, target => !isCycleRef(self, target));
            }

            result.Types = renderedTypesByModelType.Values
                .Where(rendered => rendered != null)
                .OrderBy(rendered => rendered.Model.ClrName, StringComparer.Ordinal)
                .ToList();

            result.CyclicTypes = renderedTypesByModelType.Keys
                .Count(t => renderedTypesByModelType[t] != null && renderedTypesByModelType[t].References.Any(rendered => rendered != t && isCycleRef(t, rendered)));

            if (options.OutputFolder != null)
                result.FilesWritten = OutputWriter.Write(options.OutputFolder, result.Types, options.TypeFilter == null, reporter);

            if (options.ManifestPath != null)
                File.WriteAllText(options.ManifestPath, ManifestWriter.ToJson(result.Types), new System.Text.UTF8Encoding(false));

            if (options.ReportPath != null)
                File.WriteAllText(options.ReportPath, Report(result), new System.Text.UTF8Encoding(false));

            return result;
        }

        /***************************************************/

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
