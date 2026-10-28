"""Static reader: turns bhom_schema Python files into the type manifest. Files are parsed with ast, never imported.

Generated files carry a __bhom__ marker. A hand-written class may leave it out: it is then worked out from the folder the
file is in and from the generated classes next to it (see infer_marker).
"""

from __future__ import annotations

import ast
import keyword
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py2cs.model import GenericParam, Manifest, MemberInfo, PropertyInfo, TypeInfo

ROOT_PACKAGE = "bhom_schema"
MODEL_BASES = {"SchemaModel", "BaseModel"}
ENUM_BASES = {"Enum", "IntEnum", "IntFlag", "Flag"}
FLAG_BASES = {"IntFlag", "Flag"}
IGNORED_BASES = MODEL_BASES | ENUM_BASES | {"ABC"}

PRIMITIVES = {
    "str": "string", "int": "int", "float": "double", "bool": "bool", "Decimal": "decimal",
    "datetime": "System.DateTime", "timedelta": "System.TimeSpan", "UUID": "System.Guid", "Any": "object",
    "Color": "System.Drawing.Color",
}
VALUE_TYPES = {"int", "float", "bool", "Decimal", "datetime", "timedelta", "UUID", "Color"}
LIST = "System.Collections.Generic.List"
SET = "System.Collections.Generic.HashSet"
DICT = "System.Collections.Generic.Dictionary"
# Old typing names, written by people more often than by the generator
TYPING_ALIASES = {"List": "list", "Dict": "dict", "Set": "set", "Tuple": "tuple"}
SUPPORTED = "str, int, float, bool, Decimal, datetime, timedelta, UUID, Any, list[...], dict[...], set[...], tuple[...], X | None, or a bhom_schema class"

@dataclass
class ReadError:
    """One problem found in one file."""
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}" if self.line else f"{self.path}: {self.message}"

class ReadErrors(ValueError):
    """Every problem found while reading a package, raised together."""

    def __init__(self, errors: list[ReadError]):
        super().__init__("\n".join(str(e) for e in errors))
        self.errors = errors

@dataclass
class RefInfo:
    """What a referenced class declares about itself in its __bhom__ marker (written or worked out)."""
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

@dataclass
class Inferred:
    marker: dict[str, Any]
    notes: list[str]

class Resolver:
    """Finds the marker of other modules, so a reference can be turned back into its C# name."""

    def __init__(self, package_root: Path):
        self.root = package_root
        self._refs: dict[str, RefInfo | None] = {}
        self._written: dict[Path, dict[str, Any] | None] = {}
        self._assemblies: dict[str, list[tuple[tuple[str, ...], dict[str, Any]]]] = {}

    def path_of(self, module: str) -> Path | None:
        if not module.startswith(ROOT_PACKAGE + "."):
            return None
        parts = module.split(".")[1:]
        path = self.root.joinpath(*parts).with_suffix(".py")
        return path if path.exists() else None

    def ref(self, module: str) -> RefInfo | None:
        if module in self._refs:
            return self._refs[module]
        # A placeholder, so two hand-written classes naming each other cannot recurse forever
        self._refs[module] = None
        info: RefInfo | None = None
        path = self.path_of(module)
        if path is not None:
            marker = self.written_marker(path)
            if marker is None:
                marker = self._inferred_marker(path)
            if marker is not None:
                info = RefInfo(module, marker)
        self._refs[module] = info
        return info

    def written_marker(self, path: Path) -> dict[str, Any] | None:
        """The __bhom__ marker written in a file, or None."""
        if path not in self._written:
            try:
                self._written[path] = find_marker(ast.parse(path.read_text(encoding="utf-8")))
            except (SyntaxError, ValueError):
                self._written[path] = None
        return self._written[path]

    def assembly_markers(self, assembly: str) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
        """(folders below the assembly folder, marker) of every class of an assembly folder that has a written marker."""
        if assembly not in self._assemblies:
            found: list[tuple[tuple[str, ...], dict[str, Any]]] = []
            folder = self.root / assembly
            if folder.is_dir():
                for path in sorted(folder.rglob("*.py")):
                    if path.name == "__init__.py":
                        continue
                    marker = self.written_marker(path)
                    if marker is not None:
                        found.append((path.relative_to(folder).parts[:-1], marker))
            self._assemblies[assembly] = found
        return self._assemblies[assembly]

    def _inferred_marker(self, path: Path) -> dict[str, Any] | None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            return None
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        if not classes:
            return None
        try:
            return infer_marker(path, self.root, classes[0], collect_imports(tree), self).marker
        except ValueError:
            return None

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

