using BH.oM.Base;

namespace BH.oM.FixtureBeta
{
    //Same simple name as FixtureAlpha.PointLike, in another assembly
    public class PointLike : IObject
    {
        public virtual double X { get; set; } = 0;
    }
}

namespace BH.oM.FixtureBeta.Elements
{
    public class UsesBoth : BHoMObject
    {
        public virtual FixtureAlpha.PointLike FromAlpha { get; set; } = null;
        public virtual PointLike Local { get; set; } = null;
    }
}
