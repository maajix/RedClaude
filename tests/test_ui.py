"""The console as a function, without a database and without a browser.

`tests/test_database.py` holds the half that needs rows: that every panel's
statement runs, that a Program sees only its own, that the six forms reach the
six operator verbs. This module holds the other half -- what a request produces,
what a page says, and what the socket refuses before a page is ever rendered.

That half is worth its own file because most of what this ticket asks for is
answerable without a campaign. A projection that outlived its bytes, a form that
another origin could submit, a label that arrived as markup and a table with no
header cells are all failures of the rendering rather than of the read, and each
one is a page an operator is looking at while believing something untrue.
"""

from __future__ import annotations

import http.client
import threading
import unittest
from pathlib import Path
from unittest import mock

from redkraken import operator, panels, pg, ui
from redkraken.outcome import EXIT_INVALID_CONFIGURATION, Ledger
from tests import fixtures


#: A password nowhere near a real one, in the connection strings a console
#: holds, so that "no page carries a credential" is a question with an answer.
SECRET = "not-the-real-one"
RUNTIME = f"postgresql://rk2_runtime:{SECRET}@127.0.0.1:1/rk2"
PROGRAM = "6f1b0e0a-2f3f-4a2e-9a1f-6d0a2c5b7e31"
AGENT = f"postgresql://rk2_agent:{SECRET}@127.0.0.1:1/rk2"
HUMAN = f"postgresql://rk2_human:{SECRET}@127.0.0.1:1/rk2"


def console(**overrides) -> ui.Console:
    """A console with nothing behind it, for the parts that reach nothing."""
    fields = {
        "runtime": pg.settings_from_url(RUNTIME),
        "agent": pg.settings_from_url(AGENT),
        "human": pg.settings_from_url(HUMAN),
        "configuration_path": Path("program.toml"),
        "slug": "acme-web",
        "origin": "http://127.0.0.1:8787",
    }
    return ui.Console(**(fields | overrides))


def panel(**overrides) -> dict:
    """One panel as `panels` hands it over, which is what a page renders."""
    fields = {
        "name": "findings",
        "caption": "every Finding",
        "columns": ("finding", "exploited", "blocked"),
        "rows": (("F1", "true", "false"),),
        "total": 1,
        "state": panels.READY,
    }
    return panels.Panel(**(fields | overrides)).summary()


class ProjectionTest(unittest.TestCase):
    """Criterion 5: a summary is a projection and never the record."""

    def test_a_summary_is_keyed_by_the_bytes_it_was_taken_from(self):
        held = ui.Summaries()
        held.remember("R1", "a" * 64, "the first revision")

        self.assertEqual((ui.CURRENT, "the first revision"), held.lookup("R1", "a" * 64))

    def test_a_record_that_moved_makes_its_summary_stale_rather_than_wrong(self):
        # The label is the same and the bytes are not, which is exactly the
        # case where showing the sentence would be showing last revision's
        # words under this revision's heading.
        held = ui.Summaries()
        held.remember("R1", "a" * 64, "the first revision")

        state, text = held.lookup("R1", "b" * 64)

        self.assertEqual(ui.STALE, state)
        self.assertEqual("the first revision", text)

    def test_a_label_never_summarised_is_unavailable_and_not_empty(self):
        self.assertEqual((ui.UNAVAILABLE, ""), ui.Summaries().lookup("R9", "a" * 64))

    def test_the_oldest_projection_is_forgotten_when_the_cache_is_full(self):
        held = ui.Summaries(limit=2)
        held.remember("R1", "a" * 64, "one")
        held.remember("R2", "b" * 64, "two")
        held.remember("R3", "c" * 64, "three")

        self.assertEqual(ui.UNAVAILABLE, held.lookup("R1", "a" * 64)[0])
        self.assertEqual(ui.CURRENT, held.lookup("R3", "c" * 64)[0])

    def test_summarising_again_moves_a_label_to_the_end_rather_than_keeping_its_place(self):
        held = ui.Summaries(limit=2)
        held.remember("R1", "a" * 64, "one")
        held.remember("R2", "b" * 64, "two")
        held.remember("R1", "a" * 64, "one again")
        held.remember("R3", "c" * 64, "three")

        self.assertEqual(ui.CURRENT, held.lookup("R1", "a" * 64)[0])
        self.assertEqual(ui.UNAVAILABLE, held.lookup("R2", "b" * 64)[0])

    def test_a_projection_reads_the_scalars_and_not_the_structure(self):
        text = ui.summarise({"kind": "surface", "hits": 3, "nested": {"not": "read"}})

        self.assertEqual("kind: surface, hits: 3", text)

    def test_a_record_with_no_scalar_says_so_rather_than_projecting_nothing(self):
        self.assertEqual("no scalar field to project", ui.summarise({"nested": {"a": 1}}))

    def test_a_projection_is_one_line_and_a_bounded_one(self):
        text = ui.summarise({"note": "word " * 200})

        self.assertEqual(ui.SUMMARY_CHARACTERS, len(text))
        self.assertNotIn("\n", text)


