using System.Collections.Generic;
using System.Collections.ObjectModel;
using BH.oM.Base;

namespace BH.oM.FixtureAlpha
{
    //No member has the value 0, but the C# default of a property of this type is 0
    public enum Sparse
    {
        One = 1,
        Two = 2,
    }

    public class SparseHolder : BHoMObject
    {
        public virtual Sparse Level { get; set; }
    }

    //Its default instance cannot be created in Python, because SparseHolder needs an argument
    public class SparseParent : BHoMObject
    {
        public virtual SparseHolder Holder { get; set; } = new SparseHolder();
    }

    //A generic class that names itself in a default collection
    public class TreeLike<T> : BHoMObject
    {
        public virtual Dictionary<string, TreeLike<T>> Children { get; set; } = new Dictionary<string, TreeLike<T>>();
        public virtual List<T> Values { get; set; } = new List<T>();
    }

    public class GridHolder : BHoMObject
    {
        public virtual double[,] Matrix { get; set; } = new double[2, 2];
        public virtual ReadOnlyDictionary<string, double> Table { get; set; } = new ReadOnlyDictionary<string, double>(new Dictionary<string, double>());
    }

    public interface IOpeningLike<T> : IBHoMObject
    {
    }

    //A constraint that depends on another type parameter
    public interface IPanelLike<TEdge, TOpening> : IBHoMObject where TOpening : IOpeningLike<TEdge>
    {
    }
}
