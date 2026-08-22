# 150 — Nothing records which verbs a child reached for

**What to build:** The two lists the launcher has always collected, written
where a reader can reach them.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt8` and `rk2hunt9`,
      2026-08-22. Three hunt runs across two Programs, every one told in its own
      objective to call `mcp__rk2__propose_test`, every one leaving:

      ```
      test          |0
      test_proposals|0
      ```

      and no event of any `test.*` type. Answering "did the child call it and
      get refused, or never call it" took: reading `roster.TOOL_GROUPS` to prove
      `web_hunter` is served the verb; reading `_launch.server` to prove the
      handler is built; and rebuilding `Claimed.objective` from the snapshot to
      prove the sentence reached the prompt:

      ```
      has propose_test: True
      names H1: True
      ```

      None of that was necessary. `_launch.py:1973` puts `tools_served` in the
      launcher's result and `AgentRunResult` carries `denials` beside it. Both
      are dropped: `AgentRunResult.as_dict` has no caller in this tree, and
      `agent_runs.result` is NULL for every run in `rk2hunt8` and `rk2hunt9`.

- [x] **The verbs are recorded.** `facts["agent_run"]["tools_called"]`, sorted
      and deduplicated, beside the token counts that are already there.

- [x] **The refusals are recorded.** `facts["agent_run"]["denials"]`, as the
      launcher collected them.

- [x] **Checked by something that would go red.**
      `test_the_verbs_the_child_reached_for_are_recorded_beside_its_tokens`.

## Why

An observability defect that cost two live hunts. The distinction it hides --
a tool never called versus a tool called and denied -- is the difference between
a prompt to rewrite and a permission to fix, and there was no way to tell them
apart from the record.

## What was built, 2026-08-22

Two lines beside the token counts, in the block that already translates the
SDK's stop word. Deduplicated and sorted, because `surface.served` appends once
per call and the question this answers is which verbs were reached for, not how
often. Ran 150 tests, OK.
