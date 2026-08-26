"""The graph surface as a function, without a database and without a browser.

`tests/test_database.py` holds the half that needs rows: that the three
statements run against the live schema, and that a Program's graph is drawn
from that Program's rows and no other's. This module holds the other half --
what a route produces, what it refuses before a statement is ever built, and
what the socket refuses before a route is reached.

That half is worth its own file because the things most worth being sure of
here are answerable with nothing behind them. An id that is not an id, a digest
with a separator in it, a content policy that let a captured response run as
script, and a method this surface does not have are each a way for a read-only
picture to become something else, and none of them needs a campaign to provoke.
"""

from __future__ import annotations

import ast
import http.client
import json
import math
import re
import threading
import unittest
from pathlib import Path

from redkraken import graph, pg, ui


#: A password nowhere near a real one, so that "no route carries a credential"
#: is a question with an answer.
SECRET = "not-the-real-one"
RUNTIME = f"postgresql://rk2_runtime:{SECRET}@127.0.0.1:1/rk2"


def surface(**overrides) -> graph.Graph:
    """A surface with nothing behind it, for the parts that reach nothing."""
    fields = {
        "runtime": pg.settings_from_url(RUNTIME),
        "configuration_path": Path("program.toml"),
        "slug": "acme-web",
        "origin": "http://127.0.0.1:8788",
    }
    return graph.Graph(**(fields | overrides))


class PolicyTest(unittest.TestCase):
    """What a browser is allowed to do with this page, and what it is not."""

    def test_the_policy_permits_the_one_script_this_surface_is_drawn_by(self):
        # The console refuses every script and `tests/test_ui.py` holds it to
        # that. This one is a canvas and cannot exist without one, which is the
        # whole reason it is a second command and not a page over there.
        self.assertIn("script-src 'self'", graph.POLICY)

    def test_the_policy_permits_no_script_written_into_the_page(self):
        # The one script is served from its own route so that this can say
        # `'self'` and mean it. Inline script is what an injected string would
        # arrive as, and permitting it wholesale would spend the directive on
        # nothing -- the page has no inline script left to permit.
        self.assertNotIn("'unsafe-inline'", graph.POLICY.split("style-src")[0])
        self.assertNotIn("<script>", graph.PAGE)

    def test_the_policy_permits_no_outbound_direction_at_all(self):
        # `connect-src 'self'` is the page asking this server for the JSON it
        # draws. Every other direction is the console's argument unchanged: a
        # surface that could fetch could exfiltrate what it is showing, and what
        # it is showing is a campaign against somebody else's systems.
        self.assertIn("default-src 'none'", graph.POLICY)
        self.assertIn("connect-src 'self'", graph.POLICY)
        self.assertNotIn("frame-src", graph.POLICY)
        self.assertIn("form-action 'none'", graph.POLICY)

    def test_the_only_image_this_surface_permits_is_one_it_already_holds(self):
        # The node icons are Lucide path data built into a data URL by the page
        # itself. `data:` is not an origin and cannot be fetched from, so this
        # permits a shape this file already contains and still permits no
        # request. Without it `default-src 'none'` blocks every icon.
        self.assertIn("img-src data:", graph.POLICY)
        self.assertNotIn("img-src *", graph.POLICY)
        self.assertNotIn("img-src 'self'", graph.POLICY)

    def test_every_answer_carries_nosniff(self):
        # Load-bearing rather than tidy. `/artifact` serves the bytes a target
        # actually sent, and a captured HTML response a browser were allowed to
        # sniff would run as script in the one origin allowed to ask this
        # surface for the rest of the campaign.
        self.assertIn(("X-Content-Type-Options", "nosniff"), graph.HEADERS)

    def test_the_page_carries_no_outbound_reference(self):
        # A `src` or an `href` at another origin would be a request the policy
        # blocks, which is a page whose own markup disagrees with its header.
        self.assertNotIn("http://", graph.PAGE.replace("http://www.w3.org", ""))
        self.assertNotIn("https://", graph.PAGE)


