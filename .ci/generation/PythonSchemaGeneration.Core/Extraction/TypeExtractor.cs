using PythonSchemaGeneration.Loading;
using PythonSchemaGeneration.Mapping;
using PythonSchemaGeneration.Model;
using PythonSchemaGeneration.Reporting;
using System.Reflection;

namespace PythonSchemaGeneration.Extraction
{
    //Reflection to language-neutral type model
    public class TypeExtractor
    {
        /***************************************************/

        private readonly TypeRegistry m_Registry;
        private readonly Reporter m_Reporter;
        private readonly DefaultInstanceReader m_Defaults;

        /***************************************************/

        public TypeExtractor(TypeRegistry registry, Reporter reporter)
        {
            m_Registry = registry;
            m_Reporter = reporter;
            m_Defaults = new DefaultInstanceReader(registry, reporter);
        }

        /***************************************************/

        public TypeModel Extract(Type type)
        {
            Type def = TypeRegistry.Definition(type);
            TypeModel model = new TypeModel
            {
                Type = def,
                ClrName = def.FullName,
                CanonicalName = ClrNames.Format(def),
                Namespace = def.Namespace,
                Assembly = def.Assembly.GetName().Name,
                Repo = BHoMAdapter.AssemblyRepo(def.Assembly),
                Description = MetadataReader.Description(def),
                Kind = KindOf(def),
                IsFlags = def.IsEnum && def.IsDefined(typeof(FlagsAttribute), false),
            };

            if (model.Repo == null)
                m_Reporter.Warn(model.ClrName, "assembly has no github.com URL in its Description, repo is unknown");

            foreach (Type arg in def.GetGenericArguments())
            {
                GenericParamModel p = new GenericParamModel { Name = arg.Name };
                p.Constraints.AddRange(arg.GetGenericParameterConstraints().Where(c => c != typeof(ValueType) && c != typeof(object)));
                model.GenericParams.Add(p);
            }

            if (model.Kind == TypeKind.Enum)
                ExtractEnum(def, model);
            else
            {
                ExtractBases(def, model);
                ExtractProperties(def, model);
            }

            return model;
        }

        /***************************************************/

        private static TypeKind KindOf(Type type)
        {
            if (type.IsEnum) return TypeKind.Enum;
            if (type.IsInterface) return TypeKind.Interface;
            if (type.IsValueType) return TypeKind.Struct;
            if (type.IsAbstract) return TypeKind.AbstractClass;
            return TypeKind.Class;
        }

        /***************************************************/

        private void ExtractEnum(Type def, TypeModel model)
        {
            Type underlying = Enum.GetUnderlyingType(def);
            foreach (FieldInfo field in def.GetFields(BindingFlags.Public | BindingFlags.Static).OrderBy(f => f.MetadataToken))
            {
                object rawValue = field.GetRawConstantValue();
                model.EnumMembers.Add(new EnumMemberModel
                {
                    Name = field.Name,
                    Description = MetadataReader.Description(field),
                    Value = Convert.ToString(Convert.ChangeType(rawValue, underlying), System.Globalization.CultureInfo.InvariantCulture),
                });
            }
        }

        /***************************************************/

        private void ExtractBases(Type def, TypeModel model)
        {
            Type baseType = def.BaseType;
            if (baseType != null && !def.IsInterface)
            {
                if (m_Registry.Contains(baseType))
                    model.Bases.Add(baseType);
                else if (baseType != typeof(object) && baseType != typeof(ValueType))
                    m_Reporter.Warn(model.ClrName, $"base type {ClrNames.Format(baseType)} is not an oM type and was dropped");
            }

            //Reflection returns the flattened interface list. Keep only the ones not implied by the base class or by another interface.
            List<Type> allInterfaceTypes = def.GetInterfaces().Where(i => m_Registry.Contains(i)).ToList();
            HashSet<Type> implied = new HashSet<Type>();

            if (baseType != null)
                foreach (Type i in baseType.GetInterfaces())
                    implied.Add(i);

            foreach (Type i in allInterfaceTypes)
                foreach (Type j in i.GetInterfaces())
                    implied.Add(j);

            model.Bases.AddRange(allInterfaceTypes.Where(i => !implied.Contains(i)).OrderBy(ClrNames.Format, StringComparer.Ordinal));
        }

        /***************************************************/

        private void ExtractProperties(Type def, TypeModel model)
        {
            List<PropertyInfo> properties = def
                .GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                .Where(p => p.GetIndexParameters().Length == 0 && p.GetMethod != null && p.GetMethod.IsPublic)
                .OrderBy(p => p.MetadataToken)
                .ToList();

            Dictionary<string, DefaultValue> defaultValuesByPropName = model.Kind == TypeKind.Interface
                ? new Dictionary<string, DefaultValue>()
                : m_Defaults.Read(def, properties);

            foreach (PropertyInfo property in properties)
            {
                if (property.Name.StartsWith("_"))
                {
                    m_Reporter.Warn(model.ClrName + "." + property.Name, "property name starts with an underscore, Pydantic would treat it as private, skipped");
                    continue;
                }

                defaultValuesByPropName.TryGetValue(property.Name, out DefaultValue value);

                model.Properties.Add(new PropertyModel
                {
                    Default = value,
                    Name = property.Name,
                    Type = property.PropertyType,
                    Quantity = MetadataReader.Quantity(property),
                    IsDynamic = MetadataReader.IsDynamic(property),
                    Description = MetadataReader.Description(property),
                    DisplayText = MetadataReader.DisplayText(property),
                });
            }
        }

        /***************************************************/
    }
}
