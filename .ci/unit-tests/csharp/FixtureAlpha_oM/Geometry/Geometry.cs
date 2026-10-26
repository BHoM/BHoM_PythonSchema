using System.ComponentModel;
using BH.oM.Base;

namespace BH.oM.FixtureAlpha
{
    public class PointLike : IGeometryLike
    {
        public virtual double X { get; set; } = 0;
        public virtual double Y { get; set; } = 0;
        public virtual double Z { get; set; } = 0;
    }

    [Description("A straight segment between two points.")]
    public class LineLike : ICurveLike, ILabelled
    {
        public virtual PointLike Start { get; set; } = new PointLike();
        public virtual PointLike End { get; set; } = new PointLike();
        [Description("Extends the line to infinity.")]
        public virtual bool Infinite { get; set; } = false;
        public virtual string Label { get; set; } = null;
    }
}
