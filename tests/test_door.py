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

from redkraken import door, isolation, proxy


CONTAINER = isolation.AgentContainer(
    image="rk2-agent:test",
    network="rk2-agent",
    proxy_container="rk2-door",
    proxy_url="http://rk2-door:18080",
    certificate=Path("/tmp/ca.pem"),
)


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
