"""The publisher, its isolation rules, and the tunnel it is bound behind.

Everything here is answerable without a database, which is most of what the
ticket is worried about. The directory a target may fetch from is decided once,
before a socket exists: `publishable` is that decision, and every rule it holds
is a refusal to start rather than a file quietly left out, because an operator
who put something else in that directory is an operator who does not know what
is published.

The other two seams are the shapes. `_requested` is what a request target is
allowed to be -- exactly a correlator and a file name -- and it is the reason
traversal is not a check that has to be got right here: nothing is opened by
name, so `../../etc/passwd` is a shape with nowhere to go rather than a path
somebody has to normalise. `_tunnel` is the other end: a tunnel that named
nothing is not a binding, however it failed to name it.

What needs the database -- that a fetch becomes an Interaction and an
Observation, that a released binding kills the correlators minted against it,
and that a name nobody bound cannot be minted on -- is in
`tests/test_database.py`.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import threading
import unittest
import warnings
from pathlib import Path
from unittest import mock

from redkraken import callback, oob, pg
from redkraken.outcome import (
    EXIT_DATABASE_UNREACHABLE,
    EXIT_INVALID_CONFIGURATION,
    Ledger,
)
from redkraken.store import Store
from tests.fixtures import PUBLISHED, SCOPED, scratch, unused_pid, write


UNREACHABLE = "postgresql://rk2_runtime@127.0.0.1:1/rk2"

#: The Program `PUBLISHED` names, which is the directory the publisher serves.
SLUG = "matrix-web"

#: The channel `PUBLISHED` declares with its correlator in the path, which is
#: the one a publisher can serve and the one every listener here is told it is.
CHANNEL = "oob-files"

#: One engagement file, the shape the ticket was written for: a DTD a target
#: with an XXE parses and fetches, which is the payload a canary cannot carry.
EXPLOIT = b'<!ENTITY % rk SYSTEM "file:///etc/hostname">\n'

#: The name a quick tunnel handed this channel, which is what `rk oob up` binds
#: and what every arrival from the edge carries in its `Host`. Nothing in the
#: configuration says it, which is the whole point of the binding table.
ENDPOINT = "bright-fox-1234.trycloudflare.com"

#: The row id `mint_control_correlator` answers with. Not derived from the
#: correlator it names, and not derivable from it.
CONTROL_ID = "1f0e5c22-9b3d-4c8a-8f21-6a5d0e3b7c41"

#: A channel a quick tunnel could bind and no publisher could ever serve: one
#: hostname has no labels to vary, so a correlator that lives in a label of it
#: is a canary with nowhere to be.
LABELLED = SCOPED + '''
[[callback]]
name = "oob-labelled"
kind = "http"
provider = "cloudflare-quick"
'''


def settings() -> pg.Settings:
    return pg.settings_from_url(UNREACHABLE, application_name="rk oob")


def base(files: dict[str, bytes] | None = None, slug: str = SLUG) -> Path:
    """A publish base holding one Program's directory, with files in it."""
    root = scratch()
    (root / slug).mkdir()
    for name, body in (files if files is not None else {"exploit.dtd": EXPLOIT}).items():
        (root / slug / name).write_bytes(body)
    return root


def refusal(base: Path | None, configuration: Path | None = None) -> list[str]:
    """What `publishable` says about this base, as the details it refused with."""
    ledger = Ledger()
    answer = oob.publishable(
        ledger, base, SLUG, configuration or write(PUBLISHED)
    )
    assert answer is None, answer
    return [violation.detail for violation in ledger.violations]


