from __future__ import annotations

from pathlib import Path

from helpers import module, package
from py2cs.reader import read_package

def test_reader_skips_the_hand_written_tables_mapping_and_support_folders(tmp_path: Path):
    """Checks that read_package reads the generated class and ignores every module under `tables`, `mapping` and `_support`, even one that is not a valid class.

    Protects the generator's tooling (manifest, diff, verify) from taking the hand-written table and mapping helpers for schema classes.
    """
    pkg = package(tmp_path, {
        "Demo_oM/Thing.py": module("Thing", "BH.oM.Demo.Thing", "BH.oM.Demo", "Demo_oM"),
        "tables/columns.py": "class NotASchemaClass:\n    pass\n",
        "tables/deeper/more.py": "x = 1\n",
        "mapping/model.py": "class First:\n    pass\n\nclass Second:\n    pass\n",
        "_support/helper.py": "class AlsoNot:\n    pass\n",
    })

    manifest = read_package(pkg)

    assert list(manifest) == ["BH.oM.Demo.Thing"]
