using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Text;
using System.ComponentModel;
using System.Globalization;

namespace PythonSchemaGeneration.Patcher
{
    //Changes one existing C# file member by member. Roslyn finds the members; the edits are applied to the original text,
    //so everything that is not changed (comments, blank lines, attributes the Python does not know about) stays as it is.
    public class FilePatcher
    {
        /***************************************************/

        private readonly string m_Source;
        private readonly SourceText m_Text;
        private readonly CompilationUnitSyntax m_Root;
        private readonly string m_NewLine;
        private readonly TextEdits m_Edits = new TextEdits();
        private readonly List<TextSpan> m_Removed = new List<TextSpan>();
        private readonly List<string> m_Notes = new List<string>();

        /***************************************************/

        [Description("Parses the C# source of one file with Roslyn and remembers its text and line-break style. Created only by Patch, so every edit of a file works on one "
            + "parsed copy of the original.")]
        private FilePatcher(string source)
        {
            m_Source = source;
            m_Text = SourceText.From(source);
            m_Root = CSharpSyntaxTree.ParseText(m_Text).GetCompilationUnitRoot();
            m_NewLine = source.Contains("\r\n") ? "\r\n" : "\n";
        }

        /***************************************************/

        [Description("Applies the member-level changes of one file job to the source of an existing C# file and returns the new text with notes for changes that could not "
            + "be made. The patcher's entry point: Program calls it once per file of the job that py2cs writes, and only the changed members are touched.")]
        public static PatchResult Patch(string source, FileJob job)
        {
            return new FilePatcher(source).Apply(job);
        }

        /***************************************************/

        [Description("Finds the type named in the job and applies each change to it as an edit on the original text, then adds new properties or enum members and any "
            + "missing usings. Throws when the file does not declare the type; unknown change kinds are noted and skipped.")]
        private PatchResult Apply(FileJob job)
        {
            BaseTypeDeclarationSyntax type = FindType(job.Type, job.Namespace);
            if (type == null)
                throw new InvalidOperationException($"the file does not declare {job.Type}");

            foreach (Change change in job.Changes)
            {
                switch (change.Kind)
                {
                    case "addProperty":
                    case "addEnumMember":
                        break;
                    case "removeProperty":
                        RemoveProperty(type, change);
                        break;
                    case "setPropertyType":
                        SetPropertyType(type, change);
                        break;
                    case "setPropertyInitialiser":
                        SetPropertyInitialiser(type, change);
                        break;
                    case "setDescription":
                        SetDescription(type, change);
                        break;
                    case "setAttributes":
                        SetAttributes(type, change);
                        break;
                    case "setBases":
                        SetBases(type, change);
                        break;
                    case "removeEnumMember":
                        RemoveEnumMember(type, change);
                        break;
                    case "setEnumValue":
                        SetEnumValue(type, change);
                        break;
                    default:
                        m_Notes.Add($"unknown change {change.Kind} was skipped");
                        break;
                }
            }

            AddProperties(type, job.Changes.Where(c => c.Kind == "addProperty").ToList());
            AddEnumMembers(type, job.Changes.Where(c => c.Kind == "addEnumMember").ToList());

            if (m_Edits.Count > 0)
                AddUsings(job.Usings);

            return new PatchResult { Text = m_Edits.Apply(m_Source), Notes = m_Notes };
        }

        /***************************************************/
        /**** Finding things                            ****/
        /***************************************************/

        [Description("Finds the class, struct, interface or enum with the given name in the parsed file, preferring the one in the given namespace and noting when it falls "
            + "back to another namespace. Locates the type that the patch changes.")]
        private BaseTypeDeclarationSyntax FindType(string name, string ns)
        {
            List<BaseTypeDeclarationSyntax> candidates = m_Root.DescendantNodes().OfType<BaseTypeDeclarationSyntax>().Where(t => t.Identifier.ValueText == name).ToList();
            BaseTypeDeclarationSyntax match = candidates.FirstOrDefault(t => NamespaceOf(t) == ns);
            if (match == null && candidates.Count > 0)
            {
                match = candidates[0];
                m_Notes.Add($"the file declares {name} in namespace {NamespaceOf(match)}, the Python class says {ns}; the existing one is kept");
            }

            return match;
        }