class PublishableTest(unittest.TestCase):
    """Criterion 5: a directory that fails any isolation rule refuses to start.

    Every one of these is measured before a socket is bound, and every one of
    them is a refusal rather than a skipped file. That is the property worth
    testing: an operator reading `rk oob serve`'s report knows the whole list of
    what a target can fetch, because a directory holding anything else did not
    start.
    """

    def test_the_directory_and_its_files_are_read_once_and_held(self):
        answer = oob.publishable(Ledger(), base(), SLUG, write(PUBLISHED))

        self.assertIsNotNone(answer)
        self.assertEqual({"exploit.dtd": EXPLOIT}, answer.files)
        self.assertEqual(len(EXPLOIT), answer.byte_size())

    def test_every_publishable_suffix_has_a_type_this_host_will_say(self):
        # What lets the answer key the map rather than default it. The default
        # was `application/octet-stream`, which line 74 says on purpose is not
        # in the map -- so the fallback answered with a type the module states
        # it does not serve.
        self.assertEqual(sorted(oob.PUBLISHABLE), sorted(oob.CONTENT_TYPES))

    def test_a_file_added_after_the_read_is_not_published(self):
        root = base()
        answer = oob.publishable(Ledger(), root, SLUG, write(PUBLISHED))
        (root / SLUG / "later.txt").write_bytes(b"added while it ran")

        self.assertEqual(["exploit.dtd"], sorted(answer.files))

    def test_the_root_is_the_programs_own_child_of_the_base(self):
        # Not the base itself: a base holding two Programs' directories would
        # otherwise publish both under whichever one was named.
        answer = oob.publishable(Ledger(), base(), SLUG, write(PUBLISHED))

        self.assertEqual(SLUG, answer.root.name)

    def test_a_base_nobody_named_is_refused_rather_than_defaulted(self):
        self.assertIn(f"no publish root: set ${oob.ROOT_VARIABLE}", refusal(None)[0])

    def test_a_program_with_no_directory_of_its_own_publishes_nothing(self):
        self.assertRegex(refusal(scratch())[0], r"is not a directory this Program")

    def test_a_root_that_is_a_symlink_is_refused(self):
        root = scratch()
        (root / "elsewhere").mkdir()
        (root / "elsewhere" / "exploit.dtd").write_bytes(EXPLOIT)
        (root / SLUG).symlink_to(root / "elsewhere")

        self.assertRegex(refusal(root)[0], r"is not a symlink")

    def test_a_symlink_inside_the_root_is_refused(self):
        root = base()
        (root / SLUG / "secrets.txt").symlink_to(Path.home() / ".ssh" / "id_ed25519")

        self.assertRegex(refusal(root)[0], r"secrets\.txt .* is a symlink")

    def test_a_file_with_a_suffix_nobody_allowlisted_is_refused(self):
        self.assertRegex(
            refusal(base({"exploit.dtd": EXPLOIT, "payload.sh": b"#!/bin/sh\n"}))[0],
            r"payload\.sh .* does not carry a publishable suffix",
        )

    def test_a_subdirectory_is_refused_rather_than_walked(self):
        root = base()
        (root / SLUG / "nested").mkdir()

        self.assertRegex(refusal(root)[0], r"nested .* is not a regular file")

    def test_a_dotfile_is_refused(self):
        self.assertRegex(
            refusal(base({".env": b"RK_DATABASE_URL=...\n"}))[0], r"\.env .* is a dotfile"
        )

    def test_a_file_larger_than_the_ceiling_is_refused(self):
        self.assertRegex(
            refusal(base({"big.txt": b"x" * (oob.MAX_FILE_BYTES + 1)}))[0],
            r"big\.txt .* is larger than",
        )

    def test_a_root_larger_than_the_ceiling_is_refused(self):
        many = {f"page{index}.html": b"y" * oob.MAX_FILE_BYTES for index in range(9)}

        self.assertRegex(refusal(base(many))[0], r"holds more than \d+ byte")

    def test_an_empty_root_is_a_name_in_front_of_nothing(self):
        self.assertRegex(refusal(base({}))[0], r"holds no engagement files")

    def test_a_working_tree_is_refused(self):
        root = base()
        (root / SLUG / ".git").mkdir()

        self.assertRegex(refusal(root)[0], r"it holds a \.git")

    def test_the_configurations_own_directory_is_refused(self):
        configuration = write(PUBLISHED)
        root = configuration.parent.parent
        (root / SLUG).mkdir(exist_ok=True)
        beside = configuration.parent.rename(root / SLUG / "kept")
        (root / SLUG / "exploit.dtd").write_bytes(EXPLOIT)

        self.assertRegex(
            refusal(root, beside / configuration.name)[0], r"is inside it"
        )

    def test_the_home_directory_is_refused(self):
        ledger = Ledger()
        root = base()
        with mock.patch.object(Path, "home", return_value=root / SLUG):
            answer = oob.publishable(ledger, root, SLUG, write(PUBLISHED))

        self.assertIsNone(answer)
        self.assertRegex(ledger.violations[0].detail, r"it is the home directory")


