namespace BH.oM.FixtureAlpha
{
    //File folder differs from the namespace on purpose, like dKoP_oM/AdministrativeInformation/ProjectIdentification.cs
    public class ProjectLike : ThingIdentity
    {
        public virtual string ProjectReference { get; set; } = "";
        public virtual string ProjectName { get; set; } = "";
        public virtual string ProjectLocation { get; set; } = "";
        public virtual string AdditionalReferences { get; set; } = "";
    }
}