        /***************************************************/

        [Description("Returns the dotted namespace that encloses a syntax node, from the outermost namespace to the innermost. Used by FindType to match the Python class's namespace.")]
        private static string NamespaceOf(SyntaxNode node)
        {
            return string.Join(".", node.Ancestors().OfType<BaseNamespaceDeclarationSyntax>().Reverse().Select(n => n.Name.ToString()));
        }

        /***************************************************/

        [Description("Lists the property declarations of a class, struct or interface, or an empty list for an enum. Used to look up, anchor and add properties.")]
        private static List<PropertyDeclarationSyntax> Properties(BaseTypeDeclarationSyntax type)
        {
            if (type is TypeDeclarationSyntax declaration)
                return declaration.Members.OfType<PropertyDeclarationSyntax>().ToList();

            return new List<PropertyDeclarationSyntax>();
        }

        /***************************************************/

        [Description("Finds the property or enum member with the given name in a type, returning the type itself for an empty name (a change to the type). Notes that the "
            + "member was not found, so that change is left for the developer to make by hand.")]
        private MemberDeclarationSyntax FindMember(BaseTypeDeclarationSyntax type, string name, string purpose)
        {
            if (string.IsNullOrEmpty(name))
                return type;

            MemberDeclarationSyntax member = Properties(type).FirstOrDefault(p => p.Identifier.ValueText == name);
            if (member == null && type is EnumDeclarationSyntax enumeration)
                member = enumeration.Members.FirstOrDefault(m => m.Identifier.ValueText == name);

            if (member == null)
                m_Notes.Add($"{name} was not found in {type.Identifier.ValueText}, so its {purpose} was not changed; change it by hand");

            return member;
        }

        /***************************************************/

        [Description("Lists the attributes with a given name on a member, ignoring the Attribute suffix. Used by the description and attribute changes to find what to replace or remove.")]
        private static IEnumerable<AttributeSyntax> FindAttributes(SyntaxList<AttributeListSyntax> lists, string name)
        {
            string wanted = StripAttributeSuffix(name);
            return lists.SelectMany(l => l.Attributes).Where(a => AttributeName(a) == wanted).ToList();
        }

        /***************************************************/

        [Description("Returns the plain name of an attribute without namespace qualifier or Attribute suffix. Lets FindAttributes match names however the existing file writes them.")]
        private static string AttributeName(AttributeSyntax attribute)
        {
            NameSyntax name = attribute.Name;
            if (name is QualifiedNameSyntax qualified)
                name = qualified.Right;

            if (name is AliasQualifiedNameSyntax alias)
                name = alias.Name;

            return StripAttributeSuffix(((SimpleNameSyntax)name).Identifier.ValueText);
        }

        /***************************************************/

        [Description("Removes a trailing Attribute from an attribute name so Description and DescriptionAttribute compare equal.")]
        private static string StripAttributeSuffix(string name)
        {
            return name.EndsWith("Attribute") && name.Length > "Attribute".Length ? name.Substring(0, name.Length - "Attribute".Length) : name;
        }

        /***************************************************/
        /**** Properties                                ****/
        /***************************************************/