class RequestedTest(unittest.TestCase):
    """What a request target claims: a correlator, and a file name or none.

    The split is the whole point. The correlator decides whether an arrival is
    an arrival, and the file name only decides what comes back in the body, so
    a target this publisher has nothing to serve for is still evidence that the
    payload fired.
    """

    def test_a_target_is_exactly_a_correlator_and_a_file(self):
        self.assertEqual(("c0ffee", "exploit.dtd"), oob._requested("/c0ffee/exploit.dtd"))

    def test_a_query_string_is_the_payloads_business_and_not_the_names(self):
        # Measured on 2026-08-12: a quick tunnel forwards `?q=1` verbatim.
        self.assertEqual(("c0ffee", "x.dtd"), oob._requested("/c0ffee/x.dtd?q=1"))

    def test_the_address_the_operator_embeds_names_its_correlator(self):
        # `rk callback provision` prints `https://<endpoint>/<correlator>/`, so
        # this exact target is the one a payload is most likely to fetch. It
        # names no file and is still the arrival that address exists to record.
        self.assertEqual(("c0ffee", None), oob._requested("/c0ffee/"))
        self.assertEqual(("c0ffee", None), oob._requested("/c0ffee"))
        self.assertEqual(("c0ffee", None), oob._requested("/c0ffee/?x=1"))

    def test_a_deeper_path_names_no_file_this_publisher_has(self):
        # Still an arrival on that canary: the correlator is the first segment
        # and everything after it is the payload's business.
        self.assertEqual(("c0ffee", None), oob._requested("/c0ffee/sub/exploit.dtd"))

    def test_the_root_is_not_a_listing(self):
        self.assertEqual((None, None), oob._requested("/"))

    def test_traversal_is_a_shape_with_nowhere_to_go(self):
        # Nothing here is opened by name -- the file is looked up in the mapping
        # read at startup -- so a target full of `..` names no file, and a first
        # segment that is not the shape a correlator is minted in names no
        # canary that could exist.
        self.assertEqual(("c0ffee", None), oob._requested("/c0ffee/../../etc/passwd"))
        self.assertEqual((None, None), oob._requested("/../etc/passwd"))

    def test_a_first_segment_no_correlator_is_minted_in_is_not_one(self):
        self.assertEqual((None, None), oob._requested("/C0FFEE/x.dtd"))
        self.assertEqual((None, None), oob._requested("/-c0ffee/x.dtd"))
        self.assertEqual((None, None), oob._requested("/c0ffee_1/x.dtd"))

    def test_a_dotfile_is_not_addressable_even_when_the_shape_is_right(self):
        self.assertEqual(("c0ffee", None), oob._requested("/c0ffee/.env"))


class Resolves:
    """A connection that resolves no correlator, which is this test's whole DB.

    The probe is answered before anything is looked up, so the one request here
    that reaches the resolver is the one that must not be answered out of the
    published mapping -- and "no live correlator" is exactly the answer it has
    to get.
    """

    rows: list = []

    def execute(self, statement: str, parameters: tuple = ()) -> "Resolves":
        return self


class NoteTest(unittest.TestCase):
    """What the publisher writes down about a request it was sent.

    The note is the operator's, and the request line in it is the target's:
    `BaseHTTPRequestHandler` escapes control characters before writing one, and
    an override that only changes where the line goes must not also change what
    is in it.
    """

    def note(self, format: str, *arguments: object) -> str:
        written: list[str] = []
        handler = oob.Request.__new__(oob.Request)
        handler.server = mock.Mock(note=written.append)
        handler.log_message(format, *arguments)
        return written[0]

    def test_a_request_line_does_not_write_to_the_operators_terminal(self):
        written = self.note("%s resolves no live correlator", "/\x1b[2Jc0ffee/x.dtd")

        self.assertNotIn("\x1b", written)
        self.assertIn("\\x1b", written)

    def test_an_ordinary_line_is_the_line_it_was_given(self):
        self.assertEqual("/c0ffee/x.dtd was answered", self.note("%s was answered", "/c0ffee/x.dtd"))


