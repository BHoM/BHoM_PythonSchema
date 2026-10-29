using System.ComponentModel;
using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;
using PythonSchemaGeneration.Reporting;
using System.Text;
using System.Text.RegularExpressions;

namespace PythonSchemaGeneration.Emission
{
    //Type model to Python source text, deterministic for the same input
    public class PythonEmitter
    {
        /***************************************************/

        private const string Indent = "    ";
        private readonly Reporter m_Reporter;
        private readonly TypeRegistry m_TypeRegistry;

        /***************************************************/

        [Description("Creates an emitter that writes Python modules using the given type registry to resolve names and the reporter to collect warnings. The "
            + "generator builds one and reuses it for every type in both render passes.")]
        public PythonEmitter(TypeRegistry registry, Reporter reporter)
        {
            m_TypeRegistry = registry;
            m_Reporter = reporter;
        }

        /***************************************************/

        [Description("Renders one language-neutral type model to the text of its Python module (header, imports, class with the __bhom__ marker and fields) and "
            + "returns it with its properties and the types it references. The generator calls it for every selected type, then again with an early-import "
            + "test from the CycleDetector so imports that would form a cycle move below the class.")]
        public RenderedType Render(TypeModel model, Func<Type, bool> isSafeForEarlyImport = null)
        {
            PyRef pyRef = m_TypeRegistry.Ref(model.Type);
            List<string> fieldNames = model.Properties.Select(p => Naming.Identifier(p.Name)).Concat(model.GenericParams.Select(g => g.Name)).ToList();

            NameTracker tracker = new NameTracker(model.Type, pyRef.Name, fieldNames) { IsSafeForEarlyImport = isSafeForEarlyImport };
            RenderedType rendered = new RenderedType { Model = model, Ref = pyRef };

            string classLine = ClassHeader(model, tracker, pyRef, out List<string> baseConstraintNotes);
            StringBuilder body = new StringBuilder();

            if (model.Description != null)
                body.Append(Indent).Append(Docstring(model.Description)).Append('\n');

            body.Append(Marker(model, tracker, baseConstraintNotes, rendered));

            if (model.Kind == TypeKind.Enum)
                AddEnumMembers(model, body);
            else if (model.Kind != TypeKind.Interface)
                AddFields(model, body, tracker, rendered);

            string text = Assemble(model, classLine, body.ToString(), tracker, pyRef);
            rendered.Text = text;
            rendered.References = tracker.References;
            rendered.ClosureReferences = new HashSet<Type>(tracker.References.Concat(tracker.MentionedOnly));
            return rendered;
        }

        /***************************************************/

