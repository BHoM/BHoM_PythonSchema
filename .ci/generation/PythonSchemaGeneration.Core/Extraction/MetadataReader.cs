using PythonSchemaGeneration.Model;
using System.ComponentModel;
using System.Reflection;

namespace PythonSchemaGeneration.Extraction
{
    //Reads C# attributes by name so no reference to the assemblies defining them is needed
    public static class MetadataReader
    {
        /***************************************************/

        [Description("Returns the text of the member's System.ComponentModel Description attribute, or null when it is missing or blank. The TypeExtractor uses it to carry " +
            "the C# descriptions of types, properties and enum members into the type model.")]
        public static string Description(MemberInfo member)
        {
            string text = StringArgument(member, "System.ComponentModel.DescriptionAttribute");
            return string.IsNullOrWhiteSpace(text) ? null : text;
        }

        /***************************************************/

        [Description("Returns the text of the member's DisplayText attribute, or null when it has none. The TypeExtractor stores it on the property model so the emitter " +
            "writes it as a DisplayText annotation.")]
        public static string DisplayText(MemberInfo member)
        {
            return StringArgument(member, "DisplayTextAttribute");
        }

        /***************************************************/

        [Description("Tells whether the member carries a DynamicProperty attribute, matched by name. The TypeExtractor records it on the property model for the emitter.")]
        public static bool IsDynamic(MemberInfo member)
        {
            return member.CustomAttributes.Any(x => x.AttributeType.Name == "DynamicPropertyAttribute");
        }

        /***************************************************/

        [Description("Finds the Quantity attribute (any attribute deriving from one named QuantityAttribute) on a member and returns its category, taken from the attribute " +
            "class name without the Attribute suffix, and its SI unit. Returns null when the member has no quantity; the emitter writes it as a Quantity " +
            "annotation.")]
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

        [Description("Returns the custom attribute instances of a member, or an empty sequence when they cannot be loaded. Used by Quantity so one unreadable attribute does " +
            "not stop the generator.")]
        private static IEnumerable<object> SafeAttributes(MemberInfo member)
        {
            try { return member.GetCustomAttributes(false); }
            catch { return Array.Empty<object>(); }
        }

        /***************************************************/

        [Description("Returns the first constructor argument, when it is a string, of the first attribute on the member whose full name (or plain name when none contains a " +
            "dot) equals the given name. Reads attribute data by name so the generator needs no reference to the assemblies that define the attributes; used by " +
            "Description and DisplayText.")]
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
