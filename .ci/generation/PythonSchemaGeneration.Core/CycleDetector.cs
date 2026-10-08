namespace PythonSchemaGeneration
{
    //Finds groups of types that reference each other (strongly connected components)
    public static class CycleDetector
    {
        /***************************************************/

        //Returns a predicate telling whether two types are part of the same reference cycle
        public static Func<Type, Type, bool> DetectFunction(Dictionary<Type, IEnumerable<Type>> references)
        {
            int counter = 0;
            int components = 0;
            Stack<Type> stack = new Stack<Type>();
            HashSet<Type> onStack = new HashSet<Type>();
            Dictionary<Type, int> low = new Dictionary<Type, int>();
            Dictionary<Type, int> index = new Dictionary<Type, int>();
            Dictionary<Type, int> component = new Dictionary<Type, int>();

            foreach (Type node in references.Keys.OrderBy(t => t.FullName, StringComparer.Ordinal))
            {
                if (!index.ContainsKey(node))
                    Visit(node, references, ref counter, ref components, stack, onStack, low, index, component);
            }

            Dictionary<int, int> sizes = component.GroupBy(kv => kv.Value).ToDictionary(g => g.Key, g => g.Count());
            return (a, b) => component.TryGetValue(a, out int ca) && component.TryGetValue(b, out int cb) && ca == cb && sizes[ca] > 1;
        }

        /***************************************************/

        private static void Visit(Type node, Dictionary<Type, IEnumerable<Type>> references, ref int counter, ref int components, Stack<Type> stack, HashSet<Type> onStack, Dictionary<Type, int> low, Dictionary<Type, int> index, Dictionary<Type, int> component)
        {
            index[node] = low[node] = counter++;
            stack.Push(node);
            onStack.Add(node);

            if (references.TryGetValue(node, out IEnumerable<Type> targets))
            {
                foreach (Type target in targets.Where(t => t != node && references.ContainsKey(t)))
                {
                    if (!index.ContainsKey(target))
                    {
                        Visit(target, references, ref counter, ref components, stack, onStack, low, index, component);
                        low[node] = Math.Min(low[node], low[target]);
                    }
                    else if (onStack.Contains(target))
                        low[node] = Math.Min(low[node], index[target]);
                }
            }

            if (low[node] == index[node])
            {
                Type member;
                do
                {
                    member = stack.Pop();
                    onStack.Remove(member);
                    component[member] = components;
                } while (member != node);
                components++;
            }
        }

        /***************************************************/
    }
}