def name_of(node: ast.expr, imports: dict[str, tuple[str, str]]) -> str | None:
    """The original name behind `Name` or `module.Name`, so aliased imports read the same as plain ones."""
    if isinstance(node, ast.Name):
        return imports.get(node.id, (None, node.id))[1]
    if isinstance(node, ast.Attribute):
        return node.attr
    return None

# ------------------------------------------------------------------------------------------------ inferring the marker

def namespace_prefix(markers: list[tuple[tuple[str, ...], dict[str, Any]]]) -> str | None:
    """The namespace of the assembly folder itself, from the classes in it: the generator writes BH.oM.X.A.B into Assembly/A/B."""
    prefixes: Counter[str] = Counter()
    for folders, marker in markers:
        segments = str(marker["namespace"]).split(".")
        if not folders:
            prefixes[".".join(segments)] += 1
        elif tuple(segments[-len(folders):]) == folders:
            prefixes[".".join(segments[:-len(folders)])] += 1
    return prefixes.most_common(1)[0][0] if prefixes else None

def infer_kind(cls: ast.ClassDef, imports: dict[str, tuple[str, str]], resolver: Resolver) -> tuple[str, bool]:
    """(kind, is flags enum) from the bases of a class without a marker."""
    originals: set[str] = set()
    referenced: list[str] = []
    for base in cls.bases:
        head = base.value if isinstance(base, ast.Subscript) else base
        original = name_of(head, imports)
        if original is None:
            continue
        if original in ENUM_BASES:
            return "enum", original in FLAG_BASES
        originals.add(original)
        module = imports.get(head.id, ("", ""))[0] if isinstance(head, ast.Name) else ""
        if module.startswith(ROOT_PACKAGE + ".") and not module.startswith(ROOT_PACKAGE + "._support"):
            ref = resolver.ref(module)
            if ref is not None:
                referenced.append(ref.kind)
    if originals & MODEL_BASES or any(k in ("class", "abstract", "struct") for k in referenced):
        return ("abstract" if "ABC" in originals else "class"), False
    if originals:
        return "interface", False
    raise ValueError(f"{cls.name} has no base class; derive it from SchemaModel, a bhom_schema class, Enum or an interface")

def infer_marker(path: Path, root: Path, cls: ast.ClassDef, imports: dict[str, tuple[str, str]], resolver: Resolver) -> Inferred:
    """Works out the __bhom__ marker of a hand-written class from its folder and the generated classes around it."""
    parts = path.relative_to(root).parts
    if len(parts) < 2:
        raise ValueError("the file must be inside an assembly folder, for example Structure_oM/Elements/<Name>.py")
    assembly = parts[0]
    folders = tuple(parts[1:-1])
    markers = resolver.assembly_markers(assembly)
    if not markers:
        raise ValueError(f"{assembly} is not an existing assembly folder (it has no generated class); put new classes in an existing assembly folder")

    siblings: Counter[str] = Counter(str(m["namespace"]) for f, m in markers if f == folders)
    if siblings:
        namespace = siblings.most_common(1)[0][0]
    else:
        prefix = namespace_prefix(markers)
        if prefix is None:
            raise ValueError(f"the namespace of the folders in {assembly} could not be worked out; add a __bhom__ marker")
        namespace = ".".join([prefix, *folders])

    repos: Counter[str] = Counter(str(m["repo"]) for _, m in markers if m.get("repo"))
    repo = repos.most_common(1)[0][0] if repos else None
    kind, flags = infer_kind(cls, imports, resolver)

    generics = [tp.name for tp in cls.type_params]
    simple = cls.name
    suffix = f"_{len(generics)}"
    if generics and simple.endswith(suffix):
        simple = simple[:-len(suffix)]
    marker: dict[str, Any] = {
        "clr_name": f"{namespace}.{simple}" + (f"`{len(generics)}" if generics else ""),
        "assembly": assembly,
        "namespace": namespace,
        "kind": kind,
    }
    if repo:
        marker["repo"] = repo
    if flags:
        marker["flags"] = True
    if kind == "enum":
        members = [s.targets[0].id for s in cls.body if isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Name)]
        renamed = {m: m[:-1] for m in members if m.endswith("_") and keyword.iskeyword(m[:-1])}
        if renamed:
            marker["renamed_members"] = renamed
    note = f"no __bhom__ marker was written, so it was worked out: C# name {marker['clr_name']}, repository {repo or 'unknown'}, kind {kind}"
    return Inferred(marker, [note])

