from __future__ import annotations

import pytest

from support import attach, require_output


@pytest.fixture(scope="session", autouse=True)
def fixtures_package():
    """Session fixture, applied automatically to the fixture suite: locates the generated 'fixtures' package, attaches it so imports resolve to it, and returns its folder.

    Every test in `test_fixtures` relies on it to import the generator's output for the fixture assemblies.
    """
    package = require_output("fixtures")
    attach(package)
    return package
