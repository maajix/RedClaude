"""Content-addressed artifacts: everything answerable without a server.

Four seams are pure and each one carries a criterion.

`digest` is the identifier: ticket 06 says it is the SHA-256 of the exact
plaintext bytes, which is a claim a test can hold against `hashlib` rather than
against itself. `window` is the bounded read, and its tests are about the
subtraction -- what was left before the range, what was left after it, and that
the three numbers always add up to the artifact, so a caller working from a
range knows it is a range. `Store` is the backing data, and the interesting
cases are the two ways it can be wrong: bytes that are not there, and bytes that
are there and do not hash to the name they are filed under. Both fail closed,
including when the caller asked for a range that does not overlap the damage --
the whole plaintext is verified, or nothing is returned.

The fourth is the property ticket 06 states about arguments rather than about
rows: the agent-facing read takes a label. A verb taking a hash would read
across Programs whenever the caller could guess the bytes, which for a
content-addressed store is the ordinary case rather than an unlikely one.

What needs a server -- that two Programs storing identical plaintext get one
artifact and two references, and that a bare hash from the other Program reveals
neither existence nor content -- is in `tests/test_database.py`.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import unittest
from pathlib import Path
from unittest import mock

from redkraken import artifact, pg
from redkraken.outcome import EXIT_DATABASE_UNREACHABLE, EXIT_INVALID_CONFIGURATION
from tests.fixtures import VALID, scratch, write


UNREACHABLE = "postgresql://rk2_runtime@127.0.0.1:1/rk2"

#: A body long enough that every window case is a proper subset of it.
BODY = b"".join(f"line {number}\n".encode() for number in range(64))


def settings() -> pg.Settings:
    return pg.settings_from_url(UNREACHABLE, application_name="rk artifact")


def key(data: bytes = bytes(range(32))) -> Path:
    """A key file this process will use: readable by its owner and nobody else."""
    path = scratch() / "artifact.key"
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def store() -> artifact.Store:
    return artifact.Store(scratch() / "artifacts")


class Recorder:
    """A connection that answers nothing and remembers what it was asked.

    The empty answer is the whole fixture: both cases below are about the
    statement the read sends, and one of them is about a label no row carries.
    A canned-row facility went with them for a while, keyed on a fragment of
    the statement -- nothing here ever asked for one, and a fake that matches
    statements by substring answers the wrong one as soon as two of them share
    a word.
    """

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.calls.append((sql, parameters))
        return pg.Result(columns=(), rows=(), tag="SELECT")


class DigestTest(unittest.TestCase):
    """The identifier is the hash of the plaintext, and of nothing else."""

    def test_the_identifier_is_the_sha256_of_the_exact_bytes(self):
        self.assertEqual(hashlib.sha256(BODY).hexdigest(), artifact.digest(BODY))

    def test_it_is_lowercase_hex_of_the_length_the_column_accepts(self):
        value = artifact.digest(BODY)

        self.assertEqual(64, len(value))
        self.assertEqual(value.lower(), value)
        self.assertTrue(set(value) <= set("0123456789abcdef"))

    def test_one_byte_is_enough_to_change_it(self):
        self.assertNotEqual(artifact.digest(b"a"), artifact.digest(b"b"))

    def test_an_empty_artifact_still_has_one(self):
        self.assertEqual(hashlib.sha256(b"").hexdigest(), artifact.digest(b""))


class WindowTest(unittest.TestCase):
    """A bounded range, and the omission metadata that says it was bounded."""

    def test_a_ceiling_over_the_size_omits_nothing(self):
        view = artifact.window(len(BODY), offset=0, limit=len(BODY) * 2)

        self.assertEqual(0, view.omitted_before)
        self.assertEqual(0, view.omitted_after)
        self.assertEqual(len(BODY), view.length)
        self.assertTrue(view.complete)

    def test_a_ceiling_under_the_size_omits_the_tail(self):
        view = artifact.window(len(BODY), offset=0, limit=100)

        self.assertEqual(100, view.length)
        self.assertEqual(0, view.omitted_before)
        self.assertEqual(len(BODY) - 100, view.omitted_after)
        self.assertFalse(view.complete)

    def test_an_offset_omits_the_head(self):
        view = artifact.window(len(BODY), offset=40, limit=len(BODY))

        self.assertEqual(40, view.omitted_before)
        self.assertEqual(len(BODY) - 40, view.length)
        self.assertEqual(0, view.omitted_after)
        self.assertFalse(view.complete)

    def test_the_three_numbers_always_add_up_to_the_artifact(self):
        for offset in (0, 1, 40, len(BODY) - 1, len(BODY)):
            for limit in (0, 1, 100, len(BODY), len(BODY) * 2):
                with self.subTest(offset=offset, limit=limit):
                    view = artifact.window(len(BODY), offset=offset, limit=limit)

                    self.assertEqual(
                        len(BODY),
                        view.omitted_before + view.length + view.omitted_after,
                    )

    def test_an_offset_past_the_end_returns_nothing_and_says_where_it_stopped(self):
        view = artifact.window(len(BODY), offset=len(BODY) * 3, limit=100)

        self.assertEqual(0, view.length)
        self.assertEqual(len(BODY), view.omitted_before)
        self.assertEqual(0, view.omitted_after)
        self.assertFalse(view.complete)

    def test_no_ceiling_returns_the_remainder(self):
        view = artifact.window(len(BODY), offset=10, limit=None)

        self.assertEqual(len(BODY) - 10, view.length)
        self.assertEqual(0, view.omitted_after)

    def test_an_empty_artifact_is_complete_at_zero_bytes(self):
        view = artifact.window(0, offset=0, limit=100)

        self.assertEqual(0, view.length)
        self.assertTrue(view.complete)

    def test_a_negative_bound_is_refused_rather_than_clamped(self):
        for offset, limit in ((-1, 10), (0, -1)):
            with self.subTest(offset=offset, limit=limit):
                with self.assertRaises(ValueError):
                    artifact.window(len(BODY), offset=offset, limit=limit)

    def test_the_summary_says_what_was_left_out(self):
        summary = artifact.window(len(BODY), offset=10, limit=20).summary()

        self.assertEqual(
            {
                "size": len(BODY),
                "offset": 10,
                "returned": 20,
                "omitted_before": 10,
                "omitted_after": len(BODY) - 30,
                "complete": False,
            },
            summary,
        )


class StoreTest(unittest.TestCase):
    """The backing data, and the two ways it can be wrong."""

    def test_the_path_is_the_first_two_characters_then_the_whole_hash(self):
        root = scratch()
        value = artifact.digest(BODY)

        path = artifact.path_for(root, value)

        self.assertEqual(root / value[:2] / value, path)

    def test_storing_the_same_plaintext_twice_writes_one_file(self):
        keep = store()

        first, written = keep.put(BODY)
        second, again = keep.put(BODY)

        self.assertEqual(first, second)
        self.assertTrue(written)
        self.assertFalse(again)
        self.assertEqual(1, len(list(keep.root.rglob("*"))) - 1)

    def test_what_is_read_back_is_what_was_written(self):
        keep = store()

        value, _ = keep.put(BODY)

        self.assertEqual(BODY, keep.load(value))

    def test_backing_data_that_is_not_there_fails_closed(self):
        with self.assertRaises(artifact.Missing):
            store().load(artifact.digest(BODY))

    def test_bytes_written_on_the_way_into_a_failed_write_can_be_discarded(self):
        # The one case `put` creates and cannot resolve. Discarding says whether
        # there was anything there, so a caller cannot mistake "already gone" for
        # "removed" -- and asking twice is not an error, because the state it
        # leaves behind is the state it was asked for.
        keep = store()
        value, _ = keep.put(BODY)

        self.assertTrue(keep.discard(value))
        self.assertFalse(artifact.path_for(keep.root, value).exists())
        self.assertFalse(keep.discard(value))
        with self.assertRaises(artifact.Missing):
            keep.load(value)

    def test_bytes_that_do_not_hash_to_their_name_fail_closed(self):
        keep = store()
        value, _ = keep.put(BODY)
        artifact.path_for(keep.root, value).write_bytes(BODY + b"tampered")

        with self.assertRaises(artifact.Corrupt) as raised:
            keep.load(value)

        self.assertIn(value, str(raised.exception))

    def test_a_range_is_verified_against_the_whole_plaintext(self):
        keep = store()
        value, _ = keep.put(BODY)
        artifact.path_for(keep.root, value).write_bytes(b"x" + BODY[1:])

        # The first byte is the damage and the range asked for is the tail, so a
        # reader that verified only what it returned would answer with corrupted
        # backing data and no sign of it.
        with self.assertRaises(artifact.Corrupt):
            keep.read(value, artifact.window(len(BODY), offset=10, limit=20))

    def test_a_range_of_intact_backing_data_is_the_slice_it_names(self):
        keep = store()
        value, _ = keep.put(BODY)

        chunk = keep.read(value, artifact.window(len(BODY), offset=10, limit=20))

        self.assertEqual(BODY[10:30], chunk)


class ArgumentTest(unittest.TestCase):
    """Criterion 4, where it can be asserted rather than described.

    `artifacts` is one global namespace keyed by the hash of the plaintext, so
    two Programs holding the same bytes hold the same key. What keeps that from
    being a cross-Program read is that the agent-facing verb has no way to say a
    hash: it takes a label, and a label is only resolvable through a reference
    the session's own Program holds.

    `holdings` does take a Program, and is the operator's enumeration on the
    runtime connection -- the role that owns the store and is not what isolation
    is measured on.
    """

    def test_the_agent_facing_read_takes_a_label_and_not_a_hash(self):
        names = list(inspect.signature(artifact.holding).parameters)

        self.assertEqual(["connection", "label"], names)
        self.assertEqual([], [name for name in names if "sha" in name or "hash" in name])

    def test_it_sends_the_label_and_nothing_else(self):
        connection = Recorder()

        artifact.holding(connection, "AF1")

        self.assertEqual(1, len(connection.calls))
        sql, parameters = connection.calls[0]
        self.assertEqual(("AF1",), parameters)
        self.assertNotIn("program", sql.lower())

    def test_a_label_no_reference_carries_is_absent_rather_than_an_error(self):
        self.assertIsNone(artifact.holding(Recorder(), "AF404"))


class CommandTest(unittest.TestCase):
    """What the three verbs do before they have anything to report."""

    def test_a_configuration_that_does_not_validate_never_opens_a_connection(self):
        source = write(VALID.replace("requests = 5000", "requests = -1"))
        payload = scratch() / "body.txt"
        payload.write_bytes(BODY)

        for name, call in self._verbs(source, payload):
            with self.subTest(name):
                with mock.patch.object(
                    pg, "connect", side_effect=AssertionError("connected")
                ) as opened:
                    result = call()

                opened.assert_not_called()
                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_a_source_file_that_is_not_there_is_refused_before_the_database(self):
        with mock.patch.object(
            pg, "connect", side_effect=AssertionError("connected")
        ) as opened:
            result = artifact.put(
                settings(), write(VALID), scratch() / "absent.bin", root=scratch()
            )

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        payload = scratch() / "body.txt"
        payload.write_bytes(BODY)

        for name, call in self._verbs(write(VALID), payload):
            with self.subTest(name):
                self.assertEqual(EXIT_DATABASE_UNREACHABLE, call().exit_code)

    def test_every_refusal_reports_the_same_keys_a_read_reports(self):
        payload = scratch() / "body.txt"
        payload.write_bytes(BODY)
        refused = write(VALID.replace("requests = 5000", "requests = -1"))

        for source in (refused, write(VALID)):
            for name, call in self._verbs(source, payload):
                with self.subTest(name, source=source.parent.name):
                    self.assertEqual(set(artifact.FACTS), set(call().facts))

    def test_nothing_is_written_to_the_store_before_the_bytes_are_named(self):
        root = scratch() / "artifacts"
        payload = scratch() / "body.txt"
        payload.write_bytes(BODY)

        artifact.put(settings(), write(VALID), payload, root=root)

        self.assertFalse(root.exists())

    def _verbs(self, source, payload):
        redacted = payload.parent / "redacted.txt"
        redacted.write_bytes(BODY.replace(b"line 3\n", b"[redacted]\n"))
        return (
            ("put", lambda: artifact.put(settings(), source, payload, root=scratch())),
            (
                "get",
                lambda: artifact.get(
                    settings(), settings(), source, root=scratch(), label="AF1"
                ),
            ),
            ("audit", lambda: artifact.audit(settings(), source, root=scratch())),
            (
                "seal",
                lambda: artifact.seal_wire(
                    settings(), source, payload, redacted, root=scratch(), key=key()
                ),
            ),
            (
                "open",
                lambda: artifact.open_wire(
                    settings(),
                    source,
                    root=scratch(),
                    key=key(),
                    label="AF1",
                    into=scratch() / "opened.bin",
                    authorize="a reason",
                ),
            ),
        )


class SealArgumentTest(unittest.TestCase):
    """PH2-07 §1 and §5, at the seams that need no server.

    Two properties are about the arguments themselves and hold before anything is
    read. The key material is named by a path, not carried in the configuration
    file the agent's own Program is described by, because §1 says the key lives
    outside Agent-visible configuration and a file the harness reads at startup is
    the definition of Agent-visible. And `open` takes a label, for the reason
    ticket 06 gave `get`: a verb taking a hash reads across Programs whenever the
    caller can guess the bytes.
    """

    def test_neither_verb_takes_a_hash(self):
        for name, function in (("seal", artifact.seal_wire), ("open", artifact.open_wire)):
            with self.subTest(name):
                names = list(inspect.signature(function).parameters)

                self.assertEqual([], [item for item in names if "sha" in item or "hash" in item])

    def test_the_key_is_a_path_of_its_own_and_not_a_configuration_key(self):
        for name, function in (("seal", artifact.seal_wire), ("open", artifact.open_wire)):
            with self.subTest(name):
                parameters = inspect.signature(function).parameters

                self.assertIn("key", parameters)
                self.assertEqual("Path", parameters["key"].annotation)
        self.assertNotIn("key", VALID)

    def test_opening_without_authorization_is_refused_before_a_connection(self):
        # §5. The refusal is recorded, so this cannot short-circuit the database
        # entirely -- what it can do is refuse before the plaintext is reached,
        # which is what the ordering below asserts against a live server.
        with mock.patch.object(pg, "connect", side_effect=AssertionError("connected")):
            with self.assertRaises(AssertionError):
                artifact.open_wire(
                    settings(),
                    write(VALID),
                    root=scratch(),
                    key=key(),
                    label="AF1",
                    into=scratch() / "opened.bin",
                )

    def test_key_material_this_process_will_not_use_is_refused_before_the_database(self):
        # A key file anyone else on the machine can read is a configuration
        # problem rather than a cryptographic one, and it is worth saying so
        # before a connection is opened: nothing that follows can repair it.
        loose = scratch() / "artifact.key"
        loose.write_bytes(bytes(range(32)))
        loose.chmod(0o644)

        with mock.patch.object(pg, "connect", side_effect=AssertionError("connected")) as opened:
            result = artifact.seal_wire(
                settings(),
                write(VALID),
                self._file("wire.txt", BODY),
                self._file("redacted.txt", BODY[:10]),
                root=scratch(),
                key=loose,
            )

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual("argument:--key", result.violations[0].source)

    def test_two_views_that_are_the_same_bytes_are_refused_as_one_view(self):
        # The table refuses it too -- `agent_sha256 <> sha256` -- but the useful
        # place to say so is here, where the report can name the argument to
        # change instead of quoting a constraint.
        same = self._file("wire.txt", BODY)

        with mock.patch.object(pg, "connect", side_effect=AssertionError("connected")) as opened:
            result = artifact.seal_wire(
                settings(),
                write(VALID),
                same,
                self._file("redacted.txt", BODY),
                root=scratch(),
                key=key(),
            )

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual("argument:--redacted", result.violations[0].source)

    def test_a_wire_file_that_is_not_there_names_the_argument_it_came_from(self):
        result = artifact.seal_wire(
            settings(),
            write(VALID),
            scratch() / "absent.bin",
            self._file("redacted.txt", BODY),
            root=scratch(),
            key=key(),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual("argument:--wire", result.violations[0].source)

    def test_the_plaintext_is_written_for_its_owner_alone_and_never_over_a_file(self):
        # The one place `open` puts plaintext on a disk. An existing file is a
        # refusal rather than a truncation, because a caller who named the wrong
        # path is more likely to have made a mistake than an instruction, and the
        # mistake destroys whatever was there.
        into = scratch() / "opened.bin"

        written = artifact._release(into, BODY)

        self.assertEqual(BODY, into.read_bytes())
        self.assertEqual(0o600, into.stat().st_mode & 0o777)
        self.assertEqual(into, written)
        with self.assertRaises(FileExistsError):
            artifact._release(into, b"something else")
        self.assertEqual(BODY, into.read_bytes())

    def _file(self, name: str, data: bytes) -> Path:
        path = scratch() / name
        path.write_bytes(data)
        return path


class ContentTest(unittest.TestCase):
    """How returned bytes are carried, which is not a guess about their charset."""

    def test_content_is_base64_and_says_so(self):
        carried = artifact.carried(BODY[:20])

        self.assertEqual("base64", carried["encoding"])
        self.assertEqual(BODY[:20], base64.b64decode(carried["data"]))


if __name__ == "__main__":
    unittest.main()