class ProbeTest(unittest.TestCase):
    """The readiness question `rk oob up` asks before it binds a name.

    Answered by the publisher itself and by nothing that reached it through a
    tunnel: the `Host` is the loopback address, and a quick tunnel routes by
    hostname and sends its own. So a 200 here is this machine.
    """

    @classmethod
    def setUpClass(cls):
        published = oob.publishable(Ledger(), base(), SLUG, write(PUBLISHED))
        assert published is not None
        cls.listener = oob.Listener(
            (oob.LISTEN_HOST, 0), published, Resolves(), None, lambda line: None, CHANNEL
        )
        cls.port = cls.listener.server_address[1]
        cls.probe = f"{oob.LISTEN_HOST}:{cls.port}"
        cls.serving = threading.Thread(target=cls.listener.serve_forever, daemon=True)
        cls.serving.start()

    @classmethod
    def tearDownClass(cls):
        cls.listener.shutdown()
        cls.serving.join(timeout=5)
        cls.listener.server_close()

    def ask(self, host: str) -> tuple[int, bytes]:
        session = http.client.HTTPConnection(oob.LISTEN_HOST, self.port, timeout=5)
        try:
            session.request("GET", oob.HEALTH_PATH, headers={"Host": host})
            answer = session.getresponse()
            return answer.status, answer.read()
        finally:
            session.close()

    def test_the_publisher_answers_the_probe(self):
        self.assertTrue(oob._listening(self.port))

    def test_the_probe_is_the_loopback_address_and_nothing_else(self):
        self.assertEqual((200, b"ok"), self.ask(f"{oob.LISTEN_HOST}:{self.port}"))
        # What the same request looks like through the edge, which is a request
        # for a correlator called `health`.
        self.assertEqual((404, b"not found"), self.ask("dull-tunnel.trycloudflare.com")[:2])

    def test_a_head_of_the_probe_leaves_the_connection_where_it_found_it(self):
        # `protocol_version = "HTTP/1.1"` means the socket is reused, and a HEAD
        # answered with a body is a body the next answer starts inside of. Two
        # requests on one connection is the only way to see it.
        session = http.client.HTTPConnection(oob.LISTEN_HOST, self.port, timeout=5)
        try:
            session.request("HEAD", oob.HEALTH_PATH, headers={"Host": self.probe})
            first = session.getresponse()
            self.assertEqual((200, b""), (first.status, first.read()))
            session.request("GET", oob.HEALTH_PATH, headers={"Host": self.probe})
            second = session.getresponse()
            self.assertEqual((200, b"ok"), (second.status, second.read()))
        finally:
            session.close()

    def test_a_method_this_host_does_not_answer_is_answered_anyway(self):
        # A blind server-side request forged by something we planted can be a
        # POST. `send_error(501)` never reached `_answer`, so the arrival was
        # not even counted; now it is, and the refusal names what may be asked.
        before = self.listener.answered
        session = http.client.HTTPConnection(oob.LISTEN_HOST, self.port, timeout=5)
        try:
            session.request("POST", "/deadbeefdeadbeefdeadbeefdeadbeef/x.dtd", body=b"x")
            answer = session.getresponse()
            self.assertEqual(405, answer.status)
            self.assertEqual("GET, HEAD", answer.getheader("Allow"))
        finally:
            session.close()
        self.assertEqual(before + 1, self.listener.answered)

    def test_a_get_carrying_a_body_leaves_the_connection_where_it_found_it(self):
        # The other half of the HEAD case, from the target's side: a body this
        # host never read stays in the buffer and is parsed as the next request
        # line. Two requests on one connection is the only way to see it.
        session = http.client.HTTPConnection(oob.LISTEN_HOST, self.port, timeout=5)
        try:
            session.request(
                "GET", oob.HEALTH_PATH, body=b"GET /injected HTTP/1.1\r\n\r\n",
                headers={"Host": self.probe},
            )
            self.assertEqual((200, b"ok"), (lambda one: (one.status, one.read()))(
                session.getresponse()
            ))
            session.request("GET", oob.HEALTH_PATH, headers={"Host": self.probe})
            second = session.getresponse()
            self.assertEqual((200, b"ok"), (second.status, second.read()))
        finally:
            session.close()

    def test_the_operators_own_probe_is_not_counted_as_a_target_fetch(self):
        # `answered` is what targets fetched. `rk oob up` probes before it binds
        # a name, and its own probe in that number is a number about us.
        before = self.listener.answered

        self.assertEqual((200, b"ok"), self.ask(self.probe))

        self.assertEqual(before, self.listener.answered)

    def test_a_connection_that_goes_quiet_does_not_hold_the_one_thread(self):
        # Single-threaded and keep-alive: without a socket timeout one idle
        # connection through the tunnel blocks `readline` and the host stops
        # answering anybody. The attribute is the whole mechanism, so it is what
        # is asserted -- waiting one out would put the timeout in the suite.
        self.assertIsNotNone(oob.Request.timeout)
        self.assertGreater(oob.Request.timeout, 0)

    def test_a_port_nobody_is_on_is_not_a_publisher(self):
        self.assertFalse(oob._listening(1))

    def test_the_publisher_serves_one_request_at_a_time_on_purpose(self):
        # One database connection is held for its life, and a connection is not
        # shared between threads.
        self.assertNotIsInstance(self.listener, __import__("socketserver").ThreadingMixIn)


