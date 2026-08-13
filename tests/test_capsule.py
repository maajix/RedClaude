"""The bounded capsule: what a rotated session inherits, and what it costs.

Ticket 28's third and sixth criteria are the two this file is about, and both
are properties of a document rather than of a database:

* a session that is replaced leaves nothing behind but rows, so everything the
  replacement needs has to be recompilable from those rows -- and a compile is
  testable without a server, because what it is is a fixed set of statements and
  a fitter. A fake connection records the statements and answers them.
* the capsule is measured, and a capsule over its ceiling is compacted or
  refused. Compaction is stated rather than silent: a section cut down says how
  many rows it is not carrying, so a shortened capsule cannot be read as a full
  one.

What needs a server -- that these statements are valid SQL against the schema,
that a campaign really rotates at its ceilings, and that the capsule a second
runtime compiles matches the first -- is in `tests/test_database.py`.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from redkraken import capsule, integrity, packet, pg

PROGRAM = "11111111-1111-4111-8111-111111111111"


def record(kind: str, label: str, **fields) -> dict:
    return {"kind": kind, "label": label, **fields}


def read_row(label: str, revision: int, **fields) -> tuple:
    """One row as a read section's statement answers it: label, revision, digest, record.

    The digest is the server's, which here means it is whatever this fixture
    says it is. That is the point of asserting on it: a compile that hashed the
    record in Python would disagree with a row the database can re-check.
    """
    document = record("read", label, **fields)
    return (label, revision, f"{label}-digest", json.dumps(document))


def check(name: str, ok: bool = True, detail: str = "") -> integrity.Check:
    return integrity.Check(integrity.STANDING_FAMILY, name, ok, detail)


def entry(ordinal: int, kind: str = "recon") -> dict:
    """One Slate entry in the shape `offer_slate` hands the scheduler."""
    return {
        "ordinal": ordinal,
        "task": f"T{ordinal}",
        "kind": kind,
        "entity": "EN1",
        "priority": "0.500000",
        "outstanding": ordinal == 1,
    }


def digest_of(document: object) -> str:
    return hashlib.sha256(json.dumps(document).encode()).hexdigest()


class Recorder:
    """A connection answering the capsule's reads, keyed on the whole statement.

    Keyed on the whole statement for the same reason `test_packet` keys its own
    that way: `program_capacity` and `lane_budget` are read with statements that
    differ only in the view they name, and a loose match would answer one with
    the other's rows.
    """

    def __init__(
        self,
        *,
        revision: int = 7,
        program=None,
        campaign=None,
        capacity=None,
        lanes=None,
        work=None,
        working: int | None = None,
        digests: int | None = None,
        standing=None,
        fails: tuple[str, ...] = (),
    ):
        self.calls: list[tuple[str, tuple]] = []
        self.revision = revision
        self.program = [read_row("matrix-web", 12)] if program is None else program
        self.campaign = [read_row("OS4", 0)] if campaign is None else campaign
        self.capacity = [read_row("program", 0)] if capacity is None else capacity
        self.lanes = [read_row("recon", 0)] if lanes is None else lanes
        self.work = [read_row("T9", 8)] if work is None else work
        self.working = len(self.work) if working is None else working
        # How many of the records it was sent this server digests. Short by one
        # is a server that answered a different question, which the compile has
        # to notice rather than zip past.
        self.digests = digests
        self.standing = [("orchestrator_rotation", 0, "")] if standing is None else standing
        self.fails = fails

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.calls.append((sql, parameters))
        if sql in self.fails:
            raise pg.DatabaseError({"C": "42501", "M": "permission denied"})
        return pg.Result(columns=(), rows=tuple(self._answer(sql, parameters)), tag="SELECT")

    @property
    def statements(self) -> list[str]:
        return [sql for sql, _ in self.calls]

    def sent(self, statement: str) -> list[tuple]:
        return [parameters for sql, parameters in self.calls if sql == statement]

    def _answer(self, sql: str, parameters: tuple) -> list[tuple]:
        if sql == capsule.REVISION:
            return [] if self.revision is None else [(self.revision,)]
        if sql == capsule.PROGRAM:
            return list(self.program)
        if sql == capsule.CAMPAIGN:
            return list(self.campaign)
        if sql == capsule.CAPACITY:
            return list(self.capacity)
        if sql == capsule.LANES:
            return list(self.lanes)
        if sql == capsule.WORK:
            return list(self.work)[: parameters[1]]
        if sql == capsule.WORK_COUNT:
            return [(self.working,)]
        if sql == capsule.DIGESTS:
            sent = json.loads(parameters[0])
            answered = [
                (position, digest_of(element))
                for position, element in enumerate(sent, start=1)
            ]
            return answered if self.digests is None else answered[: self.digests]
        if sql == f"SELECT name, problems, detail FROM {integrity.STANDING}()":
            return list(self.standing)
        raise AssertionError(f"the compile asked something unplanned: {sql}")


def compiled(connection: Recorder, **overrides) -> capsule.Capsule:
    settings: dict = {
        "session": "OS4",
        "generation": 4,
        "checks": (check("orchestrator_rotation"),),
        "slate": (entry(1),),
    }
    settings.update(overrides)
    return capsule.compile(connection, PROGRAM, **settings)


class CompileTest(unittest.TestCase):
    """What the compile asks, and what it makes of the answers."""

    def test_the_capsule_carries_the_five_sections_the_spec_names(self):
        built = compiled(Recorder())

        self.assertEqual(list(capsule.SECTIONS), list(built.as_dict()["sections"]))
        self.assertEqual(
            ["matrix-web", "OS4"], [row.label for row in built.section("lifecycle").rows]
        )
        self.assertEqual(
            ["program", "recon"], [row.label for row in built.section("budget").rows]
        )
        self.assertEqual(["T9"], [row.label for row in built.section("work").rows])

    def test_every_read_names_the_program_it_means(self):
        # The capsule is compiled on the runtime connection, which sees every
        # Program's rows -- so unlike a packet, nothing scopes these reads but
        # the argument. One that forgot it would compile a capsule out of the
        # whole store and it would still look like a capsule.
        connection = Recorder()
        compiled(connection)

        for sql in (capsule.REVISION, capsule.PROGRAM, capsule.CAMPAIGN,
                    capsule.CAPACITY, capsule.LANES, capsule.WORK, capsule.WORK_COUNT):
            self.assertEqual([PROGRAM], [sent[0] for sent in connection.sent(sql)], sql)

    def test_no_transcript_is_read_and_none_is_carried(self):
        # Criterion 4: the resume needs no turn of the closed session. The
        # statements are the whole of what a capsule is made from, so a compile
        # that reached for `agent_runs` history would show up here as a
        # statement this fixture never planned an answer for.
        built = compiled(Recorder())

        self.assertNotIn("transcript", json.dumps(built.as_dict()))
        self.assertEqual(
            {"read", "integrity", "recon"},
            {str(row.record.get("kind")) for row in built.rows()},
        )

    def test_the_checks_the_pass_already_ran_are_not_run_again(self):
        connection = Recorder()
        compiled(connection, checks=(check("lease_discipline"),))

        self.assertNotIn(
            f"SELECT name, problems, detail FROM {integrity.STANDING}()",
            connection.statements,
        )

    def test_a_capsule_given_no_checks_reads_them_rather_than_saying_nothing(self):
        # An empty integrity section reports a sound Program by omission, which
        # is the one thing a section about soundness must not do.
        connection = Recorder(standing=[("event_coverage", 2, "two tables")])
        built = compiled(connection, checks=None)
        stated = built.section("integrity").rows[0].record

        self.assertEqual("standing:event_coverage", built.section("integrity").rows[0].label)
        self.assertEqual(False, stated["ok"])
        self.assertIn("two tables", stated["detail"])

    def test_a_failed_check_sorts_ahead_of_a_sound_one(self):
        built = compiled(
            Recorder(),
            checks=(check("event_coverage"), check("lease_discipline", False, "1 open")),
        )

        self.assertEqual(
            ["standing:lease_discipline", "standing:event_coverage"],
            [row.label for row in built.section("integrity").rows],
        )

    def test_the_revision_is_the_programs_high_water_event(self):
        built = compiled(Recorder(revision=41))

        self.assertEqual(41, built.revision)
        self.assertEqual(("OS4", 4), (built.session, built.generation))

    def test_a_read_that_returned_no_row_is_refused_rather_than_guessed(self):
        with self.assertRaises(capsule.CapsuleError) as refused:
            compiled(Recorder(revision=None))

        self.assertIn("no row", str(refused.exception))

    def test_a_database_error_is_left_for_the_caller_to_report(self):
        # Not wrapped: the slice tells a refused read from a document that will
        # not fit, and a `CapsuleError` here would make them one case.
        with self.assertRaises(pg.DatabaseError):
            compiled(Recorder(fails=(capsule.WORK,)))


class DigestTest(unittest.TestCase):
    """Where a row's digest comes from, for the two sections built in Python."""

    def test_a_staged_rows_digest_is_the_servers_answer(self):
        connection = Recorder()
        built = compiled(connection)
        staged = built.section("slate").rows[0]

        self.assertEqual(digest_of(dict(staged.record)), staged.digest)
        self.assertEqual(0, staged.revision)
        self.assertEqual(2, len(connection.sent(capsule.DIGESTS)))

    def test_a_read_rows_digest_is_the_one_the_statement_returned(self):
        built = compiled(Recorder())

        self.assertEqual("matrix-web-digest", built.section("lifecycle").rows[0].digest)
        self.assertEqual(12, built.section("lifecycle").rows[0].revision)

    def test_a_server_that_digested_fewer_records_is_refused(self):
        # The failure this refutes is the quiet one: `zip` without `strict`
        # would pair the first digests with the first records and drop the rest,
        # and every row left would still look correctly hashed.
        with self.assertRaises(capsule.CapsuleError) as refused:
            compiled(Recorder(digests=0), checks=(), slate=(entry(1), entry(2)))

        self.assertIn("0 of 2 slate", str(refused.exception))

    def test_no_digest_is_asked_for_a_section_with_no_rows(self):
        connection = Recorder()
        compiled(connection, checks=(), slate=())

        self.assertEqual([], connection.sent(capsule.DIGESTS))


