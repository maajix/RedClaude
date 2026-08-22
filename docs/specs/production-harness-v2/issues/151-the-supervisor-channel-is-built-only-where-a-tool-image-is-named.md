# 151 — The supervisor channel is built only where a tool image is named

**What to build:** The split between the two verbs that need a container and
the three that need a database.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt7` through `rk2hunt10`,
      2026-08-22. Four Programs, six hunt runs, zero Tests and zero Findings.
      Ticket 150's recording is what finally showed why:

      ```json
      "tools_called": ["get_attack_surface", "get_hypotheses", "http_request",
                       "propose_test", "submit_mission_result"],
      "denials": []
      ```

      The child called it. And:

      ```
      test_proposals|0
      ```

      `propose_test` writes a `test_proposals` row on every path it has --
      refusal included, which its own comment states -- so a call that leaves no
      row is a call that never arrived. Proved by calling it by hand on the same
      database:

      ```
      {"outcome": "refused", "refusal": "a Test performs between 3 and 32 actions"}
      ```

      one row written, the function healthy. The chain that stopped it:

      ```
      RK_TOOL_IMAGE unset
        -> tool.image_from_environment() is None
        -> cli: Slice.tools = None
        -> execution: tooling = None          (required image AND store AND runtime)
        -> agent._serving returns None
        -> job["tooling"] is False
        -> _launch: channel = None
        -> Specification.ask returns {"served": false, "reason": "no_tooling"}
      ```

      `RK_TOOL_IMAGE` appears in no engagement `env.sh`, in no shipped
      documentation and in no default. So this is not a misconfigured
      installation; it is every installation that has not been told a variable
      nothing names.

- [x] **The three verbs that write rows no longer need an image.** `Tooling`
      keeps `runtime` required and makes `container` and `root` optional.
      `execution` builds it whenever it has a connection.

- [x] **The two that do need one still refuse without it.** `_Tools` answers
      `no_tool_image` for `run_tool` and `run_skill_script`, before opening a
      connection, because a machine with no image cannot serve them however well
      the database answers.

- [x] **Checked by something that would go red.**
      `test_a_machine_naming_only_one_of_them_still_reaches_the_runtime` and
      `test_a_supervisor_with_no_image_refuses_the_two_verbs_that_need_one`.

## Why

This is ticket 102's cause. "Nothing in this tree has ever created a Finding"
was read as a gap in the reporting verbs; it was a channel that was never built.
`propose_finding`, `propose_test` and `mint_callback` were all answered
`no_tooling` by a supervisor an installation without a tool image never made,
and the child was told so while the runtime recorded nothing.

The coupling was correct when it was written. `Tooling`'s own docstring argues
"all three or none", and that was one statement back when the supervisor
answered only `run_tool` and `run_skill_script`. Three verbs were added to the
same channel afterwards and the argument was not revisited.

## What was built, 2026-08-22

Three edits and a live run. `rk2hunt11`, first hunt after the change:

```
label|claim|status  |actions|assertions
TST1 |H2   |testable|6      |8
```

`test_proposals` records `created`. The first Test this tree has ever authored.
Ran 316 tests, OK; four gates rc=0.
