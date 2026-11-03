"""The version of an alpha release: the BHoM version of develop with a UTC time stamp, as a PEP 440 pre-release."""

from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path

BHOM_VERSION = re.compile(r'^__bhom_version__ = "(\d+\.\d+)"$', re.MULTILINE)
PACKAGE_VERSION = re.compile(r'^__version__ = ".*"$', re.MULTILINE)

def read_bhom_version(version_file: Path) -> str:
    """Returns the BHoM version (Major.Minor) that the generated _version.py holds.

    `alpha_version` builds the alpha from it.
    """
    match = BHOM_VERSION.search(version_file.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"{version_file} has no __bhom_version__ of the form Major.Minor")

    return match.group(1)

def alpha_version(bhom_version: str, released_tags: list[str], now: datetime | None = None) -> str:
    """Returns `Major.Minor.0aYYMMDDHHmm` for the BHoM version, with the UTC time of `now` (the current time when left out).

    Fails when the tag `vMajor.Minor.0` is among the released tags: the alpha would sort below that release, so develop must first move to the next BHoM version.
    The alpha workflow calls it.
    """
    if f"v{bhom_version}.0" in released_tags:
        raise ValueError(
            f"develop still reports BHoM {bhom_version}, which is already released as v{bhom_version}.0, so an alpha would sort below that release. "
            "Bump the BHoM version on develop to the next Major.Minor and let the next generation write it, then run the alpha again."
        )

    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"{bhom_version}.0a{moment:%y%m%d%H%M}"

def stamp_version_file(version_file: Path, version: str) -> None:
    """Writes the version as `__version__` into _version.py, replacing the development version.

    The alpha workflow does it in its own checkout only, so develop keeps its development version.
    """
    text = version_file.read_text(encoding="utf-8")
    stamped, count = PACKAGE_VERSION.subn(f'__version__ = "{version}"', text)
    if count != 1:
        raise ValueError(f"{version_file} must have exactly one __version__ line")

    # newline="" keeps the LF endings of the generated file
    with version_file.open("w", encoding="utf-8", newline="") as stream:
        stream.write(stamped)