class SlateSectionTest(unittest.TestCase):
    """The Slate the pass was offered, carried rather than read a second time."""

    def test_the_entries_keep_the_names_and_the_kind_they_arrived_with(self):
        # `kind` is the Task's, and it is the word the choice is made on. A
        # section marker written over it would tell the model every entry was a
        # "slate", which is the one thing it can already see.
        offered = (entry(1, kind="verify"), entry(2))
        built = compiled(Recorder(), slate=offered)

        self.assertEqual(list(offered), built.slate())
        self.assertEqual(["verify", "recon"], [item["kind"] for item in built.slate()])
        self.assertEqual(["T1", "T2"], [row.label for row in built.section("slate").rows])

    def test_the_slate_is_not_read_from_the_database(self):
        # `offer_slate` consumed the outstanding Slate to produce these entries.
        # A capsule that read it back would either re-read what this pass is
        # about to hand out or quietly offer a second one.
        connection = Recorder()
        compiled(connection)

        self.assertEqual(
            {capsule.REVISION, capsule.PROGRAM, capsule.CAMPAIGN, capsule.CAPACITY,
             capsule.LANES, capsule.WORK, capsule.WORK_COUNT, capsule.DIGESTS},
            set(connection.statements),
        )

    def test_the_brief_drops_the_slate_and_keeps_everything_else(self):
        built = compiled(Recorder())
        brief = built.brief()

        self.assertEqual(
            ["lifecycle", "budget", "integrity", "work"], list(brief["sections"])
        )
        self.assertEqual(built.revision, brief["revision"])
        self.assertEqual(list(capsule.SECTIONS), list(built.as_dict()["sections"]))
        self.assertNotIn("T1", json.dumps(brief))


