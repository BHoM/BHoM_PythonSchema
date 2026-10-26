from __future__ import annotations

import pytest

from support import attach, require_output


@pytest.fixture(scope="session", autouse=True)
def fixtures_package():
    package = require_output("fixtures")
    attach(package)
    return package