class RoutingTest(unittest.TestCase):
    """What `respond` answers, for the requests that reach no database."""

    def setUp(self):
        self.console = console()

    def test_the_stylesheet_is_served_from_this_process_as_a_stylesheet(self):
        answer = ui.respond(self.console, "GET", "/style.css")

        self.assertEqual(200, answer.status)
        self.assertEqual("text/css; charset=utf-8", answer.content_type)

    def test_a_page_this_console_does_not_have_is_a_page_and_not_a_traceback(self):
        answer = ui.respond(self.console, "GET", "/../etc/passwd")

        self.assertEqual(404, answer.status)
        self.assertIn("is not a page of this console", answer.body)
        self.assertIn("<title>", answer.body)

    def test_a_panel_this_console_does_not_have_names_the_ones_it_does(self):
        answer = ui.respond(self.console, "GET", "/panel/secrets")

        self.assertEqual(404, answer.status)
        for name in panels.NAMES:
            self.assertIn(name, answer.body)

    def test_a_method_that_is_not_get_or_post_is_refused_rather_than_handled(self):
        for method in ("PUT", "DELETE", "TRACE"):
            with self.subTest(method=method):
                self.assertEqual(405, ui.respond(self.console, method, "/").status)

    def test_a_form_posted_to_a_page_is_refused_rather_than_read_as_a_page(self):
        answer = ui.respond(self.console, "POST", "/control", {"verb": operator.HALT})

        self.assertEqual(405, answer.status)

    def test_every_page_in_the_navigation_is_linked_from_every_page(self):
        body = ui.respond(self.console, "GET", "/nowhere").body

        for href, name in ui.NAVIGATION:
            self.assertIn(f'<a href="{href}">{name}</a>', body)

    def test_no_route_takes_a_program_and_no_form_field_names_one(self):
        # Criterion 6's isolation, asked where it is decided. There is no
        # argument to pass: the console resolves one slug when it opens and
        # every read and every verb below it uses that one.
        named = {
            item.name
            for action in ui.ACTIONS.values()
            for item in action.fields
        }
        self.assertEqual(set(), named & {"program", "slug", "program_id"})


class ActionTest(unittest.TestCase):
    """Criterion 3's verbs, at the point where a form becomes one."""

    def setUp(self):
        self.console = console()

    def form(self, **fields) -> dict:
        return {"token": self.console.token} | fields

    def test_a_form_without_this_process_token_is_refused_before_the_verb_is_read(self):
        answer = ui.respond(
            self.console, "POST", "/act", {"verb": operator.HALT, "reason": "no", "token": "x"}
        )

        self.assertEqual(403, answer.status)
        self.assertIn("did not come from this console", answer.body)

    def test_a_form_with_no_token_at_all_is_refused_the_same_way(self):
        answer = ui.respond(self.console, "POST", "/act", {"verb": operator.HALT, "reason": "no"})

        self.assertEqual(403, answer.status)

    def test_the_token_is_this_process_own_and_not_a_constant(self):
        self.assertNotEqual(console().token, console().token)
        self.assertGreaterEqual(len(self.console.token), 32)

    def test_a_verb_that_is_not_an_operator_verb_reaches_nothing(self):
        answer = ui.respond(self.console, "POST", "/act", self.form(verb="drop everything"))

        self.assertEqual(404, answer.status)
        self.assertIn("is not an operator verb", answer.body)

    def test_a_form_missing_a_required_field_is_refused_by_the_name_it_was_labelled(self):
        answer = ui.respond(self.console, "POST", "/act", self.form(verb=operator.HALT))

        self.assertEqual(400, answer.status)
        self.assertIn("why", answer.body)

    def test_a_reason_of_only_whitespace_is_a_missing_reason(self):
        answer = ui.respond(
            self.console, "POST", "/act", self.form(verb=operator.HALT, reason="   ")
        )

        self.assertEqual(400, answer.status)

    def test_the_verbs_on_this_console_are_exactly_the_operators_own_seven_less_the_read(self):
        # `decision list` is the queue page and not a form, so the console
        # carries the six that write. A verb here that `operator` does not have
        # would be this console doing something the CLI cannot.
        self.assertEqual(
            {
                operator.HALT, operator.RESUME, operator.ANSWER,
                operator.SUPERSEDE, operator.REPORT, operator.CLEAR,
            },
            set(ui.ACTIONS),
        )
        self.assertEqual(
            set(ui.ACTIONS), set(ui.DECISION_ACTIONS) | set(ui.CONTROL_ACTIONS)
        )

    def test_a_grant_that_will_not_parse_is_the_default_and_not_a_refusal(self):
        self.assertEqual(operator.DEFAULT_GRANT_HOURS, ui._hours(""))
        self.assertEqual(operator.DEFAULT_GRANT_HOURS, ui._hours("two days"))
        self.assertEqual(4.0, ui._hours("4"))


