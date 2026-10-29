from __future__ import annotations

import pytest

from support import attach, require_output


@pytest.fixture(scope="session", autouse=True)
def spike_package():
    """Session fixture, applied automatically to the spike suite: locates the generated 'spike' package (real BHoM types), attaches it so imports resolve to it, and returns its folder.

    Every test in `test_spike` relies on it to import the generator's output for the real oM assemblies.
    """
    package = require_output("spike")
    attach(package)
    return package
