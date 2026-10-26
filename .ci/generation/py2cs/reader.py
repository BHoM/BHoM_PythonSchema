"""Static reader: turns generated Python files into the type manifest. Files are parsed with ast, never imported."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py2cs.model import GenericParam, Manifest, MemberInfo, PropertyInfo, TypeInfo

ROOT_PACKAGE = "bhom_schema"
IGNORED_BASES = {"SchemaModel", "ABC", "Enum", "IntFlag"}

PRIMITIVES = {
    "str": "string", "int": "int", "float": "double", "bool": "bool", "Decimal": "decimal",
    "datetime": "System.DateTime", "timedelta": "System.TimeSpan", "UUID": "System.Guid", "Any": "object",
    "Color": "System.Drawing.Color",
}
VALUE_TYPES = {"int", "float", "bool", "Decimal", "datetime", "timedelta", "UUID", "Color"}
LIST = "System.Collections.Generic.List"
SET = "System.Collections.Generic.HashSet"
DICT = "System.Collections.Generic.Dictionary"


@dataclass
class RefInfo:
    """What a referenced generated class declares about itself in its __bhom__ marker."""

    module: str
    marker: dict[str, Any]

    @property
    def clr_name(self) -> str:
        return str(self.marker["clr_name"])

    @property
    def base_name(self) -> str:
        return self.clr_name.split("`")[0].replace("+", ".")

    @property
    def kind(self) -> str:
        return str(self.marker.get("kind", "class"))

    @property
    def renamed_members(self) -> dict[str, str]:
        return dict(self.marker.get("renamed_members", {}))


class Resolver:
    """Finds the marker of other generated modules, so a reference can be turned back into its C# name."""

    def __init__(self, package_root: Path):
        self.root = package_root
        self._cache: dict[str, RefInfo | None] = {}

    def path_of(self, module: str) -> Path | None:
        if not module.startswith(ROOT_PACKAGE + "."):
            return None
        parts = module.split(".")[1:]
        path = self.root.joinpath(*parts).with_suffix(".py")
        return path if path.exists() else None

    def ref(self, module: str) -> RefInfo | None:
        if module in self._cache:
            return self._cache[module]
        info: RefInfo | None = None
        path = self.path_of(module)
        if path is not None:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            marker = find_marker(tree)
            if marker is not None:
                info = RefInfo(module, marker)
        self._cache[module] = info
        return info


def find_marker(tree: ast.Module) -> dict[str, Any] | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "__bhom__" and node.value is not None:
            return ast.literal_eval(node.value)
    return None


def collect_imports(tree: ast.Module) -> dict[str, tuple[str, str]]:
    imports: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module, alias.name)
    return imports


@dataclass
class Converter:
    """Python annotation to canonical C# type text, the inverse of the C# TypeMapper."""

    imports: dict[str, tuple[str, str]]
    type_params: set[str]
    resolver: Resolver
    self_marker: dict[str, Any]
    self_name: str
    metadata: list[ast.expr] = field(default_factory=lambda: [])

    def origin(self, local: str) -> tuple[str | None, str]:
        """(module, original name) of an imported name, or (None, name) for builtins and local names."""
        if local in self.imports:
            return self.imports[local]
        return None, local

    def original(self, node: ast.expr) -> str:
        """The original name behind a Name node, so aliased imports read the same as plain ones."""
        if isinstance(node, ast.Name):
            return self.origin(node.id)[1]
        raise ValueError(f"unsupported expression: {ast.unparse(node)}")

    def convert(self, node: ast.expr) -> tuple[str, bool]:
        """Returns the C# type and whether it is a value type on the Python side."""
        if isinstance(node, ast.Subscript) and self.original(node.value) == "Annotated":
            elements = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
            self.metadata = elements[1:]
            for meta in elements[1:]:
                if isinstance(meta, ast.Call) and self.original(meta.func) == "ClrType":
                    return str(ast.literal_eval(meta.args[0])), False
            return self.convert(elements[0])

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            for kept, other in ((node.left, node.right), (node.right, node.left)):
                if isinstance(other, ast.Constant) and other.value is None:
                    inner, value = self.convert(kept)
                    return (inner + "?" if value and not inner.endswith("?") else inner), False
            raise ValueError(f"unsupported union: {ast.unparse(node)}")

        if isinstance(node, ast.Name):
            return self._named(node.id, [])

        if isinstance(node, ast.Subscript):
            head = self.original(node.value)
            elements = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
            if head == "Callable":
                return "System.Delegate", False
            args = [self.convert(a)[0] for a in elements]
            if head == "list":
                return f"{LIST}<{args[0]}>", False
            if head == "set":
                return f"{SET}<{args[0]}>", False
            if head == "dict":
                return f"{DICT}<{args[0]}, {args[1]}>", False
            if head == "tuple":
                return f"System.Tuple<{', '.join(args)}>", False
            assert isinstance(node.value, ast.Name)
            return self._named(node.value.id, args)

        raise ValueError(f"unsupported annotation: {ast.unparse(node)}")

    def _named(self, local: str, args: list[str]) -> tuple[str, bool]:
        if local in self.type_params:
            return local, False
        if local == self.self_name and local not in self.imports:
            ref = RefInfo("", self.self_marker)
            return self._constructed(ref, args), ref.kind in ("enum", "struct")

        module, original = self.origin(local)
        if module is not None and module.startswith(ROOT_PACKAGE + ".") and not module.startswith(ROOT_PACKAGE + "._support"):
            ref = self.resolver.ref(module)
            if ref is None:
                raise ValueError(f"cannot resolve {local} from {module}")
            return self._constructed(ref, args), ref.kind in ("enum", "struct")
        if original in PRIMITIVES:
            return PRIMITIVES[original], original in VALUE_TYPES
        raise ValueError(f"unsupported type name: {local}")

    @staticmethod
    def _constructed(ref: RefInfo, args: list[str]) -> str:
        if args:
            return f"{ref.base_name}<{', '.join(args)}>"
        if "`" in ref.clr_name:
            return f"{ref.base_name}<{', '.join(ref.marker.get('generic_params', {}).keys())}>"
        return ref.base_name


