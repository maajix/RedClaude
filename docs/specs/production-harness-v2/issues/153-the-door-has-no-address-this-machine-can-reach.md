# 153 — The door has no address this machine can reach

**What to build:** A loopback address for the door, so the host-side verbs that
need the capability proxy can reach it.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt13`, 2026-08-22, the first
      lap that ever claimed a `perform` Task. The claim succeeded and the
      replay refused at its first statement:

      ```
      choice        | AR9 answered chosen (T6) after 1 pick(s)
      claim         | T6 (perform) claimed as AR10, attempt 1
      proxy_endpoint| rk2hunt-door is not a loopback address; the capability
                    | is sent to this machine only
      ```

      `proxy.endpoint` is right to refuse: the capability is plaintext for one
      hop and `rk2hunt-door` is a container name, not an address on this
      machine. What is wrong is that there is no other name to give it.
      `docker inspect rk2hunt-door` reports `PortBindings: {}` -- `door._run`
      builds its `docker run` with `--detach`, `--network`, `--add-host` and
      `--tmpfs` and never publishes the listener.

      Measured from the host, three addresses, one answer each:

      ```
      http://127.0.0.1:18080/    curl exit 7   (connection refused)
      http://192.168.16.2:18080/ HTTP 407      (the door, over the egress net)
      http://172.30.0.2:18080/   HTTP 407      (the door, over the Agent net)
      ```

      So the door is running and answering, and the one address family this
      harness will send a capability to is the one it does not have.

- [x] **Every host-side verb that needs the door can name it.** `rk proxy
      request`, `rk test replay` and the `perform` lane all take a proxy URL
      whose help text already reads `http://127.0.0.1:port`. None of them can
      be used against a door this command started.

- [x] **The door publishes on loopback and nowhere else.** Not `0.0.0.0`: the
      capability's one-hop plaintext is defended by the hop staying on this
      machine, and a published port on every interface would make the fence
      reachable from the network the egress attachment is on.

- [x] **The runtime is given the address rather than guessing it.** The child's
      URL and the host's URL are two facts about one door. Deriving the second
      from the first by rewriting the host would be a guess about a port
      mapping this harness did not make.

## What was built

`door.PUBLISHED` is `127.0.0.1` and `door._run` publishes the listener there,
on the port read out of the URL the children are given: one door, one port, and
no second statement of it to disagree with the first.

`execution.Slice` gained `proxy_url`, the door as this machine sees it, and
`_replay` spends the capability against that rather than against
`boundary.proxy_url`. Optional like the store and the tool image: only
`perform` spends a capability from the runtime, so a machine that names none
runs every other kind and refuses this one by name.

`cli._slice` reads `$RK_PROXY_URL` and does not refuse it, because the refusal
belongs where the capability would be spent.

Measured afterwards on the live door:

```
PortBindings {"18080/tcp":[{"HostIp":"127.0.0.1","HostPort":"18080"}]}
curl http://127.0.0.1:18080/  ->  HTTP 407
```

and the next lap reached the replay, which refused for a different reason
(ticket 154).

## The test that would go red

`tests/test_door.py::PublishedTest` -- three tests over the arguments `_run`
builds, without starting anything.

`tests/test_execution.py::PerformTest::test_the_capability_is_sent_to_this_machine_and_not_to_the_agent_network`
and `::test_a_machine_naming_no_door_of_its_own_refuses_by_name`.