        [Description("Inserts the properties of the addProperty changes into a type as new lines, after the property named in the change or first when none is named, using "
            + "the type's indentation and line breaks. Notes properties that already exist, types that cannot hold properties and get-only types, so only the new "
            + "lines are added to the file.")]
        private void AddProperties(BaseTypeDeclarationSyntax type, List<Change> changes)
        {
            if (changes.Count == 0)
                return;

            if (type is not TypeDeclarationSyntax declaration)
            {
                m_Notes.Add($"{type.Identifier.ValueText} cannot have properties; add {string.Join(", ", changes.Select(c => c.Name))} by hand");
                return;
            }

            List<PropertyDeclarationSyntax> properties = Properties(type);
            string indent = MemberIndent(type);
            bool readOnly = declaration is not InterfaceDeclarationSyntax && properties.Count > 0 && properties.All(IsGetOnly);

            foreach (Change change in changes)
            {
                if (properties.Any(p => p.Identifier.ValueText == change.Name))
                {
                    m_Notes.Add($"{change.Name} is already declared in {declaration.Identifier.ValueText}; it was not added again");
                    continue;
                }

                List<string> lines = change.Add.Select(a => $"[{a}]").ToList();
                lines.Add(PropertyLine(declaration, change, readOnly));
                if (readOnly)
                    m_Notes.Add($"{change.Name} was added as a get-only property because the other properties of {declaration.Identifier.ValueText} are; add it to the constructor by hand");

                PropertyDeclarationSyntax anchor = null;
                if (!string.IsNullOrEmpty(change.After))
                {
                    anchor = properties.FirstOrDefault(p => p.Identifier.ValueText == change.After);
                    if (anchor == null)
                    {
                        m_Notes.Add($"{change.After} was not found, so {change.Name} was added after the last property");
                        anchor = properties.LastOrDefault();
                    }
                }

                string block = Lines(indent, lines);
                if (anchor != null)
                    m_Edits.Insert(NextLineStart(anchor.Span.End), m_NewLine + block);
                else if (declaration.Members.Count > 0)
                    m_Edits.Insert(LineStart(StartWithComments(properties.Count > 0 ? properties[0] : declaration.Members[0])), block + m_NewLine);
                else
                    m_Edits.Insert(NextLineStart(declaration.OpenBraceToken.Span.End), block);
            }
        }

        /***************************************************/

        [Description("Builds the C# text of one new property (accessors, virtual modifier and initialiser) for a class, struct or interface. Used by AddProperties.")]
        private static string PropertyLine(TypeDeclarationSyntax declaration, Change change, bool readOnly)
        {
            string name = Identifier(change.Name);
            if (declaration is InterfaceDeclarationSyntax)
                return $"{change.Type} {name} {{ get; set; }}";

            string modifier = declaration is StructDeclarationSyntax ? "" : "virtual ";
            string accessors = readOnly ? "{ get; }" : "{ get; set; }";
            string initialiser = string.IsNullOrEmpty(change.Initialiser) ? "" : $" = {change.Initialiser};";
            return $"public {modifier}{change.Type} {name} {accessors}{initialiser}";
        }

        /***************************************************/

        [Description("Tells whether a property has accessors but no setter or init accessor. AddProperties uses it to add new properties as get-only when all existing ones are.")]
        private static bool IsGetOnly(PropertyDeclarationSyntax property)
        {
            return property.AccessorList != null && !property.AccessorList.Accessors.Any(a => a.IsKind(SyntaxKind.SetAccessorDeclaration) || a.IsKind(SyntaxKind.InitAccessorDeclaration));
        }

        /***************************************************/

        [Description("Removes the property named in a removeProperty change together with its attributes and comments. Applies a property deletion of the Python class to the existing C# file.")]
        private void RemoveProperty(BaseTypeDeclarationSyntax type, Change change)
        {
            MemberDeclarationSyntax property = FindMember(type, change.Name, "removal");
            if (property != null)
                RemoveMemberLines(property);
        }

        /***************************************************/

        [Description("Replaces the type of the named property with the type of a setPropertyType change, unless it is already the same ignoring spaces. Applies a changed "
            + "property type of the Python class and leaves the rest of the declaration untouched.")]
        private void SetPropertyType(BaseTypeDeclarationSyntax type, Change change)
        {
            if (FindMember(type, change.Name, "type") is not PropertyDeclarationSyntax property)
                return;

            if (Normalise(property.Type.ToString()) != Normalise(change.Type))
                m_Edits.Replace(property.Type.Span.Start, property.Type.Span.End, change.Type);
        }

        /***************************************************/