# ------------------------------------------------------------------------------------------------


def read_file(path: Path, root: Path, resolver: Resolver | None = None) -> TypeInfo | None:
    """Reads one generated module. Returns None for files without a generated class (for example __init__.py)."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    marker = find_marker(tree)
    if not classes or marker is None:
        return None

    resolver = resolver or Resolver(root)
    cls = classes[0]
    imports = collect_imports(tree)
    type_params = {tp.name for tp in cls.type_params}
    kind = str(marker.get("kind", "class"))

    generic_params: list[GenericParam] = []
    declared = marker.get("generic_params", {})
    for tp in cls.type_params:
        constraints = list(declared.get(tp.name, []))
        generic_params.append(GenericParam(tp.name, constraints))

    base_name = str(marker["clr_name"]).split("`")[0].replace("+", ".")
    canonical = base_name + (f"<{', '.join(p.name for p in generic_params)}>" if generic_params else "")

    converter = Converter(imports, type_params, resolver, marker, cls.name)
    bases: list[str] = []
    for base in cls.bases:
        head = base.value if isinstance(base, ast.Subscript) else base
        if isinstance(head, ast.Name) and converter.original(head) in IGNORED_BASES:
            continue
        bases.append(converter.convert(base)[0])

    info = TypeInfo(
        clr_name=str(marker["clr_name"]), name=canonical, python_name=cls.name,
        relative_path=path.relative_to(root).as_posix(), namespace=str(marker["namespace"]), assembly=str(marker["assembly"]),
        kind=kind, repo=marker.get("repo"), description=ast.get_docstring(cls), flags=bool(marker.get("flags", False)),
        bases=bases, generic_params=generic_params)

    lines = source.splitlines()
    renamed: dict[str, str] = dict(marker.get("renamed_members", {}))
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id != "__bhom__":
            info.properties.append(read_field(stmt, converter))
        elif kind == "enum" and isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
            py_name = stmt.targets[0].id
            comment = lines[stmt.lineno - 2].strip() if stmt.lineno >= 2 and lines[stmt.lineno - 2].strip().startswith("# ") else None
            info.members.append(MemberInfo(renamed.get(py_name, py_name), ast.unparse(stmt.value), comment[2:] if comment else None))

    if kind == "interface":
        for name, entry in marker.get("properties", {}).items():
            info.properties.append(PropertyInfo(name=name, clr_type=entry["type"], py_name=name, description=entry.get("description")))
    return info


def read_field(stmt: ast.AnnAssign, converter: Converter) -> PropertyInfo:
    assert isinstance(stmt.target, ast.Name)
    py_name = stmt.target.id
    converter.metadata = []
    clr, _ = converter.convert(stmt.annotation)

    prop = PropertyInfo(name=py_name, py_name=py_name, clr_type=clr)
    for meta in converter.metadata:
        if not isinstance(meta, ast.Call):
            continue
        kind = converter.original(meta.func)
        if kind == "Quantity":
            prop.quantity = (str(ast.literal_eval(meta.args[0])), str(ast.literal_eval(meta.args[1])))
        elif kind == "DisplayText":
            prop.display_text = str(ast.literal_eval(meta.args[0]))
        elif kind == "DynamicProperty":
            prop.dynamic = True

    value = stmt.value
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "Field":
        for kw in value.keywords:
            if kw.arg == "default":
                prop.has_default, prop.default = True, ast.unparse(kw.value)
            elif kw.arg == "default_factory":
                prop.has_default, prop.default = True, "<factory> " + ast.unparse(kw.value)
            elif kw.arg == "description":
                prop.description = str(ast.literal_eval(kw.value))
            elif kw.arg == "alias":
                prop.name = str(ast.literal_eval(kw.value))
    elif value is not None:
        prop.has_default, prop.default = True, ast.unparse(value)
    return prop


def read_package(package_root: Path) -> Manifest:
    """Reads every generated module under a bhom_schema folder (skipping the hand-written _support package)."""
    resolver = Resolver(package_root)
    manifest: Manifest = {}
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root).parts
        if path.name == "__init__.py" or relative[0] == "_support":
            continue
        info = read_file(path, package_root, resolver)
        if info is not None:
            manifest[info.clr_name] = info
    return manifest
