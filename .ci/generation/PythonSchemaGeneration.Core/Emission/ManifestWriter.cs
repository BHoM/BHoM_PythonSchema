using PythonSchemaGeneration.Model;
using System.Text.Json;

namespace PythonSchemaGeneration.Emission
{
    //Language-neutral list of the generated types. Compared with the manifest the Python reader builds in the tests.
    public static class ManifestWriter
    {
        /***************************************************/

        public static string ToJson(IEnumerable<RenderedType> rendered)
        {
            List<object> types = rendered
                .OrderBy(r => r.Model.ClrName, StringComparer.Ordinal)
                .Select(r => (object)Describe(r))
                .ToList();

            JsonSerializerOptions options = new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            };

            Dictionary<string, object> root = new Dictionary<string, object> { ["schemaVersion"] = 1, ["types"] = types };
            return JsonSerializer.Serialize(root, options);
        }

        /***************************************************/

        private static Dictionary<string, object> Describe(RenderedType r)
        {
            TypeModel model = r.Model;
            Dictionary<string, object> data = new Dictionary<string, object>
            {
                ["clrName"] = model.ClrName,
                ["name"] = model.CanonicalName,
                ["pythonName"] = r.Ref.Name,
                ["pythonModule"] = r.Ref.Module,
                ["relativePath"] = r.Ref.RelativePath + ".py",
                ["namespace"] = model.Namespace,
                ["assembly"] = model.Assembly,
                ["kind"] = PythonEmitter.KindText(model.Kind),
                ["bases"] = model.Bases.Select(ClrNames.Format).ToList(),
            };

            if (model.Repo != null)
                data["repo"] = model.Repo;

            if (model.Description != null)
                data["description"] = model.Description;

            if (model.IsFlags)
                data["flags"] = true;

            if (model.GenericParams.Count > 0)
            {
                data["genericParams"] = model.GenericParams.Select(g => new Dictionary<string, object>
                {
                    ["name"] = g.Name,
                    ["constraints"] = g.Constraints.Select(ClrNames.Format).ToList()
                }).ToList();
            }

            data["properties"] = r.Properties.Select(prop =>
            {
                Dictionary<string, object> propData = new Dictionary<string, object>
                {
                    ["name"] = prop.Name,
                    ["clrType"] = prop.ClrType,
                };

                if (model.Kind != TypeKind.Interface)
                {
                    propData["pyName"] = prop.PyName;
                    propData["hasDefault"] = prop.HasDefault;
                    if (prop.Default != null)
                        propData["default"] = prop.Default;
                }

                if (prop.Description != null)
                    propData["description"] = prop.Description;

                if (prop.Quantity != null)
                    propData["quantity"] = new Dictionary<string, object> { ["category"] = prop.Quantity.Category, ["unit"] = prop.Quantity.Unit ?? "" };

                if (prop.DisplayText != null)
                    propData["displayText"] = prop.DisplayText;

                if (prop.IsDynamic)
                    propData["dynamic"] = true;

                return propData;
            }).ToList();

            if (model.Kind == TypeKind.Enum)
            {
                data["members"] = model.EnumMembers.Select(e =>
                {
                    Dictionary<string, object> enumData = new Dictionary<string, object> { ["name"] = e.Name, ["value"] = e.Value };
                    if (e.Description != null)
                        enumData["description"] = e.Description;

                    return enumData;
                }).ToList();
            }

            return data;
        }

        /***************************************************/
    }
}