        [Description("Replaces, adds or removes the initialiser (default value) of the named property for a setPropertyInitialiser change, doing nothing when the value is "
            + "already equivalent. Properties with an expression body are noted and left for the developer to change.")]
        private void SetPropertyInitialiser(BaseTypeDeclarationSyntax type, Change change)
        {
            if (FindMember(type, change.Name, "default") is not PropertyDeclarationSyntax property)
                return;

            if (property.AccessorList == null)
            {
                m_Notes.Add($"{change.Name} has an expression body, so its default was not changed; change it by hand");
                return;
            }

            string wanted = string.IsNullOrEmpty(change.Initialiser) ? null : change.Initialiser;
            if (SameValue(property.Initializer?.Value.ToString(), wanted))
                return;

            int start = property.AccessorList.Span.End;
            if (property.Initializer != null)
                m_Edits.Replace(start, property.SemicolonToken.Span.End, wanted == null ? "" : $" = {wanted};");
            else
                m_Edits.Insert(start, $" = {wanted};");
        }

        /***************************************************/
        /**** Attributes                                ****/
        /***************************************************/

        [Description("Replaces, adds or removes the Description attribute of the named member (or of the type) for a setDescription change. Applies a changed docstring of "
            + "the Python class while leaving other attributes in place.")]
        private void SetDescription(BaseTypeDeclarationSyntax type, Change change)
        {
            MemberDeclarationSyntax member = FindMember(type, change.Name, "description");
            if (member == null)
                return;

            AttributeSyntax existing = FindAttributes(member.AttributeLists, "Description").FirstOrDefault();
            string wanted = string.IsNullOrEmpty(change.Description) ? null : $"Description({change.Description})";
            if (existing != null && wanted == null)
                RemoveAttribute(existing);
            else if (existing != null)
                m_Edits.Replace(existing.Span.Start, existing.Span.End, wanted);
            else if (wanted != null)
                m_Edits.Insert(LineStart(member.SpanStart), IndentAt(member.SpanStart) + $"[{wanted}]" + m_NewLine);
        }

        /***************************************************/

        [Description("Removes the attributes listed in a setAttributes change from a member and inserts the new ones on lines above it. Applies attribute changes such as "
            + "quantity or unit attributes from the Python class.")]
        private void SetAttributes(BaseTypeDeclarationSyntax type, Change change)
        {
            MemberDeclarationSyntax member = FindMember(type, change.Name, "attributes");
            if (member == null)
                return;

            foreach (string name in change.Remove)
            {
                List<AttributeSyntax> found = FindAttributes(member.AttributeLists, name).ToList();
                if (found.Count == 0)
                    m_Notes.Add($"attribute {name} was not found on {change.Name}; nothing was removed");

                foreach (AttributeSyntax attribute in found)
                    RemoveAttribute(attribute);
            }

            if (change.Add.Count == 0)
                return;

            int position = LineStart(member.SpanStart);
            if (member.AttributeLists.Count > 0)
            {
                AttributeListSyntax last = member.AttributeLists.Last();
                SyntaxToken next = last.GetLastToken().GetNextToken();
                if (LineNumber(next.SpanStart) != LineNumber(last.Span.End))
                    position = NextLineStart(last.Span.End);
            }

            m_Edits.Insert(position, Lines(IndentAt(member.SpanStart), change.Add.Select(a => $"[{a}]")));
        }

        /***************************************************/

        [Description("Removes one attribute from a member, together with its whole list or line when nothing else is in it. Used by the description and attribute changes.")]
        private void RemoveAttribute(AttributeSyntax attribute)
        {
            AttributeListSyntax list = (AttributeListSyntax)attribute.Parent;
            if (list.Attributes.Count > 1)
            {
                int index = list.Attributes.IndexOf(attribute);
                if (index > 0)
                    m_Edits.Remove(list.Attributes[index - 1].Span.End, attribute.Span.End);
                else
                    m_Edits.Remove(attribute.Span.Start, list.Attributes[1].Span.Start);

                return;
            }

            TextLine first = m_Text.Lines.GetLineFromPosition(list.SpanStart);
            TextLine last = m_Text.Lines.GetLineFromPosition(list.Span.End);
            bool aloneOnItsLines = string.IsNullOrWhiteSpace(m_Text.ToString(TextSpan.FromBounds(first.Start, list.SpanStart)))
                && string.IsNullOrWhiteSpace(m_Text.ToString(TextSpan.FromBounds(list.Span.End, last.End)));

            if (aloneOnItsLines)
            {
                m_Edits.Remove(first.Start, last.EndIncludingLineBreak);
                return;
            }

            int end = list.Span.End;
            while (end < m_Source.Length && m_Source[end] == ' ')
                end++;

            m_Edits.Remove(list.SpanStart, end);
        }