        [Description("Builds the Python class line for a type: its base classes (enum, SchemaModel, parent class, interfaces, ABC) and PEP 695 generic parameters "
            + "with their bounds. Also returns notes for generic constraints that cannot be represented; Render puts them in the marker.")]
        private string ClassHeader(TypeModel model, NameTracker tracker, PyRef pyRef, out List<string> notes)
        {
            notes = new List<string>();
            List<string> bases = new List<string>();
            TypeMapper typeMapper = new TypeMapper(m_TypeRegistry, m_Reporter, tracker, model.ClrName) { IsSafeForEarlyImport = true };

            if (model.Kind == TypeKind.Enum)
                bases.Add(tracker.AddStandardName("enum", model.IsFlags ? "IntFlag" : "Enum"));
            else
            {
                Type baseClass = model.Bases.FirstOrDefault(b => !b.IsInterface);
                List<Type> interfaces = model.Bases.Where(b => b.IsInterface).ToList();

                if (model.Kind != TypeKind.Interface)
                    bases.Add(baseClass != null ? typeMapper.Map(baseClass).Expression : tracker.AddStandardName("bhom_schema._support", "SchemaModel"));

                bases.AddRange(interfaces.Select(i => typeMapper.Map(i).Expression));
                bool hasAbcBase = interfaces.Count > 0;

                if ((model.Kind == TypeKind.Interface || model.Kind == TypeKind.AbstractClass) && !hasAbcBase)
                    bases.Add(tracker.AddStandardName("abc", "ABC"));
            }

            string generics = "";
            if (model.GenericParams.Count > 0)
            {
                TypeMapper lazyMapper = new TypeMapper(m_TypeRegistry, m_Reporter, tracker, model.ClrName) { IsSafeForEarlyImport = true };
                List<string> parts = new List<string>();

                foreach (GenericParamModel param in model.GenericParams)
                {
                    List<Type> usable = param.Constraints.Where(c => m_TypeRegistry.Contains(c)).ToList();
                    if (param.Constraints.Count > usable.Count)
                        notes.Add($"{param.Name}: constraint not representable and dropped");

                    if (usable.Count == 0)
                    {
                        parts.Add(param.Name);
                        continue;
                    }

                    string bound = lazyMapper.Map(usable[0]).Expression;

                    //A PEP 695 bound cannot mention a type parameter, so those arguments become Any
                    if (usable[0].ContainsGenericParameters)
                    {
                        string any = tracker.AddStandardName("typing", "Any");
                        foreach (GenericParamModel other in model.GenericParams)
                            bound = Regex.Replace(bound, $@"\b{Regex.Escape(other.Name)}\b", any);
                    }

                    parts.Add($"{param.Name}: {bound}");
                }

                generics = "[" + string.Join(", ", parts) + "]";
            }

            return $"class {pyRef.Name}{generics}({string.Join(", ", bases)}):";
        }

        /***************************************************/

        [Description("Builds the indented __bhom__ dictionary that records the C# name, assembly, namespace, repo, kind, generic parameters, interface members and "
            + "renamed enum members. Interface members are also added to the rendered properties; Render places the result at the top of every generated "
            + "class.")]
        private string Marker(TypeModel model, NameTracker tracker, List<string> notes, RenderedType rendered)
        {
            string any = tracker.AddStandardName("typing", "Any");
            string classVar = tracker.AddStandardName("typing", "ClassVar");

            List<KeyValuePair<string, string>> entries = new List<KeyValuePair<string, string>>
            {
                new KeyValuePair<string, string>("clr_name", PyLiteral.Str(model.ClrName)),
                new KeyValuePair<string, string>("assembly", PyLiteral.Str(model.Assembly)),
                new KeyValuePair<string, string>("namespace", PyLiteral.Str(model.Namespace)),
            };

            if (model.Repo != null)
                entries.Add(new KeyValuePair<string, string>("repo", PyLiteral.Str(model.Repo)));

            entries.Add(new KeyValuePair<string, string>("kind", PyLiteral.Str(KindText(model.Kind))));
            if (model.IsFlags)
                entries.Add(new KeyValuePair<string, string>("flags", "True"));

            if (model.GenericParams.Count > 0)
            {
                string items = string.Join(", ", model.GenericParams.Select(p =>
                    PyLiteral.Str(p.Name) + ": [" + string.Join(", ", p.Constraints.Select(c => PyLiteral.Str(ClrNames.Format(c)))) + "]"));

                entries.Add(new KeyValuePair<string, string>("generic_params", "{" + items + "}"));
            }

            if (notes.Count > 0)
                entries.Add(new KeyValuePair<string, string>("notes", "[" + string.Join(", ", notes.Select(PyLiteral.Str)) + "]"));

            if (model.Kind == TypeKind.Interface && model.Properties.Count > 0)
            {
                List<string> props = new List<string>();
                foreach (PropertyModel p in model.Properties)
                {
                    Mention(p.Type, tracker);
                    string entry = "{'type': " + PyLiteral.Str(ClrNames.Format(p.Type));

                    if (p.Description != null)
                        entry += ", 'description': " + PyLiteral.Str(p.Description);

                    props.Add(PyLiteral.Str(p.Name) + ": " + entry + "}");

                    //Interface members are only listed in the marker, but the types they use still need a Python class
                    rendered.Properties.Add(new RenderedProperty
                    {
                        Name = p.Name,
                        PyName = p.Name,
                        ClrType = ClrNames.Format(p.Type),
                        Description = p.Description
                    });
                }

                entries.Add(new KeyValuePair<string, string>("properties", "{" + string.Join(", ", props) + "}"));
            }

            if (model.Kind == TypeKind.Enum)
            {
                Dictionary<string, string> renamed = model.EnumMembers
                    .Where(m => Naming.Identifier(m.Name) != m.Name)
                    .ToDictionary(m => Naming.Identifier(m.Name), m => m.Name);

                rendered.RenamedMembers = renamed;
                if (renamed.Count > 0)
                    entries.Add(new KeyValuePair<string, string>("renamed_members",
                        "{" + string.Join(", ", renamed.Select(kv => PyLiteral.Str(kv.Key) + ": " + PyLiteral.Str(kv.Value))) + "}"));
            }

            StringBuilder sb = new StringBuilder();
            sb.Append(Indent).Append($"__bhom__: {classVar}[dict[str, {any}]] = {{\n");

            foreach (KeyValuePair<string, string> kv in entries)
                sb.Append(Indent).Append(Indent).Append(PyLiteral.Str(kv.Key)).Append(": ").Append(kv.Value).Append(",\n");

            sb.Append(Indent).Append("}\n");
            return sb.ToString();
        }

