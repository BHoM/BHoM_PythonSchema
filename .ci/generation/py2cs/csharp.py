"""C# source for a type manifest entry: whole new files. Existing files are changed member by member (see patch.py)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from py2cs.model import Manifest, PropertyInfo, TypeInfo

KEYWORD_TYPES = {"bool", "byte", "sbyte", "short", "ushort", "int", "uint", "long", "ulong", "float", "double", "decimal", "char", "string", "object"}
COPYRIGHT = """/*
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
"""
INTERFACE_TO_CLASS = {
    "System.Collections.Generic.IList": "System.Collections.Generic.List",
    "System.Collections.Generic.ICollection": "System.Collections.Generic.List",
    "System.Collections.Generic.IEnumerable": "System.Collections.Generic.List",
    "System.Collections.Generic.IReadOnlyList": "System.Collections.Generic.List",
    "System.Collections.Generic.IReadOnlyCollection": "System.Collections.Generic.List",
    "System.Collections.Generic.ISet": "System.Collections.Generic.HashSet",
    "System.Collections.Generic.IDictionary": "System.Collections.Generic.Dictionary",
    "System.Collections.Generic.IReadOnlyDictionary": "System.Collections.Generic.Dictionary",
}


# ------------------------------------------------------------------------------------------------ type names

@dataclass
class TypeNode:
    name: str
    args: list["TypeNode"] = field(default_factory=lambda: [])
    suffix: str = ""     # "?" and array markers, in order


def parse_type(text: str) -> TypeNode:
    """Parses C# type text such as `List<int>?` or `double[,]` into a TypeNode tree, raising ValueError when text is left over.

    The drafting code uses it to shorten names and to read collection types.
    """
    node, index = _parse(text, 0)
    if index != len(text):
        raise ValueError(f"cannot parse C# type {text!r}")
    return node


def _parse(text: str, i: int) -> tuple[TypeNode, int]:
    """Parses one type name, its generic arguments and its `?` or array suffixes starting at an index, and returns the node with the next index.

    Recursive worker of `parse_type`.
    """
    start = i
    while i < len(text) and (text[i].isalnum() or text[i] in "._"):
        i += 1
    node = TypeNode(text[start:i])
    if i < len(text) and text[i] == "<":
        i += 1
        while True:
            arg, i = _parse(text, i)
            node.args.append(arg)
            while text[i] == " ":
                i += 1
            if text[i] == ",":
                i += 1
                while text[i] == " ":
                    i += 1
                continue
            break
        assert text[i] == ">"
        i += 1
    while i < len(text) and text[i] in "?[":
        if text[i] == "?":
            node.suffix += "?"
            i += 1
        else:
            end = text.index("]", i)
            node.suffix += text[i:end + 1]
            i = end + 1
    return node, i


@dataclass
class Names:
    """Shortens qualified names to simple names and remembers the usings they need."""

    namespace: str
    ambiguous: frozenset[str] = frozenset()     # simple names used by several types of the manifest: always written in full
    usings: set[str] = field(default_factory=lambda: set[str]())
    _simple: dict[str, str] = field(default_factory=lambda: {})

    def render(self, text: str) -> str:
        """Writes C# type text with qualified names shortened to simple names, recording the usings they need.

        Used when drafting whole files and member changes so the code uses `using` directives like hand-written BHoM code.
        """
        return self._render(parse_type(text))

    def _render(self, node: TypeNode) -> str:
        """Renders one TypeNode: shortens a qualified name unless its simple name is ambiguous or already taken by another namespace, and adds the namespace to the usings.

        Worker of `render`, also called with built nodes by `Defaults`.
        """
        name = node.name
        if "." in name:
            namespace, simple = name.rsplit(".", 1)
            known = self._simple.get(simple)
            if simple in self.ambiguous:
                pass
            elif known is None or known == namespace:
                self._simple[simple] = namespace
                if namespace != self.namespace:
                    self.usings.add(namespace)
                name = simple
        text = name
        if node.args:
            text += "<" + ", ".join(self._render(a) for a in node.args) + ">"
        return text + node.suffix


def csharp_string(text: str) -> str:
    """Returns text as a C# string literal in double quotes, escaping backslashes, quotes and control characters.

    Used for `[Description]` and `[DisplayText]` attributes and string defaults in drafted C#.
    """
    out = ['"']
    for c in text:
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        elif ord(c) < 0x20:
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


# ------------------------------------------------------------------------------------------------ defaults

class Defaults:
    def __init__(self, names: Names, manifest: Manifest):
        """Stores the name shortener and manifest used to translate Python defaults into C# initialisers.

        Created per type by `render_type` and by `patch` for member-level changes.
        """
        self.names = names
        self.manifest = manifest

    def initialiser(self, prop: PropertyInfo) -> str | None:
        """Translates the Python default of a property to C# initialiser text, or None when it has no default or cannot be translated.

        Used when drafting new files and new members; untranslatable defaults become reviewer notes.
        """
        if not prop.has_default or prop.default is None:
            return None
        text = prop.default
        try:
            if text.startswith("<factory> "):
                return self._factory(text[len("<factory> "):], prop)
            return self._literal(ast.parse(text, mode="eval").body, prop)
        except (ValueError, SyntaxError, KeyError):
            return None

    # -- literals

    def _literal(self, node: ast.expr, prop: PropertyInfo) -> str | None:
        """Translates a literal Python default (number, string, bool, Decimal, UUID, datetime, timedelta, enum member, signed number) to a C# expression; raises ValueError otherwise.

        Worker of `initialiser`.
        """
        clr = prop.clr_type.rstrip("?")
        if isinstance(node, ast.Constant):
            value = node.value
            if value is None:
                return None
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, str):
                return f"'{value}'" if clr == "char" else csharp_string(value)
            if isinstance(value, int):
                return str(value)
            if isinstance(value, float):
                return self._float(value, clr)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            return "-" + (self._literal(node.operand, prop) or "0")
        if isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            if func == "Decimal":
                return f"{ast.literal_eval(node.args[0])}m"
            if func == "float":
                return {"nan": "double.NaN", "inf": "double.PositiveInfinity", "-inf": "double.NegativeInfinity"}[str(ast.literal_eval(node.args[0]))]
            if func == "UUID":
                if node.keywords:
                    return "Guid.Empty"
                return f"new Guid({csharp_string(str(ast.literal_eval(node.args[0])))})"
            if func == "datetime":
                parts = [int(ast.literal_eval(a)) for a in node.args]
                text = f"new DateTime({', '.join(str(p) for p in parts[:6])})"
                if len(parts) > 6 and parts[6]:
                    text += f".AddTicks({parts[6] * 10})"
                return text
            if func == "timedelta":
                if node.keywords:
                    seconds = float(ast.literal_eval(node.keywords[0].value))
                    return f"TimeSpan.FromSeconds({int(seconds) if seconds == int(seconds) else seconds})"
                return "TimeSpan.Zero"
            enum = self.manifest.get(clr)
            if enum is not None and enum.kind == "enum":
                return f"({self.names.render(clr)}){ast.unparse(node.args[0])}"
        if isinstance(node, ast.Attribute):
            owner = ast.unparse(node.value)
            if owner == "datetime" and node.attr == "min":
                return "DateTime.MinValue"
            enum = self.manifest.get(clr)
            if enum is not None and enum.kind == "enum":
                member = node.attr
                known = {m.name for m in enum.members}
                if member not in known and member.endswith("_") and member[:-1] in known:
                    member = member[:-1]
                return f"{self.names.render(clr)}.{member}"
        raise ValueError(f"cannot translate default {ast.unparse(node)}")

    @staticmethod
    def _float(value: float, clr: str) -> str:
        """Formats a Python float as a C# literal, with infinities as `double` constants and an `f` suffix for `float` properties.

        Used by `_literal`.
        """
        if value == float("inf"):
            return "double.PositiveInfinity"
        if value == float("-inf"):
            return "double.NegativeInfinity"
        text = repr(value).replace("e", "E")
        if "." not in text and "E" not in text:
            text += ".0"
        return text + ("f" if clr == "float" else "")

    # -- factories

    def _factory(self, text: str, prop: PropertyInfo) -> str | None:
        """Translates a `default_factory` (list, set, dict, uuid4, Color, datetime.now, or a lambda building a class, colour, collection or rectangular array) to a C# initialiser; raises ValueError otherwise.

        Worker of `initialiser` for fields whose default is built per instance.
        """
        clr = prop.clr_type.rstrip("?")
        node = ast.parse(text, mode="eval").body
        if isinstance(node, ast.Name):
            if node.id in ("list", "set", "dict"):
                return self._new_collection(clr)
            if node.id == "uuid4":
                return "Guid.NewGuid()"
            if node.id == "Color":
                return "Color.Empty"
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in ("list", "set", "dict"):
            return self._new_collection(clr)
        if isinstance(node, ast.Attribute) and ast.unparse(node) == "datetime.now":
            return "DateTime.Now"
        if isinstance(node, ast.Lambda):
            body = node.body
            if isinstance(body, ast.Call) and isinstance(body.func, ast.Name) and not body.args and not body.keywords:
                return f"new {self.names.render(clr)}()"
            if isinstance(body, ast.Call) and isinstance(body.func, ast.Name) and body.func.id == "Color":
                values = {k.arg: ast.literal_eval(k.value) for k in body.keywords}
                return f"Color.FromArgb({values['A']}, {values['R']}, {values['G']}, {values['B']})"
            if isinstance(body, (ast.List, ast.Set, ast.Dict)) and not (body.elts if not isinstance(body, ast.Dict) else body.keys):
                return self._new_collection(clr)
            if isinstance(body, ast.List) and any(isinstance(e, ast.List) for e in body.elts):
                node = parse_type(clr)
                if node.suffix != "[,]" or not all(isinstance(e, ast.List) for e in body.elts):
                    return None

                element = TypeNode(node.name, node.args, "")
                cell_type = PropertyInfo(name="", clr_type=self.names._render(element))  # pyright: ignore[reportPrivateUsage]
                rows = ", ".join("{ " + ", ".join(self._literal(c, cell_type) or "default" for c in row.elts) + " }" for row in body.elts if isinstance(row, ast.List))
                return f"new {self.names._render(element)}[,] {{ {rows} }}"  # pyright: ignore[reportPrivateUsage]
            if isinstance(body, (ast.List, ast.Set)):
                items = ", ".join(self._literal(e, PropertyInfo(name="", clr_type=self._element(clr))) or "null" for e in body.elts)
                return f"new {self._concrete(clr)} {{ {items} }}"
        raise ValueError(f"cannot translate factory {text}")

    def _concrete(self, clr: str) -> str:
        """Returns the C# text of a type that can be constructed, replacing a collection interface with its usual class.

        Used by `_factory` and `_new_collection` to write `new ...`.
        """
        node = parse_type(clr)
        if node.suffix.startswith("["):
            return self.names.render(clr)
        replacement = INTERFACE_TO_CLASS.get(node.name)
        if replacement:
            node = TypeNode(replacement, node.args, node.suffix)
        return self.names._render(node)  # pyright: ignore[reportPrivateUsage]

    def _new_collection(self, clr: str) -> str:
        """Returns a `new` expression for an empty collection of the given C# type: an empty array, a read-only wrapper around an empty one, or the plain class.

        Used by `_factory` for empty list, set and dict defaults.
        """
        node = parse_type(clr)
        if node.suffix.startswith("[") and "," not in node.suffix:
            element = TypeNode(node.name, node.args, "")
            return f"new {self.names._render(element)}[0]"  # pyright: ignore[reportPrivateUsage]
        for read_only, writable in (("ObjectModel.ReadOnlyDictionary<", "Generic.Dictionary<"), ("ObjectModel.ReadOnlyCollection<", "Generic.List<")):
            if read_only in clr:
                inner = clr.replace(read_only, writable, 1)
                return f"new {self._concrete(clr)}(new {self._concrete(inner)}())"

        return f"new {self._concrete(clr)}()"

    @staticmethod
    def _element(clr: str) -> str:
        """Returns the text of the first generic argument of a type, or the type without its suffix, as the element type of a collection.

        Used by `_factory` to translate the items of a list or set default.
        """
        node = parse_type(clr)
        if node.args:
            return _format(node.args[0])
        return _format(TypeNode(node.name, node.args, ""))


def _format(node: TypeNode) -> str:
    """Writes a TypeNode back to C# text without shortening any name.

    Used by `Defaults._element` to build a type for translating collection items.
    """
    text = node.name
    if node.args:
        text += "<" + ", ".join(_format(a) for a in node.args) + ">"
    return text + node.suffix


# ------------------------------------------------------------------------------------------------ rendering

def ambiguous_names(manifest: Manifest) -> frozenset[str]:
    """Returns the simple type names that more than one type of the manifest uses. Writing them unqualified could bind to the wrong type, so they are always written in full.

    Passed to `Names` by `render_type` and by `patch`.
    """
    owners: dict[str, set[str]] = {}
    for info in manifest.values():
        owners.setdefault(info.simple_name, set()).add(info.clr_name.split("`")[0])
    return frozenset(name for name, full in owners.items() if len(full) > 1)


def render_type(info: TypeInfo, manifest: Manifest, notes: list[str] | None = None, read_only_required: bool = False) -> tuple[str, set[str]]:
    """Returns the namespace block of C# for one type (enum, class, struct or interface) and the namespaces it needs.

    Fields without a default become settable properties without an initial value, unless read_only_required is set: they then become get-only properties set by a constructor, as in the immutable oM types they were generated from. `emit_new` calls it when py2cs drafts a whole new file.
    """
    names = Names(info.namespace, ambiguous_names(manifest))
    defaults = Defaults(names, manifest)
    usings: set[str] = set()
    lines: list[str] = []
    indent = "    "

    def attribute(text: str) -> str:
        """Formats an attribute as an indented bracketed line.

        A small helper inside `render_type` that no code currently calls.
        """
        return f"{indent * 2}[{text}]"

    if info.description:
        usings.add("System.ComponentModel")
        lines.append(f"{indent}[Description({csharp_string(info.description)})]")

    if info.kind == "enum":
        lines.extend(_enum(info, usings))
    else:
        lines.extend(_class_like(info, manifest, names, defaults, usings, notes, read_only_required))

    block = f"namespace {info.namespace}\n{{\n" + "\n".join(lines) + "\n}\n"
    return block, usings | names.usings


def _enum(info: TypeInfo, usings: set[str]) -> list[str]:
    """Returns the C# lines of an enum: `[Flags]` for flags enums, members with descriptions and explicit values when they are not simply sequential.

    Called by `render_type` for the enum kind.
    """
    indent = "    "
    lines: list[str] = []
    if info.flags:
        usings.add("System")
        lines.append(f"{indent}[Flags]")
    lines.append(f"{indent}public enum {info.simple_name}")
    lines.append(f"{indent}{{")
    sequential = all(m.value == str(i) for i, m in enumerate(info.members))
    for i, member in enumerate(info.members):
        if member.description:
            usings.add("System.ComponentModel")
            lines.append(f"{indent * 2}[Description({csharp_string(member.description)})]")
        value = "" if sequential and not info.flags else f" = {member.value}"
        lines.append(f"{indent * 2}{member.name}{value}{',' if i < len(info.members) - 1 else ''}")
    lines.append(f"{indent}}}")
    return lines


def _class_like(info: TypeInfo, manifest: Manifest, names: Names, defaults: Defaults, usings: set[str], notes: list[str] | None, read_only_required: bool) -> list[str]:
    """Returns the C# lines of a class, abstract class, struct or interface: header with bases and generic constraints, properties and, for required fields, a constructor.

    Called by `render_type`; adds reviewer notes for fields drafted without an initial value.
    """
    indent = "    "
    lines: list[str] = []
    keyword = {"interface": "interface", "struct": "struct"}.get(info.kind, "class")
    modifier = "abstract " if info.kind == "abstract" else ""
    generics = f"<{', '.join(g.name for g in info.generic_params)}>" if info.generic_params else ""
    bases = [names.render(b) for b in info.bases]
    header = f"{indent}public {modifier}{keyword} {info.simple_name}{generics}"
    if bases:
        header += " : " + ", ".join(bases)
    for param in info.generic_params:
        if param.constraints:
            header += f" where {param.name} : " + ", ".join(names.render(c) for c in param.constraints)
    lines.append(header)
    lines.append(f"{indent}{{")

    required = [p for p in info.properties if not p.has_default] if info.kind != "interface" and read_only_required else []
    if info.kind != "interface" and not read_only_required and notes is not None:
        notes.extend(f"{p.name} has no default in Python, so it was drafted without an initial value" for p in info.properties if not p.has_default)
    if info.properties:
        lines.append(f"{indent * 2}/***************************************************/")
        lines.append(f"{indent * 2}/**** Properties                                ****/")
        lines.append(f"{indent * 2}/***************************************************/")
        lines.append("")
        for prop in info.properties:
            lines.extend(_property(info, prop, names, defaults, usings, notes, read_only=prop in required))
            lines.append("")
    if required:
        lines.extend(_constructor(info, required, names))
    if info.properties:
        lines.append(f"{indent * 2}/***************************************************/")
    lines.append(f"{indent}}}")
    return lines


