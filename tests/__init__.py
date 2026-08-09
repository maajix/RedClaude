"""The repository test suite.

A package, so that `python3 -m unittest discover` runs every module, test
modules can share fixtures by import, and the application is put on the import
path from a source checkout in exactly one place.
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"

if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))
