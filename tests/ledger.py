"""The shipped v1 ledger, and a way to write a broken copy of it somewhere else.

Shared by the row gate's tests and the closing gate's, because both of them ask
the same kind of question: what does the checker say when one row of the real
ledger is missing, changed or duplicated? Reading the real file rather than
building a small one is the point -- a fixture ledger would agree with whatever
the fixture author believed, and these gates exist to catch the day the ledger
and the tree stop agreeing.

Neither function writes anything the caller did not name, and the two writers
write only into a directory they are handed, so the shipped ledger is never the
copy under test.
"""

import csv
import json
from pathlib import Path

from tests import ROOT


LEDGER = ROOT / "baseline" / "v1-dispositions.tsv"
INTAKE = ROOT / "baseline" / "technique-intake.tsv"
MODES = ROOT / "baseline" / "multiagent-modes.tsv"
REVIEW = ROOT / "baseline" / "final-review.tsv"
TECHNIQUES = ROOT / "baseline" / "technique-ledger.jsonl"
SOURCES = ROOT / "baseline" / "technique-sources.tsv"


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


def technique_records(without: str | None = None) -> list[dict]:
    """The shipped corpus ledger, optionally missing the record with one id.

    Dictionaries rather than raw lines, because a record is JSON already: the
    negatives here change a field or repeat an id, which is what a reader that
    parsed the line can do and a reader holding the text cannot.
    """
    return [
        record
        for line in TECHNIQUES.read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line))["id"] != without
    ]


def source_rows(without: str | None = None) -> list[list[str]]:
    """The shipped sources table, optionally missing the row with one id."""
    return table_rows(SOURCES, without)


def written_records(
    records: list[dict], directory: str, name: str = "technique-ledger.jsonl"
) -> Path:
    """Those records as one file inside `directory`, in the form the gate reads."""
    path = Path(directory) / name
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


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
