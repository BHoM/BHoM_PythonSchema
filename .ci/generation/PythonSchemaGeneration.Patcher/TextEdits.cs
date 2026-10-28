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

        [Description("Replaces the text between start and end. Several inserts at one position are kept in the order they were added.")]
        public void Replace(int start, int end, string text)
        {
            m_Edits.Add(new Edit { Start = start, End = end, Text = text, Order = m_Edits.Count });
        }

        /***************************************************/

        public void Insert(int position, string text)
        {
            Replace(position, position, text);
        }

        /***************************************************/

        public void Remove(int start, int end)
        {
            Replace(start, end, "");
        }

        /***************************************************/

        [Description("The source with every edit applied. Overlapping edits are an error rather than a guess.")]
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
