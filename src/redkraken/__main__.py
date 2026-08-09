"""`python -m redkraken` runs the same command line as the installed `rk`."""

import sys

from redkraken.cli import main


if __name__ == "__main__":
    sys.exit(main())
