using System.ComponentModel;

namespace PythonSchemaGeneration.Reporting
{
    public class Reporter
    {
        public List<string> Warnings { get; } = new List<string>();
        public List<string> Infos { get; } = new List<string>();

        /***************************************************/

        [Description("Records a warning message without a context. The generator stages use it for problems that concern the whole run, and the WarningBaseline later compares the kinds of the warnings with the committed list.")]
        public void Warn(string message) { Warnings.Add(message); }

        /***************************************************/

        [Description("Records a warning message prefixed with the context, usually the type or member it concerns, in square brackets. The extraction and mapping stages use it for every conversion problem, and it ends up in the report and the warning baseline check.")]
        public void Warn(string context, string message) { Warnings.Add($"[{context}] {message}"); }

        /***************************************************/

        [Description("Records an informational message, for example that an assembly was loaded or skipped. The messages are listed in the generation report.")]
        public void Info(string message) { Infos.Add(message); }

        /***************************************************/
    }
}