class RoutingTest(unittest.TestCase):
    """What each route answers, decided with nothing behind it."""

    def setUp(self):
        self.graph = surface()

    def test_the_root_is_the_page_with_this_programs_name_in_it(self):
        answer = graph.respond(self.graph, "GET", "/")

        self.assertEqual(200, answer.status)
        self.assertIn("text/html", answer.content_type)
        self.assertIn('<body data-program="acme-web">', answer.body)
        self.assertIn('<script src="/app.js">', answer.body)
        self.assertNotIn("__PROGRAM__", answer.body)

    def test_a_program_name_cannot_close_the_attribute_it_is_written_into(self):
        # The slug is the operator's own word out of their own file, so this is
        # not a boundary anything hostile crosses. It is escaped anyway, because
        # "the input is trusted" is a claim about today's callers.
        answer = graph.respond(surface(slug='a"><script>alert(1)</script>'), "GET", "/")

        self.assertNotIn("<script>alert", answer.body)
        self.assertIn("&quot;&gt;&lt;script&gt;", answer.body)

    def test_the_script_is_served_whole_and_names_no_program(self):
        # It is the same bytes for every Program this command is ever opened
        # against. The name it draws comes off the page it was loaded by, which
        # is what lets the policy name this script by origin.
        answer = graph.respond(self.graph, "GET", "/app.js")

        self.assertEqual(200, answer.status)
        self.assertIn("text/javascript", answer.content_type)
        self.assertIn("const PROGRAM = document.body.dataset.program;", answer.body)
        self.assertNotIn("acme-web", answer.body)

    def test_a_body_the_browser_already_holds_is_answered_and_not_resent(self):
        # The page polls this route every three seconds and the whole campaign
        # is in the answer. Between two laps that changed nothing, an
        # unconditional read is a megabyte transferred and a megabyte parsed to
        # redraw the picture already on the screen.
        first = graph.respond(self.graph, "GET", "/data.json")

        self.assertEqual(200, first.status)
        self.assertTrue(first.etag.startswith('W/"'), first.etag)

        again = graph.respond(self.graph, "GET", "/data.json", none_match=first.etag)

        self.assertEqual(304, again.status)
        self.assertEqual("", again.body)
        self.assertEqual(first.etag, again.etag)

    def test_a_tag_for_a_body_this_surface_does_not_hold_is_the_whole_body(self):
        answer = graph.respond(self.graph, "GET", "/data.json", none_match='W/"nothing"')

        self.assertEqual(200, answer.status)
        self.assertNotEqual("", answer.body)

    def test_a_node_grows_with_its_edges_and_stops_at_the_ceiling(self):
        # The rule is JavaScript in a string, so what is asked here is the two
        # numbers the page ships and the shape they make. Read out of the
        # script rather than repeated, so a change to one is a failure here
        # rather than a picture nobody compared with its own description.
        growth = re.search(r"const MAX_GROWTH = (\d+);", graph.SCRIPT)
        spread = re.search(r"const GROWTH_SPREAD = ([\d.]+);", graph.SCRIPT)
        self.assertIsNotNone(growth)
        self.assertIsNotNone(spread)

        cap, over = int(growth.group(1)), float(spread.group(1))
        sized = [min(cap, 1 + math.sqrt(d) / over) for d in range(0, 400)]

        # A node with no edges is its own base size, growth is monotone in the
        # edge count, and nothing ever exceeds the ceiling.
        self.assertEqual(1.0, sized[0])
        self.assertEqual(sorted(sized), sized)
        self.assertEqual(cap, max(sized))
        # And the ceiling is somewhere a real graph reaches. Measured on the
        # here engagement: median 3 edges, 95th percentile 9, busiest 22.
        self.assertLess(sized.index(cap), 200)
        # The spread has to be visible, not merely present: the busiest node
        # measured here is at least three times a leaf. At the first numbers
        # shipped -- cap 5, spread 2.2 -- it was 3.1x and read as flat.
        self.assertGreater(sized[22], 3.0)

    def test_a_route_this_surface_does_not_have_is_answered_and_not_drawn(self):
        answer = graph.respond(self.graph, "GET", "/databases")

        self.assertEqual(404, answer.status)

    def test_this_surface_has_no_method_but_get(self):
        # Not a form it refuses: a method it does not have. There is no verb
        # here, so there is nothing a POST could be asking for.
        answer = graph.respond(self.graph, "POST", "/data.json")

        self.assertEqual(405, answer.status)