CSHARP_KEYWORDS = {"abstract", "as", "base", "bool", "break", "byte", "case", "catch", "char", "checked", "class", "const", "continue", "decimal", "default",
                   "delegate", "do", "double", "else", "enum", "event", "explicit", "extern", "false", "finally", "fixed", "float", "for", "foreach", "goto", "if",
                   "implicit", "in", "int", "interface", "internal", "is", "lock", "long", "namespace", "new", "null", "object", "operator", "out", "override",
                   "params", "private", "protected", "public", "readonly", "ref", "return", "sbyte", "sealed", "short", "sizeof", "stackalloc", "static",
                   "string", "struct", "switch", "this", "throw", "true", "try", "typeof", "uint", "ulong", "unchecked", "unsafe", "ushort", "using", "virtual",
                   "void", "volatile", "while"}


def identifier(name: str) -> str:
    """Returns a property name, prefixed with `@` when it is a C# keyword.

    Used when writing properties and constructor assignments in drafted C#.
    """
    return "@" + name if name in CSHARP_KEYWORDS else name


def parameter_name(name: str) -> str:
    """Returns a property name as a constructor parameter name: first letter lower-cased, prefixed with `@` when it is a C# keyword.

    Used by `_constructor` when drafting get-only types.
    """
    text = name[:1].lower() + name[1:]
    return "@" + text if text in CSHARP_KEYWORDS else text


