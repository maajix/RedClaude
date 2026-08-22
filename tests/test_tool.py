"""The rule a tool answer is held to: a result is not narrower than its source.

Three places in this harness turn a rich runtime value into something a model
reads, and each of them is a chance to lose a fact silently. `proxy._answered`
reads one HTTP response into an `Answer`; `_launch._spend` turns that `Answer`
into the dict `mcp__rk2__http_request` hands back; `tool.serve` turns an
`isolation.ToolProcess` into the dict `mcp__rk2__run_tool` hands back. Ticket
108 is the finding that the last of them dropped three fields with nothing
written down about it, and this file is where the rule that catches the next one
lives: every field of a source is either mentioned by the function that narrows
it or named below with the reason it is not.

The table is hand-written and the field lists are not. Which boundaries exist is
a judgement about the design and has to be stated; what a source holds is a
reading of the source, so adding a field to `ToolProcess` or to `Answer` without
deciding about it fails here rather than passing quietly.

The two readings are `check_wiring`'s own, so this file and the gate cannot
drift into disagreeing about what "carried" means. What is here and not there is
the third boundary and the reasons: W5 measures the two sources that are
dataclasses in this tree, and `http.client.HTTPResponse` is neither in this tree
nor a dataclass -- so what it holds is written down once here, and asserted
against a live response so that a rename in the standard library is a test that
fails rather than a boundary that stopped being measured.
"""

import ast
import http.client
import io
import unittest
from collections.abc import Mapping
from dataclasses import dataclass, field

from tools import check_wiring


def declared(source: str, holder: str) -> tuple[str, ...]:
    """The annotated fields of one dataclass of this package, as it declares them."""
    return check_wiring.fields(
        ast.parse((check_wiring.PACKAGE / source).read_text(encoding="utf-8")), holder
    )


@dataclass(frozen=True)
class Boundary:
    """One place a runtime value becomes something narrower, and what it may leave.

    `holds` is what the source carries and `drops` is the part of it this
    boundary answers for not carrying. A field in neither is the defect: a fact
    the runtime had, that the model was never given, that nobody decided about.
    """

    label: str
    module: str
    function: str
    holder: str
    holds: tuple[str, ...]
    drops: Mapping[str, str] = field(default_factory=dict)

    def narrowed(self) -> frozenset[str]:
        """Every name the function that narrows this source mentions, however."""
        tree = ast.parse((check_wiring.PACKAGE / self.module).read_text(encoding="utf-8"))
        return check_wiring.carried(check_wiring.named(tree, self.function))


#: What one HTTP response says, as the door reads it. Written down rather than
#: read, because this source is the standard library's and its instance
#: attributes are half reader plumbing -- `fp`, `chunk_left`, `debuglevel` --
#: which is a list of things to explain rather than a list of facts a target
#: stated. These four are the readings, and the body underneath them.
RESPONSE = ("status", "reason", "version", "headers")

#: The three boundaries, and the fields each of them answers for not carrying.
BOUNDARIES = (
    Boundary(
        "proxy._answered",
        "proxy.py",
        "_answered",
        "http.client.HTTPResponse",
        RESPONSE,
        {
            "reason": (
                "the phrase beside the status code is whatever the target typed there and"
                " nothing decides on it; the transcript the Receipt names holds the start"
                " line byte for byte for an auditor who wants it"
            ),
            "version": (
                "`describes_this_hop` in another form: this is the version the door spoke"
                " to this caller, not the one the target answered the door in, and a"
                " caller that read it as the target's would be reading the fence"
            ),
        },
    ),
    Boundary(
        "_launch._spend",
        "_launch.py",
        "_spend",
        "proxy.Answer",
        declared("proxy.py", "Answer"),
    ),
    Boundary(
        "tool.serve",
        "tool.py",
        "serve",
        "isolation.ToolProcess",
        declared("isolation.py", "ToolProcess"),
    ),
)

