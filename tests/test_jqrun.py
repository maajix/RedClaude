"""The wrapper that hands jq a body instead of an envelope.

`jqrun.py` runs inside the tool container and is never imported by the
application, so what is asked here is what a container would see: the carrier
rule, the argv shape `open_offline_tool_run` builds, and the exit code jq's
answer travels back on.

The carrier rule is the reason this file exists rather than a docstring. It is
a second copy of `jsscan.carried_body`, which cannot be shared because each
analyser is mounted alone at `/input` with no `redkraken` on its path. Two
copies of a rule is one place to forget, so the first case here holds them
against each other over the cases that separate them.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from redkraken import jqrun, jsscan

#: Run as a program rather than called, because that is how it runs: the
#: container is handed `python3 /input/jqrun.py jq <filter> <artifact>` and
#: nothing imports it.
PROGRAM = Path(jqrun.__file__)

#: What the door writes in front of a response, as `proxy.transcript` writes
#: it. CRLF throughout, because that is what the rule keys on.
HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 13\r\n\r\n"


class CarrierRuleTest(unittest.TestCase):
    """The rule, against the copy of it that this file exists to track."""

    CASES = (
        HEAD + b'{"a":1,"b":2}',
        b'{"a":1}',
        # A body that begins with a blank line of its own. The rule cuts at the
        # start line plus the CRLF break and nothing else, so a file holding a
        # blank line keeps its top.
        b"// banner\n\n{}\n",
        # A start line with no break after it, which is a truncated capture
        # rather than a response: returned whole rather than cut at nothing.
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n",
        # LF-only, which no door of this harness writes.
        b"HTTP/1.1 200 OK\nContent-Type: application/json\n\n{}",
        b"",
    )

    def test_both_copies_of_the_rule_answer_the_same(self):
        for raw in self.CASES:
            with self.subTest(raw=raw[:24]):
                self.assertEqual(jsscan.carried_body(raw), jqrun.carried_body(raw))

    def test_the_constants_are_the_same_constants(self):
        # The rule is two functions and two pairs of bytes. Held here so a
        # change to one pair is a failure rather than a drift.
        self.assertEqual(jsscan.CARRIER, jqrun.CARRIER)
        self.assertEqual(jsscan.CARRIER_BREAK, jqrun.CARRIER_BREAK)

    def test_a_response_is_cut_at_its_own_break(self):
        body, carried = jqrun.carried_body(HEAD + b'{"a":1,"b":2}')

        self.assertEqual(b'{"a":1,"b":2}', body)
        self.assertEqual(len(HEAD), carried)


class ProgramTest(unittest.TestCase):
    """The argv shape, and what comes back on each stream.

    Run against a stand-in for jq rather than jq itself: this module is about
    the wrapper, the tool image is what holds jq, and a case that needed the
    image would stand down on every machine that has no container engine.
    """

    STANDIN = (
        "import sys\n"
        "raw = sys.stdin.buffer.read()\n"
        "if '--version' in sys.argv:\n"
        "    sys.stdout.write('jq-1.7\\n'); raise SystemExit(0)\n"
        "sys.stderr.write('filter=' + sys.argv[1] + '\\n')\n"
        "sys.stdout.buffer.write(raw)\n"
        "raise SystemExit(0 if raw.startswith(b'{') else 5)\n"
    )

    def setUp(self):
        self.root = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        standin = self.root / "jq"
        standin.write_text(f"#!{sys.executable}\n{self.STANDIN}", encoding="utf-8")
        standin.chmod(0o755)
        self.program = self.root / "jqrun.py"
        self.program.write_text(
            PROGRAM.read_text(encoding="utf-8").replace(
                'JQ = "/usr/bin/jq"', f'JQ = {str(standin)!r}'
            ),
            encoding="utf-8",
        )

    def run_it(self, *argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.program), *argv],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_the_version_names_the_wrapper_and_the_tool(self):
        # `offline_tools.version_pattern` is held against this exact line, so
        # the two are one statement rather than two that can drift.
        answer = self.run_it("--version")

        self.assertEqual(0, answer.returncode)
        self.assertEqual("rk2-jq 1 (jq-1.7)", answer.stdout.strip())

    def test_a_wrapped_response_reaches_jq_as_its_body(self):
        # The whole ticket: before this wrapper jq met `HTTP/1.1 200 OK` and
        # exited 5 on every call this campaign made.
        artifact = self.root / "AF1"
        artifact.write_bytes(HEAD + b'{"a":1,"b":2}')

        answer = self.run_it("jq", "keys", str(artifact))

        self.assertEqual(0, answer.returncode)
        self.assertEqual('{"a":1,"b":2}', answer.stdout)
        self.assertIn(f"skipped {len(HEAD)} carrier byte(s)", answer.stderr)

    def test_a_bare_body_is_passed_through_untouched(self):
        artifact = self.root / "AF2"
        artifact.write_bytes(b'{"a":1}')

        answer = self.run_it("jq", ".", str(artifact))

        self.assertEqual(0, answer.returncode)
        self.assertEqual('{"a":1}', answer.stdout)
        # Nothing was skipped, so nothing is claimed to have been.
        self.assertNotIn("carrier byte", answer.stderr)

    def test_jqs_own_exit_code_is_what_comes_back(self):
        # jq's 1, 4 and 5 each mean something a caller acts on. A wrapper that
        # flattened them would turn "the filter matched nothing" into "the tool
        # failed", which is the shape of refusal this ticket started from.
        artifact = self.root / "AF3"
        artifact.write_bytes(b"not json at all")

        answer = self.run_it("jq", ".", str(artifact))

        self.assertEqual(5, answer.returncode)

    def test_an_argv_the_registry_would_not_build_is_refused(self):
        # `open_offline_tool_run` builds `[analyser, tool, filter, input]` and
        # nothing else does. Anything shorter is a caller this file does not
        # have, and it says so instead of reading argv[3] that is not there.
        self.assertEqual(2, self.run_it("jq", "keys").returncode)
        self.assertEqual(2, self.run_it("js_routes", "keys", "x").returncode)

    def test_an_unreadable_input_is_a_refusal_and_not_a_traceback(self):
        answer = self.run_it("jq", ".", str(self.root / "nothing-here"))

        self.assertEqual(2, answer.returncode)
        self.assertIn("the input could not be read", answer.stderr)
        self.assertNotIn("Traceback", answer.stderr)


if __name__ == "__main__":
    unittest.main()
