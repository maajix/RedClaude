"""Bounded state reads: everything answerable without a server.

Two seams are pure and both are load-bearing. `bound` is the one that decides
what a caller is not told: given every entry a read returned and a byte
ceiling, it drops until the answer fits and reports how many it dropped, which
is the difference between a bounded read and a truncated one. `Compact.summary`
is the shape that carries it, and it names every kind whether or not the
Program holds one, so a reader cannot mistake "none" for "not asked about".

The other thing testable here is the property ticket 05 states about arguments
rather than about rows: no read verb takes a Program, and none sends one. A
fake connection records what was asked, so that is an assertion about the SQL
this module emits rather than about a convention someone has to keep.

What needs a server -- that two Programs holding the same label do not see each
other's rows, and that reading twice changes nothing -- is in
`tests/test_database.py`.
"""

from __future__ import annotations

import inspect
import json
import unittest
from unittest import mock

from redkraken import pg, state
from redkraken.outcome import EXIT_DATABASE_UNREACHABLE, EXIT_INVALID_CONFIGURATION
from tests.fixtures import VALID, write


UNREACHABLE = "postgresql://rk2_runtime@127.0.0.1:1/rk2"


def settings() -> pg.Settings:
    return pg.settings_from_url(UNREACHABLE, application_name="rk state")


def entry(kind: str, number: int, revision: int) -> state.Entry:
    return state.Entry(
        kind=kind,
        label=f"{kind[0].upper()}{number}",
        revision=revision,
        digest=f"{number:064x}",
    )


class Recorder:
    """A connection that answers with canned rows and remembers what it was asked."""

    def __init__(self, answers: dict[str, list[tuple]] | None = None):
        self.calls: list[tuple[str, tuple]] = []
        self.answers = answers or {}

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.calls.append((sql, parameters))
        for fragment, rows in self.answers.items():
            if fragment in sql:
                return pg.Result(columns=(), rows=tuple(rows), tag="SELECT")
        return pg.Result(columns=(), rows=(), tag="SELECT")


class BoundTest(unittest.TestCase):
    """What a caller is not told, and how the answer says so."""

    def test_everything_that_fits_is_returned_and_nothing_is_marked_omitted(self):
        entries = [entry("entity", n, n) for n in range(3)]

        compact = state.bound(entries, {"entity": 3}, byte_limit=state.DEFAULT_BYTES)

        self.assertEqual(3, len(compact.entries))
        self.assertEqual(
            0, sum(item["omitted"] for item in compact.summary()["kinds"])
        )

    def test_rows_the_program_holds_beyond_the_row_limit_are_counted_as_omitted(self):
        # The count comes from the database and the entries from a capped read,
        # so the marker is the difference between them: a caller is told the
        # size of what it was not shown, which is the whole point of the marker.
        entries = [entry("entity", n, n) for n in range(2)]

        compact = state.bound(entries, {"entity": 40}, byte_limit=state.DEFAULT_BYTES)

        kinds = {item["kind"]: item for item in compact.summary()["kinds"]}
        self.assertEqual(40, kinds["entity"]["count"])
        self.assertEqual(2, kinds["entity"]["returned"])
        self.assertEqual(38, kinds["entity"]["omitted"])

    def test_a_byte_ceiling_drops_entries_and_says_it_did(self):
        entries = [entry("entity", n, n) for n in range(20)]

        compact = state.bound(entries, {"entity": 20}, byte_limit=400)

        self.assertLessEqual(compact.bytes, 400)
        self.assertLess(len(compact.entries), 20)
        kinds = {item["kind"]: item for item in compact.summary()["kinds"]}
        self.assertEqual(20 - len(compact.entries), kinds["entity"]["omitted"])

    def test_the_ceiling_is_spent_across_kinds_rather_than_on_the_first_one(self):
        # A read that spent its whole budget on entities would report a Program
        # with no findings in it, which is a different claim from "not shown".
        entries = [entry("entity", n, n) for n in range(20)]
        entries += [entry("finding", n, n) for n in range(20)]

        compact = state.bound(
            entries, {"entity": 20, "finding": 20}, byte_limit=600
        )

        kinds = {item.kind for item in compact.entries}
        self.assertEqual({"entity", "finding"}, kinds)

    def test_the_stalest_entry_of_a_kind_is_the_one_dropped(self):
        # Entries arrive newest-revision first. Dropping from the tail is what
        # makes a bounded read carry the part of the state that just moved.
        entries = [entry("entity", n, 100 - n) for n in range(20)]

        compact = state.bound(entries, {"entity": 20}, byte_limit=400)

        revisions = [item.revision for item in compact.entries]
        self.assertEqual(sorted(revisions, reverse=True), revisions)
        self.assertEqual(100, revisions[0])

    def test_a_ceiling_nothing_fits_under_returns_nothing_and_omits_everything(self):
        entries = [entry("entity", n, n) for n in range(4)]

        compact = state.bound(entries, {"entity": 4}, byte_limit=1)

        self.assertEqual((), compact.entries)
        self.assertEqual(0, compact.bytes)
        kinds = {item["kind"]: item for item in compact.summary()["kinds"]}
        self.assertEqual(4, kinds["entity"]["omitted"])

    def test_the_reported_size_is_never_over_the_ceiling_that_produced_it(self):
        # Including the ceilings nothing fits under. A read that answered with
        # no records and a size over the limit would be reporting a bound it did
        # not meet, which is worse than a bound it could not meet.
        entries = [entry(kind, n, n) for kind in ("entity", "finding") for n in range(8)]

        for byte_limit in (0, 1, 2, 3, 60, 200, 1000, state.DEFAULT_BYTES):
            with self.subTest(byte_limit):
                compact = state.bound(entries, {"entity": 8, "finding": 8}, byte_limit=byte_limit)

                self.assertLessEqual(compact.bytes, byte_limit)

    def test_every_kind_is_named_whether_or_not_the_program_holds_one(self):
        compact = state.bound([], {}, byte_limit=state.DEFAULT_BYTES)

        self.assertEqual(
            list(state.KINDS), [item["kind"] for item in compact.summary()["kinds"]]
        )
        self.assertEqual(0, sum(item["count"] for item in compact.summary()["kinds"]))

    def test_the_reported_size_is_the_size_of_what_was_returned(self):
        entries = [entry("entity", n, n) for n in range(5)]

        compact = state.bound(entries, {"entity": 5}, byte_limit=state.DEFAULT_BYTES)

        rendered = json.dumps(compact.summary()["records"], separators=(",", ":"))
        self.assertEqual(len(rendered.encode("utf-8")), compact.bytes)