def _constructor(info: TypeInfo, required: list[PropertyInfo], names: Names) -> list[str]:
    """Returns the C# lines of a constructor taking the required fields and assigning them to the get-only properties.

    Called by `_class_like` when `read_only_required` is set; types with required fields are immutable in the oM.
    """
    indent = "        "
    parameters = ", ".join(f"{names.render(p.clr_type)} {parameter_name(p.name)}" for p in required)
    lines = [f"{indent}/***************************************************/",
             f"{indent}/**** Constructors                              ****/",
             f"{indent}/***************************************************/",
             "",
             f"{indent}public {info.simple_name}({parameters})",
             f"{indent}{{"]
    lines += [f"{indent}    {identifier(p.name)} = {parameter_name(p.name)};" for p in required]
    lines += [f"{indent}}}", ""]
    return lines


def property_attributes(prop: PropertyInfo, usings: set[str]) -> list[str]:
    """Returns the C# attributes of a property, without the square brackets: Description, quantity, DisplayText and DynamicProperty, adding the usings they need.

    Used by `_property` for new files and by `patch` for new members of existing files.
    """
    attributes: list[str] = []
    if prop.description:
        usings.add("System.ComponentModel")
        attributes.append(f"Description({csharp_string(prop.description)})")
    if prop.quantity:
        usings.add("BH.oM.Quantities.Attributes")
        attributes.append(prop.quantity[0])
    if prop.display_text:
        usings.add("BH.oM.Base.Attributes")
        attributes.append(f"DisplayText({csharp_string(prop.display_text)})")
    if prop.dynamic:
        usings.add("BH.oM.Base.Attributes")
        attributes.append("DynamicProperty")
    return attributes