#: Every key `tool.serve` answers a child with, and the whole of what ticket 108
#: added: `stderr` beside `stdout`, the flag that says it was cut, and the two
#: ceilings that say the supervisor stopped the run rather than the tool ending
#: it. Hand-written, because the point of the ticket is that this list is the
#: thing that was silently short.
SERVED = (
    "served",
    "tool_run",
    "tool",
    "version",
    "status",
    "exit_code",
    "detail",
    "outputs",
    "stdout",
    "truncated",
    "stderr",
    "stderr_truncated",
    "timed_out",
    "overflowed",
)


def answered(module: str, function: str) -> tuple[str, ...]:
    """The keys of the one dict literal a function returns, in the order written."""
    tree = ast.parse((check_wiring.PACKAGE / module).read_text(encoding="utf-8"))
    returned = [
        node.value
        for node in ast.walk(check_wiring.named(tree, function))
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
    ]
    assert len(returned) == 1, f"{module}:{function} returns {len(returned)} dict literals"
    return tuple(
        key.value for key in returned[0].keys if isinstance(key, ast.Constant)
    )


def live_response() -> http.client.HTTPResponse:
    """One real response, read off bytes rather than off a socket.

    `HTTPResponse` asks its socket for a reader and nothing else, so a stream is
    a whole one for the purpose of asking what a response holds after `begin`.
    """

    class Reader:
        def makefile(self, *_arguments, **_named):
            return io.BytesIO(
                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nX-Vary: a\r\n\r\nhi"
            )

    answer = http.client.HTTPResponse(Reader())
    answer.begin()
    return answer


class BoundaryTest(unittest.TestCase):
    """Ticket 108: what a model is handed is not narrower than what it was built from."""

    def test_every_field_a_boundary_narrows_is_carried_or_declared_dropped(self):
        # The rule itself. A generous reading of "carried" is what makes a
        # failure here hard to argue with: the function does not so much as say
        # the word, and no line below says why it should not have to.
        for boundary in BOUNDARIES:
            narrowed = boundary.narrowed()
            for held in boundary.holds:
                with self.subTest(boundary=boundary.label, field=held):
                    self.assertTrue(
                        held in narrowed or held in boundary.drops,
                        f"{boundary.label} drops {boundary.holder}.{held}"
                        " and declares no reason",
                    )

    def test_no_declared_drop_names_a_field_its_source_does_not_hold(self):
        # The other direction, for the register's reason: a reason left behind
        # after the field it excused was carried or renamed reads as a decision
        # somebody made, and is a sentence about nothing.
        for boundary in BOUNDARIES:
            for held, reason in boundary.drops.items():
                with self.subTest(boundary=boundary.label, field=held):
                    self.assertIn(held, boundary.holds)
                    self.assertTrue(reason.strip())

    def test_the_response_the_door_reads_holds_the_readings_this_table_names(self):
        # The one source that is not in this tree, asked of the real class. A
        # reading the standard library renames would otherwise be a field this
        # table went on excusing after it stopped existing.
        held = vars(live_response())

        for reading in RESPONSE:
            with self.subTest(reading=reading):
                self.assertIn(reading, held)

    def test_the_wiring_gate_measures_every_boundary_it_can(self):
        # Two places name these boundaries and they have to name the same ones.
        # The gate measures the two whose source is a dataclass here; this table
        # is the one that also carries the reasons, so it is the longer list and
        # never the shorter.
        self.assertLessEqual(
            {label for label, *_ in check_wiring.BOUNDARIES},
            {boundary.label for boundary in BOUNDARIES},
        )


class ServedAnswerTest(unittest.TestCase):
    """What `tool.serve` hands back, which is the answer ticket 108 widened."""

    def test_a_served_run_answers_with_both_streams_and_both_ceilings(self):
        self.assertEqual(SERVED, answered("tool.py", "serve"))

    def test_the_diagnostic_a_failed_run_wrote_is_one_of_them(self):
        # The finding in one line. A tool that failed wrote to stderr, and an
        # answer that carried the exit code without it said that something went
        # wrong and hid what.
        self.assertIn("stderr", SERVED)
        self.assertIn("stderr", BOUNDARIES[-1].narrowed())


if __name__ == "__main__":
    unittest.main()