class ArgumentTest(unittest.TestCase):
    """Criterion 2, where it can be asserted rather than described.

    A Program is bound to the session by the runtime. If a read verb could take
    one, the binding would be advice; the isolation would rest on every caller
    passing the right value, and one wrong value would read another Program.
    """

    def test_no_read_verb_takes_a_program(self):
        for verb in (state.records, state.record):
            with self.subTest(verb.__name__):
                names = list(inspect.signature(verb).parameters)
                self.assertEqual("connection", names[0])
                self.assertEqual(
                    [], [name for name in names if "program" in name.lower()]
                )

    def test_the_compact_read_sends_no_identifier(self):
        connection = Recorder()

        state.records(connection)

        for sql, parameters in connection.calls:
            with self.subTest(sql[:40]):
                self.assertNotIn("program", sql.lower())
                self.assertEqual(
                    [], [value for value in parameters if _looks_like_a_uuid(value)]
                )

    def test_a_record_read_sends_the_label_and_nothing_else(self):
        connection = Recorder()

        state.record(connection, "H1")

        self.assertEqual(1, len(connection.calls))
        sql, parameters = connection.calls[0]
        self.assertEqual(("H1",), parameters)
        self.assertNotIn("program", sql.lower())

    def test_a_label_no_row_carries_is_absent_rather_than_an_error(self):
        self.assertIsNone(state.record(Recorder(), "H404"))


class ReadTest(unittest.TestCase):
    """What the command does before it has anything to report."""

    def test_a_configuration_that_does_not_validate_never_opens_a_connection(self):
        source = write(VALID.replace("requests = 5000", "requests = -1"))

        with mock.patch.object(pg, "connect", side_effect=AssertionError("connected")) as opened:
            result = state.read(settings(), settings(), source)

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = state.read(settings(), settings(), write(VALID))

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.exit_code)

    def test_every_refusal_reports_the_same_keys_a_read_reports(self):
        results = (
            state.read(
                settings(),
                settings(),
                write(VALID.replace("requests = 5000", "requests = -1")),
            ),
            state.read(settings(), settings(), write(VALID)),
        )

        for result in results:
            with self.subTest(result.violations[0].code):
                self.assertEqual(set(state.FACTS), set(result.facts))

    def test_the_report_carries_no_value_out_of_the_configuration(self):
        result = state.read(settings(), settings(), write(VALID))

        rendered = repr(result.as_dict())
        for secret in ("app.example.com", "slot://identity/member", "X-Bounty-Id"):
            self.assertNotIn(secret, rendered)


def _looks_like_a_uuid(value: object) -> bool:
    text = str(value)
    return len(text) == 36 and text.count("-") == 4


if __name__ == "__main__":
    unittest.main()
