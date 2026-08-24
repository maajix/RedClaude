"""What a fixture declares, what the corpus refuses, and what gets served.

Two halves. The first is the compiler, written the way `test_playbook`'s is: a
corpus on disk per case, because every negative below is a document that must not
exist under `src/redkraken/fixtures/` and the only way to hold both the rule and
its violation is to write the violation somewhere the corpus is not.

The second is the part of the evaluator that needs no database -- serving a
variant and writing the Program configuration for it. Those two are tested here
rather than beside the database cases because what they claim is checkable
without one: that what listens is the bytes the catalogue digested, that the two
variants of a pair actually differ, and that the document the evaluator writes is
one the production configuration reader accepts.
"""

import http.client
import json
import ssl
import unittest
from pathlib import Path
from typing import NamedTuple

from redkraken import config, document, evaluation, fixture, isolation, scope
from redkraken.outcome import Ledger
from tests.fixtures import frontmatter, scratch, write


#: The smallest fixture that compiles, as a pair. Every negative is this with one
#: thing changed, so the thing that changed is the thing under test.
FIELDS = {
    "description": "A note API where one route names an object by path and two sessions are issued.",
    "bb:kind": "own_pair",
    "bb:classes": ["authorization.object_ownership"],
    "bb:subject": "/notes/2",
    "bb:facts": ["multiple_test_identities", "object_identifier"],
    "bb:identities": ["alice", "bob"],
    "bb:provenance": "Written for the suite from the class description; no upstream corpus.",
}

#: What a third-party fixture declares instead of having a secure twin.
COVERAGE = {"upstream_list_size": 10, "converted": 4}

BODY = """
# Two notes, two sessions, one flag

The vulnerable variant returns any note to any valid session; the secure variant
checks the note's owner against the caller.
"""

#: An application whose only job is to be distinguishable per variant. Written
#: as text because that is what a corpus holds and what `source_sha256` digests.
APPLICATION = '''\
"""One route, two variants, no state that outlives the process."""

from http.server import BaseHTTPRequestHandler

VARIANTS = ("vulnerable", "secure")


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    if variant not in VARIANTS:
        raise ValueError(variant)
    status = 200 if variant == "vulnerable" else 403

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            payload = variant.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent."""

    return Fixture
'''


def corpus(**fixtures: tuple[str | None, str | None]) -> Path:
    """A corpus root holding one directory per named fixture.

    A `None` on either side makes the directory and leaves that file out, which
    is the pair of negatives no document can express.
    """
    root = scratch() / "fixtures"
    root.mkdir()
    for name, (document, application) in fixtures.items():
        directory = root / name.replace("_", "-")
        directory.mkdir()
        if document is not None:
            (directory / fixture.DOCUMENT).write_text(document, encoding="utf-8")
        if application is not None:
            (directory / fixture.APPLICATION).write_text(application, encoding="utf-8")
    return root


def one(fields: dict | None = None, body: str = BODY, **changes: object) -> Path:
    """A corpus holding exactly one fixture, well-formed unless a caller says so."""
    declared = (fields or FIELDS) | changes
    for key, value in list(declared.items()):
        if value is None:
            del declared[key]
    return corpus(object_ownership=(frontmatter(declared) + body, APPLICATION))


def compiled(root: Path) -> fixture.Fixture:
    return fixture.compile_corpus(root)["object-ownership"]