        /***************************************************/
        /**** Bases                                     ****/
        /***************************************************/

        [Description("Removes and adds base types and interfaces in the base list of a class or struct for a setBases change, keeping the bases that stay. Notes bases that "
            + "were not written in the file, and writes nothing when the list is unchanged.")]
        private void SetBases(BaseTypeDeclarationSyntax type, Change change)
        {
            if (type is not TypeDeclarationSyntax declaration)
            {
                m_Notes.Add($"the bases of {type.Identifier.ValueText} cannot be changed; change them by hand");
                return;
            }

            List<BaseTypeSyntax> existing = declaration.BaseList?.Types.ToList() ?? new List<BaseTypeSyntax>();
            List<string> kept = new List<string>();
            bool changed = false;
            foreach (BaseTypeSyntax baseType in existing)
            {
                if (change.Remove.Any(r => SameType(baseType.Type.ToString(), r)))
                    changed = true;
                else
                    kept.Add(baseType.ToString());
            }

            foreach (string removed in change.Remove.Where(r => !existing.Any(b => SameType(b.Type.ToString(), r))))
                m_Notes.Add($"{removed} is not written as a base of {declaration.Identifier.ValueText} (it may come through another base); nothing was removed");

            foreach (string added in change.Add.Where(a => !kept.Any(k => SameType(k, a))))
            {
                kept.Add(added);
                changed = true;
            }

            if (!changed)
                return;

            int nameEnd = declaration.TypeParameterList?.Span.End ?? declaration.Identifier.Span.End;
            if (declaration.BaseList == null)
                m_Edits.Insert(nameEnd, " : " + string.Join(", ", kept));
            else if (kept.Count == 0)
                m_Edits.Remove(nameEnd, declaration.BaseList.Span.End);
            else
                m_Edits.Replace(existing[0].SpanStart, existing.Last().Span.End, string.Join(", ", kept));
        }

        /***************************************************/
        /**** Enum members                              ****/
        /***************************************************/

