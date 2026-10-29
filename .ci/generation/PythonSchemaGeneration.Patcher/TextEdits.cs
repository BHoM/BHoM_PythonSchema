using System.ComponentModel;
using System.Text;

namespace PythonSchemaGeneration.Patcher
{
    //Edits to a source text, applied together so every position refers to the original text
    public class TextEdits
    {
        /***************************************************/

        private class Edit
        {
            public int Start { get; set; }

            public int End { get; set; }

            public string Text { get; set; }

            public int Order { get; set; }
        }

        private readonly List<Edit> m_Edits = new List<Edit>();

        /***************************************************/

        public int Count { get { return m_Edits.Count; } }

        /***************************************************/

        [Description("Records the replacement of the text between start and end, to be applied later together with the other edits. The patcher collects every change this "
            + "way so all positions refer to the original text; inserts at one position keep the order they were added.")]
        public void Replace(int start, int end, string text)
        {
            m_Edits.Add(new Edit { Start = start, End = end, Text = text, Order = m_Edits.Count });
        }

        /***************************************************/

        [Description("Records an insertion of text at a position of the original source. Shorthand for an empty replacement, used by FilePatcher to add members, attributes and usings.")]
        public void Insert(int position, string text)
        {
            Replace(position, position, text);
        }

        /***************************************************/

        [Description("Records the removal of the text between start and end of the original source. Shorthand for replacing with nothing, used by FilePatcher to delete members and attributes.")]
        public void Remove(int start, int end)
        {
            Replace(start, end, "");
        }

        /***************************************************/

        [Description("Returns the source with all recorded edits applied in position order, leaving the text between them unchanged. Overlapping edits throw an error rather "
            + "than guessing, so py2cs reports the file for hand editing.")]
        public string Apply(string source)
        {
            StringBuilder result = new StringBuilder();
            int cursor = 0;
            foreach (Edit edit in m_Edits.OrderBy(e => e.Start).ThenBy(e => e.End == e.Start ? 0 : 1).ThenBy(e => e.Order))
            {
                if (edit.Start < cursor)
                    throw new InvalidOperationException($"two changes overlap at position {edit.Start}; apply them by hand");

                result.Append(source, cursor, edit.Start - cursor);
                result.Append(edit.Text);
                cursor = edit.End;
            }

            result.Append(source, cursor, source.Length - cursor);
            return result.ToString();
        }

        /***************************************************/
    }
}