# ------------------------------------------------------------------------------------------------ annotations

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
        """The original name behind a Name or module.Name node, so aliased imports read the same as plain ones."""
        name = name_of(node, self.imports)
        if name is None:
            raise ValueError(f"unsupported expression: {ast.unparse(node)}")
        return name

    def convert(self, node: ast.expr) -> tuple[str, bool]:
        """Returns the C# type and whether it is a value type on the Python side."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return self.convert(ast.parse(node.value, mode="eval").body)

        if isinstance(node, ast.Subscript) and self.original(node.value) == "Annotated":
            elements = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
            self.metadata = elements[1:]
            for meta in elements[1:]:
                if isinstance(meta, ast.Call) and self.original(meta.func) == "ClrType":
                    return str(ast.literal_eval(meta.args[0])), False
            return self.convert(elements[0])

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            for kept, other in ((node.left, node.right), (node.right, node.left)):
                if is_none(other):
                    return self._nullable(kept)
            raise ValueError(f"unsupported union: {ast.unparse(node)}; only 'X | None' is supported")

        if isinstance(node, ast.Name):
            return self._named(node.id, [])

        if isinstance(node, ast.Attribute):
            if node.attr in PRIMITIVES:
                return PRIMITIVES[node.attr], node.attr in VALUE_TYPES
            raise ValueError(f"unsupported type '{ast.unparse(node)}'; use {SUPPORTED}")

        if isinstance(node, ast.Subscript):
            head = self.original(node.value)
            elements = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
            if head == "Optional":
                return self._nullable(elements[0])
            if head == "Union":
                kept = [e for e in elements if not is_none(e)]
                if len(kept) == 1 and len(kept) < len(elements):
                    return self._nullable(kept[0])
                raise ValueError(f"unsupported union: {ast.unparse(node)}; only 'X | None' is supported")
            if head == "Callable":
                return "System.Delegate", False
            head = TYPING_ALIASES.get(head, head)
            args = [self.convert(a)[0] for a in elements]
            if head == "list":
                return f"{LIST}<{args[0]}>", False
            if head == "set":
                return f"{SET}<{args[0]}>", False
            if head == "dict":
                return f"{DICT}<{args[0]}, {args[1]}>", False
            if head == "tuple":
                return f"System.Tuple<{', '.join(args)}>", False
            if not isinstance(node.value, ast.Name):
                raise ValueError(f"unsupported type '{ast.unparse(node)}'; use {SUPPORTED}")
            return self._named(node.value.id, args)

        raise ValueError(f"unsupported annotation: {ast.unparse(node)}")

    def _nullable(self, node: ast.expr) -> tuple[str, bool]:
        inner, value = self.convert(node)
        return (inner + "?" if value and not inner.endswith("?") else inner), False

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
        raise ValueError(f"unsupported type '{local}'; use {SUPPORTED}")

    @staticmethod
    def _constructed(ref: RefInfo, args: list[str]) -> str:
        if args:
            return f"{ref.base_name}<{', '.join(args)}>"
        if "`" in ref.clr_name:
            return f"{ref.base_name}<{', '.join(ref.marker.get('generic_params', {}).keys())}>"
        return ref.base_name

def is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None

def is_class_var(node: ast.expr, converter: Converter) -> bool:
    head = node.value if isinstance(node, ast.Subscript) else node
    return name_of(head, converter.imports) == "ClassVar"

# ------------------------------------------------------------------------------------------------ files

def read_file(path: Path, root: Path, resolver: Resolver | None = None, errors: list[ReadError] | None = None) -> TypeInfo | None:
    """Reads one module. Returns None for files without a class (for example __init__.py) or that cannot be read.

    Problems are added to errors; without an errors list they are raised.
    """
    relative = path.relative_to(root).as_posix()
    problems: list[ReadError] = []

    def error(line: int, message: str) -> None:
        problems.append(ReadError(relative, line, message))

    info = _read(path, root, resolver or Resolver(root), error)
    if errors is not None:
        errors.extend(problems)
    elif problems:
        raise ReadErrors(problems)
    return info

def _read(path: Path, root: Path, resolver: Resolver, error: Callable[[int, str], None]) -> TypeInfo | None:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        error(e.lineno or 0, f"not valid Python: {e.msg}")
        return None

    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if not classes:
        return None

    for extra in classes[1:]:
        error(extra.lineno, f"only one class per file is read; move {extra.name} to its own file")

    cls = classes[0]
    imports = collect_imports(tree)
    marker = find_marker(tree)
    notes: list[str] = []
    if marker is None:
        try:
            inferred = infer_marker(path, root, cls, imports, resolver)
        except ValueError as e:
            error(cls.lineno, f"{cls.name} has no __bhom__ marker and it could not be worked out: {e}")
            return None
        marker, notes = inferred.marker, inferred.notes

    type_params = {tp.name for tp in cls.type_params}
    kind = str(marker.get("kind", "class"))
    converter = Converter(imports, type_params, resolver, marker, cls.name)

    generic_params: list[GenericParam] = []
    declared = marker.get("generic_params", {})
    for tp in cls.type_params:
        constraints = list(declared.get(tp.name, []))
        if tp.name not in declared and isinstance(tp, ast.TypeVar) and tp.bound is not None:
            try:
                constraints = [converter.convert(tp.bound)[0]]
            except ValueError as e:
                error(cls.lineno, f"type parameter {tp.name}: {e}")
        generic_params.append(GenericParam(tp.name, constraints))

    base_name = str(marker["clr_name"]).split("`")[0].replace("+", ".")
    canonical = base_name + (f"<{', '.join(p.name for p in generic_params)}>" if generic_params else "")

    bases: list[str] = []
    for base in cls.bases:
        head = base.value if isinstance(base, ast.Subscript) else base
        if name_of(head, imports) in IGNORED_BASES:
            continue
        try:
            bases.append(converter.convert(base)[0])
        except ValueError as e:
            error(cls.lineno, f"base {ast.unparse(base)}: {e}")

    info = TypeInfo(
        clr_name=str(marker["clr_name"]), name=canonical, python_name=cls.name,
        relative_path=path.relative_to(root).as_posix(), namespace=str(marker["namespace"]), assembly=str(marker["assembly"]),
        kind=kind, repo=marker.get("repo"), description=ast.get_docstring(cls), flags=bool(marker.get("flags", False)),
        bases=bases, generic_params=generic_params, notes=notes)

    lines = source.splitlines()
    renamed: dict[str, str] = dict(marker.get("renamed_members", {}))
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id != "__bhom__":
            name = stmt.target.id
            if is_class_var(stmt.annotation, converter):
                continue
            if name.startswith("_"):
                error(stmt.lineno, f"{name}: a field name cannot start with an underscore (Pydantic treats it as private)")
                continue
            try:
                info.properties.append(read_field(stmt, converter))
            except ValueError as e:
                error(stmt.lineno, f"{name}: {e}")
        elif kind == "enum" and isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
            py_name = stmt.targets[0].id
            comment = lines[stmt.lineno - 2].strip() if stmt.lineno >= 2 and lines[stmt.lineno - 2].strip().startswith("# ") else None
            info.members.append(MemberInfo(renamed.get(py_name, py_name), ast.unparse(stmt.value), comment[2:] if comment else None))

    if kind == "interface":
        for name, entry in marker.get("properties", {}).items():
            info.properties.append(PropertyInfo(name=name, clr_type=entry["type"], py_name=name, description=entry.get("description")))
    return info

def is_field_call(node: ast.expr, converter: Converter) -> bool:
    return isinstance(node, ast.Call) and name_of(node.func, converter.imports) == "Field"

def is_ellipsis(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is Ellipsis

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
    if isinstance(value, ast.Call) and is_field_call(value, converter):
        # Field(x, ...) and Field(default=x, ...) both give a default; Field(...) with an ellipsis means required
        if value.args and not is_ellipsis(value.args[0]):
            prop.has_default, prop.default = True, ast.unparse(value.args[0])
        for kw in value.keywords:
            if kw.arg == "default" and not is_ellipsis(kw.value):
                prop.has_default, prop.default = True, ast.unparse(kw.value)
            elif kw.arg == "default_factory":
                prop.has_default, prop.default = True, "<factory> " + ast.unparse(kw.value)
            elif kw.arg == "description":
                prop.description = str(ast.literal_eval(kw.value))
            elif kw.arg == "alias":
                prop.name = str(ast.literal_eval(kw.value))
    elif value is not None and not is_ellipsis(value):
        prop.has_default, prop.default = True, ast.unparse(value)
    return prop

def read_package(package_root: Path, errors: list[ReadError] | None = None) -> Manifest:
    """Reads every module under a bhom_schema folder (skipping the hand-written _support package).

    Problems are added to errors; without an errors list they are raised together as ReadErrors.
    """
    problems: list[ReadError] = []
    resolver = Resolver(package_root)
    manifest: Manifest = {}
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root).parts
        if path.name == "__init__.py" or relative[0] == "_support":
            continue
        info = read_file(path, package_root, resolver, problems)
        if info is None:
            continue
        if info.clr_name in manifest:
            problems.append(ReadError(info.relative_path, 0, f"{info.clr_name} is already declared in {manifest[info.clr_name].relative_path}"))
            continue
        manifest[info.clr_name] = info
    if errors is not None:
        errors.extend(problems)
    elif problems:
        raise ReadErrors(problems)
    return manifest
