/*
 * This file is part of the Buildings and Habitats object Model (BHoM)
 * Copyright (c) 2015 - 2025, the respective contributors. All rights reserved.
 *
 * Each contributor holds copyright over their respective contributions.
 * The project versioning (Git) records all such contribution source information.
 *
 *
 * The BHoM is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation, either version 3.0 of the License, or
 * (at your option) any later version.
 *
 * The BHoM is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this code. If not, see <https://www.gnu.org/licenses/lgpl-3.0.html>.
 */

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using BH.oM.Base;
using BH.oM.Base.Attributes;
using BH.oM.Quantities.Attributes;

namespace BH.oM.FixtureAlpha
{
    //Immutable: no parameterless constructor, so every field is required, on top of the defaulted BHoMObject fields
    public class ImmutableThing : BHoMObject, IImmutable
    {
        public virtual string Id { get; }
        public virtual double Length { get; }

        public ImmutableThing(string id, double length)
        {
            Id = id;
            Length = length;
        }
    }

    public class Wrapper<T> : BHoMObject where T : IBHoMObject
    {
        public virtual List<T> Items { get; set; } = new List<T>();
    }

    public class Beam : BHoMObject
    {
        [Length]
        [DisplayText("Span length")]
        [Description("Distance between the supports.")]
        public virtual double Span { get; set; } = 1.5;

        public virtual SupportKind Support { get; set; } = SupportKind.Pinned;
        public virtual Options Flags { get; set; } = Options.A;
        public virtual PointLike Start { get; set; } = null;
        public virtual long Count { get; set; } = 3;
        public virtual float Small { get; set; } = 0.5f;
    }

    public class Collections : BHoMObject
    {
        public virtual HashSet<string> Names { get; set; } = new HashSet<string>();
        public virtual HashSet<PointLike> Points { get; set; } = new HashSet<PointLike>();
        public virtual Dictionary<string, double> Lookup { get; set; } = new Dictionary<string, double>();
        public virtual Dictionary<PointLike, string> ByPoint { get; set; } = new Dictionary<PointLike, string>();
        public virtual double[] Values { get; set; } = new double[0];
        public virtual List<List<int>> Matrix { get; set; } = new List<List<int>>();
        public virtual IEnumerable<string> Words { get; set; } = new List<string> { "a", "b" };
        public virtual int? OptionalCount { get; set; } = null;
        public virtual Tuple<int, string> Pair { get; set; } = null;
        public virtual object Anything { get; set; } = null;
    }

    public class Scalars : BHoMObject
    {
        public virtual DateTime Created { get; set; } = DateTime.Now;
        public virtual DateTime Fixed { get; set; } = new DateTime(2020, 1, 2, 3, 4, 5);
        public virtual Guid Key { get; set; } = Guid.Empty;
        public virtual decimal Cost { get; set; } = 1.5m;
        public virtual Color Colour { get; set; } = Color.Empty;
        public virtual TimeSpan Duration { get; set; } = TimeSpan.FromSeconds(90);
        public virtual char Letter { get; set; } = 'x';
        public virtual string Quote { get; set; } = "it's \"here\"";
        public virtual Type TypeRef { get; set; } = null;
        public virtual Func<double, double> Callback { get; set; } = null;
        public virtual double Big { get; set; } = double.MaxValue;
    }

    public class GeometryHolder : BHoMObject
    {
        public virtual IGeometryLike Geometry { get; set; } = null;
        public virtual List<ICurveLike> Curves { get; set; } = new List<ICurveLike>();
    }

    public class CycleA : IObject
    {
        public virtual CycleB Other { get; set; } = null;
    }

    public class CycleB : IObject
    {
        public virtual CycleA Other { get; set; } = null;
    }
}
