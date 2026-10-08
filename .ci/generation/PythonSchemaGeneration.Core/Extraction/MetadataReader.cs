using PythonSchemaGeneration.Model;
using System.Reflection;

namespace PythonSchemaGeneration.Extraction
{
    //Reads C# attributes by name so no reference to the assemblies defining them is needed
    public static class MetadataReader
    {
        /***************************************************/

        public static string Description(MemberInfo member)
        {
            string text = StringArgument(member, "System.ComponentModel.DescriptionAttribute");
            return string.IsNullOrWhiteSpace(text) ? null : text;
        }

        /***************************************************/

        public static string DisplayText(MemberInfo member)
        {
            return StringArgument(member, "DisplayTextAttribute");
        }

        /***************************************************/

        public static bool IsDynamic(MemberInfo member)
        {
            return member.CustomAttributes.Any(x => x.AttributeType.Name == "DynamicPropertyAttribute");
        }

        /***************************************************/

        public static QuantityModel Quantity(MemberInfo member)
        {
            foreach (object attribute in SafeAttributes(member))
            {
                Type attributeType = attribute.GetType();
                bool isQuantity = false;

                for (Type b = attributeType; b != null; b = b.BaseType)
                {
                    if (b.Name == "QuantityAttribute")
                    {
                        isQuantity = true;
                        break;
                    }
                }

                if (!isQuantity)
                    continue;

                string unit = attributeType.GetProperty("SIUnit")?.GetValue(attribute)?.ToString();

                string categoryName;
                if (attributeType.Name.EndsWith("Attribute"))
                {
                    categoryName = attributeType.Name.Substring(0, attributeType.Name.Length - 9);
                }
                else
                {
                    categoryName = attributeType.Name;
                }

                return new QuantityModel { Category = categoryName, Unit = unit };
            }

            return null;
        }

        /***************************************************/

        private static IEnumerable<object> SafeAttributes(MemberInfo member)
        {
            try { return member.GetCustomAttributes(false); }
            catch { return Array.Empty<object>(); }
        }

        /***************************************************/

        private static string StringArgument(MemberInfo member, string attributeName)
        {
            foreach (CustomAttributeData data in member.CustomAttributes)
            {
                Type t = data.AttributeType;
                if (t.FullName == attributeName || (!attributeName.Contains('.') && t.Name == attributeName))
                {
                    if (data.ConstructorArguments.Count > 0 && data.ConstructorArguments[0].Value is string text)
                        return text;
                }
            }

            return null;
        }

        /***************************************************/
    }
}