class RenderingTest(unittest.TestCase):
    """Criterion 4's ladder, criterion 6's states, and what escaping is for."""

    def test_a_rung_that_was_reached_prints_its_own_word(self):
        for rung in ui.RUNGS:
            with self.subTest(rung=rung):
                self.assertIn(rung, ui._mark(rung, "true"))

    def test_a_rung_that_was_not_reached_is_not_the_word_of_the_rung_beside_it(self):
        marked = {rung: ui._mark(rung, "false") for rung in ui.RUNGS}

        self.assertEqual(1, len(set(marked.values())))
        for rung in ui.RUNGS:
            self.assertNotIn(rung, marked[rung])

    def test_the_two_columns_whose_true_is_bad_news_are_marked_as_warnings(self):
        self.assertIn("warn", ui._mark("blocked", "true"))
        self.assertIn("warn", ui._mark("holds", "no"))
        self.assertIn("warn", ui._mark("freshness", "stale"))
        self.assertNotIn("warn", ui._mark("freshness", "current"))

    def test_exploited_is_progress_where_blocked_is_a_refusal_to_send(self):
        # The same word in two columns, marked opposite ways round, which is
        # why the warnings are pairs rather than values.
        self.assertIn("rung", ui._mark("exploited", "true"))
        self.assertIn("warn", ui._mark("blocked", "true"))

    def test_a_ready_panel_is_a_table_with_a_caption_and_header_cells(self):
        body = ui._panel_html(panel(), linked=True)

        self.assertIn("<caption>every Finding</caption>", body)
        self.assertIn('<th scope="col">finding</th>', body)
        self.assertIn("<td>F1</td>", body)

    def test_an_empty_panel_says_so_where_the_rows_would_be(self):
        body = ui._panel_html(panel(rows=(), total=0, state=panels.EMPTY), linked=True)

        self.assertIn("this Program holds no findings", body)
        self.assertNotIn("<tbody>", body)

    def test_a_pending_panel_says_the_page_ran_out_of_time_and_not_that_it_is_empty(self):
        shown = panels.deferred(panels.FINDINGS, detail="not read yet: out of time").summary()

        body = ui._panel_html(shown, linked=True)

        self.assertIn("pending", body)
        self.assertIn("not read yet: out of time", body)
        self.assertNotIn("holds no findings", body)

    def test_a_panel_that_could_not_be_read_carries_the_refusal_and_not_a_blank(self):
        body = ui._panel_html(
            panel(rows=(), total=0, state=panels.ERROR, detail="permission denied"), linked=True
        )

        self.assertIn("this panel could not be read: permission denied", body)

    def test_a_bounded_panel_says_how_much_of_the_campaign_is_not_on_the_page(self):
        body = ui._panel_html(panel(total=20000), linked=True)

        self.assertIn("19999 further row(s) are held and not shown", body)

    def test_a_panel_that_showed_everything_says_nothing_about_omissions(self):
        self.assertNotIn("further row(s)", ui._panel_html(panel(), linked=True))

    def test_a_label_written_by_a_model_is_text_and_not_markup(self):
        body = ui._panel_html(panel(rows=(("<script>alert(1)</script>", "true", "false"),)),
                              linked=True)

        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_a_panel_name_in_a_link_is_escaped_in_the_href_as_well_as_in_the_text(self):
        body = ui._panel_html(panel(name='a" onmouseover="x'), linked=True)

        self.assertNotIn('onmouseover="x"', body)
        self.assertIn("&quot;", body)

    def test_a_column_with_no_answer_yet_is_blank_and_not_the_word_none(self):
        # `answered_by` on a question nobody has answered. `None` in that cell
        # would read as the name of whoever answered it.
        self.assertEqual("", ui._e(None))

    def test_a_stale_projection_is_named_as_stale_rather_than_shown_as_the_record(self):
        self.assertIn("stale", ui._summary_cell(ui.STALE, "the old sentence"))
        self.assertNotIn("the old sentence", ui._summary_cell(ui.STALE, "the old sentence"))

    def test_a_projection_that_was_forgotten_reads_as_unavailable(self):
        self.assertIn(ui.UNAVAILABLE, ui._summary_cell(ui.UNAVAILABLE, ""))

    def test_the_note_on_a_record_page_shows_what_the_stale_summary_had_said(self):
        # Different from the list, and deliberately: the canonical record is on
        # this page, so the superseded sentence can be shown beside it without
        # any chance of being read as the record.
        note = ui._summary_note(ui.STALE, "the old sentence")

        self.assertIn("warn", note)
        self.assertIn("the old sentence", note)
        self.assertEqual("", ui._summary_note(ui.CURRENT, ""))