        [Description("Inserts the members of the addEnumMember changes into an enum as new lines, with explicit values and descriptions where needed. Without explicit "
            + "values new members only go at the end so the existing values do not shift, and each decision that differs from the request is noted.")]
        private void AddEnumMembers(BaseTypeDeclarationSyntax type, List<Change> changes)
        {
            if (changes.Count == 0)
                return;

            if (type is not EnumDeclarationSyntax enumeration)
            {
                m_Notes.Add($"{type.Identifier.ValueText} is not an enum; add {string.Join(", ", changes.Select(c => c.Name))} by hand");
                return;
            }

            SeparatedSyntaxList<EnumMemberDeclarationSyntax> members = enumeration.Members;
            bool explicitValues = members.Any(m => m.EqualsValue != null);
            bool trailingComma = members.Count > 0 && members.SeparatorCount == members.Count;
            SortedDictionary<int, List<Change>> groups = new SortedDictionary<int, List<Change>>();

            foreach (Change change in changes)
            {
                if (members.Any(m => m.Identifier.ValueText == change.Name))
                {
                    m_Notes.Add($"{change.Name} is already a member of {enumeration.Identifier.ValueText}; it was not added again");
                    continue;
                }

                //Without explicit values the members after a new one would change value, so new members only go at the end
                int index = members.Count - 1;
                if (explicitValues)
                {
                    index = string.IsNullOrEmpty(change.After) ? -1 : IndexOf(members, change.After);
                    if (index < 0 && !string.IsNullOrEmpty(change.After))
                    {
                        m_Notes.Add($"{change.After} was not found, so {change.Name} was added at the end");
                        index = members.Count - 1;
                    }
                }
                else if (change.After != members.LastOrDefault()?.Identifier.ValueText)
                {
                    m_Notes.Add($"{change.Name} was added at the end of {enumeration.Identifier.ValueText} so the other members keep their values");
                }

                if (!groups.ContainsKey(index))
                    groups[index] = new List<Change>();

                groups[index].Add(change);
            }

            string indent = MemberIndent(enumeration);
            int implicitNext = members.Count;
            foreach (KeyValuePair<int, List<Change>> group in groups)
            {
                bool atEnd = group.Key == members.Count - 1;
                List<string> lines = new List<string>();
                for (int i = 0; i < group.Value.Count; i++)
                {
                    Change change = group.Value[i];
                    if (!string.IsNullOrEmpty(change.Description))
                        lines.Add($"[Description({change.Description})]");

                    string value = "";
                    if (!string.IsNullOrEmpty(change.Value) && (explicitValues || change.Value != implicitNext.ToString(CultureInfo.InvariantCulture)))
                        value = " = " + change.Value;

                    implicitNext = int.TryParse(change.Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int number) ? number + 1 : implicitNext + 1;
                    bool comma = !atEnd || i < group.Value.Count - 1 || trailingComma;
                    lines.Add(Identifier(change.Name) + value + (comma ? "," : ""));
                }

                string block = Lines(indent, lines);
                if (members.Count == 0)
                {
                    m_Edits.Insert(NextLineStart(enumeration.OpenBraceToken.Span.End), block);
                }
                else if (group.Key < 0)
                {
                    m_Edits.Insert(LineStart(StartWithComments(members[0])), block);
                }
                else if (group.Key < members.SeparatorCount)
                {
                    m_Edits.Insert(NextLineStart(members.GetSeparator(group.Key).Span.End), block);
                }
                else
                {
                    m_Edits.Insert(members[group.Key].Span.End, ",");
                    m_Edits.Insert(NextLineStart(members[group.Key].Span.End), block);
                }
            }
        }

        /***************************************************/

        [Description("Removes the named enum member together with its comments for a removeEnumMember change. Refuses members that share a line with others and notes when "
            + "the values of later members shift.")]
        private void RemoveEnumMember(BaseTypeDeclarationSyntax type, Change change)
        {
            if (FindMember(type, change.Name, "removal") is not EnumMemberDeclarationSyntax member)
                return;

            SeparatedSyntaxList<EnumMemberDeclarationSyntax> members = ((EnumDeclarationSyntax)type).Members;
            int index = members.IndexOf(member);
            bool sharesItsLine = members.Any(m => m != member && LineNumber(m.SpanStart) == LineNumber(member.SpanStart));
            if (sharesItsLine)
            {
                m_Notes.Add($"{change.Name} shares its line with other members, so it was not removed; remove it by hand");
                return;
            }

            int start = LineStart(StartWithComments(member));
            int end = index < members.SeparatorCount ? NextLineStart(members.GetSeparator(index).Span.End) : NextLineStart(member.Span.End);
            m_Edits.Remove(start, end);

            if (!members.Any(m => m.EqualsValue != null) && index < members.Count - 1)
                m_Notes.Add($"the members after {change.Name} change value now that it is removed; give them explicit values if their numbers matter");
        }

        /***************************************************/

        [Description("Replaces or adds the explicit value of the named enum member for a setEnumValue change. Applies a changed enum value of the Python class.")]
        private void SetEnumValue(BaseTypeDeclarationSyntax type, Change change)
        {
            if (FindMember(type, change.Name, "value") is not EnumMemberDeclarationSyntax member)
                return;

            if (member.EqualsValue != null)
                m_Edits.Replace(member.EqualsValue.Value.Span.Start, member.EqualsValue.Value.Span.End, change.Value);
            else
                m_Edits.Insert(member.Identifier.Span.End, " = " + change.Value);
        }

        /***************************************************/

