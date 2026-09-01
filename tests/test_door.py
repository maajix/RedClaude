"""What the door's own container is started with.

`rk proxy door` is the one command that starts the capability proxy, and the
arguments it builds are the whole of the door's topology: which networks it is
attached to, what it is denied, and -- ticket 153 -- which address on this
machine can reach it at all.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from redkraken import door, isolation, pg, proxy


CONTAINER = isolation.AgentContainer(
    image="rk2-agent:test",
    network="rk2-agent",
    proxy_container="rk2-door",
    proxy_url="http://rk2-door:18080",
    certificate=Path("/tmp/ca.pem"),
)

VERSION = "20270109T000000Z__a_dead_correlator_is_graded_against_the_clock"
OLDER_VERSION = "20261003T000000Z__server_baseline"
NEWER_VERSION = "20270110T000000Z__a_future_migration"


def started(**overrides) -> list[str]:
    """The engine arguments `_run` would have spent, without spending them."""
    container = CONTAINER if not overrides else CONTAINER.__class__(
        **{**CONTAINER.__dict__, **overrides}
    )
    with mock.patch.object(isolation, "engine_command") as engine:
        door._run(
            "docker",
            container,
            egress="rk2-egress",
            root=Path("/tmp/artifacts"),
            authority=Path("/tmp/authority"),
            key=None,
            fence="postgres://rk2_proxy@host.docker.internal:5432/rk2",
            host_environment={},
        )
    return list(engine.call_args.args[1])


class PublishedTest(unittest.TestCase):
    """Ticket 153: the door has an address this machine can reach.

    A child reaches the door by container name over the Agent network. The
    runtime is not on that network, and `proxy.endpoint` sends a capability to
    a loopback address and nothing else -- so every host-side verb that spends
    one had nothing to name. The first lap that ever claimed a `perform` Task
    measured it: `rk2hunt-door is not a loopback address`.
    """

    def test_the_listener_is_published_on_this_machine(self):
        arguments = started()

        self.assertIn("--publish", arguments)
        self.assertEqual(
            "127.0.0.1:18080:18080", arguments[arguments.index("--publish") + 1]
        )

    def test_the_port_is_the_one_the_door_was_told_to_listen_on(self):
        # Read from the URL the children are given rather than fixed here: one
        # door, one port, and a second statement of it would be a second answer
        # the day an operator moves it.
        arguments = started(proxy_url="http://rk2-door:19999")

        self.assertEqual(
            "127.0.0.1:19999:19999", arguments[arguments.index("--publish") + 1]
        )

    def test_it_is_published_on_loopback_and_on_no_other_interface(self):
        # The capability rides one hop in the clear and that hop staying on
        # this machine is the whole defence. A listener on every interface
        # would be one reachable from the egress network the door's second
        # attachment is on.
        published = started()[started().index("--publish") + 1]

        self.assertTrue(published.startswith(f"{door.PUBLISHED}:"))
        self.assertEqual(door.PUBLISHED, proxy.peer(f"http://{published.split(':')[0]}")[0])


if __name__ == "__main__":
    unittest.main()


class ServingTest(unittest.TestCase):
    """Ticket 149: the door says which database it opened, and a stale one is refused.

    `RK_PROXY_DATABASE_URL` is read once, when the container starts, and the door
    outlives the command that started it -- ticket 82's design. A run against a
    second database therefore reaches a door that cannot see its Program, and the
    door cannot file the blocked Receipt that would say so, because the label
    counter it needs is keyed on a Program row that is not there. `rk2hunt8` spent
    three Tool runs and three attempts finding that out from `docker logs`.

    The name and not the address: a door on the Agent network and a runtime on
    this machine reach one database by two addresses.
    """

    def logs(self, written: str):
        """`_ask` answering with what the container has printed so far."""
        answer = mock.Mock(stdout=written, stderr="")
        return mock.patch.object(door, "_ask", return_value=answer)

    def test_the_door_answers_where_it_is_bound_and_what_it_serves(self):
        with self.logs(
            f"{door.READY}0.0.0.0:18080{door.SERVING}rk2hunt21"
            f"{door.IDENTITY}rk2hunt21:16422:2026-08-23{door.CORPUS}{VERSION}\n"
        ):
            self.assertEqual(
                (
                    "0.0.0.0:18080",
                    "rk2hunt21",
                    "rk2hunt21:16422:2026-08-23",
                    VERSION,
                ),
                door._listening("docker", "rk2-door", {}, 1.0),
            )

    def test_a_door_from_before_this_question_names_no_database(self):
        # A build older than this ticket announces the endpoint alone. Answered
        # as an empty name rather than guessed at, because a door too old to say
        # is exactly the stale door the question is asked about.
        with self.logs(f"{door.READY}0.0.0.0:18080\n"):
            self.assertEqual(
                ("0.0.0.0:18080", "", "", ""),
                door._listening("docker", "rk2-door", {}, 1.0),
            )

    def test_a_door_from_before_the_version_handshake_names_no_corpus(self):
        with self.logs(
            f"{door.READY}0.0.0.0:18080{door.SERVING}rk2hunt21"
            f"{door.IDENTITY}rk2hunt21:16422:2026-08-23\n"
        ):
            self.assertEqual(
                ("0.0.0.0:18080", "rk2hunt21", "rk2hunt21:16422:2026-08-23", ""),
                door._listening("docker", "rk2-door", {}, 1.0),
            )

    def test_the_announcement_carries_the_database_the_door_opened(self):
        # The one place the sentence is built. A door that stopped naming its
        # database would leave `start` comparing against nothing at all.
        self.assertIn("{settings.database}", self.announcement())

    def test_the_announcement_carries_the_corpus_the_process_started_with(self):
        self.assertIn("{corpus_version}", self.announcement())

    def announcement(self) -> str:
        source = Path(door.__file__).read_text(encoding="utf-8")
        opening = source.index("announce_identity=lambda endpoint, identity:")
        return source[opening : source.index("\n", source.index("flush=True", opening))]


class PreflightTest(unittest.TestCase):
    def connection(self, visible: bool = True, applied: str = VERSION):
        connection = mock.Mock()
        connection.settings = pg.Settings("db", "rk2hunt21", "runtime")
        visible_result = mock.Mock()
        visible_result.scalar.return_value = visible
        applied_result = mock.Mock()
        applied_result.scalar.return_value = applied
        connection.execute.side_effect = (visible_result, applied_result)
        return connection

    def test_the_runtime_program_and_the_doors_exact_database_match(self):
        connection = self.connection()
        with mock.patch.object(pg, "database_identity", return_value="identity"), \
             mock.patch.object(isolation, "engine_for", return_value="docker"), \
             mock.patch.object(isolation, "peered"), \
             mock.patch.object(
                 door,
                 "_listening",
                 return_value=("0.0.0.0:18080", "rk2hunt21", "identity", VERSION),
             ):
            detail = door.preflight(CONTAINER, connection, "00000000-0000-4000-8000-1")

        self.assertIn("rk2hunt21", detail)
        self.assertIn(VERSION, detail)

    def test_the_same_database_name_on_another_cluster_is_refused(self):
        connection = self.connection()
        with mock.patch.object(pg, "database_identity", return_value="runtime-identity"), \
             mock.patch.object(isolation, "engine_for", return_value="docker"), \
             mock.patch.object(isolation, "peered"), \
             mock.patch.object(
                 door,
                 "_listening",
                 return_value=("0.0.0.0:18080", "rk2hunt21", "door-identity", VERSION),
             ):
            with self.assertRaisesRegex(isolation.Unavailable, "exact database identities"):
                door.preflight(CONTAINER, connection, "00000000-0000-4000-8000-1")

    def test_a_program_missing_from_the_runtime_database_is_refused_before_engine_access(self):
        with mock.patch.object(isolation, "engine_for") as engine:
            with self.assertRaisesRegex(isolation.Unavailable, "not visible"):
                door.preflight(
                    CONTAINER,
                    self.connection(visible=False),
                    "00000000-0000-4000-8000-1",
                )
        engine.assert_not_called()

    def test_a_door_older_than_the_database_is_refused_with_the_remedy(self):
        connection = self.connection()
        with mock.patch.object(pg, "database_identity", return_value="identity"), \
             mock.patch.object(isolation, "engine_for", return_value="docker"), \
             mock.patch.object(isolation, "peered"), \
             mock.patch.object(
                 door,
                 "_listening",
                 return_value=("0.0.0.0:18080", "rk2hunt21", "identity", OLDER_VERSION),
             ):
            with self.assertRaisesRegex(
                isolation.Unavailable, rf"Door.*{OLDER_VERSION}.*{VERSION}.*restart"
            ):
                door.preflight(CONTAINER, connection, "00000000-0000-4000-8000-1")

    def test_a_door_with_no_version_is_old_and_names_the_same_remedy(self):
        connection = self.connection()
        with mock.patch.object(pg, "database_identity", return_value="identity"), \
             mock.patch.object(isolation, "engine_for", return_value="docker"), \
             mock.patch.object(isolation, "peered"), \
             mock.patch.object(
                 door,
                 "_listening",
                 return_value=("0.0.0.0:18080", "rk2hunt21", "identity", ""),
             ):
            with self.assertRaisesRegex(isolation.Unavailable, r"Door.*no.*version.*restart"):
                door.preflight(CONTAINER, connection, "00000000-0000-4000-8000-1")

    def test_a_database_behind_its_door_names_migrate_not_restart(self):
        connection = self.connection()
        with mock.patch.object(pg, "database_identity", return_value="identity"), \
             mock.patch.object(isolation, "engine_for", return_value="docker"), \
             mock.patch.object(isolation, "peered"), \
             mock.patch.object(
                 door,
                 "_listening",
                 return_value=("0.0.0.0:18080", "rk2hunt21", "identity", NEWER_VERSION),
             ):
            with self.assertRaisesRegex(isolation.Unavailable, r"rk db migrate") as refusal:
                door.preflight(CONTAINER, connection, "00000000-0000-4000-8000-1")

        self.assertNotIn("restart", str(refusal.exception).lower())

    def test_a_door_that_is_not_running_does_not_claim_to_be_old(self):
        connection = self.connection()
        with mock.patch.object(pg, "database_identity", return_value="identity"), \
             mock.patch.object(isolation, "engine_for", return_value="docker"), \
             mock.patch.object(
                 isolation,
                 "peered",
                 side_effect=isolation.Unavailable("Door rk2-door is not running"),
             ):
            with self.assertRaisesRegex(isolation.Unavailable, "not running") as refusal:
                door.preflight(CONTAINER, connection, "00000000-0000-4000-8000-1")

        self.assertNotIn("restart", str(refusal.exception).lower())
