"""What the harness calls a path, asked of both things that decide it.

Two programs read a path out of a source Artifact and they cannot share a line
of code: `redkraken.jsscan` is an analyser the runtime ships into a container,
and `skills/analyse-source/scripts/extract_paths.py` is a Skill script that runs
with an empty working directory and nothing beside it to import. So the rule
they are held to is not "one implementation" but "one answer": for any literal
both of them call a path, the path they report is the same string.

They are still allowed to disagree about *whether* something is a path, and do.
`path_of` follows an absolute URL and a protocol-relative one down to their path
because a route is what it is asking for; `extract_paths` refuses both, because
a literal naming somebody's host is a scope decision rather than a path this
Task found, and files it under `urls` instead. Those are different questions
with different answers and this file pins them apart rather than together.

The third seam is the one ticket 90's measurement did not find and reading the
schema did. `paths` is not the analyst's view: `tool.serve` files it into
`tool_run_paths`, and `rk2_source_citation` runs a proposed route and a stored
one through `rk2_clean_path` before comparing them. So a path in `paths` that
`rk2_clean_path` refuses is worse than a missing one -- it is a row that says
the run found something and can never be matched to anybody who proposes it.
`groundable` is that acceptor restated where the analyser can reach it, and what
is tested here is that nothing else can get into `paths`.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from redkraken import jsscan

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "src/redkraken/skills/analyse-source/scripts/extract_paths.py"


def _extract_paths():
    """`extract_paths.py` as a module, loaded from where the harness ships it."""
    spec = importlib.util.spec_from_file_location("_extract_paths", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract_paths = _extract_paths()


def script(text: str) -> dict:
    """One run of the shipped script over one Artifact, through its real stdin.

    Run as a subprocess rather than by calling `extract` directly, because what
    the registry starts is a program reading an envelope, and a test that
    imported around that would stop checking the half that has been wrong
    before -- the reading of stdin.
    """
    envelope = json.dumps({"artifacts": [{"sha256": "0" * 64, "text": text}]})
    done = subprocess.run(
        [sys.executable, "-s", str(SCRIPT)],
        input=envelope.encode(),
        capture_output=True,
        check=True,
    )
    return json.loads(done.stdout)


#: One literal, what `path_of` makes of it, and what `extract_paths` makes of
#: it. `None` on either side means that reader does not call this a path, which
#: is a difference the first test allows and the second test spells out.
CORPUS = (
    # The plain case, which has always worked and is here so a regression in
    # the rest of this table is visibly a regression in the rest of the table.
    ("/api/v1/users", "/api/v1/users", "/api/v1/users"),
    # A braced segment is a path segment. `jsscan._named_hole` already spells a
    # template hole `{id}`, so this is a shape the harness emits and, until
    # ticket 92, one half of it declined to read back.
    ("/orgs/{org}/labels", "/orgs/{org}/labels", "/orgs/{org}/labels"),
    ("/orders/${id}", "/orders/${id}", "/orders/${id}"),
    # The shape ticket 90 measured: one method, one space, one path, which is
    # how a generated API client writes its whole surface down.
    ("GET /orgs/{org}/labels", "/orgs/{org}/labels", "/orgs/{org}/labels"),
    ("POST /users/login", "/users/login", "/users/login"),
    ("DELETE /articles/{slug}", "/articles/{slug}", "/articles/{slug}"),
    # And the ways that shape is not that shape. The verbs are named rather
    # than matched, uppercase and one space, so prose does not walk in behind
    # them.
    ("GETTER /x", None, None),
    ("get /x", None, None),
    ("GET  /x", None, None),
    ("GET /x /y", None, None),
    ("GET x", None, None),
    ("PATCH", None, None),
    ("not a path at all", None, None),
    ("", None, None),
    # The query is cut on both sides now. It is still reported -- see
    # `LiteralTest` -- but not under the key the runtime files as ground truth.
    ("/api/orders?id=1&sort=asc", "/api/orders", "/api/orders"),
    ("GET /api/orders?id=1", "/api/orders", "/api/orders"),
)

#: Literals the two readers answer differently on purpose, with the answer each
#: gives. A host is a scope decision, so `extract_paths` refuses to call one a
#: path and files it under `urls`; `path_of` is asked for the route and gives
#: the route.
DIVIDED = (
    ("https://cdn.example.com/app.js", "/app.js", None),
    ("//cdn.example.com/app.js", "/app.js", None),
    ("/api/orders#fragment", "/api/orders", None),
    # The bare root. `path_of` is asked what route a literal names and this one
    # names the root; `extract_paths` requires a character after the slash,
    # because a bundle holding `"/"` has told an analyst nothing and the list it
    # is reading is meant to be worth reading.
    ("/", "/", None),
)


class AgreementTest(unittest.TestCase):
    """Ticket 92 criterion 1: one answer, from two programs that cannot share."""

    def test_both_readers_report_the_same_path_for_the_same_literal(self):
        for literal, expected, _ in CORPUS:
            with self.subTest(literal=literal):
                self.assertEqual(expected, jsscan.path_of(literal))
        for literal, _, expected in CORPUS:
            with self.subTest(literal=literal):
                self.assertEqual(expected, extract_paths.path_of(literal))

    def test_where_they_differ_they_differ_on_purpose(self):
        for literal, mine, theirs in DIVIDED:
            with self.subTest(literal=literal):
                self.assertEqual(mine, jsscan.path_of(literal))
                self.assertEqual(theirs, extract_paths.path_of(literal))

    def test_each_reader_names_the_other_and_the_test_that_holds_them(self):
        # The comment is the only thing keeping two copies of one rule in step
        # between the day one is edited and the day this test is run, so its
        # absence is the failure rather than a style note.
        for source in (Path(jsscan.__file__), SCRIPT):
            with self.subTest(source=source.name):
                text = source.read_text(encoding="utf-8")
                self.assertIn("tests/test_jsscan.py", text)


class VerbTest(unittest.TestCase):
    """Ticket 92 criterion 2: a literal that names its own method says so."""

    def test_the_method_is_reported_beside_the_path(self):
        self.assertEqual("GET", jsscan.verb_of("GET /orgs/{org}"))
        self.assertEqual("POST", jsscan.verb_of("POST /users"))
        self.assertEqual("GET", extract_paths.verb_of("GET /orgs/{org}"))

    def test_a_literal_that_names_no_method_names_none(self):
        for literal in ("/orgs/{org}", "get /x", "GETTER /x", "not a path",
                        "GET  /x", "GET/x", "GET x", "GET /x\n"):
            with self.subTest(literal=literal):
                self.assertIsNone(jsscan.verb_of(literal))
                self.assertIsNone(extract_paths.verb_of(literal))

    def test_stripping_the_method_does_not_strip_the_newline_rule_with_it(self):
        # `$` matches before a trailing newline, and the method came off before
        # `path_of` reached its own newline guard, so `"GET /x\n"` -- a literal
        # holding a newline -- became a route. The rule the method form is
        # admitted through is the one it was quietly widening.
        for literal in ("GET /x\n", "POST /a/b\n"):
            with self.subTest(literal=literal):
                self.assertIsNone(jsscan.path_of(literal))
                self.assertIsNone(extract_paths.path_of(literal))

    def test_the_named_methods_are_the_whole_of_what_is_admitted(self):
        # The same list `calls` already reads a call site's verb from, reused
        # rather than copied: two lists would drift and the drift would be
        # silent, because a route under no verb still reports its path.
        self.assertEqual(
            ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"),
            tuple(sorted(jsscan.METHODS)),
        )
        self.assertEqual(tuple(sorted(jsscan.METHODS)), tuple(sorted(extract_paths.METHODS)))

    def test_the_operators_that_cut_are_the_same_tuple_on_both_sides(self):
        # Both files say in a comment that this test keeps their `CUTS` in step.
        # It did not until the review said so, which is how a comment claiming a
        # check that does not exist is worse than no comment.
        self.assertEqual(("?", "&", "#"), jsscan.CUTS)
        self.assertEqual(jsscan.CUTS, extract_paths.CUTS)


class TemplateTest(unittest.TestCase):
    """A URI template writes its query inside the braces, so the cut is too.

    RFC 6570's `operator` rule, read rather than recalled: `op-level2` is
    `"+" / "#"` and `op-level3` is `"." / "/" / ";" / "?" / "&"`. Three of those
    open something that is not the path. The rest expand inside it, and a cut
    there would report a prefix of a route as the route.

    This is not a corner. Every one of the six paths ticket 92's own measurement
    got wrong on the real octokit bundle was this shape, and the way it was
    wrong was the dangerous way: `/repos/{owner}/{repo}/actions/caches{` is
    groundable, so it would have been filed as a path the run found.
    """

    QUERY = (
        ("/orgs/{org}/packages/{name}/restore{?token}", "/orgs/{org}/packages/{name}/restore"),
        ("/repos/{owner}/{repo}/actions/caches{?key,ref}", "/repos/{owner}/{repo}/actions/caches"),
        ("/repos/{owner}/{repo}/releases/{id}/assets{?name,label}",
         "/repos/{owner}/{repo}/releases/{id}/assets"),
        ("/search{&page,per_page}", "/search"),
        ("/page{#section}", "/page"),
        ("/orders/{id}?full=1", "/orders/{id}"),
    )

    #: Braces that do not pair, either because the source left one open or
    #: because a nested expansion invites the cut into the middle of one. The
    #: spec review found all three: `/x/{a{?b}}` cut at the inner `{?` gave
    #: `/x/{a`, which is dangling and `groundable`, so it would have been filed.
    RAGGED = (
        ("/a{b", None),
        ("/a}b", None),
    )

    #: RFC 6570 has no nested expression, so this is not a template anybody
    #: wrote and the two readers are allowed to land differently on it. What
    #: neither may do is cut inside the outer brace: that is where `/x/{a` came
    #: from, and `/x/{a` is dangling and `groundable`.
    NESTED = "/x/{a{?b}}"

    #: The operators that expand inside the path. Cutting at one of these would
    #: be reporting less than the file said.
    KEPT = (
        "/base{+path}",
        "/base{.format}",
        "/base{/segment}",
        "/base{;matrix}",
    )

    def test_a_query_expansion_is_not_part_of_the_route(self):
        for literal, expected in self.QUERY:
            with self.subTest(literal=literal):
                self.assertEqual(expected, jsscan.path_of(literal))
                self.assertEqual(expected, extract_paths.path_of(literal))

    def test_an_expansion_inside_the_path_stays_in_the_path(self):
        for literal in self.KEPT:
            with self.subTest(literal=literal):
                self.assertEqual(literal, jsscan.path_of(literal))
                self.assertEqual(literal, extract_paths.path_of(literal))

    def test_what_the_cut_leaves_behind_is_never_a_dangling_brace(self):
        # The failure this class exists for, stated as the property rather than
        # as the six examples: a cut that landed inside a template would leave
        # an unbalanced brace, and an unbalanced brace still grounds.
        for literal in [one for one, _ in self.QUERY + self.RAGGED] + [self.NESTED]:
            with self.subTest(literal=literal):
                for reader in (jsscan.path_of, extract_paths.path_of):
                    answer = reader(literal)
                    if answer is not None:
                        self.assertEqual(answer.count("{"), answer.count("}"))

    def test_a_brace_that_does_not_pair_is_not_a_path(self):
        # `_named_hole` spells a hole `{id}`, so a lone brace is not a shape
        # either program emits, and `extract_paths.PATH` already refused it.
        # `jsscan.path_of` did not, which is a disagreement criterion 1 forbids.
        for literal, expected in self.RAGGED:
            with self.subTest(literal=literal):
                self.assertEqual(expected, jsscan.path_of(literal))
                self.assertEqual(expected, extract_paths.path_of(literal))

    def test_a_nested_expansion_is_never_cut_into(self):
        # jsscan reports the literal whole; `extract_paths.PATH` has no
        # production for a brace inside a brace and refuses it. Both are honest
        # answers and neither is `/x/{a`.
        self.assertEqual(self.NESTED, jsscan.path_of(self.NESTED))
        self.assertIsNone(extract_paths.path_of(self.NESTED))

    def test_a_hole_holds_one_segment_and_never_a_sentence(self):
        # The space rule, arriving through the template extension: `[^{}]`
        # admitted a newline and a space, so a comment in braces was a path.
        for literal in ("/a{see the docs}", "/a${see the docs}", "/a{x\ny}"):
            with self.subTest(literal=literal):
                self.assertIsNone(jsscan.path_of(literal))
                self.assertIsNone(extract_paths.path_of(literal))

    def test_the_dollar_is_a_sub_delim_like_any_other(self):
        # RFC 3986: `sub-delims = "!" / "$" / "&" / "'" / "(" / ")" / "*" / "+"
        # / "," / ";" / "="`. It was the one this repository's own class left
        # out, so a real path carrying it was not a path here.
        self.assertEqual("/api/a$b", jsscan.path_of("/api/a$b"))
        self.assertEqual("/api/a$b", extract_paths.path_of("/api/a$b"))

    def test_every_sub_delim_the_rfc_names_is_admitted(self):
        for mark in "!$&'()*+,;=":
            literal = f"/api/a{mark}b"
            with self.subTest(mark=mark):
                self.assertEqual(literal, jsscan.path_of(literal))
                self.assertEqual(literal, extract_paths.path_of(literal))


class GroundableTest(unittest.TestCase):
    """Ticket 92 criterion 7: `paths` holds what `rk2_clean_path` will take.

    The acceptor is in
    `migrations/20260813T090000Z__a_recon_run_becomes_typed_surface.sql`. It is
    restated here rather than imported because the analyser runs in a container
    with no database, and it is tested against its own list rather than against
    the SQL for the same reason.
    """

    ACCEPTED = ("/", "/api/orders", "/orgs/{org}/labels", "/orders/${id}", "/a/b.c~d")
    REFUSED = (
        "",
        "api/orders",          # not absolute
        "//cdn.example.com",   # a host, not a route
        "/api//orders",        # `rk2_clean_path` refuses `%//%` anywhere
        "/api/orders?id=1",    # a query is not part of the route
        "/api/orders#f",       # a fragment never leaves the client
        "/api/a%20b",          # percent-encoding: send the decoded route
        "/api/ orders",        # whitespace
        "/api/./orders",       # not in normal form
        "/api/../orders",
        "/api/orders/..",
        "/api/orders/.",
    )

    def test_every_shape_the_schema_stores_is_groundable(self):
        for path in self.ACCEPTED:
            with self.subTest(path=path):
                self.assertTrue(jsscan.groundable(path))
                self.assertTrue(extract_paths.groundable(path))

    def test_every_shape_the_schema_refuses_is_not(self):
        for path in self.REFUSED:
            with self.subTest(path=path):
                self.assertFalse(jsscan.groundable(path))
                self.assertFalse(extract_paths.groundable(path))


class LiteralTest(unittest.TestCase):
    """Ticket 92 criterion 8: what `paths` drops is still reported somewhere.

    `paths` is the grounding key and every entry in it has to clean. The literal
    as the build actually wrote it is a different fact and a useful one -- the
    query string is the parameter half of a surface -- so it is reported beside
    it rather than instead of it.
    """

    SOURCE = (
        'const E={a:["POST /orgs/{org}/actions/runners/{runner_id}/labels"],'
        'b:["GET /repos/{owner}/{repo}"]};'
        'fetch("/api/orders?id=1&sort=asc");'
        'const cdn="//cdn.example.com/app.js";'
        'const u="https://cdn.example.com/app.js";'
        'const t="not a path";'
    )

    @classmethod
    def setUpClass(cls):
        cls.answer = script(cls.SOURCE)

    def test_paths_holds_the_routes_and_every_one_of_them_grounds(self):
        self.assertEqual(
            [
                "/api/orders",
                "/orgs/{org}/actions/runners/{runner_id}/labels",
                "/repos/{owner}/{repo}",
            ],
            self.answer["paths"],
        )
        for path in self.answer["paths"]:
            with self.subTest(path=path):
                self.assertTrue(extract_paths.groundable(path))

    def test_the_literal_the_build_wrote_is_kept_as_it_was_written(self):
        self.assertEqual(
            [
                "/api/orders?id=1&sort=asc",
                "GET /repos/{owner}/{repo}",
                "POST /orgs/{org}/actions/runners/{runner_id}/labels",
            ],
            self.answer["literals"],
        )

    def test_a_host_is_still_a_url_and_not_a_path(self):
        self.assertEqual(["https://cdn.example.com/app.js"], self.answer["urls"])

    def test_the_denominator_still_says_how_many_strings_were_looked_at(self):
        self.assertEqual(6, self.answer["scanned_literals"])


class MeasurementTest(unittest.TestCase):
    """Ticket 92 criterion 5: the shape ticket 90 measured, with its own count.

    The real file is `@octokit/plugin-rest-endpoint-methods` 10.4.1's `dist-web`
    build, 87,967 bytes of almost nothing but a target's API written this way,
    and it is not checked in: it is a third party's release, and this repository
    ships the harness rather than the things it reads. What is checked in is the
    shape, below, in the spelling that file uses. The count is stated rather than
    asserted to be positive, because "more than zero" was true before ticket 92
    as well -- `js_parse` answered one and `extract_paths` answered none.
    """

    #: Eight rows in the spelling the real file uses, three of them naming the
    #: same path under two methods, so the count of paths and the count of
    #: literals are different numbers and a test cannot pass by conflating them.
    SOURCE = (
        'var Endpoints = {\n'
        '  actions: {\n'
        '    addCustomLabels: ["POST /orgs/{org}/actions/runners/{runner_id}/labels"],\n'
        '    listLabels: ["GET /orgs/{org}/actions/runners/{runner_id}/labels"],\n'
        '    removeAllLabels: ["DELETE /orgs/{org}/actions/runners/{runner_id}/labels"]\n'
        '  },\n'
        '  repos: {\n'
        '    get: ["GET /repos/{owner}/{repo}"],\n'
        '    update: ["PATCH /repos/{owner}/{repo}"],\n'
        '    delete: ["DELETE /repos/{owner}/{repo}"]\n'
        '  },\n'
        '  users: {\n'
        '    getAuthenticated: ["GET /user"],\n'
        '    listEmails: ["GET /user/emails"]\n'
        '  }\n'
        '};\n'
    )

    EXPECTED = [
        "/orgs/{org}/actions/runners/{runner_id}/labels",
        "/repos/{owner}/{repo}",
        "/user",
        "/user/emails",
    ]

    def test_the_skill_script_reports_every_endpoint_the_client_lists(self):
        answer = script(self.SOURCE)
        self.assertEqual(self.EXPECTED, answer["paths"])
        self.assertEqual(8, len(answer["literals"]))

    def test_js_parse_reports_every_endpoint_and_says_nothing_requests_them(self):
        raw = self.SOURCE.encode()
        answer = jsscan.parse(raw, self.SOURCE)
        self.assertEqual(self.EXPECTED, answer["paths"])
        self.assertEqual(8, len(answer["path_literals"]))
        # Every one of them is a table entry rather than a call site, which is
        # the fact `js_routes` is right to report as no routes at all.
        self.assertEqual([], [one for one in answer["path_literals"] if one["requested"]])

    def test_the_method_the_literal_names_reaches_the_answer(self):
        answer = jsscan.parse(self.SOURCE.encode(), self.SOURCE)
        found = {(one["method"], one["value"]) for one in answer["path_literals"]}
        self.assertIn(("GET", "/user"), found)
        self.assertIn(("DELETE", "/repos/{owner}/{repo}"), found)

    def test_js_routes_still_answers_nothing_here_and_that_is_correct(self):
        # Ticket 92's sixth criterion. octokit reaches
        # `octokit.request.defaults(defaults)` with the route inside an object,
        # so no call site carries a path literal. A change that made this report
        # the endpoints would have broken the grounding rule that is worth more
        # than the endpoints.
        answer = jsscan.routes(self.SOURCE.encode(), self.SOURCE)
        self.assertEqual([], answer["routes"])
        self.assertEqual([], answer["paths"])


class VersionTest(unittest.TestCase):
    """Ticket 92 criterion 9: the answer shape moved, so the version moved."""

    def test_the_analyser_reports_the_shape_it_now_prints(self):
        self.assertEqual("rk2-jsscan 2", jsscan.VERSION)
