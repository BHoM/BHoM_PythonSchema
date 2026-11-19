"""Where a mapping file lives and how it is read and written.

One file per silver table, named after the table, in a `bhom-mappings` folder of the tool: the folder that holds its notebooks. A notebook finds the file by the table name, in its own folder
or in any folder above it, so a notebook in a subfolder uses the tool's mapping without a copy. Reading and writing need PyYAML (`pip install bhom-schema[mapping]`; Databricks runtimes have it).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from bhom_schema.mapping.model import TABLE, TableMapping, mapping_to_data, parse_mapping

FOLDER = "bhom-mappings"
SUFFIX = ".yml"

def yaml_module() -> Any:
    """Imports PyYAML, or raises ImportError that says how to install it."""
    try:
        import yaml
    except ImportError as error:
        raise ImportError("reading and writing mapping files needs PyYAML: pip install bhom-schema[mapping]") from error

    return yaml

def check_table(table: str) -> None:
    """Raises ValueError unless the text is the full name of a table, `catalog.schema.table`, which is also the name of its file."""
    if not TABLE.match(table):
        raise ValueError(f"{table!r} is not the full name of a table: use catalog.schema.table")

def mapping_path(table: str, folder: str | os.PathLike[str] | None = None) -> Path:
    """Returns where the mapping of a table is kept in a tool's folder: `<folder>/bhom-mappings/<table>.yml`. Without a folder, the current one (a notebook's own folder)."""
    check_table(table)
    return Path(folder if folder is not None else Path.cwd()) / FOLDER / (table + SUFFIX)

def find_mapping(table: str, start: str | os.PathLike[str] | None = None) -> Path | None:
    """Finds the mapping file of a table: `bhom-mappings/<table>.yml` in the starting folder (a notebook's own folder, by default), then in each folder above it.

    Returns the first that exists, or None.
    """
    check_table(table)
    folder = Path(start if start is not None else Path.cwd()).resolve()
    for candidate in (folder, *folder.parents):
        path = candidate / FOLDER / (table + SUFFIX)
        if path.is_file():
            return path

    return None

def is_path(source: str | os.PathLike[str]) -> bool:
    """Tells a path from a table name: anything that is not text, or text that ends in .yml or .yaml or holds a path separator."""
    if not isinstance(source, str):
        return True

    return bool(re.search(r"\.ya?ml$|[\\/]", source))

def load_mapping(source: str | os.PathLike[str], *, start: str | os.PathLike[str] | None = None) -> TableMapping:
    """Reads a mapping file and checks it against every rule, raising MappingError that lists all the problems.

    `source` is a table name (`catalog.schema.table`), which is looked for with `find_mapping` from `start`, or the path of a file. Raises FileNotFoundError when the file is not there.
    """
    if is_path(source):
        path = Path(source)
    else:
        name = str(source)
        found = find_mapping(name, start)
        if found is None:
            raise FileNotFoundError(f"no {FOLDER}/{name}{SUFFIX} in {Path(start if start is not None else Path.cwd()).resolve()} or any folder above it")

        path = found

    data = yaml_module().safe_load(path.read_text(encoding="utf-8"))
    return parse_mapping(data)

def save_mapping(mapping: TableMapping, path: str | os.PathLike[str] | None = None, *, folder: str | os.PathLike[str] | None = None) -> Path:
    """Writes a mapping as YAML and returns the path. Without a path, the file goes to `bhom-mappings/<source>.yml` in `folder` (the current one by default).

    The data is read back and checked before anything is written, so a file that would not load is never saved. The file is replaced in one step.
    """
    data = mapping_to_data(mapping)
    parse_mapping(data)
    target = Path(path) if path is not None else mapping_path(mapping.source, folder)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = yaml_module().safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=None, width=160)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(target)
    return target
