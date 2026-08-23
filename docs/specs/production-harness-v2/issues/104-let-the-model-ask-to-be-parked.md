# 104 — Let the model ask to be parked for a human

**What to build:** The handler for `mcp__rk2__park_for_human`, so that the
human-decision loop is reachable from the model side as well as from the network
side.

**Blocked by:** nothing.

**Status:** resolved

- [x] `mcp__rk2__park_for_human` is served. It is declared at
      `src/redkraken/roster.py:727-745` with `writes=("pending_decisions",)`, a
      required `task_label`, a required `question_code` closed to five values --
      `scope_ambiguous`, `destructive_action`, `third_party_impact`,
      `credential_needed`, `policy_unclear` -- and a free-text `question`.
      `src/redkraken/_launch.py`'s `server()` builds thirteen tools and none of
      them is this one, and `agent.SERVED_MEMBERS`
      (`src/redkraken/agent.py:151`) names only `get_slate` and `pick_task` out
      of `sched.pick`.
- [x] The asymmetry the ticket closes is stated as the reason for it. The door
      can already park a Tool run: `park_for_human(uuid, interval)` is granted
      to `rk2_runtime` at `0038_receipt_capabilities.sql:261` and called from
      `src/redkraken/proxy.py` as `PARK_TOOL_RUN = "SELECT park_for_human($1::uuid)"`.
      So a run that walks into a scope ambiguity gets parked by the network,
      and a model that recognises one first has a declared question code for
      exactly that and no way to use it.
- [x] `question` stops being the anomaly it is today. It is one of only two
      entries in `OPEN_ARGUMENTS` (`roster.py:555`), which is the roster's
      register of arguments exempted from the constraint rule -- an exemption
      spent on a tool that does not exist. After this ticket the exemption buys
      something.
- [x] The parked run's request is the model's own claim and is recorded as such.
      The door's park path resolves the Tool run it is parking; a model-side
      park names a Task label, so the runtime resolves the Task to the run and
      refuses a label that is not this run's.
- [x] The three unserved Contracts stop being three. `request_validation` and
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

## What was built, 2026-08-23

`20261028T000000Z__a_model_asks_to_be_parked_and_the_task_waits.sql`, one
Contract already declared and now served, one dispatch in `agent.py` and one
tool in `_launch.py`.

**The verb.** `park_task_for_human(p_agent_run_id, p_task, p_question_code,
p_question, p_ttl)` (`:362`). It is not the door's `park_for_human(uuid,
interval)` under another name: the door parks a Tool run it is holding, this
parks the Task an Agent run is running. `rk2_park_the_work` (`:198`) is the
half both sides share -- release the Leases, close the run, leave the Task
parked and its attempt unspent -- and `rk2_ask_for_the_run` (`:311`) is the
half only this side has: the question a person will read.

**Criterion 4, as a refusal rather than as a paragraph.** The Task comes from
the run and the label comes from the model, and the verb compares them
(`:396-400`): a run holding `T...` that names any other Task is answered
`this run holds <label> and a run parks the Task it is running` and writes
nothing. The three refusals before it are the same shape -- no such run, a run
already finished, a run holding no Task (`:377-391`) -- and each answers with a
sentence rather than raising, because the caller is a model and a raised
exception is a turn it cannot use.

**The question is the model's own claim and is recorded as one.**
`rk2_agent_ask_digest` (`:120`) builds the digest the decision carries and
`rk2_quoted_claim` (`:108`) is what marks the free-text half as reported speech;
`render_decision_question` (`:144`) is extended rather than replaced, so an
operator reads a model's ask and the door's own park in the same form.
`revalidate_decision` (`:451`) and `assert_impact_question_parks_its_task`
(`:73`) keep the pre-existing impact path answering the way it did.

**Served.** `mcp__rk2__park_for_human` joins `agent.SERVED_MEMBERS`
(`src/redkraken/agent.py:167-171`), which is `sched.pick` served in part and
not in whole. `_launch.py` declares the tool at `:1254` and hands it to the
supervisor channel at `:1378-1379`; `agent.py` dispatches it at `:1504` over
`PARK` (`:314-315`). The Contract's shape did not have to change: it is at
`src/redkraken/roster.py:1687` with the five question codes and the required
`task_label` the ticket cites; what the roster gained is the constant
`PARK_FOR_HUMAN` (`:1957`) the dispatch matches on.

**Criterion 3 and criterion 5, both by arithmetic.** `question` stays the one
`OPEN_ARGUMENTS` entry it always was (`roster.py:966`) and is now spent on a
tool that exists. The three unserved Contracts are two: `request_validation`
and `request_report` remain ticket 105's, and `agent.py:155-166` says so in the
comment that used to say three.

**Checked.** `AgentAskTest` (`tests/test_database.py:50033`), 10 cases: the
four refusals, the digest, the rendered question, the Leases released, the
attempt unspent and the Task reaching `parked`. `check_agent_asks()` (`:574`)
is the standing check behind them, filed as `agent_asks` (`:616`) -- one of the
two rows that took `standing_checks` to 66. `rk db verify` answers 96
assertions, 0 violations.

## Why ticket 65 rests on this, 2026-08-23

Ticket 65 demonstrates a *safe* hunt from a fresh install, and its seventh
criterion makes the operator's stop prerequisites part of what the release
ships. A stop the model cannot reach is not a stop: the door could park a Tool
run it was holding, and a model that recognised a scope ambiguity or a
destructive action first had five declared question codes and no way to use
one, so the approval-requiring path ran with nothing on the model side able to
halt it. `park_task_for_human` is that halt, and `agent_asks` is one of the 66
standing checks `rk db verify` answers on the release run. Ticket 65 names this
ticket in its `Blocked by:` line for that reason.