class Refusals(unittest.TestCase):
    """Every shape of malformed fixture, by the code it refuses with.

    On the code rather than on the sentence, for `document.DocumentError`'s
    reason: the sentence is for a person reading a refusal and should stay free
    to improve.
    """

    def refuses(self, code: str, root: Path) -> fixture.FixtureError:
        with self.assertRaises(fixture.FixtureError) as caught:
            fixture.compile_corpus(root)
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def test_a_fixture_without_an_application_is_not_a_target(self):
        self.refuses("file_missing", corpus(object_ownership=(frontmatter(FIELDS) + BODY, None)))

    def test_a_fixture_without_ground_truth_is_not_scoreable(self):
        self.refuses("file_missing", corpus(object_ownership=(None, APPLICATION)))

    def test_an_empty_body_explains_nothing(self):
        self.refuses("body_missing", one(body=""))

    def test_every_required_key_is_required(self):
        for key in fixture.REQUIRED_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, self.refuses("key_missing", one(**{key: None})).detail)

    def test_a_fixture_may_not_name_the_playbooks_it_tests(self):
        # The binding is derived from two independent declarations. A fixture
        # that could name its Playbooks would let one side choose the pairing,
        # which is criterion 1.
        for key in ("bb:playbooks", "bb:tests", "bb:variants", "bb:id", "bb:version", "name"):
            with self.subTest(key=key):
                self.assertIn(key, self.refuses("key_forbidden", one(**{key: ["x"]})).detail)

    def test_a_key_nothing_reads_is_refused_rather_than_ignored(self):
        self.refuses("key_unknown", one(**{"bb:severity": "high"}))

    def test_a_class_that_is_not_a_property_class_is_refused(self):
        self.refuses("value_malformed", one(**{"bb:classes": ["Authorization.ObjectOwnership"]}))

    def test_a_subject_that_names_a_host_is_refused(self):
        # Where a fixture is served is the evaluator's to decide and changes
        # every run; a subject that carried an origin would be stating it.
        self.refuses("value_malformed", one(**{"bb:subject": "http://127.0.0.1:8080/notes/2"}))

    def test_a_kind_outside_the_vocabulary_is_refused(self):
        self.refuses("value_malformed", one(**{"bb:kind": "synthetic"}))

    def test_a_pair_declares_no_coverage_fraction(self):
        self.refuses("key_forbidden", one(**{"bb:coverage": COVERAGE}))

    def test_a_third_party_fixture_states_its_coverage(self):
        self.refuses("key_missing", one(**{"bb:kind": "third_party"}))

    def test_a_coverage_missing_half_of_the_fraction_is_refused(self):
        # A converted count without the list it came from is a statement about
        # our transcription, so neither half stands alone.
        for half in fixture.COVERAGE_KEYS:
            with self.subTest(half=half):
                self.refuses(
                    "value_malformed",
                    one(**{"bb:kind": "third_party", "bb:coverage": {half: 4}}),
                )

    def test_a_third_party_fixture_cannot_convert_more_than_it_read(self):
        self.refuses(
            "value_malformed",
            one(
                **{
                    "bb:kind": "third_party",
                    "bb:coverage": {"upstream_list_size": 4, "converted": 5},
                }
            ),
        )

    def test_a_coverage_written_as_a_bare_line_is_refused(self):
        # `document.field` reads a bare scalar as text, so the numbers only
        # arrive as numbers inside JSON. A document that wrote them any other way
        # would parse and then mean something else.
        self.refuses(
            "value_malformed", one(**{"bb:kind": "third_party", "bb:coverage": "10 of 4"})
        )

    def test_a_file_nothing_reads_is_refused(self):
        root = one()
        (root / "object-ownership" / "notes.md").write_text("scratch", encoding="utf-8")
        self.refuses("stray_file", root)

    def test_compiled_bytecode_beside_the_application_is_not_a_stray(self):
        # `pip install` byte-compiles the application every fixture ships, so
        # this is in every installed corpus and in no checkout.
        root = one()
        cache = root / "object-ownership" / document.BYTECODE_DIR
        cache.mkdir()
        (cache / "app.cpython-314.pyc").write_bytes(b"\x00\x01\x02")

        self.assertEqual("object-ownership", compiled(root).name)

    def test_a_symbolic_link_wearing_the_bytecode_name_is_still_a_stray(self):
        root = one()
        (root / "object-ownership" / document.BYTECODE_DIR).symlink_to(scratch())
        self.refuses("stray_file", root)

    def test_a_corpus_with_nothing_in_it_is_refused(self):
        self.refuses("corpus_missing", corpus())

    def test_a_corpus_that_is_not_there_is_refused(self):
        self.refuses("corpus_missing", scratch() / "absent")