        [Description("Returns the position of the enum member with the given name, or -1. Used by AddEnumMembers to place new members after a named member.")]
        private static int IndexOf(SeparatedSyntaxList<EnumMemberDeclarationSyntax> members, string name)
        {
            for (int i = 0; i < members.Count; i++)
            {
                if (members[i].Identifier.ValueText == name)
                    return i;
            }

            return -1;
        }

        /***************************************************/
        /**** Usings                                    ****/
        /***************************************************/

        [Description("Adds the using directives the job needs that the file does not already have, after the last existing using or above the first member. Apply calls it "
            + "only when some edit was made, so untouched files stay as they are.")]
        private void AddUsings(List<string> usings)
        {
            HashSet<string> existing = m_Root.Usings
                .Concat(m_Root.DescendantNodes().OfType<BaseNamespaceDeclarationSyntax>().SelectMany(n => n.Usings))
                .Select(u => u.Name?.ToString())
                .ToHashSet();

            List<string> missing = usings.Where(u => !existing.Contains(u)).Distinct().ToList();
            if (missing.Count == 0)
                return;

            string text = string.Concat(missing.Select(u => $"using {u};{m_NewLine}"));
            if (m_Root.Usings.Count > 0)
                m_Edits.Insert(NextLineStart(m_Root.Usings.Last().Span.End), text);
            else if (m_Root.Members.Count > 0)
                m_Edits.Insert(LineStart(m_Root.Members[0].SpanStart), text + m_NewLine);
            else
                m_Edits.Insert(0, text);
        }

        /***************************************************/
        /**** Text helpers                              ****/
        /***************************************************/

        [Description("Removes the lines of a member with the comments directly above it, plus one neighbouring blank line so the spacing of the other members stays the "
            + "same. Used when a property is removed.")]
        private void RemoveMemberLines(SyntaxNode node)
        {
            int start = LineStart(StartWithComments(node));
            int startLine = LineNumber(start);
            TextLine last = m_Text.Lines.GetLineFromPosition(node.Span.End);
            int end = last.EndIncludingLineBreak;

            if (IsBlank(last.LineNumber + 1))
                end = m_Text.Lines[last.LineNumber + 1].EndIncludingLineBreak;
            else if (startLine > 0 && IsBlank(startLine - 1) && !m_Removed.Any(s => s.Contains(m_Text.Lines[startLine - 1].Start)))
                start = m_Text.Lines[startLine - 1].Start;

            m_Removed.Add(TextSpan.FromBounds(start, end));
            m_Edits.Remove(start, end);
        }

        /***************************************************/

