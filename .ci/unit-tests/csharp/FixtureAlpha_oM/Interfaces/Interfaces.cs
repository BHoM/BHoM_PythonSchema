using BH.oM.Base;

namespace BH.oM.FixtureAlpha
{
    public interface IGeometryLike : IObject { }

    public interface IElement1DLike : IObject { }

    //Two parent interfaces, like ICurve : IGeometry, IElement1D
    public interface ICurveLike : IGeometryLike, IElement1DLike { }

    //No "I" prefix on purpose, like IdKoPObject
    public interface ThingIdentity : IObject { }

    public interface ILabelled : IObject
    {
        string Label { get; set; }
    }
}