class AccessTest(unittest.TestCase):
    """Criterion 6's keyboard access, which is what not writing a script buys."""

    def setUp(self):
        self.console = console()
        self.body = ui.respond(self.console, "GET", "/control").body

    def test_every_page_starts_with_a_link_past_the_navigation(self):
        self.assertIn('<a class="skip" href="#content">', self.body)
        self.assertIn('<main id="content"', self.body)

    def test_every_page_has_one_heading_and_names_the_program_it_is_about(self):
        self.assertEqual(1, self.body.count("<h1>"))
        self.assertIn('<p class="program">acme-web</p>', self.body)

    def test_every_input_on_every_form_is_labelled_by_an_id_that_exists(self):
        for verb, action in ui.ACTIONS.items():
            body = ui._form(self.console, action)
            for item in action.fields:
                identifier = f"{verb}-{item.name}".replace(" ", "-")
                with self.subTest(verb=verb, field=item.name):
                    self.assertIn(f'<label for="{identifier}">', body)
                    self.assertIn(f'id="{identifier}"', body)

    def test_two_forms_on_one_page_do_not_label_two_inputs_with_one_id(self):
        body = ui.respond(self.console, "GET", "/control").body
        identifiers = [
            f"{verb}-{item.name}".replace(" ", "-")
            for verb in ui.CONTROL_ACTIONS
            for item in ui.ACTIONS[verb].fields
        ]

        self.assertEqual(len(identifiers), len(set(identifiers)))
        for identifier in identifiers:
            self.assertEqual(1, body.count(f'id="{identifier}"'))

    def test_a_choice_is_a_select_and_not_a_field_an_operator_has_to_spell(self):
        body = ui._form(self.console, ui.ACTIONS[operator.ANSWER])

        self.assertIn('<option value="approve">', body)
        self.assertIn('<option value="deny">', body)

    def test_the_content_policy_permits_no_script_and_no_outbound_request(self):
        self.assertIn("default-src 'none'", ui.POLICY)
        self.assertNotIn("script-src", ui.POLICY)
        self.assertNotIn("<script", self.body)
        self.assertNotIn("javascript:", self.body)
        self.assertNotIn(" on", ui.STYLESHEET)

    def test_no_page_carries_the_credential_the_console_holds(self):
        # Criterion 6's redaction. `pg.Settings.describe` carries a user, a host
        # and a database and never a password, and nothing here renders even
        # that: the pages are about a campaign, not about a connection.
        for path in ("/control", "/style.css", "/nowhere"):
            with self.subTest(path=path):
                self.assertNotIn(SECRET, ui.respond(self.console, "GET", path).body)


