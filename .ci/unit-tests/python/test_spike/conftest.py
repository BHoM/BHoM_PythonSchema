from __future__ import annotations

import pytest

from support import attach, require_output


@pytest.fixture(scope="session", autouse=True)
def spike_package():
    package = require_output("spike")
    attach(package)
    return package