class Compiled(unittest.TestCase):
    """What a well-formed fixture becomes."""

    def test_the_two_digests_move_separately(self):
        # Rewriting the ground truth changes how a result is scored without
        # changing what was served, and the other way round. A test run freezes
        # both, so they have to be two values.
        first = compiled(one())
        reworded = compiled(one(body=BODY + "\nAnd it says so twice.\n"))
        self.assertEqual(first.source_sha256, reworded.source_sha256)
        self.assertNotEqual(first.ground_truth_sha256, reworded.ground_truth_sha256)

    def test_the_source_digest_is_of_the_application_and_not_the_document(self):
        root = one()
        (root / "object-ownership" / fixture.APPLICATION).write_text(
            APPLICATION + "\n# and one more line\n", encoding="utf-8"
        )
        edited = fixture.compile_corpus(root)["object-ownership"]
        self.assertEqual(compiled(one()).ground_truth_sha256, edited.ground_truth_sha256)
        self.assertNotEqual(compiled(one()).source_sha256, edited.source_sha256)

    def test_a_fixture_with_no_caller_is_not_a_fixture_missing_one(self):
        # `/search` has nobody to be. The empty list is a value, not a gap.
        self.assertEqual((), compiled(one(**{"bb:identities": []})).identities)

    def test_only_a_pair_has_a_control(self):
        self.assertTrue(compiled(one()).paired)
        third_party = compiled(one(**{"bb:kind": "third_party", "bb:coverage": COVERAGE}))
        self.assertFalse(third_party.paired)
        self.assertEqual((10, 4), (third_party.upstream_list_size, third_party.converted))

    def test_the_path_is_where_a_maintainer_finds_it(self):
        self.assertEqual("fixtures/object-ownership/fixture.md", compiled(one()).path)
        self.assertEqual("fixtures/object-ownership/app.py", compiled(one()).application_path)


class Corpus(unittest.TestCase):
    """The corpus this package ships, which is what an installed `rk` grades against."""

    def test_the_shipped_corpus_compiles(self):
        self.assertTrue(fixture.FIXTURES)
        self.assertEqual(sorted(fixture.FIXTURES), list(fixture.FIXTURES))

    def test_every_shipped_fixture_declares_at_least_one_class(self):
        for name, one_fixture in fixture.FIXTURES.items():
            with self.subTest(fixture=name):
                self.assertTrue(one_fixture.classes)

    def test_the_corpus_is_read_only(self):
        with self.assertRaises(TypeError):
            fixture.FIXTURES["invented"] = None  # type: ignore[index]

    def test_the_compiler_never_executes_what_it_digests(self):
        # `compile_corpus` reads and hashes. A corpus that will not compile must
        # still be a corpus nobody ran, and the way to state that is a fixture
        # whose application raises at import.
        root = corpus(object_ownership=(frontmatter(FIELDS) + BODY, "raise SystemExit(9)\n"))
        self.assertTrue(fixture.compile_corpus(root)["object-ownership"].source_sha256)


class Serving(unittest.TestCase):
    """`evaluation.served`: what listens, and whether it is what was digested."""

    def get(self, where: evaluation.Served, path: str = "/notes/2") -> tuple[int, bytes]:
        connection = http.client.HTTPConnection(where.host, where.port, timeout=5)
        try:
            # `Connection: close`, so the server closes first. The fixture
            # speaks HTTP/1.1 and would otherwise sit in `readline` until this
            # client hangs up, and a TLS socket closed without a `close_notify`
            # raises `ConnectionResetError` inside the handler thread -- a
            # traceback printed into the suite output about nothing.
            connection.request("GET", path, headers={"Connection": "close"})
            answer = connection.getresponse()
            return answer.status, answer.read()
        finally:
            connection.close()

    def test_the_two_variants_of_a_pair_differ(self):
        # Not an assertion about these particular statuses -- it is the claim
        # that a control exists at all. A pair whose halves answered alike could
        # not tell a Playbook that reads the target from one that always fires.
        one_fixture = compiled(one())
        answers = {}
        for variant in evaluation.PAIR:
            with evaluation.served(one_fixture, variant) as where:
                answers[variant] = self.get(where)
        self.assertNotEqual(answers["vulnerable"], answers["secure"])

    def test_what_is_served_is_the_bytes_the_catalogue_digested(self):
        # The application is executed from `Fixture.source`, so a file edited
        # after the compile cannot be what answers. Without this, "the run used
        # fixture X" and "the row records digest Y" are two separate claims.
        root = one()
        one_fixture = fixture.compile_corpus(root)["object-ownership"]
        (root / "object-ownership" / fixture.APPLICATION).write_text(
            APPLICATION.replace("variant.encode", "'edited'.encode"), encoding="utf-8"
        )
        with evaluation.served(one_fixture, "vulnerable") as where:
            self.assertEqual((200, b"vulnerable"), self.get(where))

    def test_an_application_with_no_handler_is_refused_rather_than_served(self):
        root = corpus(object_ownership=(frontmatter(FIELDS) + BODY, "MARKER = 1\n"))
        one_fixture = fixture.compile_corpus(root)["object-ownership"]
        with self.assertRaises(fixture.FixtureError) as caught:
            with evaluation.served(one_fixture, "vulnerable"):
                pass
        self.assertEqual("value_malformed", caught.exception.code)

    def test_a_variant_the_application_does_not_know_is_refused_by_it(self):
        with self.assertRaises(ValueError):
            with evaluation.served(compiled(one()), "convenient"):
                pass

    def test_the_port_is_released_when_the_block_ends(self):
        # Each repeat opens fresh Programs against a fresh port. A listener that
        # outlived its block would leave the previous repeat's application
        # answering for the next one's.
        one_fixture = compiled(one())
        with evaluation.served(one_fixture, "vulnerable") as where:
            self.assertEqual(200, self.get(where)[0])
        with self.assertRaises(OSError):
            self.get(where)

    def test_it_listens_on_loopback_unless_it_is_told_otherwise(self):
        self.assertEqual("127.0.0.1", evaluation.HOST)
        with evaluation.served(compiled(one()), "vulnerable") as where:
            self.assertEqual(evaluation.HOST, where.host)

    def test_it_listens_at_the_one_address_the_route_named(self):
        # The door route serves the fixture where the proxy can dial it, which
        # is not loopback -- and it is still one address rather than every
        # interface, so nothing else this machine is attached to gains a target.
        # A second loopback address stands in for it here: what is under test is
        # that `host` is honoured and bounded, and that needs no container.
        one_fixture = compiled(one())
        with evaluation.served(one_fixture, "vulnerable", "127.0.0.2") as where:
            self.assertEqual("127.0.0.2", where.host)
            self.assertEqual((200, b"vulnerable"), self.get(where))
            elsewhere = evaluation.Served(
                variant="vulnerable", host="127.0.0.1", port=where.port, scheme="http"
            )
            with self.assertRaises(OSError):
                self.get(elsewhere)