class SurfaceTest(unittest.TestCase):
    """That the console is an adapter, asked of the module rather than of a page."""

    #: Uppercase on purpose. The corpus writes SQL in uppercase and HTML in
    #: lowercase, so `<select>` on a form is not a SELECT against a table.
    STATEMENTS = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", " FROM ", "COMMIT")

    def setUp(self):
        self.source = Path(ui.__file__).read_text(encoding="utf-8")

    def test_this_console_holds_no_statement_of_its_own(self):
        # Criterion 2. Every view is one call into `panels`, `state`, `operator`
        # or `reporting`; a statement here would be a second definition of
        # something the CLI already answers, free to drift from it.
        for statement in self.STATEMENTS:
            with self.subTest(statement=statement.strip()):
                self.assertNotIn(statement, self.source)

    def test_this_console_opens_no_connection_and_executes_nothing(self):
        self.assertNotIn(".execute(", self.source)
        self.assertNotIn("open_connection", self.source)

    def test_the_reads_a_page_makes_are_the_ones_the_cli_makes(self):
        for name in ("panels.read", "panels.forms", "state.read", "operator.queue",
                     "reporting.run"):
            with self.subTest(read=name):
                self.assertIn(name, self.source)

    def test_every_operator_verb_this_console_offers_is_called_through_operator(self):
        for verb in ui.ACTIONS:
            with self.subTest(verb=verb):
                self.assertIn(f"operator.{verb.split()[-1].replace('-', '_')}", self.source)