class BoundTest(unittest.TestCase):
    """Criterion 6: measured, then compacted or refused."""

    def test_a_capsule_under_its_ceiling_omits_nothing(self):
        built = compiled(Recorder())

        self.assertLessEqual(built.bytes, built.limits.byte_ceiling)
        self.assertEqual(
            [0, 0, 0, 0, 0],
            [body["omitted"] for body in built.as_dict()["sections"].values()],
        )

    def test_work_states_what_it_is_not_carrying_when_more_is_running(self):
        # The one section whose total is measured rather than counted: the row
        # limit cuts the read itself, so without the count a capsule listing
        # five running Tasks would claim five were running.
        built = compiled(
            Recorder(work=[read_row(f"T{n}", 1) for n in range(3)], working=9),
            limits=packet.Limits(rows=2),
        )
        body = built.as_dict()["sections"]["work"]

        self.assertEqual(2, len(body["rows"]))
        self.assertEqual(9, body["total"])
        self.assertEqual(7, body["omitted"])

    def test_a_capsule_over_its_ceiling_is_compacted_until_it_fits(self):
        connection = Recorder(work=[read_row(f"T{n}", 1, note="x" * 40) for n in range(12)])
        built = compiled(connection, limits=packet.Limits(byte_limit=2048))

        self.assertLessEqual(built.bytes, 2048)
        self.assertLess(len(built.section("work").rows), 12)
        self.assertEqual(12, built.section("work").total)
        self.assertGreater(built.as_dict()["sections"]["work"]["omitted"], 0)

    def test_the_smaller_of_the_two_ceilings_is_the_one_that_binds(self):
        # `Limits` states bytes and tokens separately and they do not have to
        # agree. A capsule that honoured only the byte limit would satisfy the
        # configuration and still crowd out the child's first turn.
        connection = Recorder(work=[read_row(f"T{n}", 1, note="x" * 40) for n in range(12)])
        built = compiled(
            connection, limits=packet.Limits(byte_limit=65536, token_limit=400)
        )

        self.assertLessEqual(built.tokens, 400)
        self.assertLessEqual(built.bytes, 1600)

    def test_a_ceiling_below_the_empty_document_is_refused_not_emptied(self):
        # Nothing left to drop and still over: a capsule of no rows would be a
        # session started against a bound the runtime quietly broke.
        with self.assertRaises(capsule.CapsuleError) as refused:
            compiled(Recorder(), limits=packet.Limits(byte_limit=64))

        self.assertIn("does not fit", str(refused.exception))
        self.assertIn("64", str(refused.exception))

    def test_the_measurement_is_of_the_document_that_is_actually_sent(self):
        built = compiled(Recorder())

        self.assertEqual(
            len(json.dumps(built.as_dict(), separators=(",", ":"), default=str)),
            built.bytes,
        )
        self.assertEqual(-(-built.bytes // packet.BYTES_PER_TOKEN), built.tokens)


class DocumentTest(unittest.TestCase):
    """What crosses into the child, and what the child does with a bad one."""

    def test_a_capsule_survives_the_round_trip_the_boundary_puts_it_through(self):
        built = compiled(Recorder(), slate=(entry(1), entry(2)))

        again = capsule.Capsule.from_dict(json.loads(json.dumps(built.as_dict())))

        self.assertEqual(built.as_dict(), again.as_dict())
        self.assertEqual(built.slate(), again.slate())
        self.assertEqual(built.limits.byte_ceiling, again.limits.byte_ceiling)

    def test_an_empty_capsule_is_a_capsule(self):
        # What a child launched by something that had none is given, and it has
        # to read as "nothing inherited" rather than as a malformed document.
        empty = capsule.Capsule.from_dict(capsule.Capsule().as_dict())

        self.assertEqual([], empty.slate())
        self.assertEqual([], empty.rows())
        self.assertEqual(1, empty.generation)

    def test_a_section_the_child_does_not_know_is_dropped_rather_than_carried(self):
        document = capsule.Capsule().as_dict()
        document["sections"]["transcript"] = {"total": 1, "rows": []}

        self.assertEqual(
            list(capsule.SECTIONS),
            list(capsule.Capsule.from_dict(document).as_dict()["sections"]),
        )

    def test_a_malformed_capsule_fails_when_it_is_read(self):
        # The child has no database to check the document against, so the shape
        # is the only thing it can check -- and a missing key has to fail at the
        # boundary rather than three turns into a session.
        document = compiled(Recorder()).as_dict()
        del document["sections"]["work"]["rows"][0]["digest"]

        with self.assertRaises(capsule.CapsuleError) as refused:
            capsule.Capsule.from_dict(document)

        self.assertIn("not a capsule", str(refused.exception))

    def test_anything_that_is_not_a_document_is_refused_as_one(self):
        for document in ({"sections": 3}, {"limits": 3}, {"generation": "many"}):
            with self.subTest(document=document):
                with self.assertRaises(capsule.CapsuleError):
                    capsule.Capsule.from_dict(document)


if __name__ == "__main__":
    unittest.main()
