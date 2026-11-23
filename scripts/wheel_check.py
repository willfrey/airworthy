"""Check that a built wheel ships the package's py.typed marker."""

import sys
import zipfile
from pathlib import Path
from typing import Final

MARKER: Final = "airworthy/py.typed"


def main(wheel: Path) -> int:
    """Check that `wheel` contains the marker, printing why if not.

    Returns:
        0 when the wheel has the marker, else 1.
    """
    with zipfile.ZipFile(wheel) as archive:
        if MARKER not in archive.namelist():
            _ = sys.stderr.write(f"{wheel.name} is missing {MARKER}\n")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
