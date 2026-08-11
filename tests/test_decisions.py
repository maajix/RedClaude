"""What the sweep does with a channel, without a database under it.

`tests/test_database.py` holds the half a server has to answer -- that a
question is retired when its deadline passes, that a delivery is written down,
that a question no channel will carry again is a standing failure. This module
holds the other half: what is handed to an operator-supplied command, and what
happens when that command is not there, hangs, or refuses.

That half is worth its own file because it is the only place in this harness
where text the model influenced becomes an argument list. The body of a question
is rendered from the request the agent asked to make, so its host and its path
came from somewhere that is not trusted, and the thing on the other end is
whatever an operator put in `notification_channels`.
"""

from __future__ import annotations

import sys
import unittest

from redkraken import decisions


#: What the corpus ships as the desktop channel, verbatim. Pinned rather than
#: read from a database, because what this module is about is the substitution
#: -- and a test that took the argv from the same place the code does would
#: agree with it whatever either one said.
DESKTOP = ["notify-send", "redKrakenV2 {label}", "{body}"]


class CommandTest(unittest.TestCase):
    """The one place a question becomes an argument list."""

    def test_the_label_and_the_question_are_substituted_into_their_places(self):
        command = decisions._command(DESKTOP, "D7", "[approval_required] POST example.com/x")

        self.assertEqual(
            ["notify-send", "redKrakenV2 D7", "[approval_required] POST example.com/x"], command
        )

    def test_a_placeholder_is_substituted_wherever_in_an_element_it_sits(self):
        # An operator writes the argv, so the placeholder is as likely to be
        # inside a sentence as to be the whole of an argument.
        command = decisions._command(["mail", "-s", "rk2 {label} needs you", "{body}"], "D7", "x")

        self.assertEqual(["mail", "-s", "rk2 D7 needs you", "x"], command)

    def test_the_result_is_a_list_and_never_a_string_a_shell_parses(self):
        # The host in the body came from the request the agent asked to make. A
        # single element carrying shell syntax is still a single argument, and
        # that is the whole of the claim: this substitution never joins them.
        command = decisions._command(DESKTOP, "D7", "POST example.com/x; rm -rf ~")

        self.assertEqual(3, len(command))
        self.assertEqual("POST example.com/x; rm -rf ~", command[-1])

    def test_control_characters_in_a_question_do_not_reach_the_channel(self):
        # A terminal is a thing that interprets bytes, and an operator reads the
        # notification in one. Escapes are the shape of a body that rewrites what
        # the human is being asked.
        command = decisions._command(DESKTOP, "D7", "POST \x1b[2Kapprove\r\nme\x00")

        self.assertEqual("POST  [2Kapprove  me ", command[-1])

    def test_a_question_longer_than_the_bound_is_cut_rather_than_passed_on(self):
        command = decisions._command(DESKTOP, "D7", "u" * (decisions.BODY_BYTES + 50))

        self.assertEqual(decisions.BODY_BYTES, len(command[-1]))

    def test_a_channel_with_no_argv_produces_no_command_to_run(self):
        # Which is what makes it reportable rather than executable: the caller
        # tests the list, and an empty one is the channel that delivers nothing.
        self.assertEqual([], decisions._command([], "D7", "x"))


class ChannelTest(unittest.TestCase):
    """Running one operator-supplied command once."""

    def python(self, *statements: str) -> list[str]:
        return [sys.executable, "-c", ";".join(statements)]

    def test_a_channel_that_exits_zero_carried_the_question(self):
        ok, detail = decisions._run_channel(self.python("pass"))

        self.assertTrue(ok)
        self.assertEqual("", detail)

    def test_a_channel_that_refuses_is_reported_with_what_it_said(self):
        ok, detail = decisions._run_channel(
            self.python("import sys", "sys.stderr.write('no session bus')", "sys.exit(7)")
        )

        self.assertFalse(ok)
        self.assertEqual("exit 7: no session bus", detail)

    def test_a_channel_that_says_nothing_is_still_reported_by_its_status(self):
        ok, detail = decisions._run_channel(self.python("import sys; sys.exit(3)"))

        self.assertFalse(ok)
        self.assertEqual("exit 3:", detail.strip())

    def test_a_channel_that_is_not_installed_is_a_failed_delivery_and_not_a_crash(self):
        # An operator's argv names a program this machine may not have. The queue
        # is what decides when to stop trying; this process only reports.
        ok, detail = decisions._run_channel(["rk2-no-such-notifier-9c4e17"])

        self.assertFalse(ok)
        self.assertIn("FileNotFoundError", detail)

    def test_a_channel_that_hangs_does_not_hold_up_the_questions_behind_it(self):
        ok, detail = decisions._run_channel(
            self.python(f"import time; time.sleep({decisions.DELIVERY_SECONDS + 30})")
        )

        self.assertFalse(ok)
        self.assertIn("TimeoutExpired", detail)

    def test_what_a_channel_says_is_bounded_before_it_is_written_down(self):
        # `last_error` is a column and an operator reads it. A channel that
        # answers with a megabyte of output is not a reason to store one.
        ok, detail = decisions._run_channel(
            self.python("import sys", "sys.stderr.write('u' * 5000)", "sys.exit(1)")
        )

        self.assertFalse(ok)
        self.assertEqual(decisions.ERROR_BYTES, len(detail))


if __name__ == "__main__":
    unittest.main()