        /***************************************************/

        [Description("Records the registered types used by an interface member type (looking inside arrays and generic arguments) so they are generated too, "
            + "without importing them. Marker calls it for interface properties, because their types still need a Python class.")]
        private void Mention(Type type, NameTracker tracker)
        {
            if (type.FullName == "BH.oM.Base.FragmentSet")     //written as a list of fragments, see TypeMapper
            {
                Type fragment = type.Assembly.GetType("BH.oM.Base.IFragment");
                if (fragment != null)
                    Mention(fragment, tracker);

                return;
            }

            if (type.IsArray)
                Mention(type.GetElementType(), tracker);
            else if (type.IsGenericType)
            {
                foreach (Type argument in type.GetGenericArguments())
                    Mention(argument, tracker);
                if (m_TypeRegistry.Contains(type))
                    tracker.MentionedOnly.Add(TypeRegistry.Definition(type));
            }
            else if (m_TypeRegistry.Contains(type))
                tracker.MentionedOnly.Add(type);
        }

        /***************************************************/

        [Description("Returns the marker text for a type kind (abstract, interface, enum, struct or class). Used by the emitter for the __bhom__ marker and by the "
            + "ManifestWriter so both state the same kind.")]
        public static string KindText(TypeKind kind)
        {
            switch (kind)
            {
                case TypeKind.AbstractClass: return "abstract";
                case TypeKind.Interface: return "interface";
                case TypeKind.Enum: return "enum";
                case TypeKind.Struct: return "struct";
                default: return "class";
            }
        }

        /***************************************************/

        [Description("Appends the member lines of an enum class (name = value, with the member description as a comment) to the class body, or a pass line when "
            + "there are none. Render calls it for enum types.")]
        private void AddEnumMembers(TypeModel model, StringBuilder body)
        {
            body.Append('\n');
            if (model.EnumMembers.Count == 0)
            {
                body.Append(Indent).Append("pass\n");
                return;
            }

            foreach (EnumMemberModel member in model.EnumMembers)
            {
                if (member.Description != null)
                    body.Append(Indent).Append("# ").Append(member.Description.Replace("\r", " ").Replace("\n", " ")).Append('\n');

                body.Append(Indent).Append(Naming.Identifier(member.Name)).Append(" = ").Append(member.Value).Append('\n');
            }
        }

        /***************************************************/