class ServingOverTls(unittest.TestCase):
    """`evaluation.served` when the fixture configures its own handshake.

    The shipped pair rather than a written one, deliberately. Every other case
    in this file builds its corpus on disk so the violation can exist somewhere
    the real corpus is not; there is no violation here, and what is under test
    is that the one fixture whose ground truth is a handshake actually gets one.
    A hand-written stand-in would prove that `served` can wrap a socket and
    would prove nothing about the corpus.
    """

    NAME = "tls-configuration-pair"
    SUBJECT = "/app"

    def client(self) -> ssl.SSLContext:
        """A client that verifies nothing, because there is nothing to verify.

        `served` mints a fresh authority per call into a directory it deletes,
        and hands nobody the root. That is the design rather than a shortcut --
        `receipts.transport_citable` is generated from the two verification
        columns, so an exchange with this fixture is recorded as unverified,
        which is what it is.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    class Answer(NamedTuple):
        """One exchange with the fixture, from both sides of the wrapped socket.

        `version` is above the answer rather than in it, and that is the whole
        subject of this pair: the two halves agree on `status`, `body` and
        `advertised`, and the field they differ in is the one no handler wrote.
        """

        status: int
        body: bytes
        advertised: str | None
        version: str

    def read(self, where: evaluation.Served, path: str) -> "ServingOverTls.Answer":
        connection = http.client.HTTPSConnection(
            where.host, where.port, timeout=5, context=self.client()
        )
        try:
            # `Connection: close`, so the server closes first. The fixture
            # speaks HTTP/1.1 and would otherwise sit in `readline` until this
            # client hangs up, and a TLS socket closed without a `close_notify`
            # raises `ConnectionResetError` inside the handler thread -- a
            # traceback printed into the suite output about nothing.
            connection.request("GET", path, headers={"Connection": "close"})
            answer = connection.getresponse()
            body = answer.read()
            # Asked of the socket rather than of the response, and asserted
            # rather than rendered: `version()` answers `None` on a socket that
            # never completed a handshake, and `str(None)` is a string that
            # compares like any other and would let a failed negotiation pass
            # for a measurement.
            negotiated = connection.sock.version()
            self.assertIsNotNone(negotiated)
            return self.Answer(
                status=answer.status,
                body=body,
                advertised=answer.getheader("Strict-Transport-Security"),
                version=str(negotiated),
            )
        finally:
            connection.close()

    def test_the_fixture_that_configures_a_handshake_is_served_over_one(self):
        one_fixture = fixture.FIXTURES[self.NAME]
        for variant in evaluation.PAIR:
            with self.subTest(variant=variant):
                with evaluation.served(one_fixture, variant) as where:
                    self.assertEqual("https", where.scheme)
                    self.assertEqual(200, self.read(where, self.SUBJECT).status)

    def test_every_other_fixture_is_still_served_over_cleartext(self):
        # The scheme is a property of the fixture and not a mode the evaluator
        # is put into. One fixture in the corpus has a handshake; the rest are
        # the corpus this ticket did not change.
        for name, one_fixture in fixture.FIXTURES.items():
            if name == self.NAME:
                continue
            with self.subTest(name=name):
                with evaluation.served(one_fixture, "vulnerable") as where:
                    self.assertEqual("http", where.scheme)

    def test_the_two_halves_differ_in_the_handshake_and_in_nothing_else(self):
        # The whole of this pair, as one assertion. `transport.tls_configuration`
        # is settled over `tls_version`, `cipher` and `alpn`, so a pair whose
        # halves also differed in a byte would let a reading establish the class
        # from the wrong evidence -- and one whose halves agreed on the version
        # would not be a pair at all.
        one_fixture = fixture.FIXTURES[self.NAME]
        answers = {}
        for variant in evaluation.PAIR:
            with evaluation.served(one_fixture, variant) as where:
                answers[variant] = self.read(where, self.SUBJECT)

        self.assertEqual("TLSv1.2", answers["vulnerable"].version)
        self.assertEqual("TLSv1.3", answers["secure"].version)
        self.assertEqual(answers["vulnerable"][:3], answers["secure"][:3])

    def test_the_advertisement_is_the_same_on_both_halves(self):
        # The header is what makes the weaker handshake a finding rather than a
        # preference, so it has to be identical: a pair that advertised
        # differently would be positive for `transport.header_policy` instead.
        one_fixture = fixture.FIXTURES[self.NAME]
        said = {}
        for variant in evaluation.PAIR:
            with evaluation.served(one_fixture, variant) as where:
                said[variant] = self.read(where, self.SUBJECT).advertised

        self.assertEqual(said["vulnerable"], said["secure"])
        self.assertIn("preload", str(said["vulnerable"]))

    def test_an_application_whose_tls_is_not_callable_is_refused(self):
        # The same refusal `handler` gets, for the same reason: a fixture that
        # declared a handshake and did not supply one would be served over
        # cleartext and graded as though it had negotiated something.
        root = corpus(
            object_ownership=(frontmatter(FIELDS) + BODY, APPLICATION + "tls = 3\n")
        )
        one_fixture = fixture.compile_corpus(root)["object-ownership"]
        with self.assertRaises(fixture.FixtureError) as refused:
            with evaluation.served(one_fixture, "vulnerable"):
                pass

        self.assertEqual("value_malformed", refused.exception.code)


class Routing(unittest.TestCase):
    """`evaluation.route`: which way a run reaches its fixture, decided once."""

    def boundary(self, container: str) -> isolation.AgentContainer:
        return isolation.AgentContainer(
            image="rk2-selftest:none",
            network="rk2-selftest-absent-network",
            proxy_container=container,
            proxy_url=f"http://{container}:18080",
            certificate=Path("/nonexistent/ca.pem"),
        )

    def test_a_machine_with_no_agent_boundary_grades_over_loopback(self):
        ledger = Ledger()

        self.assertEqual(
            evaluation.Route(name=evaluation.LOOPBACK, host=evaluation.HOST),
            evaluation.route(ledger, None),
        )
        self.assertEqual([], list(ledger.violations))

    def test_a_door_that_cannot_be_read_is_a_refusal_and_not_a_fall_back(self):
        # An operator who described a boundary asked for a run graded through
        # the door. Serving on loopback under that name would file zeroes that
        # read exactly like a Playbook which found nothing.
        ledger = Ledger()

        self.assertIsNone(evaluation.route(ledger, self.boundary("rk2-selftest-absent-door")))

        violation = list(ledger.violations)[0]
        self.assertEqual(1, len(list(ledger.violations)))
        self.assertEqual("environment:RK_AGENT_PROXY_CONTAINER", violation.source)
        self.assertIn("the fixture has to be served where the door can dial it", violation.detail)


class Configuration(unittest.TestCase):
    """The Program document each repeat is opened under."""

    def written(self, one_fixture: fixture.Fixture, slug: str = "eval-selftest") -> Path:
        where = evaluation.Served(
            variant="vulnerable", host=evaluation.HOST, port=44321, scheme="http"
        )
        return evaluation.configuration(scratch(), slug, one_fixture, where)

    def test_the_document_is_one_the_production_reader_accepts(self):
        # The whole point of criterion 6: what is written here goes through
        # `config.load`, not through an evaluation-only parser.
        loaded, refusals = config.load(self.written(compiled(one())))
        self.assertEqual([], list(refusals))
        self.assertIsNotNone(loaded)

    def test_the_document_compiles_to_a_scope_policy(self):
        # And through the production scope compiler, which is a second reader
        # with rules of its own: a document that loads and does not compile
        # authorises nothing, so `program.run` refuses it before it reaches a
        # Program. This is what refuses a scope written as the loopback address.
        loaded, _ = config.load(self.written(compiled(one())))
        policy, refusals = scope.compile_policy(loaded)
        self.assertEqual([], list(refusals))
        # Two: the origin and the route the card declares. Ticket 176.
        self.assertEqual(2, len(policy.rules))

    def test_the_scope_names_the_fixture_at_the_port_it_is_listening_on(self):
        loaded, _ = config.load(self.written(compiled(one())))
        included = loaded.document["scope"]["include"]
        self.assertEqual(1, len(included))
        self.assertEqual("object-ownership.localhost", included[0]["host"])
        self.assertEqual([44321], included[0]["ports"])
        self.assertEqual(["http"], included[0]["protocols"])

    def test_the_scope_names_the_route_the_card_declares(self):
        # Ticket 176. `record_configured_subjects` writes one Application per
        # exact target rule and `open_configured_recon` one recon Task per
        # Application, so this list is the whole of what a fresh Program is
        # pointed at. Every fixture in the corpus serves one route and answers
        # 404 at `/`, so the root alone opened the only recon Task against a
        # subject that does not exist.
        loaded, _ = config.load(self.written(compiled(one())))
        self.assertEqual(["/", "/notes/2"], loaded.document["scope"]["include"][0]["paths"])

    def test_a_card_whose_route_is_the_root_names_it_once(self):
        loaded, _ = config.load(self.written(compiled(one(**{"bb:subject": "/"}))))
        self.assertEqual(["/"], loaded.document["scope"]["include"][0]["paths"])

    def test_the_scope_may_not_name_the_address_the_fixture_is_bound_to(self):
        # The reason the two differ, held as a rule rather than as a comment:
        # an inclusion naming loopback is refused by the compiler every Program
        # is opened through, so a fixture scoped that way is ungradeable.
        loaded, _ = config.load(
            write(
                self.written(compiled(one())).read_text(encoding="utf-8").replace(
                    "object-ownership.localhost", evaluation.HOST
                ),
                "eval-address.toml",
            )
        )
        self.assertIsNone(scope.compile_policy(loaded)[0])

    def test_two_fixtures_served_at_once_are_two_origins(self):
        other = fixture.compile_corpus(
            corpus(error_detail=(frontmatter(FIELDS) + BODY, APPLICATION))
        )["error-detail"]
        self.assertNotEqual(evaluation.origin(compiled(one())), evaluation.origin(other))

    def test_the_fixture_s_identities_are_carried_into_the_program(self):
        loaded, _ = config.load(self.written(compiled(one())))
        self.assertEqual(
            ["alice", "bob"], [item["name"] for item in loaded.document["identity"]]
        )

    def test_a_fixture_with_no_caller_declares_no_identity(self):
        loaded, _ = config.load(self.written(compiled(one(**{"bb:identities": []}))))
        self.assertEqual([], loaded.document.get("identity", []))

    def test_nothing_the_evaluation_runs_may_mutate_the_fixture(self):
        # A grading run that changed the target would be measuring a different
        # application on the second repeat than on the first.
        loaded, _ = config.load(self.written(compiled(one())))
        self.assertFalse(loaded.document["rules_of_engagement"]["mutation"])

    def test_a_slug_the_reader_would_refuse_is_refused_by_the_reader(self):
        # `_nameable` checks this up front against `config.SLUG`, which is the
        # same pattern this proves the reader applies -- so the two cannot drift.
        _, refusals = config.load(self.written(compiled(one()), slug="Eval-Selftest"))
        self.assertTrue(refusals)

    def test_the_written_document_is_utf_8_json_safe_text(self):
        path = self.written(compiled(one()))
        self.assertTrue(json.dumps(path.read_text(encoding="utf-8")))