class Answer:
    """One statement's answer, in the two shapes the code under test reads."""

    def __init__(self, rows: list) -> None:
        self.rows = rows

    def scalar(self) -> object:
        return self.rows[0][0]


class Recording:
    """The publisher's connection: every correlator is live and every arrival files.

    Deliberately incurious about which correlator it was asked about. What the
    control has to demonstrate is that a request at the bound name travels the
    publisher's ordinary path -- `_answer`, `_serves`, `_record` -- and the
    arrival this collects is the thing that proves it did.
    """

    rows: list = []

    def __init__(self, channel: str = CHANNEL) -> None:
        self.channel = channel
        self.arrivals: list[dict] = []

    @contextlib.contextmanager
    def transaction(self):
        yield self

    def execute(self, statement: str, parameters: tuple = ()) -> Answer:
        if statement == oob.RESOLVE:
            return Answer([(self.channel, "path")])
        if statement == callback.RECORD:
            self.arrivals.append(json.loads(parameters[1]))
            return Answer(
                [
                    (
                        json.dumps(
                            {
                                "interaction": "CB1",
                                "observation": None,
                                "artifact": "AR1",
                                "duplicate": False,
                                "is_control": True,
                            }
                        ),
                    )
                ]
            )
        return Answer([])


class Operator:
    """The connection `rk oob up` holds while it takes a control.

    Scripted rather than faked loosely: what each test varies is one of the
    three answers `_control` reads -- the mint, whether the arrival landed, and
    nothing else -- and every statement is kept so that the order they were
    asked in is itself assertable.
    """

    def __init__(self, *, refusal: str | None = None, recording: "Recording | None" = None) -> None:
        self.refusal = refusal
        #: The publisher this control is being taken against, or nothing when
        #: the case under test is one where it never files. Held rather than
        #: answered by a flag, because that is what the reader in the database
        #: does: `callback_control_arrival` reports the control when the row is
        #: there, so a poll that answered before the publisher had written would
        #: be a fake that races where the real one waits.
        self.recording = recording
        self.statements: list[tuple[str, tuple]] = []
        self.correlator: str | None = None

    @contextlib.contextmanager
    def transaction(self):
        yield self

    def executed(self, statement: str) -> list[tuple[str, tuple]]:
        return [one for one in self.statements if one[0] == statement]

    def execute(self, statement: str, parameters: tuple = ()) -> Answer:
        self.statements.append((statement, parameters))
        if statement == oob.CONTROL_MINT:
            if self.refusal is not None:
                return Answer(
                    [(json.dumps({"outcome": "refused", "refusal": self.refusal}),)]
                )
            self.correlator = str(parameters[1])
            return Answer(
                [
                    (
                        json.dumps(
                            {
                                "outcome": "minted",
                                "correlator_id": CONTROL_ID,
                                "channel": CHANNEL,
                                "kind": "http",
                                "placement": "path",
                                "endpoint": ENDPOINT,
                            }
                        ),
                    )
                ]
            )
        if statement == oob.CONTROL_ARRIVAL:
            landed = bool(self.recording is not None and self.recording.arrivals)
            return Answer(
                [
                    (
                        json.dumps(
                            {
                                "declared": True,
                                "publishable": True,
                                "bound": True,
                                "endpoint": ENDPOINT,
                                "has_control": landed,
                                "fresh": landed,
                                "interaction": "CB1" if landed else None,
                                "correlator_id": CONTROL_ID if landed else None,
                                "age_seconds": 0,
                                "window_seconds": 86400,
                            }
                        ),
                    )
                ]
            )
        return Answer([])