        [Description("Appends one annotated field line per property to the class body: maps the type, adds | None for null defaults, wraps the annotation with "
            + "ClrType, Quantity, DisplayText and DynamicProperty markers, and writes the default, description and alias through Field. Also fills the "
            + "rendered property list that the manifest uses; Render calls it for classes and structs.")]
        private void AddFields(TypeModel model, StringBuilder body, NameTracker tracker, RenderedType rendered)
        {
            bool first = true;
            TypeMapper mapper = new TypeMapper(m_TypeRegistry, m_Reporter, tracker, model.ClrName);
            IEnumerable<string> typeParams = model.GenericParams.Select(g => g.Name);
            DefaultFormatter formatter = new DefaultFormatter(m_TypeRegistry, m_Reporter, tracker, model.ClrName, typeParams);

            foreach (PropertyModel property in model.Properties)
            {
                MappedType mapped = mapper.Map(property.Type);
                DefaultText value = formatter.Format(property, mapped);

                string expression = mapped.Expression;

                //Check if the property is nullable and the type is not a value type, and if so, add " | None" to the type expression
                bool addNone = value.IsNull && !expression.EndsWith(" | None") && !mapped.IsValueType;
                if (addNone)
                    expression += " | None";

                string actualClrName = ClrNames.Format(property.Type);
                string defaultClrName = mapped.DefaultClr;
                string clrNameOverride = actualClrName != defaultClrName ? actualClrName : null;

                List<string> markers = new List<string>();
                if (clrNameOverride != null)
                    markers.Add($"{tracker.AddStandardName("bhom_schema._support", "ClrType")}({PyLiteral.Str(clrNameOverride)})");

                if (property.Quantity != null)
                    markers.Add($"{tracker.AddStandardName("bhom_schema._support", "Quantity")}({PyLiteral.Str(property.Quantity.Category)}, {PyLiteral.Str(property.Quantity.Unit ?? "")})");

                if (property.DisplayText != null)
                    markers.Add($"{tracker.AddStandardName("bhom_schema._support", "DisplayText")}({PyLiteral.Str(property.DisplayText)})");

                if (property.IsDynamic)
                    markers.Add($"{tracker.AddStandardName("bhom_schema._support", "DynamicProperty")}()");

                string annotation;
                if (markers.Count == 0)
                    annotation = expression;
                else
                    annotation = $"{tracker.AddStandardName("typing", "Annotated")}[{expression}, {string.Join(", ", markers)}]";

                string pyName = Naming.Identifier(property.Name);
                List<string> fieldArgs = new List<string>();
                if (value.Kind == DefaultKind.Literal)
                    fieldArgs.Add("default=" + value.Text);

                if (value.Kind == DefaultKind.Factory)
                    fieldArgs.Add("default_factory=" + value.Text);

                if (property.Description != null)
                    fieldArgs.Add("description=" + PyLiteral.Str(property.Description));

                if (pyName != property.Name)
                    fieldArgs.Add("alias=" + PyLiteral.Str(property.Name));

                string assignment = "";
                if (fieldArgs.Count == 0)
                    assignment = value.Kind == DefaultKind.Literal ? " = " + value.Text : "";
                else if (fieldArgs.Count == 1 && value.Kind == DefaultKind.Literal)
                    assignment = " = " + value.Text;
                else
                    assignment = $" = {tracker.AddStandardName("pydantic", "Field")}({string.Join(", ", fieldArgs)})";

                if (first)
                    body.Append('\n');
                first = false;

                body.Append(Indent).Append(pyName).Append(": ").Append(annotation).Append(assignment).Append('\n');

                rendered.Properties.Add(new RenderedProperty
                {
                    Name = property.Name,
                    PyName = pyName,
                    ClrType = actualClrName,
                    PyType = expression,
                    HasDefault = value.Kind != DefaultKind.None,
                    Default = value.Kind == DefaultKind.None ? null : (value.Kind == DefaultKind.Factory ? "<factory> " + value.Text : value.Text),
                    Description = property.Description,
                    Quantity = property.Quantity,
                    DisplayText = property.DisplayText,
                    IsDynamic = property.IsDynamic
                });
            }
        }

        /***************************************************/

