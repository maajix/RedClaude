"""The shipped v1 ledger, and a way to write a broken copy of it somewhere else.

Shared by the row gate's tests and the closing gate's, because both of them ask
the same kind of question: what does the checker say when one row of the real
ledger is missing, changed or duplicated? Reading the real file rather than
building a small one is the point -- a fixture ledger would agree with whatever
the fixture author believed, and these gates exist to catch the day the ledger
and the tree stop agreeing.

Neither function writes anything the caller did not name, and `written` writes
only into a directory it is handed, so the shipped ledger is never the copy
under test.
"""

import csv
from pathlib import Path

from tests import ROOT


LEDGER = ROOT / "baseline" / "v1-dispositions.tsv"
INTAKE = ROOT / "baseline" / "technique-intake.tsv"
MODES = ROOT / "baseline" / "multiagent-modes.tsv"


def table_rows(path: Path, without: str | None = None) -> list[list[str]]:
    """One shipped table as raw rows, optionally missing the row keyed on a value.

    Raw rather than dictionaries because these are the inputs to negatives: a
    test that deletes a column or widens a row has to be able to write something
    the reader will refuse, and a dictionary cannot hold a malformed row.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.reader(handle, delimiter="\t") if row[0] != without]


def ledger_rows(without: str | None = None) -> list[list[str]]:
    """The shipped disposition ledger, optionally missing the row for one source."""
    return table_rows(LEDGER, without)


def intake_rows(without: str | None = None) -> list[list[str]]:
    """The shipped intake ledger, optionally missing the row for one technique."""
    return table_rows(INTAKE, without)


def written(
    rows: list[list[str]], directory: str, name: str = "v1-dispositions.tsv"
) -> Path:
    """Those rows as a table inside `directory`, in the format the gates read."""
    path = Path(directory) / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(
            handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE
        ).writerows(rows)
    return path