class ControlTest(unittest.TestCase):
    """The positive control: an arrival this harness caused, so silence can mean something.

    Until there was one, a canary that never fired and a publisher that was
    never reachable were the same reading, and a step reporting the second as
    the first was reporting our own plumbing as a fact about somebody's
    software. What this asserts is the three things that make the difference: the
    request is one the publisher takes as an arrival rather than as a probe, it
    carries the bound name exactly as the edge would send it, and a control that
    did not reach the record is a refusal rather than a shrug.

    The publisher here is a real listener on a real socket with a fake database
    beneath it; the operator's side is a second fake, because what `rk oob up`
    does between the mint and the clear is decided in this process.
    """

    @classmethod
    def setUpClass(cls):
        published = oob.publishable(Ledger(), base(), SLUG, write(PUBLISHED))
        assert published is not None
        cls.published = published

    def publisher(self) -> tuple[oob.Listener, Recording, int]:
        """One publisher, serving until this test is over."""
        recording = Recording()
        listener = oob.Listener(
            (oob.LISTEN_HOST, 0),
            self.published,
            recording,
            Store(scratch()),
            lambda line: None,
            CHANNEL,
        )
        serving = threading.Thread(target=listener.serve_forever, daemon=True)
        serving.start()
        self.addCleanup(listener.server_close)
        self.addCleanup(serving.join, 5)
        self.addCleanup(listener.shutdown)
        return listener, recording, listener.server_address[1]

    def test_the_control_is_an_arrival_at_the_bound_name(self):
        # The whole claim, in one row: the request the control makes is the same
        # shape an arrival from the edge has -- the tunnel routes by hostname and
        # forwards the one it was given -- so a publisher that files this one is
        # a publisher that would have filed a target's.
        listener, recording, port = self.publisher()
        connection = Operator(recording=recording)
        ledger = Ledger()

        answer = oob._control(ledger, connection, CHANNEL, ENDPOINT, port)

        self.assertEqual([], ledger.violations)
        self.assertEqual("CB1", answer["interaction"])
        self.assertEqual(
            [
                {
                    "host": ENDPOINT,
                    "arrival_kind": "http",
                    "peer_class": "client",
                    "received_at": None,
                    "path": f"/{connection.correlator}/",
                }
            ],
            recording.arrivals,
        )
        self.assertEqual(1, listener.recorded)

    def test_the_control_correlator_is_ended_however_the_fetch_turned_out(self):
        # A control left live is a canary at a name we published and told nobody
        # about, so it is ended in a `finally` and the failing case is the one
        # worth asserting.
        for name, arrives in (("arrived", True), ("never arrived", False)):
            with self.subTest(name):
                _, recording, port = self.publisher()
                connection = Operator(recording=recording if arrives else None)
                with mock.patch.object(oob, "CONTROL_TIMEOUT", 1.0):
                    oob._control(Ledger(), connection, CHANNEL, ENDPOINT, port)

                self.assertEqual(
                    [(oob.CLEAR_CORRELATOR, (CONTROL_ID,))],
                    connection.executed(oob.CLEAR_CORRELATOR),
                )

    def test_a_control_that_never_reaches_the_record_is_a_refusal(self):
        # Answered and not written down is the failure this exists to catch: the
        # socket is up, the request came back, and nothing about the channel has
        # been demonstrated. `rk oob up` reads this as a name not to hand out.
        _, _, port = self.publisher()
        ledger = Ledger()

        with mock.patch.object(oob, "CONTROL_TIMEOUT", 0.2):
            answer = oob._control(ledger, Operator(), CHANNEL, ENDPOINT, port)

        self.assertIsNone(answer)
        self.assertEqual(["database"], [one.source for one in ledger.violations])
        self.assertIn(ENDPOINT, ledger.violations[0].detail)

    def test_a_publisher_that_stopped_answering_is_named_as_the_port_it_was_on(self):
        # Between the readiness probe and here, which is the window `_listening`
        # cannot cover: it is asked before the tunnel starts and this is asked
        # after the name is bound. Port 1, which is the port the probe's own
        # "nobody is on this" test uses and for the same reason.
        ledger = Ledger()

        answer = oob._control(ledger, Operator(), CHANNEL, ENDPOINT, 1)

        self.assertIsNone(answer)
        self.assertEqual(["argument:--port"], [one.source for one in ledger.violations])
        self.assertIn(f"{oob.LISTEN_HOST}:1", ledger.violations[0].detail)

    def test_a_channel_no_control_can_be_taken_on_is_refused_in_the_databases_words(self):
        # The reader's sentence rather than a second one composed here: what a
        # control cannot be taken on is a question about the channel row, and an
        # operator reading a paraphrase would be reading this file's opinion of
        # it.
        ledger = Ledger()
        said = "channel oob-files declares its own endpoint, which this harness does not publish"

        answer = oob._control(ledger, Operator(refusal=said), CHANNEL, ENDPOINT, 1)

        self.assertIsNone(answer)
        self.assertIn(said, ledger.violations[0].detail)
        self.assertEqual(["argument:--channel"], [one.source for one in ledger.violations])

    def test_nothing_is_fetched_before_a_correlator_exists_to_fetch(self):
        # A request at a name with no live correlator is an arrival attributable
        # to nothing, and this command would have caused it.
        _, recording, port = self.publisher()

        oob._control(
            Ledger(), Operator(refusal="no binding"), CHANNEL, ENDPOINT, port
        )

        self.assertEqual([], recording.arrivals)


