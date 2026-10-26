"""Structural comparison of two manifests (for example C# reflection against what is read back from the Python)."""

from __future__ import annotations

import ast
import inspect

from py2cs.model import Manifest, PropertyInfo, TypeInfo


def clean(text: str | None) -> str | None:
    """Docstring-style normalisation, so indentation and trailing blanks do not matter."""
    return None if text is None else inspect.cleandoc(text)


def normalise_default(text: str | None) -> str | None:
    if text is None:
        return None
    prefix = "<factory> " if text.startswith("<factory> ") else ""
    body = text[len(prefix):]
    try:
        return prefix + ast.unparse(ast.parse(body, mode="eval"))
    except SyntaxError:
        return text


def compare_manifests(expected: Manifest, actual: Manifest, check_defaults: bool = True, allow_extra: bool = True, ignore: frozenset[str] = frozenset()) -> list[str]:
    problems: list[str] = []
    for key, left in sorted(expected.items()):
        right = actual.get(key)
        if right is None:
            problems.append(f"{key}: missing")
            continue
        problems.extend(compare_types(left, right, check_defaults, ignore))
    if not allow_extra:
        problems.extend(f"{key}: unexpected type" for key in sorted(set(actual) - set(expected)))
    return problems


def compare_types(left: TypeInfo, right: TypeInfo, check_defaults: bool = True, ignore: frozenset[str] = frozenset()) -> list[str]:
    where = left.clr_name
    problems: list[str] = []

    def check(label: str, a: object, b: object) -> None:
        if label not in ignore and a != b:
            problems.append(f"{where}: {label} differs: {a!r} != {b!r}")

    check("kind", left.kind, right.kind)
    check("namespace", left.namespace, right.namespace)
    check("assembly", left.assembly, right.assembly)
    check("repo", left.repo, right.repo)
    check("path", left.relative_path, right.relative_path)
    check("flags", left.flags, right.flags)
    check("name", left.name, right.name)
    check("bases", left.bases, right.bases)
    check("generic params", [(g.name, g.constraints) for g in left.generic_params], [(g.name, g.constraints) for g in right.generic_params])
    check("description", clean(left.description), clean(right.description))
    check("property names", [p.name for p in left.properties], [p.name for p in right.properties])
    check("members", [(m.name, m.value) for m in left.members], [(m.name, m.value) for m in right.members])

    right_props = {p.name: p for p in right.properties}
    for p in left.properties:
        q = right_props.get(p.name)
        if q is not None:
            problems.extend(compare_properties(where, p, q, left.kind == "interface", check_defaults))
    return problems


def compare_properties(where: str, p: PropertyInfo, q: PropertyInfo, interface: bool, check_defaults: bool) -> list[str]:
    problems: list[str] = []
    label = f"{where}.{p.name}"
    if p.clr_type != q.clr_type:
        problems.append(f"{label}: clr type differs: {p.clr_type!r} != {q.clr_type!r}")
    if clean(p.description) != clean(q.description):
        problems.append(f"{label}: description differs")
    if not interface:
        if p.has_default != q.has_default:
            problems.append(f"{label}: has_default differs: {p.has_default} != {q.has_default}")
        elif check_defaults and normalise_default(p.default) != normalise_default(q.default):
            problems.append(f"{label}: default differs: {p.default!r} != {q.default!r}")
        if p.py_name != q.py_name and p.py_name and q.py_name:
            problems.append(f"{label}: python name differs")
        if p.quantity != q.quantity:
            problems.append(f"{label}: quantity differs: {p.quantity} != {q.quantity}")
        if p.display_text != q.display_text:
            problems.append(f"{label}: display text differs")
        if p.dynamic != q.dynamic:
            problems.append(f"{label}: dynamic differs")
    return problems
