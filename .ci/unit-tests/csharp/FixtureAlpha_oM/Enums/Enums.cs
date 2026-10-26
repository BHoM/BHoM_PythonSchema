using System;
using System.ComponentModel;

namespace BH.oM.FixtureAlpha
{
    [Description("Kinds of support.")]
    public enum SupportKind
    {
        None,
        [Description("Fully fixed.")]
        Fixed,
        Pinned
    }

    [Flags]
    public enum Options
    {
        A = 1,
        B = 2,
        Both = 3
    }
}
