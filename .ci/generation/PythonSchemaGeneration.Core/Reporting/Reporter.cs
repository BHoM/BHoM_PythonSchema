namespace PythonSchemaGeneration.Reporting
{
    public class Reporter
    {
        public List<string> Warnings { get; } = new List<string>();
        public List<string> Infos { get; } = new List<string>();

        public void Warn(string message) { Warnings.Add(message); }
        public void Warn(string context, string message) { Warnings.Add($"[{context}] {message}"); }
        public void Info(string message) { Infos.Add(message); }
    }
}