def untranslated_default(prop: PropertyInfo, initialiser: str | None) -> str | None:
    """Returns a reviewer note when a Python default has no C# translation, or None.

    Used when drafting new files and members so the pull request tells the reviewer to set the default by hand.
    """
    if prop.has_default and initialiser is None and prop.default not in (None, "None"):
        return f"the default {prop.default} of {prop.name} could not be translated to C#; set it by hand"
    return None

def _property(info: TypeInfo, prop: PropertyInfo, names: Names, defaults: Defaults, usings: set[str], notes: list[str] | None, read_only: bool = False) -> list[str]:
    """Returns the C# lines of one property: its attributes and either an interface accessor or a `public virtual` property with an initialiser translated from the Python default.

    Called by `_class_like` for each field of a new type.
    """
    indent = "        "
    lines = [f"{indent}[{a}]" for a in property_attributes(prop, usings)]

    type_text = names.render(prop.clr_type)
    if info.kind == "interface":
        lines.append(f"{indent}{type_text} {identifier(prop.name)} {{ get; set; }}")
        return lines

    modifier = "" if info.kind == "struct" else "virtual "
    init = defaults.initialiser(prop)
    suffix = f" = {init};" if init is not None else ""
    accessors = "{ get; }" if read_only else "{ get; set; }"
    lines.append(f"{indent}public {modifier}{type_text} {identifier(prop.name)} {accessors}{suffix}")
    note = untranslated_default(prop, init)
    if note is not None and notes is not None:
        notes.append(note)
    return lines


# ------------------------------------------------------------------------------------------------ files

def _using_lines(namespaces: set[str]) -> list[str]:
    """Returns sorted `using` lines for a set of namespaces, with System namespaces last.

    Used by `emit_new` to write the top of a drafted file.
    """
    return [f"using {ns};" for ns in sorted(namespaces, key=lambda n: (n.startswith("System"), n))]


def emit_new(info: TypeInfo, manifest: Manifest, notes: list[str] | None = None, read_only_required: bool = False) -> str:
    """Returns the text of a whole new C# file (copyright header, usings and namespace block) for a type that does not exist yet. Reviewer notes are added to notes.

    The `plan` step uses it for added types, and the `plan` command writes the result into the draft C# repository.
    """
    block, namespaces = render_type(info, manifest, notes, read_only_required)
    usings = "\n".join(_using_lines(namespaces))
    return COPYRIGHT + "\n" + (usings + "\n\n" if usings else "") + block