class PanelTest(unittest.TestCase):
    """The parts of `panels` that are decided before a connection is opened."""

    def test_a_panel_that_does_not_exist_is_refused_by_name_and_reaches_nothing(self):
        answer = panels.read(
            pg.settings_from_url(RUNTIME), Path("program.toml"), names=("secrets",)
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertEqual("argument:--panel", answer.violations[0].source)
        self.assertIn("no such panel: secrets", answer.violations[0].detail)

    def test_the_omission_marker_is_the_subtraction_and_not_a_second_count(self):
        held = panels.Panel(
            name="findings", caption="", columns=(), rows=(("F1",),), total=20000,
            state=panels.READY,
        )

        self.assertEqual(19999, held.omitted)
        self.assertEqual(19999, held.summary()["omitted"])

    def test_a_panel_holding_everything_omits_nothing_and_never_less_than_nothing(self):
        held = panels.Panel(
            name="findings", caption="", columns=(), rows=(("F1",), ("F2",)), total=1,
            state=panels.READY,
        )

        self.assertEqual(0, held.omitted)

    def test_a_deferred_panel_keeps_its_columns_so_the_page_can_still_be_read(self):
        held = panels.deferred(panels.FINDINGS, detail="out of time")

        self.assertEqual(panels.PENDING, held.state)
        self.assertEqual(panels.FINDINGS.columns, held.columns)
        self.assertEqual((), held.rows)

    def test_every_read_names_columns_for_the_values_it_selects(self):
        for read in panels.READS:
            with self.subTest(panel=read.name):
                self.assertTrue(read.columns)
                self.assertEqual(read.source == panels.SQL, bool(read.total))

    def test_the_ladder_this_ticket_names_is_the_ladder_the_findings_panel_carries(self):
        self.assertEqual(ui.RUNGS, tuple(c for c in panels.FINDINGS.columns if c in ui.RUNGS))

    def test_a_session_that_went_away_leaves_a_page_of_panels_that_say_so(self):
        """`pg.ConnectionError_` is not a `pg.DatabaseError`; both end the same way.

        A lost session used to escape `collect` uncaught and take the whole
        report with it, so an operator whose database went away got a command
        that raised instead of a page saying which reads did not happen.
        """
        class Lost:
            def transaction(self):
                raise pg.ConnectionError_("the session went away")

        ledger = Ledger()

        collected = panels.collect(ledger, Lost(), PROGRAM, "acme", limit=5)

        self.assertEqual(len(panels.NAMES), len(collected))
        self.assertEqual({panels.ERROR}, {held.state for held in collected})
        self.assertEqual(
            [], [held.name for held in collected if "went away" not in held.detail]
        )
        self.assertEqual(len(panels.NAMES), len(ledger.violations))


class ServerTest(unittest.TestCase):
    """The two questions the socket answers, which a page cannot answer for it."""

    def setUp(self):
        self.console = console()
        self.server = ui.server(self.console, host="127.0.0.1", port=0)
        self.address = f"127.0.0.1:{self.server.server_address[1]}"
        self.console.origin = f"http://{self.address}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.shutdown)

    def request(self, method: str, path: str, *, host: str | None = None,
                headers: dict | None = None, body: str = "") -> http.client.HTTPResponse:
        connection = http.client.HTTPConnection(self.address, timeout=10)
        self.addCleanup(connection.close)
        sent = {"Host": host if host is not None else self.address} | (headers or {})
        if body:
            sent["Content-Type"] = "application/x-www-form-urlencoded"
        connection.request(method, path, body=body, headers=sent)
        return connection.getresponse()

    def test_the_stylesheet_comes_back_with_the_headers_every_answer_carries(self):
        answer = self.request("GET", "/style.css")

        self.assertEqual(200, answer.status)
        self.assertEqual(ui.POLICY, answer.headers["Content-Security-Policy"])
        self.assertEqual("DENY", answer.headers["X-Frame-Options"])
        self.assertEqual("nosniff", answer.headers["X-Content-Type-Options"])
        self.assertEqual("no-referrer", answer.headers["Referrer-Policy"])
        self.assertEqual("no-store", answer.headers["Cache-Control"])

    def test_a_request_naming_another_host_is_refused_before_it_is_routed(self):
        # DNS rebinding: what the other page controls is the name, and what it
        # cannot control is the Host header that name arrives in.
        answer = self.request("GET", "/style.css", host="console.example.com")

        self.assertEqual(421, answer.status)

    def test_a_form_submitted_from_another_origin_is_refused_before_the_token(self):
        answer = self.request(
            "POST", "/act", headers={"Origin": "http://evil.example.com"},
            body=f"verb=halt&reason=x&token={self.console.token}",
        )

        self.assertEqual(403, answer.status)
        self.assertIn("another origin", answer.read().decode())

    def test_a_form_from_this_console_own_origin_is_read(self):
        answer = self.request(
            "POST", "/act", headers={"Origin": self.console.origin},
            body="verb=halt&reason=x&token=forged",
        )

        # Refused for the token and not for the origin, which is the point.
        self.assertEqual(403, answer.status)
        self.assertIn("did not come from this console", answer.read().decode())

    def test_a_body_too_large_to_be_a_form_is_not_read_as_one(self):
        answer = self.request("POST", "/act", body="reason=" + "x" * ui.MAX_BODY)

        self.assertEqual(413, answer.status)

    def test_a_refused_body_closes_the_socket_it_was_not_drained_from(self):
        # The 413 path does not read the body, so under HTTP/1.1 the connection
        # cannot be kept alive: the undrained bytes would be parsed as the next
        # request line. The server closes it, and a second request on the same
        # socket finds it gone rather than answered from the leftover body.
        connection = http.client.HTTPConnection(self.address, timeout=10)
        self.addCleanup(connection.close)
        connection.request(
            "POST", "/act",
            body="reason=" + "x" * ui.MAX_BODY,
            headers={"Host": self.address,
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        first = connection.getresponse()
        self.assertEqual(413, first.status)
        first.read()

        with self.assertRaises((ConnectionError, http.client.RemoteDisconnected)):
            connection.request("GET", "/style.css", headers={"Host": self.address})
            connection.getresponse()

    def test_the_console_serves_one_request_at_a_time_on_purpose(self):
        self.assertNotIsInstance(self.server, __import__("socketserver").ThreadingMixIn)


class ServeTest(unittest.TestCase):
    """`rk ui serve`, at the two points it can fail before a page exists.

    `serve_forever` is patched rather than a test-only flag being threaded
    through `serve`: the loop is the one line these tests do not want to run, and
    a parameter that only ever exists so a test can turn the loop off would be a
    branch in the shipped code that only the test takes.
    """

    def test_a_configuration_that_will_not_load_is_refused_in_the_terminal(self):
        path = fixtures.write("this is not toml")

        with mock.patch.object(ui.Server, "serve_forever"):
            answer = ui.serve(
                pg.settings_from_url(RUNTIME),
                pg.settings_from_url(AGENT),
                pg.settings_from_url(HUMAN),
                path,
                port=0,
            )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, answer.exit_code)
        self.assertIsNone(answer.facts["address"])

    def test_the_address_reported_is_the_one_the_socket_got(self):
        # `--port 0` is a port the kernel picks, so the origin the Host header
        # is checked against cannot be settled before the bind.
        path = fixtures.write(fixtures.VALID)

        with mock.patch.object(ui.Server, "serve_forever") as looping:
            answer = ui.serve(
                pg.settings_from_url(RUNTIME),
                pg.settings_from_url(AGENT),
                pg.settings_from_url(HUMAN),
                path,
                port=0,
            )

        looping.assert_called_once()
        self.assertTrue(answer.ok)
        self.assertEqual("acme-web", answer.facts["program_slug"])
        self.assertRegex(answer.facts["address"], r"^http://127\.0\.0\.1:\d+$")
        self.assertNotIn(":0", answer.facts["address"])