        [Description("Returns the position where a member's directly preceding comments start, so edits that remove or insert before a member keep its comments with it.")]
        private static int StartWithComments(SyntaxNode node)
        {
            int start = node.SpanStart;
            int lineBreaks = 0;
            foreach (SyntaxTrivia trivia in node.GetLeadingTrivia().Reverse())
            {
                if (trivia.IsKind(SyntaxKind.EndOfLineTrivia))
                {
                    lineBreaks++;
                    if (lineBreaks > 1)
                        break;
                }
                else if (trivia.IsKind(SyntaxKind.SingleLineCommentTrivia) || trivia.IsKind(SyntaxKind.MultiLineCommentTrivia)
                    || trivia.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) || trivia.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia))
                {
                    start = trivia.SpanStart;
                    //A documentation comment includes its own line break
                    lineBreaks = trivia.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) ? 1 : 0;
                }
                else if (!trivia.IsKind(SyntaxKind.WhitespaceTrivia))
                {
                    break;
                }
            }

            return start;
        }

        /***************************************************/

        [Description("Returns the indentation used by the existing members of a type, or one level deeper than the type when it is empty. New properties and enum members are written with it.")]
        private string MemberIndent(BaseTypeDeclarationSyntax type)
        {
            SyntaxNode first = null;
            if (type is TypeDeclarationSyntax declaration && declaration.Members.Count > 0)
                first = declaration.Members[0];
            else if (type is EnumDeclarationSyntax enumeration && enumeration.Members.Count > 0)
                first = enumeration.Members[0];

            return first != null ? IndentAt(first.SpanStart) : IndentAt(type.SpanStart) + "    ";
        }

        /***************************************************/

        [Description("Joins lines of text into a block that is indented and ends each line with the file's own line break. Builds the text of inserted members.")]
        private string Lines(string indent, IEnumerable<string> lines)
        {
            return string.Concat(lines.Select(l => indent + l + m_NewLine));
        }

        /***************************************************/

        [Description("Returns the line number of a position in the original text. Used to tell whether two nodes share a line.")]
        private int LineNumber(int position)
        {
            return m_Text.Lines.GetLineFromPosition(position).LineNumber;
        }

        /***************************************************/

        [Description("Returns the position where the line of a given position starts in the original text. Used to insert whole lines.")]
        private int LineStart(int position)
        {
            return m_Text.Lines.GetLineFromPosition(position).Start;
        }

        /***************************************************/

        [Description("Returns the position just after the line break of the line holding a given position. Used to insert or remove after a whole line.")]
        private int NextLineStart(int position)
        {
            return m_Text.Lines.GetLineFromPosition(position).EndIncludingLineBreak;
        }

        /***************************************************/

        [Description("Returns the leading whitespace of the line at a position. Used to indent inserted attribute lines like the member they belong to.")]
        private string IndentAt(int position)
        {
            string line = m_Text.Lines.GetLineFromPosition(position).ToString();
            return line.Substring(0, line.Length - line.TrimStart().Length);
        }

        /***************************************************/

        [Description("Tells whether a line of the original text exists and is empty or whitespace. RemoveMemberLines uses it to decide which blank line goes with a removed member.")]
        private bool IsBlank(int lineNumber)
        {
            return lineNumber < m_Text.Lines.Count && string.IsNullOrWhiteSpace(m_Text.Lines[lineNumber].ToString());
        }

        /***************************************************/

        [Description("Returns a name as a valid C# identifier, adding @ when it is a keyword. Applied to names of new properties and enum members.")]
        private static string Identifier(string name)
        {
            return SyntaxFacts.GetKeywordKind(name) != SyntaxKind.None ? "@" + name : name;
        }

        /***************************************************/

        [Description("Removes all whitespace from a text so that C# types and values can be compared regardless of formatting.")]
        private static string Normalise(string text)
        {
            return new string((text ?? "").Where(c => !char.IsWhiteSpace(c)).ToArray());
        }

        /***************************************************/

        [Description("Tells whether two initialisers mean the same value, for example 0 and 0.0, or null and no initialiser. SetPropertyInitialiser uses it to avoid "
            + "rewriting a default that has not really changed.")]
        private static bool SameValue(string current, string wanted)
        {
            current = current == "null" ? null : current;
            wanted = wanted == "null" ? null : wanted;
            if (current == null || wanted == null)
                return current == wanted;

            if (Normalise(current) == Normalise(wanted))
                return true;

            return double.TryParse(current.TrimEnd('f', 'F', 'd', 'D', 'm', 'M'), NumberStyles.Float, CultureInfo.InvariantCulture, out double a)
                && double.TryParse(wanted.TrimEnd('f', 'F', 'd', 'D', 'm', 'M'), NumberStyles.Float, CultureInfo.InvariantCulture, out double b)
                && a == b;
        }

        /***************************************************/

        [Description("Tells whether two base types are the same, comparing the simple name when one is written with its namespace. SetBases uses it to match bases from "
            + "Python with those in the file.")]
        private static bool SameType(string a, string b)
        {
            return Normalise(a) == Normalise(b) || SimpleName(a) == SimpleName(b);
        }

        /***************************************************/

        [Description("Returns a type name without its namespace but keeping generic arguments. Used by SameType.")]
        private static string SimpleName(string text)
        {
            string name = Normalise(text);
            int generic = name.IndexOf('<');
            string head = generic < 0 ? name : name.Substring(0, generic);
            string arguments = generic < 0 ? "" : name.Substring(generic);
            return head.Substring(head.LastIndexOf('.') + 1) + arguments;
        }

        /***************************************************/
    }
}
