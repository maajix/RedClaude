# 104 — Let the model ask to be parked for a human

**What to build:** The handler for `mcp__rk2__park_for_human`, so that the
human-decision loop is reachable from the model side as well as from the network
side.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] `mcp__rk2__park_for_human` is served. It is declared at
      `src/redkraken/roster.py:727-745` with `writes=("pending_decisions",)`, a
      required `task_label`, a required `question_code` closed to five values --
      `scope_ambiguous`, `destructive_action`, `third_party_impact`,
      `credential_needed`, `policy_unclear` -- and a free-text `question`.
      `src/redkraken/_launch.py`'s `server()` builds thirteen tools and none of
      them is this one, and `agent.SERVED_MEMBERS`
      (`src/redkraken/agent.py:151`) names only `get_slate` and `pick_task` out
      of `sched.pick`.
- [ ] The asymmetry the ticket closes is stated as the reason for it. The door
      can already park a Tool run: `park_for_human(uuid, interval)` is granted
      to `rk2_runtime` at `0038_receipt_capabilities.sql:261` and called from
      `src/redkraken/proxy.py` as `PARK_TOOL_RUN = "SELECT park_for_human($1::uuid)"`.
      So a run that walks into a scope ambiguity gets parked by the network,
      and a model that recognises one first has a declared question code for
      exactly that and no way to use it.
- [ ] `question` stops being the anomaly it is today. It is one of only two
      entries in `OPEN_ARGUMENTS` (`roster.py:555`), which is the roster's
      register of arguments exempted from the constraint rule -- an exemption
      spent on a tool that does not exist. After this ticket the exemption buys
      something.
- [ ] The parked run's request is the model's own claim and is recorded as such.
      The door's park path resolves the Tool run it is parking; a model-side
      park names a Task label, so the runtime resolves the Task to the run and
      refuses a label that is not this run's.
- [ ] The three unserved Contracts stop being three. `request_validation` and
      `request_report` remain unserved and are ticket 105's; the compile refuses
      an unclassified one after ticket 130 lands, and until then this ticket
      leaves `agent.py:143-146`'s comment accurate by removing the member it now
      over-counts.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 2.7 calls this "the
sharpest" of the three unserved Contracts: "The runtime can park it from the
network side; the model cannot ask to be parked." Section 4 records the same
finding from the argument side: `park_for_human.task_label`, `.question_code`
and `.question` are three of the four Contract arguments in the whole roster
that reach nothing, and all four belong to unserved Contracts.

The roster states its own rule at `roster.py:800-805`: "A declared argument the
runtime drops is a promise the schema cannot keep, and the honest form of 'not
yet' is not to declare it." That rule is kept for arguments and broken for
tools, and this is the one of the three where the runtime side already exists.