class NodeTest(unittest.TestCase):
    """What is refused before a statement is built, which is where it matters."""

    def setUp(self):
        self.graph = surface()

    def refused(self, identifier: str) -> str:
        body, kind = graph.node(self.graph.runtime, self.graph.slug, identifier)
        self.assertEqual(graph.JSON, kind)
        return json.loads(body)["error"]

    def test_an_id_that_is_not_an_id_never_reaches_a_connection(self):
        # If it reached one it would fail on the socket, because the settings
        # above point at a port nothing is listening on. An answer here is the
        # proof that the check ran first.
        self.assertEqual("not an id", self.refused("' OR 1=1 --"))

    def test_an_id_that_is_a_uuid_with_something_after_it_is_not_an_id(self):
        self.assertEqual(
            "not an id", self.refused("6f1b0e0a-2f3f-4a2e-9a1f-6d0a2c5b7e31'--")
        )

    def test_an_address_may_hold_only_what_stands_in_an_address(self):
        self.assertEqual("not an address", self.refused("ip:127.0.0.1; DROP"))
        self.assertEqual("not an address", self.refused("ip:"))

    def test_an_address_longer_than_any_address_is_refused(self):
        self.assertEqual("not an address", self.refused("ip:" + "a" * 46))


class ArtifactTest(unittest.TestCase):
    """The one route that reads bytes off a disk instead of out of a database."""

    def setUp(self):
        self.root = Path(self.enterContext(_temporary()))
        self.digest = "a" * 64
        held = self.root / self.digest[:2] / self.digest
        held.parent.mkdir(parents=True)
        held.write_bytes(b"GET / HTTP/1.1\r\nHost: acme.example\r\n\r\n")

    def test_the_bytes_the_door_filed_come_back_as_text(self):
        body, kind = graph.artifact(self.root, self.digest)

        self.assertEqual(graph.TEXT, kind)
        self.assertIn("Host: acme.example", body.decode())

    def test_a_digest_with_a_separator_in_it_is_refused_before_a_path_is_built(self):
        for asked in ("../" * 20 + "etc/passwd", "/" * 64, "a/" + "b" * 62):
            with self.subTest(asked=asked):
                body, _ = graph.artifact(self.root, asked)
                self.assertEqual(b"not a digest", body)

    def test_a_digest_that_is_not_lowercase_hexadecimal_is_refused(self):
        body, _ = graph.artifact(self.root, "A" * 64)

        self.assertEqual(b"not a digest", body)

    def test_a_digest_this_installation_does_not_hold_says_so(self):
        body, _ = graph.artifact(self.root, "b" * 64)

        self.assertIn(b"does not hold", body)

    def test_an_installation_with_no_store_says_that_rather_than_raising(self):
        # The command does not refuse a missing store, unlike every other place
        # one is asked for: this route only reads, so an absent store costs the
        # proof pane and not the graph.
        body, _ = graph.artifact(None, self.digest)

        self.assertIn(b"not told where the artifacts are", body)

    def test_a_body_larger_than_the_cap_is_capped_and_says_by_how_much(self):
        big = "c" * 64
        held = self.root / big[:2] / big
        held.parent.mkdir(parents=True)
        held.write_bytes(b"x" * (graph.ARTIFACT_CAP + 500))

        body, _ = graph.artifact(self.root, big)

        self.assertIn("500 more byte(s) not shown", body.decode())