        [Description("Joins the header comment, grouped imports, class line and body into the final module text, with imports of types in a cycle placed after the "
            + "class followed by model_rebuild. The last step of Render.")]
        private string Assemble(TypeModel model, string classLine, string body, NameTracker tracker, PyRef pyRef)
        {
            StringBuilder sb = new StringBuilder();
            sb.Append($"# Generated by BHoM_PythonSchema from the C# oM type {model.ClrName}. Do not edit by hand.\n");
            sb.Append("# Copyright (c) 2015 - 2026, the respective contributors. All rights reserved.\n");
            sb.Append("# Licensed under the GNU Lesser General Public License, version 3.0 or later.\n");

            bool isModel = model.Kind != TypeKind.Enum && model.Kind != TypeKind.Interface;
            if (isModel)
                sb.Append("# pyright: reportUnknownVariableType=false, reportIncompatibleVariableOverride=false\n");

            sb.Append("\nfrom __future__ import annotations\n\n");
            List<ImportEntry> imports = tracker.Imports.ToList();

            //Standard library, then third party, then this package
            IEnumerable<ImportEntry>[] groups =
            [
                imports.Where(i => !i.IsOm && IsStandardLib(i.Module)),
                imports.Where(i => !i.IsOm && i.Module == "pydantic"),
                imports.Where(i => (!i.IsOm && i.Module.StartsWith("bhom_schema._support")) || (i.IsOm && i.IsSafeForEarlyImport))
            ];

            bool wrote = false;
            foreach (IEnumerable<ImportEntry> group in groups)
            {
                List<ImportEntry> entries = group.ToList();
                if (entries.Count == 0)
                    continue;

                if (wrote)
                    sb.Append('\n');

                AppendFromImports(sb, entries);
                wrote = true;
            }

            sb.Append('\n').Append('\n');
            sb.Append(classLine).Append('\n');
            sb.Append(body);

            //Types only used in annotations are imported after the class so circular references cannot break module loading
            List<ImportEntry> bottom = imports.Where(i => i.IsOm && !i.IsSafeForEarlyImport).ToList();
            if (bottom.Count > 0)
            {
                sb.Append('\n').Append('\n');
                AppendFromImports(sb, bottom);

                if (isModel)
                    sb.Append($"\n{pyRef.Name}.model_rebuild()\n");
            }

            string text = sb.ToString();
            while (text.EndsWith("\n\n"))
                text = text.Substring(0, text.Length - 1);

            return text;
        }

        /***************************************************/

        [Description("Tells whether a module name is one of the Python standard library modules the generator imports from. Assemble uses it to put those imports "
            + "in the first import group.")]
        private static bool IsStandardLib(string module)
        {
            return module == "abc" || module == "collections.abc" || module == "datetime" || module == "decimal" ||
                   module == "enum" || module == "typing" || module == "uuid";
        }

        /***************************************************/

        [Description("Appends from-import lines for the given import entries, grouped by module and sorted so the output is deterministic. Assemble calls it for each import group.")]
        private static void AppendFromImports(StringBuilder sb, IEnumerable<ImportEntry> imports)
        {
            foreach (IGrouping<string, ImportEntry> group in imports.GroupBy(i => i.Module).OrderBy(g => g.Key, StringComparer.Ordinal))
            {
                IEnumerable<string> names = group
                    .OrderBy(i => i.Name, StringComparer.Ordinal)
                    .Select(i => i.Name == i.Local ? i.Name : $"{i.Name} as {i.Local}");
                sb.Append($"from {group.Key} import {string.Join(", ", names)}\n");
            }
        }

        /***************************************************/

        [Description("Turns a C# description into an indented Python triple-quoted docstring, escaping backslashes and quotes. Render uses it for the class description.")]
        private static string Docstring(string text)
        {
            string escaped = text.Replace("\\", "\\\\").Replace("\"\"\"", "\\\"\\\"\\\"");
            if (escaped.EndsWith("\"")) escaped = escaped.Substring(0, escaped.Length - 1) + "\\\"";
            return "\"\"\"" + escaped.Replace("\r\n", "\n").Replace("\n", "\n" + Indent) + "\"\"\"";
        }

        /***************************************************/
    }
}
