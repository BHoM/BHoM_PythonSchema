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

using BH.oM.Base.Attributes;
using BH.oM.Quantities.Attributes;
using System;
using System.Collections.Generic;
using System.ComponentModel;

namespace BH.oM.Demo
{
    [Description("Has every kind of property.")]
    public class Everything : IdentityBase
    {
        /***************************************************/
        /**** Properties                                ****/
        /***************************************************/

        public virtual string Required { get; }

        public virtual string Text { get; set; } = "";

        public virtual string Quoted { get; set; } = "say \"hi\"";

        public virtual long Count { get; set; } = 3;

        public virtual float Small { get; set; } = 0.5f;

        public virtual double Ratio { get; set; } = 1.5;

        [Description("A flag.")]
        public virtual bool Flag { get; set; } = false;

        public virtual Mode Choice { get; set; } = Mode.None;

        public virtual Mode Other { get; set; } = Mode.Fast;

        public virtual HashSet<string> Names { get; set; } = new HashSet<string>();

        public virtual Dictionary<string, double> Lookup { get; set; } = new Dictionary<string, double>();

        public virtual double[] Values { get; set; } = new double[0];

        public virtual IEnumerable<string> Words { get; set; } = new List<string> { "a", "b" };

        public virtual int? Maybe { get; set; }

        public virtual Guid Key { get; set; } = Guid.Empty;

        public virtual Guid Fresh { get; set; } = Guid.NewGuid();

        public virtual decimal Cost { get; set; } = 1.5m;

        public virtual DateTime Fixed { get; set; } = new DateTime(2020, 1, 2, 3, 4, 5);

        public virtual DateTime Created { get; set; } = DateTime.Now;

        [Description("Distance between supports.")]
        [Length]
        [DisplayText("Span length")]
        public virtual double Span { get; set; } = 1.5;

        /***************************************************/
        /**** Constructors                              ****/
        /***************************************************/

        public Everything(string required)
        {
            Required = required;
        }

        /***************************************************/
    }
}