class StatementTest(unittest.TestCase):
    """That the statements are parameterised, asked of the source.

    Read as a tree rather than as text. The tooling this grew out of built its
    statements with `str.format`, guarded by a UUID parse and a character
    allowlist -- which was right, and which is the kind of right that has to
    stay right at every call site forever. A parameter is right once.
    """

    #: The three the module holds, and there are no others: a fourth would be a
    #: statement somebody added without deciding how its values get in.
    STATEMENTS = ("SURFACE", "NODE", "ADDRESS")

    def setUp(self):
        self.source = Path(graph.__file__).read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_no_statement_is_built_by_formatting_anything_into_it(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.JoinedStr):
                self.assertNotIn("SELECT", ast.unparse(node).upper())
            if isinstance(node, ast.Attribute) and node.attr == "format":
                self.fail(f"a statement formatted at line {node.lineno}")

    def test_every_statement_scopes_every_table_it_reads_to_one_program(self):
        # The runtime's row-level policy is `true` -- it is the agent role that
        # `rk2_program()` fences -- so a subselect that forgot its `program_id`
        # would quietly draw this campaign's graph with another's rows in it.
        # Counted rather than eyeballed: every `FROM <table>` that is not a
        # lateral or a subquery alias is answered by a `program_id` filter.
        for name in self.STATEMENTS:
            statement = getattr(graph, name)
            with self.subTest(statement=name):
                self.assertGreater(statement.count("program_id = $1"), 0)
                self.assertNotIn("program_id = '", statement)

    def test_the_surface_read_is_bounded_and_says_what_it_left_out(self):
        # A bounded picture that did not say it was bounded would read as the
        # whole campaign, which is the one lie a graph can tell by being honest
        # about every row it drew.
        self.assertIn("LIMIT $2", graph.SURFACE)
        self.assertIn("'omitted'", graph.SURFACE)

    def test_the_read_cannot_write_whatever_the_statement_above_it_says(self):
        # Asserted once, in `ask`, rather than trusted to every statement in the
        # module being a SELECT.
        self.assertIn('"SET TRANSACTION READ ONLY"', self.source)


class ServerTest(unittest.TestCase):
    """The one question the socket answers, which a route cannot answer for it."""

    def setUp(self):
        self.graph = surface()
        self.server = graph.server(self.graph, host="127.0.0.1", port=0)
        self.address = f"127.0.0.1:{self.server.server_address[1]}"
        self.graph.origin = f"http://{self.address}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.shutdown)

    def request(self, method: str, path: str, *, host: str | None = None):
        """One request on a connection this test does not keep.

        `Connection: close` is not politeness. The server answers one request at
        a time and speaks HTTP/1.1, so a connection left open is a connection it
        is still waiting on -- and a test that asked twice would block on its
        own first socket rather than reach the second route.
        """
        connection = http.client.HTTPConnection(self.address, timeout=10)
        self.addCleanup(connection.close)
        connection.request(
            method,
            path,
            headers={
                "Host": host if host is not None else self.address,
                "Connection": "close",
            },
        )
        return connection.getresponse()

    def test_the_page_comes_back_with_the_headers_every_answer_carries(self):
        answer = self.request("GET", "/")

        self.assertEqual(200, answer.status)
        self.assertEqual(graph.POLICY, answer.headers["Content-Security-Policy"])
        self.assertEqual("DENY", answer.headers["X-Frame-Options"])
        self.assertEqual("nosniff", answer.headers["X-Content-Type-Options"])
        self.assertEqual("no-referrer", answer.headers["Referrer-Policy"])
        self.assertEqual("no-store", answer.headers["Cache-Control"])

    def test_a_request_naming_another_host_is_refused_before_it_is_routed(self):
        # DNS rebinding: what the other page controls is the name, and what it
        # cannot control is the Host header that name arrives in.
        answer = self.request("GET", "/", host="graph.example.com")

        self.assertEqual(421, answer.status)

    def test_a_post_is_refused_with_the_method_and_not_with_a_form(self):
        answer = self.request("POST", "/data.json")

        self.assertEqual(405, answer.status)

    def test_no_route_carries_the_password_this_surface_connects_with(self):
        for path in ("/", "/node?id=nonsense", "/artifact?sha=nonsense"):
            with self.subTest(path=path):
                self.assertNotIn(SECRET, self.request("GET", path).read().decode())


class BuildTest(unittest.TestCase):
    """Opening the surface, which is where a bad configuration is found."""

    def test_a_configuration_that_will_not_load_is_refused_in_the_terminal(self):
        from redkraken.outcome import Ledger

        ledger = Ledger()

        opened = graph.build(
            ledger, pg.settings_from_url(RUNTIME), Path("no-such-file.toml")
        )

        self.assertIsNone(opened)
        self.assertTrue(ledger.violations)


class ResponseTest(unittest.TestCase):
    """That this surface answers in the shape the console already answers in."""

    def test_a_response_here_is_the_consoles_response(self):
        # Not a second dataclass with the same three fields. Two shapes for one
        # answer is two places for a header to be forgotten.
        answer = graph.respond(surface(), "GET", "/")

        self.assertIsInstance(answer, ui.Response)


def _temporary():
    import tempfile

    return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
