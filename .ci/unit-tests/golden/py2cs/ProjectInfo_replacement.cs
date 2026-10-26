/*
 * Existing header, kept as is.
 */

using BH.oM.Base;
using System;
using System.Text;
using System.Collections.Generic;
using System.ComponentModel;

namespace BH.oM.Demo
{
    public class ProjectInfo : IdentityBase
    {
        /***************************************************/
        /**** Properties                                ****/
        /***************************************************/

        public virtual string Reference { get; set; } = "";

        public virtual List<string> Items { get; set; } = new List<string>();

        [Description("A note.")]
        public virtual string Note { get; set; } = "";

        /***************************************************/
    }
}
