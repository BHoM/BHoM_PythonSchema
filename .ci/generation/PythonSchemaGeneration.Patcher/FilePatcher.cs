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

        private FilePatcher(string source)
        {
            m_Source = source;
            m_Text = SourceText.From(source);
            m_Root = CSharpSyntaxTree.ParseText(m_Text).GetCompilationUnitRoot();
            m_NewLine = source.Contains("\r\n") ? "\r\n" : "\n";
        }

        /***************************************************/

        [Description("Applies the changes of a job to the source of one file. Changes that cannot be made are listed in the notes.")]
        public static PatchResult Patch(string source, FileJob job)
        {
            return new FilePatcher(source).Apply(job);
        }

        /***************************************************/

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

        private static string NamespaceOf(SyntaxNode node)
        {
            return string.Join(".", node.Ancestors().OfType<BaseNamespaceDeclarationSyntax>().Reverse().Select(n => n.Name.ToString()));
        }

        /***************************************************/

        private static List<PropertyDeclarationSyntax> Properties(BaseTypeDeclarationSyntax type)
        {
            if (type is TypeDeclarationSyntax declaration)
                return declaration.Members.OfType<PropertyDeclarationSyntax>().ToList();

            return new List<PropertyDeclarationSyntax>();
        }

        /***************************************************/

        [Description("The property or enum member with that name, or the type itself for an empty name. A missing member is noted.")]
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

        private static IEnumerable<AttributeSyntax> FindAttributes(SyntaxList<AttributeListSyntax> lists, string name)
        {
            string wanted = StripAttributeSuffix(name);
            return lists.SelectMany(l => l.Attributes).Where(a => AttributeName(a) == wanted).ToList();
        }

        /***************************************************/

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

        private static string StripAttributeSuffix(string name)
        {
            return name.EndsWith("Attribute") && name.Length > "Attribute".Length ? name.Substring(0, name.Length - "Attribute".Length) : name;
        }

        /***************************************************/
        /**** Properties                                ****/
        /***************************************************/

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

        private static bool IsGetOnly(PropertyDeclarationSyntax property)
        {
            return property.AccessorList != null && !property.AccessorList.Accessors.Any(a => a.IsKind(SyntaxKind.SetAccessorDeclaration) || a.IsKind(SyntaxKind.InitAccessorDeclaration));
        }

        /***************************************************/

        private void RemoveProperty(BaseTypeDeclarationSyntax type, Change change)
        {
            MemberDeclarationSyntax property = FindMember(type, change.Name, "removal");
            if (property != null)
                RemoveMemberLines(property);
        }

        /***************************************************/

        private void SetPropertyType(BaseTypeDeclarationSyntax type, Change change)
        {
            if (FindMember(type, change.Name, "type") is not PropertyDeclarationSyntax property)
                return;

            if (Normalise(property.Type.ToString()) != Normalise(change.Type))
                m_Edits.Replace(property.Type.Span.Start, property.Type.Span.End, change.Type);
        }

        /***************************************************/

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

        [Description("Removes one attribute, and its whole list or line when nothing else is in it.")]
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

        [Description("Removes the lines of a member and its comments, with one blank line next to it so the spacing between the others stays the same.")]
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

        [Description("Where a member starts, including the comments written directly above it (with no blank line between).")]
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

        private string Lines(string indent, IEnumerable<string> lines)
        {
            return string.Concat(lines.Select(l => indent + l + m_NewLine));
        }

        /***************************************************/

        private int LineNumber(int position)
        {
            return m_Text.Lines.GetLineFromPosition(position).LineNumber;
        }

        /***************************************************/

        private int LineStart(int position)
        {
            return m_Text.Lines.GetLineFromPosition(position).Start;
        }

        /***************************************************/

        private int NextLineStart(int position)
        {
            return m_Text.Lines.GetLineFromPosition(position).EndIncludingLineBreak;
        }

        /***************************************************/

        private string IndentAt(int position)
        {
            string line = m_Text.Lines.GetLineFromPosition(position).ToString();
            return line.Substring(0, line.Length - line.TrimStart().Length);
        }

        /***************************************************/

        private bool IsBlank(int lineNumber)
        {
            return lineNumber < m_Text.Lines.Count && string.IsNullOrWhiteSpace(m_Text.Lines[lineNumber].ToString());
        }

        /***************************************************/

        private static string Identifier(string name)
        {
            return SyntaxFacts.GetKeywordKind(name) != SyntaxKind.None ? "@" + name : name;
        }

        /***************************************************/

        private static string Normalise(string text)
        {
            return new string((text ?? "").Where(c => !char.IsWhiteSpace(c)).ToArray());
        }

        /***************************************************/

        [Description("True when two initialisers mean the same value, for example 0 and 0.0, or null and no initialiser.")]
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

        [Description("True when two base types are the same, comparing the simple name when one of them is written with its namespace.")]
        private static bool SameType(string a, string b)
        {
            return Normalise(a) == Normalise(b) || SimpleName(a) == SimpleName(b);
        }

        /***************************************************/

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