class RunningTest(unittest.TestCase):
    """Whether a tunnel process is still there, which is the whole of a binding."""

    def test_this_process_is_running(self):
        self.assertTrue(oob._running(os.getpid()))

    def test_a_process_that_is_gone_is_gone(self):
        self.assertFalse(oob._running(unused_pid()))

    def test_a_process_this_user_may_not_signal_is_still_a_process(self):
        with mock.patch.object(os, "kill", side_effect=PermissionError):
            self.assertTrue(oob._running(1))


class TunnelTest(unittest.TestCase):
    """Starting the tunnel, and the three ways it fails to name one."""

    def start(self, ledger: Ledger, binary: str, port: int, timeout: float):
        """`_tunnel`, with the warning a deliberately detached child raises muted.

        A tunnel outlives the command that starts it, so the `Popen` inside
        `_tunnel` is collected while its child is still running and says so.
        That is the design rather than a leak -- `rk oob up` returns and the
        tunnel keeps serving -- and outside a test runner nothing prints it,
        because `ResourceWarning` is ignored by default.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            return oob._tunnel(ledger, binary, port, timeout)

    def script(self, body: str) -> str:
        path = scratch() / "cloudflared"
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)
        return str(path)

    def test_the_name_is_read_from_the_tunnels_own_output(self):
        binary = self.script(
            "echo 'INF |  https://dull-tunnel.trycloudflare.com  |' >&2\nsleep 30\n"
        )
        ledger = Ledger()

        started = self.start(ledger, binary, 8787, timeout=10)
        try:
            self.assertIsNotNone(started, [v.detail for v in ledger.violations])
            self.assertEqual("dull-tunnel.trycloudflare.com", started.host)
            self.assertIn(b"trycloudflare.com", started.output)
            self.assertTrue(oob._running(started.pid))
        finally:
            if started is not None:
                os.kill(started.pid, 15)

    def test_the_url_it_was_pointed_at_is_the_loopback_publisher(self):
        binary = self.script(
            'echo "$@" >&2\n' "echo 'https://dull-tunnel.trycloudflare.com' >&2\n"
        )

        started = self.start(Ledger(), binary, 9999, timeout=10)

        self.assertIn(b"tunnel --url http://127.0.0.1:9999", started.output)

    def test_a_binary_that_is_not_installed_is_refused_by_name(self):
        ledger = Ledger()

        self.assertIsNone(self.start(ledger, str(scratch() / "absent"), 8787, 10))
        self.assertRegex(ledger.violations[0].detail, r"absent did not start")

    def test_a_tunnel_that_exits_without_naming_one_is_not_a_binding(self):
        ledger = Ledger()
        binary = self.script("echo 'ERR failed to connect' >&2\nexit 3\n")

        self.assertIsNone(self.start(ledger, binary, 8787, 10))
        self.assertRegex(ledger.violations[0].detail, r"exited 3 without naming a tunnel")

    def test_a_tunnel_that_never_names_one_does_not_outlive_the_attempt(self):
        ledger = Ledger()
        binary = self.script("sleep 30\n")

        with mock.patch.object(oob, "TUNNEL_POLL", 0.05):
            self.assertIsNone(self.start(ledger, binary, 8787, timeout=0.3))
        self.assertRegex(ledger.violations[0].detail, r"named no tunnel within")


class ServeRefusalTest(unittest.TestCase):
    """The three things `rk oob serve` settles before it binds a socket."""

    def test_a_configuration_that_does_not_validate_never_opens_a_connection(self):
        answer = oob.serve(
            settings(), write("this is not toml"), "oob-files",
            store=scratch(), port=0, root=base(),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertIsNone(answer.facts["oob"])

    def test_a_channel_this_program_does_not_declare_is_refused(self):
        answer = oob.serve(
            settings(), write(PUBLISHED), "oob-files-2",
            store=scratch(), port=0, root=base(),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertRegex(answer.violations[0].detail, r"declares no callback channel")

    def test_a_channel_whose_correlator_is_a_label_has_no_publisher(self):
        # One bound hostname has no labels to vary, so a publisher in front of
        # a label channel would answer every canary as the same one.
        answer = oob.serve(
            settings(), write(PUBLISHED), "oob-http",
            store=scratch(), port=0, root=base(),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertRegex(answer.violations[0].detail, r"carries its correlator in the label")

    def test_the_directory_is_checked_before_the_database_is_reached(self):
        answer = oob.serve(
            settings(), write(PUBLISHED), "oob-files",
            store=scratch(), port=0, root=scratch(),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertRegex(answer.violations[0].detail, r"is not a directory this Program")

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        answer = oob.serve(
            settings(), write(PUBLISHED), "oob-files",
            store=scratch(), port=0, root=base(),
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, answer.exit_code)

    def test_the_publish_root_comes_from_the_environment_when_nobody_passes_one(self):
        root = base()
        with mock.patch.dict(os.environ, {oob.ROOT_VARIABLE: str(root)}):
            answer = oob.serve(
                settings(), write(PUBLISHED), "oob-files", store=scratch(), port=0
            )

        # Past every refusal the directory could have raised, and stopped at the
        # database, which is the next thing `serve` reaches.
        self.assertEqual(EXIT_DATABASE_UNREACHABLE, answer.exit_code)


class LifecycleRefusalTest(unittest.TestCase):
    """What `up`, `status` and `down` settle before they reach the database."""

    def test_a_channel_whose_name_the_operator_declared_is_not_bound_by_up(self):
        answer = oob.up(
            settings(), write(PUBLISHED), "oob-http", store=scratch(), port=0
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertRegex(answer.violations[0].detail, r"declares provider static")

    def test_a_channel_a_publisher_could_not_serve_is_not_bound_either(self):
        # `serve` has always refused a label channel, because one hostname has
        # no labels to vary. `up` binds a name in front of that publisher, so a
        # name bound for a label channel was a name in front of nothing -- and
        # it is also the one shape no control could be taken on, since the
        # publisher reads a correlator out of the path and would find none.
        answer = oob.up(
            settings(), write(LABELLED), "oob-labelled", store=scratch(), port=0
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertRegex(answer.violations[0].detail, r"has\s+no labels to vary")
        self.assertEqual(["argument:--channel"], [one.source for one in answer.violations])

    def test_an_undeclared_channel_is_refused_by_every_verb(self):
        for verb in (oob.status, oob.down):
            with self.subTest(verb.__name__):
                answer = verb(settings(), write(PUBLISHED), "oob-files-2")

                self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
                self.assertRegex(answer.violations[0].detail, r"declares no callback channel")

    def test_a_configuration_with_no_dynamic_channel_at_all_still_answers(self):
        answer = oob.status(settings(), write(SCOPED), "oob-files")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertRegex(answer.violations[0].detail, r"oob-dns, oob-http")

    def test_every_refusal_reports_the_keys_a_bound_name_reports(self):
        # A caller reading `facts["oob"]` must not have to ask whether the
        # command got far enough to have facts.
        for answer in (
            oob.up(settings(), write("nope"), "oob-files", store=scratch(), port=0),
            oob.status(settings(), write("nope"), "oob-files"),
            oob.down(settings(), write("nope"), "oob-files"),
        ):
            with self.subTest(answer.command):
                self.assertEqual(
                    {"program_id", "oob", "released"} if answer.command == oob.UP
                    else {"program_id", "oob"},
                    set(answer.facts),
                )
                self.assertIsNone(answer.facts["oob"])


if __name__ == "__main__":
    unittest.main()
