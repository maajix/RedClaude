"""One ready Task, run from the Slate to a canonical Observation.

This is the slice `rk run` was missing. Everything either side of it already
existed and was tested on its own: the scheduler decides what is worth doing,
the isolation boundary decides what a child can reach, the capability proxy
decides what one request may do, and the promotion function decides what
becomes canonical. What was absent was the thing that runs them in one order,
once, and leaves nothing open behind it.

Four properties are what the order is for, and each of them is a property of
the sequence rather than of any step in it:

* Nothing is claimed that cannot be run. The boundary is resolved before the
  claim, because a Task claimed by a runtime with no container to start is a
  Task holding a lease for nothing.
* The capability is minted against a Tool run that names the Task, and it is
  handed to the child rather than mintable by it. A child that could mint one
  would be a child deciding what it may call.
* The child's structured result is staged and promoted on the runtime's own
  connection, against canonical rows the child cannot see, let alone write.
  Its prose closes nothing: `tasks_completion_needs_promotion` is what refuses
  that, and this module never tries.
* The attempt is closed in a `finally`, by the one database call that closes
  Tool runs, the Agent run, the Leases and the Task together. Whatever went
  wrong above it, the rows do not stay open.

The module imports `program` and is never imported by it. `rk run` reaches the
slice through a callback it is given, because `proxy` imports `program` and a
`program` that imported this module would close that loop.
"""

from __future__ import annotations

import functools
import hashlib
import json
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from redkraken import _startup, agent, build, capsule as capsule_module, isolation, migrate
from redkraken import packet as packet_module, pg, playbook as playbook_module
from redkraken import program, proposal, proxy, replay as replay_module, roster, state as state_module, store
from redkraken.outcome import INTEGRITY_FAILED, INVALID_CONFIGURATION, Ledger


__all__ = [
    "APPLICATION",
    "CERTIFICATE",
    "Claimed",
    "HOME",
    "IMAGE",
    "NETWORK",
    "OPTIONAL",
    "PROXY_CONTAINER",
    "PROXY_URL",
    "REQUIRED",
    "SDK",
    "Slice",
    "boundary",
    "requested",
]


#: Where the Agent boundary is described. Environment rather than the Program's
#: configuration file, for the reason the configuration file is hashed: the
#: image, the network and the proxy container are properties of the machine the
#: harness runs on, not of the Program, and moving to another machine must not
#: read as a policy change that every earlier Finding has to be reconciled with.
IMAGE = "RK_AGENT_IMAGE"
NETWORK = "RK_AGENT_NETWORK"
PROXY_CONTAINER = "RK_AGENT_PROXY_CONTAINER"
PROXY_URL = "RK_AGENT_PROXY_URL"
APPLICATION = "RK_AGENT_APPLICATION"
SDK = "RK_AGENT_SDK"
HOME = "RK_AGENT_HOME"

#: The one the door already owns a name for. A second variable for the same
#: certificate would be a second answer the day one of them is set.
CERTIFICATE = proxy.CA_VARIABLE

#: The five without which there is no boundary, and the three directories that
#: are absent by default because absent is the contained value.
REQUIRED = (IMAGE, NETWORK, PROXY_CONTAINER, PROXY_URL, CERTIFICATE)
OPTIONAL = ((APPLICATION, "application"), (SDK, "sdk"), (HOME, "home"))

#: What it takes for this machine to be claiming a boundary at all. Every
#: variable above except the certificate, because the certificate is the door's
#: name as well: `rk send --ca` falls back to it, so an operator who exports it
#: to talk to the fence by hand has said nothing about running children -- and
#: a `rk run` that read it as a half-described boundary would refuse the command
#: that worked yesterday.
CLAIMED = tuple(name for name in REQUIRED if name != CERTIFICATE) + tuple(
    name for name, _ in OPTIONAL
)

#: What the child is told the Task is, in one sentence per kind. A kind with no
#: sentence here is not refused: the fallback names the kind and the subject,
#: which is the honest description of a Task nobody has written prose for yet.
#: The one kind this runtime performs itself. Named because two places read it
#: -- the dispatch branch and the roster agreement below -- and a kind spelled
#: out at each is a kind that can be renamed in one place out of two.
PERFORM = "perform"

#: The kind that names a Finding rather than measuring one, named for the same
#: reason: the dispatch branch and ticket 163's vocabulary read both ask for it.
CONCLUDE = "conclude"

MISSIONS = {
    "recon": "Map what this target exposes.",
    "hunt": "Look for one exploitable weakness in this target.",
    "analyze": "Read what this target returned and say what it implies.",
    "perform": "Perform the Test that was written to settle this claim.",
    "conclude": "Say what the claim this Test settled is a Finding of.",
    "validate": "Decide whether what was claimed about this target holds.",
    "report": "Write up what has been established about this target.",
}

#: How a child stopped, in the words `agent_runs.stop_reason` accepts. Two
#: vocabularies because they have two authors: the column's is 0006's, extended
#: by 0012, and the word the launcher reads off a `ResultMessage` is the API's
#: -- `end_turn`, `max_tokens`, `tool_use`, `stop_sequence`, `pause_turn`,
#: `refusal`, of which only the last is in both.
#:
#: Writing an unmapped word is not a cosmetic error. `finish_task_attempt` sets
#: the column inside the transaction that also closes the Tool runs, releases
#: the Leases and settles the Task, so the check violation would roll all four
#: back and leave a finished child's attempt open -- exactly the state criterion
#: 5 says a success must not leave.
STOP_REASONS = {
    "end_turn": "completed",
    "stop_sequence": "stop_condition",
    "max_tokens": "budget",
    "pause_turn": "aborted",
    "refusal": "refusal",
}

#: The other side of the same column: what it already accepts. Kept beside the
#: mapping because a launcher answering in the database's own vocabulary is
#: answering correctly, and mapping that answer to `error` would report a
#: finished run as a broken one.
ACCEPTED_STOPS = (
    "completed", "stop_condition", "budget", "refusal", "error", "aborted", "parked",
)

#: The two words that mean a run ended of its own accord. Ticket 161: everything
#: else in `ACCEPTED_STOPS` means the run was cut where it stood -- a token
#: ceiling, a turn ceiling, an SDK error, a child that died -- and a session cut
#: off mid-sentence did not decline the Slate, it never finished reading it.
#: Named as the small set rather than the large one because the large one grows:
#: a stop reason added later is a way of being cut off until somebody says it is
#: not, which is the safe direction for this particular question.
ANSWERED_STOPS = ("completed", "stop_condition")

#: One scheduler pass, in the three steps the corpus states it in. All three,
#: because `offer_slate` on its own offers nothing: `rank_candidates` filters on
#: `t.estimated_cost`, which is NULL until a ranking writes it, and NULL fails
#: the affordability comparison silently. A runtime that only offered would find
#: an empty slate for every Task it had just created and report an idle slate.
#:
#: `advance_lane_quota` sits between them because 0037 says it does: the quota
#: is an input to the entitlement sort and to nothing in the priority formula,
#: so running it after the ranking cannot invalidate the numbers just written.
#:
#: `offer_slate` consumes the outstanding slate and writes a new one, so calling
#: it is not a peek: it is the offer, and the claim takes from it.
#:
#: Every column of it, not a count. A slate the runtime reduced to a number is a
#: slate nobody was offered -- ticket 23's Slate is what the orchestrator chooses
#: from, and a choice needs the entries, their factors and when the offer stops
#: being good. `claim_task()` still takes no argument here: this loop is the
#: runtime's own path, and decision 3 says the runtime takes the first entry.
RANK = "SELECT rank_pass('runtime')"
QUOTA = "SELECT advance_lane_quota('runtime')"
OFFER = "SELECT * FROM offer_slate()"
CLAIM = "SELECT claim_task()"

#: Why an empty Slate is empty, in the scheduler's own words. Ticket 208.
#: `claimable_for` is the predicate `offer_slate` filters on, so asking it
#: directly is reading the reason rather than guessing at one -- and the reasons
#: are worlds apart: a campaign with nothing left to do and a campaign holding
#: 685 Tasks it has no lane budget to fund both answered "no Task is ready", and
#: an operator was told the first when it was the second.
#:
#: Grouped and not listed. The point is which wall the pass hit, and a Program
#: can have hundreds of Tasks behind one.
UNREADY = (
    "SELECT claimable_for(t, w) AS reason, count(*) AS tasks"
    "  FROM tasks t"
    "  CROSS JOIN (SELECT * FROM scheduler_weights WHERE active) w"
    " WHERE t.status = 'pending' AND t.program_id = rk2_program_required()"
    " GROUP BY 1 ORDER BY 2 DESC, 1"
)

#: The decision between the offer and the claim. `open_orchestrator_session`
#: opens the Task-less Agent run the choice is made in and answers the two
#: ceilings the child has no database to read; `record_choice` writes what came
#: back, downgrading a label the current Slate no longer carries to `off_slate`
#: rather than substituting one of its own.
#:
#: `claim_task()` above still takes no argument, and that is what makes the two
#: paths one path: called with none it prefers this Program's outstanding pick,
#: re-checks it under a lock and walks the Slate only when there is no pick to
#: honour. So a session that chose is committed by the same statement that
#: covers a session that chose nothing, and neither can name a Task the offer
#: did not carry.
OPEN_SESSION = "SELECT open_orchestrator_session()"

#: The other half of criterion 2, asked once at the end of every pass. The open
#: above asks it too, so this is not where rotation is decided -- it is where a
#: campaign that reached a ceiling on what turns out to be the last pass of the
#: day gets closed anyway, with its Event, instead of sitting open until a
#: supervisor happens to run again.
ROTATE = "SELECT rotate_orchestrator_session()"
CHOICE = "SELECT record_choice($1::uuid, $2, $3, $4)"

#: What one orchestrator session is told. The Slate is not repeated into it: the
#: entries are served by `get_slate` from the same job document, and an
#: objective carrying them as prose would be a second copy for the model to
#: prefer. What this does say is the bound -- one call, the runtime re-checks
#: it, and choosing nothing is an answer with a defined consequence rather than
#: a failure.
#:
#: The capsule is repeated into it, and that is ticket 28's criterion rather than
#: an exception to the rule above: a rotated session "receives" what it inherits,
#: and a document behind a tool call is a document a model can decline to read.
#: Its Slate section is dropped on the way in -- `Capsule.brief` -- so the one
#: copy of the entries is still the one `get_slate` serves.
PLANNING = (
    "Choose the Task this harness runs next.\n\n"
    "You are {session}, generation {generation} of this campaign. What the "
    "sessions before you left is below, and it is all of it: there is no "
    "transcript, and every session before this one has been closed.\n\n"
    "{capsule}\n\n"
    "Call mcp__rk2__get_slate for the {count} Task(s) on offer, each with its kind, "
    "subject, priority and the factors behind that priority. Read what the Program "
    "already knows with the state tools where it helps you tell them apart. Then "
    "call mcp__rk2__pick_task once, with the label of the one to run.\n\n"
    "You are choosing, not running. Nothing you pick is executed by you, and the "
    "runtime re-checks the Task inside the transaction that claims it: a label this "
    "Slate no longer carries is refused rather than replaced. Name nothing and the "
    "runtime claims the first entry that still holds."
)

#: What ends a worker run, said to the worker. Every one of them is a mechanism
#: this runtime already had and never mentioned: `_launch` breaks the message
#: loop the turn the token ceiling is crossed, the SDK ends the session at the
#: role's turn count, and `authorize_tool_run` refuses to mint against a Task
#: whose Lease has expired. A child that learns any of the three by hitting it
#: has already spent the attempt it would have shortened.
MISSION_STOPS = (
    "you submit the mission result, which is the only ending that files anything",
    "a ceiling above is reached, which cuts the run where it stands",
    "this Task's Lease expires, after which no further request is authorised",
)

#: The same, for the session that chooses rather than runs. It holds no Lease --
#: nothing was claimed for it -- so the third condition is not one it has.
PLANNING_STOPS = (
    "you pick a Task, which is the whole of this decision",
    "a ceiling above is reached, which cuts the run where it stands",
)


#: The one outcome word no `scheduler.chose` row ever carries. `record_choice`
#: writes five; this is the sixth, and it exists for the case where the write
#: itself did not happen -- a session named a Task and the database refused the
#: statement that would have made it the outstanding pick.
#:
#: It is a word rather than a `None` because the two are opposite instructions.
#: Nothing recorded and nothing chosen is what the fallback walk answers; a
#: choice that was made and could not be committed is a choice this pass may
#: neither honour nor replace, which is the distinction below.
UNRECORDED = "unrecorded"

#: The outcomes a pass stops on, and what the hold says about each. ADR 0003 is
#: explicit that a stale or off-Slate choice is refused and not substituted, and
#: claiming after either of these would substitute one: the runtime's walk is
#: the answer to "nobody chose", never to "the choice was refused".
REFUSED = {
    "off_slate": "this Slate no longer carries",
    UNRECORDED: "could not be committed",
}

#: What was claimed, read back through the Agent run the claim created rather
#: than assembled from what this process asked for. The claim is the database's
#: decision -- which Task, which role, which model -- and a runtime that
#: described the run from its own request would be describing a different run
#: the moment the two disagreed.
#:
#: The target is built here rather than in Python for the same reason: an
#: endpoint's URL is its application's base joined to its template, and the
#: join is one expression over two rows this query already has.
#:
#: The Program is a predicate and not a convenience. `claim_task` answers with
#: an Agent run *label*, and a label is a per-Program counter: every Program's
#: first run is `AR1`. This connection is the runtime's, which sees every
#: Program, so a lookup on the label alone reads back whichever `AR1` the
#: planner reached first -- and the attempt would then be opened against another
#: Program's run. The Task is joined on the same Program for the other half of
#: criterion 5: a run of one Program holding a Task of another is a substitution
#: nothing downstream could notice, so this read answers with no row at all and
#: the claim is reported as one that opened nothing.
#:
#: The cross-role subagent cap comes back with the run for the same reason the
#: Lease TTL is read rather than assumed: it is a column on the one active
#: weights row, which an operator versions for the whole scheduler, and the
#: gate inside the child has to refuse at the number the scheduler offered and
#: claimed under. Read here rather than in a second statement so that it is the
#: row this claim ran against -- a weights version activated between the claim
#: and the launch would otherwise start a child under a cap no part of this
#: attempt was scheduled by.
#:
#: A scalar subquery and not a join, so that a scheduler with no active row
#: answers NULL here rather than no rows at all: the claim would otherwise be
#: reported as a run that cannot be read back, which is the wrong rule for a
#: configuration this query can name exactly.
STARTED = (
    "SELECT ar.id::text, ar.label, ar.role,"
    " t.id::text, t.label, t.kind, t.attempts,"
    " e.id::text, e.type, e.label,"
    " coalesce(ep.method, 'GET'),"
    # Ticket 157. This used to be a CASE over `applications` and `endpoints`
    # here, and `rk2_subject_addressable` was the same rule written a second
    # time in SQL for `ready_for` to read. One of the two could be changed
    # without the other, and the second one was: a claim promoted against a
    # Domain froze in `rk2hunt16` because the predicate said no address where
    # this side could have resolved one. Both now ask the one function.
    " rk2_subject_url(e.id),"
    " (SELECT w.max_concurrent_subagents FROM scheduler_weights w WHERE w.active),"
    " (SELECT br.tokens FROM budget_reservations br"
    "   WHERE br.agent_run_id = ar.id AND br.settled_at IS NULL),"
    " h.label, ts.label,"
    # Ticket 131. The one Identity this Task selected, as the door's two
    # readings of it: the slot name a request is opened under, and the class
    # that decides whether it is opened under one at all. A LEFT JOIN because
    # the column is NOT NULL and a missing row would be a claim this runtime
    # could not describe rather than one it should refuse to describe.
    " coalesce(i.slot_name, ''), coalesce(i.class, 'anonymous')"
    " FROM agent_runs ar"
    " JOIN tasks t ON t.id = ar.task_id AND t.program_id = ar.program_id"
    " JOIN entities e ON e.id = t.subject_entity_id"
    " LEFT JOIN identities i ON i.entity_id = t.selected_identity_entity_id"
    " LEFT JOIN endpoints ep ON ep.entity_id = e.id"
    " LEFT JOIN hypotheses h ON h.id = t.hypothesis_id AND h.program_id = t.program_id"
    " LEFT JOIN tests ts ON ts.id = t.test_id AND ts.program_id = t.program_id"
    " WHERE ar.label = $1 AND ar.program_id = $2::uuid"
)

#: Whether this Task's Playbooks have already been decided. A retry finds them
#: decided: `playbook_selections` is unique on (task_id, playbook_id), so a
#: second record is refused by the constraint -- and it should be. The digests
#: frozen on the first attempt are what the grading in `rk playbook evaluate`
#: keys on, and a Task that recorded a second set would have two answers to
#: "which text did the model read".
RECORDED = "SELECT count(*)::int FROM playbook_selections WHERE task_id = $1::uuid"

#: What one Mission packet may cost, from the row that says what anything may
#: cost. Read on the runtime connection rather than carried on the claim,
#: because unlike the subagent and token caps the scheduler did not rank or
#: reserve under this one -- it binds the document, at the moment the document
#: is built.
PACKET_LIMITS = (
    "SELECT packet_max_bytes, packet_max_tokens FROM scheduler_weights WHERE active"
)

#: Story 182's demotion, asked at the one moment its answer changes something.
#: `demote_playbooks` takes the stable Playbooks whose own test now fails or
#: whose review date has passed, writes the ledger row and puts them back to
#: draft. It runs immediately before a selection because that is where a stale
#: `stable` costs something: `select_playbooks` drops an expired Playbook on its
#: own, and a failing one it would otherwise keep -- the status is what says the
#: catalogue stands behind it, and nothing else in a hunt reads the verdict.
DEMOTE = "SELECT count(*) FROM demote_playbooks()"

#: The selection, run and written down in one call. Three of the five arguments
#: are left to the database's own defaults rather than restated here, because
#: this runtime does not hold them: there is no property class for a Task whose
#: subject has not been narrowed, no autonomy ceiling anywhere in the installed
#: configuration, and no cap on the selection that is this caller's to set. The
#: program and the role the function derives from the Task itself.
RECORD_SELECTION = "SELECT record_playbook_selection($1::uuid, $2::uuid)"

#: What was kept, read back rather than assumed from the count the call returns.
#: The row is what the run is graded against, so the row is what the child is
#: handed -- an ordering by rank because the ranks are the selection's own
#: preference and the prompt reads top down.
SELECTED = (
    "SELECT p.path, s.playbook_sha256, s.playbook_version"
    " FROM playbook_selections s JOIN playbooks p ON p.id = s.playbook_id"
    " WHERE s.task_id = $1::uuid AND s.dropped_because IS NULL"
    " ORDER BY s.rank"
)

#: Ticket 163. The words a `conclude` child is allowed to name, read from the
#: table that defines them. Read per attempt rather than held as a Python
#: constant for the reason the roster already gives for not making it an enum:
#: a second copy of this table goes stale, and a migration that seeds a new
#: class would leave the prompt describing the old vocabulary. `rk2hunt17` spent
#: six runs and eighteen proposals guessing words that were never in it.
CLASSES = "SELECT id FROM vulnerability_classes ORDER BY id"

#: Ticket 164's answer to "nothing in the corpus is about this subject", which
#: was true and unusable: it named no Playbook and no fact, so an operator
#: looking at a Drupal login page and a corpus holding a CMS Playbook had
#: nothing to read. Asked only when the selection kept nothing, because that is
#: the one moment the near miss is the whole of the news -- a run with a
#: Playbook is a run whose strategy is already in the ledger.
#:
#: One fact short and no further. Two facts short is most of a fifty-document
#: catalogue against a thin surface, and a list that long says the same thing
#: the empty one did.
NEAR_MISSES = (
    "SELECT path, array_to_string(missing_facts, ', ')"
    " FROM playbook_near_misses($1::uuid, $2::uuid, 1)"
)

#: The staleness sweep, which 027 wrote and nothing has ever run. Staleness is
#: evaluated at selection and never again inside a run, so what this writes is a
#: record rather than an eviction: a live selection whose Playbook expired under
#: it gets the stamp, the mission goes on reading the text it was handed, and
#: `check_playbook_integrity` is where the stamp is read back out. Without a
#: caller that warning asks for a row nothing could produce.
SWEEP_STALE = "SELECT mark_stale_selections()"

#: What the selection turned out to have been worth, asked once the Task it was
#: made for is settled rather than once this attempt is over. The two are
#: different questions: an attempt that promoted nothing hands a Task with
#: attempts left back onto the Slate, and the retry runs under these same rows,
#: so a settlement charged per attempt would retire a Playbook against a subject
#: on the strength of a container that failed to start. The verb reads the
#: Task's status for itself and declines to write while it is still open.
SETTLE_SELECTION = "SELECT settle_playbook_selections($1::uuid)"

#: The retest lane's two writes, in the order they have to happen in. 007 gave a
#: settled claim a watch row and never wrote one; 034 gave a kept refutation a
#: relevance rule and reads the watch rows beside it. Arming first is what keeps
#: the two from colliding: a watch is stamped with the Application's fingerprint
#: as it stands now, so a watch armed in this transaction compares equal in the
#: refresh that follows it and cannot fire on the pass that created it.
ARM_WATCHES = "SELECT arm_retest_watches()"
REFRESH_NEGATIVES = "SELECT refresh_negative_knowledge()"

#: What the lane is holding, as the operator's own view renders it. `standing`
#: is computed per row by `rk2_negative_standing`, so `due` here is the same
#: word `rk state` would show and not a second opinion assembled out of columns.
#: Named by Program because the view is: `rk2_runtime` reads every Program on
#: the machine, and a pass that reported another hunt's refutations would be
#: reporting them under this hunt's name.
DUE_RETESTS = (
    "SELECT hypothesis, hypothesis_status, subject, property_class, application,"
    "       reason, retest"
    "  FROM v_negative_knowledge"
    " WHERE standing = 'due'"
    "   AND program = (SELECT p.slug FROM programs p WHERE p.id = $1::uuid)"
    " ORDER BY settled_at, hypothesis"
    " LIMIT $2"
)

#: And what moved, which is the other half of the same sentence: a refutation
#: made due names the delta that did it, and this is the delta with its subject
#: and the classes it puts back in question. Newest first, because a pass report
#: is read for what has just happened.
SURFACE_MOVES = (
    "SELECT application, kind, subject, subject_key, property_classes,"
    "       detected_at::text"
    "  FROM v_surface_deltas"
    " WHERE program = (SELECT p.slug FROM programs p WHERE p.id = $1::uuid)"
    " ORDER BY detected_at DESC, subject_key"
    " LIMIT $2"
)

#: How many rows of each the pass report carries. A hunt accumulates refutations
#: and deltas for as long as it runs, and a report that grew with the Program
#: would be a report nobody finishes reading; the counts the two verbs answer
#: with are unbounded and say how much is behind the list.
RETEST_ROWS = 20

#: The Tool run the capability is minted against. `proxy.OPEN_TOOL_RUN` cannot
#: be reused: `authorize_tool_run` requires a Tool run's Task to match its Agent
#: run's, and the proxy's own row carries no Task because the command that opens
#: it has none. Everything else about the row is the same, including the tool
#: name -- `proxy.TOOL` is what `canonical_request`, the `net_*` risk rules and
#: the egress authorisation all key on, and a second spelling would be a row no
#: rule matches.
OPEN_TOOL_RUN = (
    "INSERT INTO tool_runs (program_id, agent_run_id, task_id, tool, args, status, transport)"
    " VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5::jsonb, 'running', 'runtime')"
    " RETURNING id::text, label"
)

#: How long the capability has left, asked of the database that set it rather
#: than parsed out of the verdict. The child is given no longer than this: a
#: run still going when its capability lapses is a run whose remaining turns
#: cannot reach anything, and the honest thing to do with them is not spend them.
LIFETIME = (
    "SELECT greatest(0, extract(epoch FROM (egress_token_expires_at - clock_timestamp())))"
    " FROM tool_runs WHERE id = $1::uuid"
)

#: What the door recorded for this Tool run, which is how the runtime learns
#: what the child's one request actually did. The child reports too, and its
#: report is not evidence: the Receipt is written by the fence, on the fence's
#: own connection, and is the row a promoted Observation has to cite.
#: Every Receipt the door wrote under one Tool run, newest first. All of them
#: and not the newest alone: how the run closes turns on whether anything
#: actually refused it, and one run may make several requests -- a refusal and,
#: separately, a target that did not answer. `_exchange` reads the first row for
#: what the run ended on and the rest for that question.
EXCHANGE = (
    "SELECT label, decision, status_code, reason FROM receipts"
    " WHERE program_id = $1::uuid AND tool_run_id = $2::uuid"
    " ORDER BY ts_arrival DESC"
)

CAUSE = "SELECT set_cause($1::uuid, $2::uuid)"
PROMOTE = "SELECT promote_proposal($1::uuid)"
FINGERPRINT = "SELECT fingerprint_program_surface()"
#: The address a Receipt pinned, read back as a Host and as the two edges
#: that hang off it. No argument: the function's own default sweeps every
#: allowed Receipt of this Program that has no topology yet, which is
#: idempotent, and naming one Receipt would ask this side to know which
#: Receipts the promotion had just made attachable -- which it does not.
TOPOLOGY = "SELECT record_receipt_topology()"
#: The one call that closes an Agent run, its Task and its Reservation. Named
#: arguments rather than positional ones since ticket 165 widened it: the
#: parameters past the two totals all default to NULL and are applied as
#: `coalesce`, so a caller that names them cannot be broken by one being added
#: between two others.
FINISH = (
    "SELECT finish_task_attempt("
    "p_agent_run => $1::uuid,"
    " p_stop_reason => $2,"
    " p_input_tokens => $3,"
    " p_output_tokens => $4,"
    " p_uncached_input_tokens => $5,"
    " p_cache_creation_input_tokens => $6,"
    " p_cache_read_input_tokens => $7,"
    " p_answer_count => $8,"
    " p_budget_tokens => $9,"
    " p_budget_policy => $10,"
    " p_error_detail => $11,"
    " p_attempt_profile_sha256 => $12)"
)

#: What a child reported spending, in the order `FINISH` names it after the two
#: totals. One tuple rather than the names written out at each of the two
#: closings, because the two would drift and the drift would be silent: a key
#: spelled here and not there is a column that stays NULL for half the runs.
SPEND = (
    "uncached_input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "answer_count",
    "budget_tokens",
    "budget_policy",
    "error_detail",
)


#: The word this build charges a run against its ceiling under. Ticket 165: the
#: provider's own `input_tokens` is every turn's whole request, prefix and all,
#: which made a token ceiling into a turn ceiling -- 250 000 bought a
#: `web_hunter` six turns and a `conclude` needs more than six. The child does
#: the counting and reports the word back; this copy is what the dispatch is
#: profiled under, because a profile is needed before there is a child to ask.
BUDGET_POLICY = "cache-credit-v1"

#: How many times this Task has already ended on its ceiling under exactly this
#: dispatch. Read rather than counted from the facts, because the attempts that
#: matter are earlier passes' and this process has no memory of them.
BUDGET_ENDS = (
    "SELECT count(*)::int FROM agent_runs"
    " WHERE task_id = $1::uuid AND stop_reason = 'budget'"
    " AND attempt_profile_sha256 = $2"
)


@functools.cache
def _tree_digest() -> str:
    """What this installation's modules hash to, computed once per process.

    Part of the attempt profile because a build that changed is a dispatch that
    changed: the objective, the ceiling arithmetic and the tool surface all live
    in these modules, so a Task refused a third attempt under one build is owed
    a first one under the next.
    """
    return build.verify().tree_digest


def attempt_profile(claimed: Claimed, mission: packet_module.Packet, role: roster.Role) -> str:
    """What this dispatch is, as one digest, so that a repeat can be recognised.

    Ticket 165. `rk2hunt20`'s T6 ended on `budget` twice and was still at the
    top of the ranking for a third identical attempt: the scheduler ranks a
    Task, not a Task-and-how-it-was-sent, so "already tried and it did not fit"
    is not a thing it can see. This is the sentence that makes it visible.

    Everything that changes what the child is asked to do inside what ceiling:
    the Task, the packet it reads, the role and model that read it, the ceiling
    itself, the policy the ceiling is counted under and the build doing the
    counting. A change to any of them is a genuinely different attempt and earns
    a first retry again.

    Not the recovery hint. The hint is what this runtime says *because* the
    profile repeated, so a profile that included it would differ on the retry it
    is the consequence of -- and the second budget end would look like a first
    one forever.
    """
    described = {
        "task": claimed.task_id,
        "packet": hashlib.sha256(packet_module.encode(mission.as_dict())).hexdigest(),
        "role": claimed.role,
        "model": role.model,
        "token_cap": claimed.token_cap,
        "budget_policy": BUDGET_POLICY,
        "build": _tree_digest(),
        "runtime": list(_startup.KNOWN_RUNTIME),
    }
    return hashlib.sha256(
        json.dumps(described, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def spent(result: "agent.AgentRunResult | None") -> dict:
    """What one child's report says its run cost, keyed as the columns are.

    Nothing rather than zero where no child answered, for the reason the facts
    already give about the two totals: a run whose child never reported spent an
    amount nobody measured, and a zero written here would be settled against.
    """
    if result is None:
        return dict.fromkeys(SPEND)
    return {
        "uncached_input_tokens": result.uncached_input_tokens,
        "cache_creation_input_tokens": result.cache_creation_input_tokens,
        "cache_read_input_tokens": result.cache_read_input_tokens,
        "answer_count": result.answer_count,
        "budget_tokens": result.budget_tokens,
        # Empty is a child that named no policy, and the column is left alone
        # rather than told the run was counted under a word nobody used.
        "budget_policy": result.budget_policy or None,
        "error_detail": result.error_detail,
    }


def charged(usage: Mapping[str, object]) -> tuple:
    """The seven `SPEND` values, with the budget pair kept together.

    `agent_runs_budget_tokens_named`: a number and the name of what produced it
    are both written or neither is. A child counts from zero and names no policy
    until it has one, so a run that reported no accounting of its own arrives
    here as a charge of zero under no name -- which the schema refuses, and
    rightly, because nobody can read that charge backwards. Dropping both is
    what hands the run to `derive_budget_tokens`, which charges the raw sum
    under `legacy-raw-v1`: the answer this schema already has for a run that did
    not count for itself, rather than a second one invented at the wire.
    """
    values = {name: usage.get(name) for name in SPEND}
    if not values["budget_policy"]:
        values["budget_policy"] = None
        values["budget_tokens"] = None
    return tuple(values[name] for name in SPEND)

#: Ticket 143. The other ending, for a Task that never reached an attempt
#: because this runtime cannot dispatch it. `FINISH` settles an attempt and
#: this one settles a Task, which is why it is a second verb and not a
#: fourth argument to the first: an attempt that did not happen is not one
#: to spend, and a Task returned to pending is one the next pass claims and
#: refuses in exactly the same words.
RETIRE = "SELECT retire_task($1::uuid, $2)"

#: The Lease this run was given, and the one call that moves both halves of it.
#: The TTL is read rather than assumed: it is a weights column, so a harness
#: that shortened it would shorten what a crash costs, and a runtime carrying
#: its own copy would keep beating on the old one.
LEASE_TTL = "SELECT extract(epoch FROM lease_ttl) FROM scheduler_weights WHERE active"
HEARTBEAT = "SELECT heartbeat_leases($1::uuid)"

#: What a beat may not outlast. This connection has no timeout of its own -- no
#: statement in this module does -- so a server that stops answering blocks the
#: caller forever, and for every other statement here that is the caller's own
#: thread and its own problem. For a beat it is a second thread the closing has
#: to join before it may use the connection again, so the beat is the one
#: statement that says how long it is willing to wait.
BEAT_TIMEOUT = "SET LOCAL statement_timeout = '20s'"

#: Recovery for what an owner that stopped beating left in flight, asked once
#: per pass and before anything is offered. A crashed sibling's Tasks are not
#: this run's to wait for, and the offer that follows is the first reader that
#: would otherwise skip them.
RECONCILE = "SELECT reconcile_leases()"

#: How many beats fit in one TTL. Three, so two may be lost -- to a slow
#: statement, a paused container, a machine that swapped -- before the Lease
#: lapses and this run's work becomes something another one may take. One would
#: make every missed beat fatal; ten would spend the log on saying nothing.
BEATS_PER_TTL = 3

#: The three answers the gate can give, and the two this runtime may act on.
ALLOW = "allow"
ASK = "ask"

#: The roster group holding the one tool this slice's whole attempt is about.
NET = "net.request"


def requested(environment: Mapping[str, str]) -> bool:
    """Whether this machine was configured to run anything at all.

    A blank environment is not a misconfiguration: it is `rk run` used the way
    every earlier ticket used it, to open a Program and report it. Only a
    half-described boundary is an error, and telling the two apart is what this
    predicate is for.
    """
    return any(environment.get(name) for name in CLAIMED)


def boundary(
    environment: Mapping[str, str],
) -> tuple[isolation.AgentContainer | None, tuple[str, ...]]:
    """The described boundary, or nothing and the names that were missing.

    Nothing is defaulted. An image name guessed here would start a child in
    whatever the guess happened to match, and a proxy URL guessed here would
    point a child's only route at whatever answers on that port -- both of them
    the sort of mistake that looks like a working run.
    """
    missing = tuple(name for name in REQUIRED if not environment.get(name))
    if missing:
        return None, missing
    supplied = {
        field: Path(environment[name])
        for name, field in OPTIONAL
        if environment.get(name)
    }
    container = isolation.AgentContainer(
        image=environment[IMAGE],
        network=environment[NETWORK],
        proxy_container=environment[PROXY_CONTAINER],
        proxy_url=environment[PROXY_URL],
        certificate=Path(environment[CERTIFICATE]),
        **supplied,
    )
    return container, ()


def stopped_as(reported: str | None) -> str:
    """One word for how a child stopped, in the vocabulary the column has.

    Nothing reported is `completed`: a session that ran to the end of its own
    accord is reported with no reason at all, and it did stop. A word neither
    vocabulary has is `error` rather than `completed`, because a run that ended
    for a reason this harness cannot name is not a run it can call finished.
    """
    if reported is None:
        return "completed"
    if reported in ACCEPTED_STOPS:
        return reported
    return STOP_REASONS.get(reported, "error")


def cut_off(result: "agent.AgentRunResult | None") -> str | None:
    """The word for a session that answered nothing because it ran out of room.

    Ticket 161. `rk2hunt17` lap 6 offered three ready Tasks, the orchestrator
    stopped on `budget` at 175 027 input tokens without picking one, and the
    pass reported `nothing_to_execute` -- which `hunt.sh` reads as "the campaign
    is finished" and stopped on, with six of twelve laps unused. A session that
    declined the Slate and a session that never got to look at it are different
    events, and only the first is a campaign decision.

    Nothing for a session that answered, whatever it answered: a pick, an
    unreadable pick, or a considered nothing. The word for the ones that did not
    is the stop reason itself, because "which ceiling" is the next question an
    operator asks and it is already in the answer.
    """
    if result is None or result.choice or result.pick_attempts:
        return None
    stopped = stopped_as(result.stop_reason)
    return None if stopped in ANSWERED_STOPS else stopped


@dataclass(frozen=True, slots=True)
class Chosen:
    """What one orchestrator decision came to, in the words the runtime acts on.

    `outcome` is the database's rather than this runtime's: `record_choice`
    takes what the session answered and returns what it made of it, and the one
    word it can change is `chosen` into `off_slate` -- which it does when the
    Slate no longer carries the label. So a label is here only when a pick was
    actually written, and everything else falls back to the runtime's own walk.
    The exception is `UNRECORDED`, which is the runtime's own and says that no
    row was written at all; it falls back to nothing, because a choice nobody
    recorded is still a choice this pass has no right to replace.

    `task_label` is what the session named even where the outcome refused it.
    A refusal that forgot the label would leave an operator asking why nothing
    ran with no way to see what was asked for.

    `cut_off` is the half `outcome` cannot carry. `record_choice` writes five
    words and none of them distinguishes a session that declined the Slate from
    one that was cut off before it read it -- both are `no_choice` there, and
    ticket 161 is what that cost. So the stop reason travels beside the outcome
    rather than instead of it: the row still says what the database recorded,
    and the pass can still say which of the two an operator is looking at.
    """

    agent_run_id: str
    agent_run_label: str
    outcome: str
    task_label: str | None
    attempts: int
    detail: str | None
    cut_off: str | None = None

    @property
    def committed(self) -> bool:
        """Whether a pick was written, and therefore what the claim must take.

        The word alone, without also asking whether a label came back with it:
        `record_choice` refuses `chosen` with no label, so the two can only
        disagree if the database stopped meaning what it says -- and then the
        pair of them is exactly what the assertion below should be failing on
        rather than quietly passing over.
        """
        return self.outcome == "chosen"

    def facts(self) -> dict:
        return {
            "agent_run": self.agent_run_label,
            "outcome": self.outcome,
            "task": self.task_label,
            "attempts": self.attempts,
            "detail": self.detail,
            "cut_off": self.cut_off,
        }


@dataclass(frozen=True, slots=True)
class Session:
    """The Task-less Agent run one decision is made in.

    `open_orchestrator_session` answers with the run and with the two ceilings
    the child has no database to read for itself, and each step of the decision
    needs a different few of them -- the label to report by, the id to record
    and to close against, the caps to start the child under. One value rather
    than the same four parameters threaded through four methods, which is the
    reason `Claimed` is one value and not twelve.

    The caps are resolved here rather than at the point of use so that the
    defaulting happens once: a Program that stated no token ceiling and a
    weights row read before this ticket existed are both answers this runtime
    has to turn into a number, and turning them into one twice is how the child
    comes to be started under a cap the record does not show.
    """

    agent_run_id: str
    label: str
    subagent_cap: int
    token_cap: int | None
    session_label: str = ""
    generation: int = 1
    capsule_bytes: int = packet_module.DEFAULT_BYTES
    capsule_tokens: int = packet_module.DEFAULT_TOKENS
    #: The `scheduler.rotated` payload the open handed back, or nothing when
    #: this pass closed no campaign. Held whole rather than reduced to a label:
    #: it is the Event's own object, and the two things this runtime says about
    #: a rotation -- which session ended and which ceiling ended it -- are two
    #: keys of it rather than two columns to keep in step.
    rotated: Mapping[str, object] | None = None

    @classmethod
    def from_row(cls, row: dict) -> Session:
        return cls(
            agent_run_id=str(row.get("agent_run")),
            label=str(row.get("label")),
            subagent_cap=int(row.get("subagent_cap") or roster.DEFAULT_SUBAGENTS),
            token_cap=(
                None if row.get("token_cap") is None else int(row["token_cap"])
            ),
            session_label=str(row.get("session_label") or ""),
            generation=int(row.get("generation") or 1),
            capsule_bytes=int(row.get("capsule_bytes") or packet_module.DEFAULT_BYTES),
            capsule_tokens=int(
                row.get("capsule_tokens") or packet_module.DEFAULT_TOKENS
            ),
            rotated=_rotation(row.get("rotated")),
        )

    @property
    def closed(self) -> str:
        """The session this pass closed, as the Event named it."""
        return "" if self.rotated is None else str(self.rotated.get("session") or "")

    @property
    def closed_reason(self) -> str:
        """Which ceiling ended it, in the Event's own word."""
        return "" if self.rotated is None else str(self.rotated.get("reason") or "")

    def limits(self) -> packet_module.Limits:
        """What this session's capsule may cost, from the weights it opened under.

        The row count is the packet default and is not configured beside the two
        ceilings: the sections a capsule carries are the Program's shape rather
        than its contents -- one lifecycle, one budget, the standing checks, what
        is running, the Slate -- and none of them is long enough for a row cap to
        be the bound that bites. The bytes are.
        """
        return packet_module.Limits(
            byte_limit=self.capsule_bytes, token_limit=self.capsule_tokens
        )


@dataclass(frozen=True, slots=True)
class Claimed:
    """One claimed Task and the run the database opened for it.

    A single value rather than fourteen passed around together, because every
    step below the claim needs some of them and no step needs a different
    fourteen. `url` is the one that can be absent: a subject that is neither an
    application nor an endpoint has no address to send a request to, and that
    is a refusal with a reason rather than a missing field to work around.

    `subject_entity_id` is the subject as a row rather than as a name. The
    label is what a report and a prompt say; the id is what `playbook_selections`
    and `select_playbooks` are keyed on, and resolving one from the other later
    would be a second lookup of a subject this row already identified.

    `subagent_cap` is the odd one: it describes the weights row rather than the
    Task, and it is here because it has to travel with the claim. The scheduler
    ranked and claimed under it, and the gate in the child refuses under it, so
    a copy carried anywhere else would be a second statement of the one number
    ticket 73 exists to have only one of.

    `token_cap` travels for the same reason and is read the same way: it is what
    the claim reserved out of the Program's capacity, so it is the number this
    child may spend and no other. NULL is a Program that stated no ceiling and
    has no total to derive one from, which is the one case where nothing was
    reserved and nothing bounds the run but its turn count.
    """

    agent_run_id: str
    agent_run_label: str
    role: str
    task_id: str
    task_label: str
    kind: str
    attempts: int
    subject_entity_id: str
    subject_type: str
    subject_label: str
    method: str
    url: str | None
    subagent_cap: int
    token_cap: int | None
    hypothesis_label: str | None = None
    test_label: str | None = None
    #: Ticket 131: the slot name of the one Identity this Task selected, and its
    #: class. `_anonymous`/`anonymous` is a choice like any other -- a Task that
    #: acts as nobody says so, rather than leaving the question open.
    identity_slot_name: str = ""
    identity_class: str = "anonymous"

    @property
    def identity_slot(self) -> str:
        """What the Tool run's args carry, which is not quite the selection.

        The empty string is the door's own word for "this run acts as no
        Identity" -- `resolve_egress_identity` resolves it to nothing and says
        so -- and the anonymous Identity is exactly that run with a row behind
        it. Writing `_anonymous` here instead would name a slot the door would
        then look for a live Lease on, and would escalate every unauthenticated
        hunt to `approval_required` through `net_borrowed_identity`, which
        grades any non-empty slot as a borrowed account.
        """
        return "" if self.identity_class == "anonymous" else self.identity_slot_name

    @classmethod
    def from_row(cls, row) -> Claimed:
        return cls(
            agent_run_id=str(row[0]),
            agent_run_label=str(row[1]),
            role=str(row[2]),
            task_id=str(row[3]),
            task_label=str(row[4]),
            kind=str(row[5]),
            attempts=int(row[6]),
            subject_entity_id=str(row[7]),
            subject_type=str(row[8]),
            subject_label=str(row[9]),
            method=str(row[10]),
            url=None if row[11] is None else str(row[11]),
            subagent_cap=int(row[12]),
            token_cap=None if row[13] is None else int(row[13]),
            # Absent for every kind but `hunt`, and absent for a hunt only if
            # something other than `derive_hypothesis_hunts` minted it: that
            # derivation writes `tasks.hypothesis_id` on every row it creates,
            # which is why the label is a join here and not a second lookup.
            hypothesis_label=(
                None if len(row) < 15 or row[14] is None else str(row[14])
            ),
            # Present for a `perform` Task and nothing else. `derive_test_performances`
            # writes `tasks.test_id` on every row it creates, and the label is
            # what `replay.run` takes: it resolves a Test by name inside its own
            # transaction, so handing it the id would be handing it a value it
            # would look the name up from anyway.
            test_label=(None if len(row) < 16 or row[15] is None else str(row[15])),
            # Ticket 131. Defaulted rather than indexed blindly for the reason
            # the two above are: `STARTED` is not the only shape a row of this
            # class is built from, and a fixture one column short should read as
            # the anonymous run it describes.
            identity_slot_name=("" if len(row) < 17 or row[16] is None else str(row[16])),
            identity_class=(
                "anonymous" if len(row) < 18 or row[17] is None else str(row[17])
            ),
        )

    def objective(
        self,
        playbooks: Sequence[playbook_module.Projection],
        vocabulary: Sequence[str] = (),
        completion_only: bool = False,
    ) -> str:
        """The whole of what the child is told, and the shape of what it owes back.

        The target is named because the child cannot look it up: its packet
        holds what the Program knows, not what this attempt is for. The citation
        rule is stated because it is the rule promotion applies -- an
        Observation citing no Receipt is dropped, and a child that learns that
        from the drop has already spent the attempt.

        The claim paragraph is here rather than in the tool description because
        a description says what the argument accepts and a Mission says what the
        run owes. Six live hunts on 2026-08-22 filed 47 Observations and no
        Hypothesis at all, which was not the model declining to think: this
        method asked for one observation per thing established and named nothing
        else, so nothing else came back, and every mechanism downstream of a
        claim stayed cold for want of an input nobody requested. It is bounded in
        the same breath it is asked for, because the failure mode of asking is a
        run that manufactures claims its one answer cannot carry, and a claim
        with no surviving supporting edge is rolled back whole -- taking the
        Observations attached to it with it.

        The Playbooks come last and in full, because they are the longest part
        and the instructions above are what the run is graded on. An empty
        sequence is a real answer and reads as one: the selection ran and this
        subject's facts matched nothing, which is a hunt with no strategy behind
        it rather than a hunt whose strategy went missing. It is a parameter and
        not a default for the same reason -- a caller that forgot it would
        produce exactly the prompt this method was written to stop producing.
        """
        mission = MISSIONS.get(self.kind, f"Carry out this {self.kind} Task.")
        head = (
            f"{mission}\n\n"
            f"Subject: the {self.subject_type} {self.subject_label}.\n"
            f"Target: {self.method} {self.url}\n\n"
        )
        if self.kind == CONCLUDE and self.hypothesis_label is not None:
            return self._finishing(
                self._selected(self._conclusion(head, vocabulary), playbooks), completion_only
            )
        # Ticket 188. One sentence, and for `recon` it was the wrong one. Every
        # kind got "send that one request", which is what a hunt against a
        # single claim does and the opposite of what mapping a surface is: 17
        # recon runs on `rk2here` called `http_request` exactly once each and
        # submitted, and 11 of the answers were redirects nobody followed. The
        # Skill that says what a walk is made of is named here rather than left
        # to the child to notice, because a Skill is offered and the measurement
        # is that this one never was opened.
        opening = (
            "That target is where this Task starts and not where it ends. Load the "
            "Skill enumerate-surface before the first request, then walk what it "
            "describes with mcp__rk2__http_request: this Task is graded on the "
            "surface it leaves behind, and a run that sent one request and stopped "
            "mapped one URL. "
            if self.kind == "recon"
            else "Send that one request with mcp__rk2__http_request and read the answer. "
        )
        prompt = (
            f"{head}{opening}"
            "Then call mcp__rk2__submit_mission_result once, with one observation per "
            "thing you actually established, each citing the Receipt the request "
            "answered with. Nothing you write becomes canonical until the runtime "
            "promotes it, and it promotes only what cites a Receipt from this run.\n\n"
            "An Observation is what the answer showed. A Hypothesis is what you "
            "think is wrong with this subject and how somebody could show you "
            "were not. File one wherever this answer grounds one, and file none "
            "where it does not. A claim carries a property_class, a statement, a "
            "rationale answering mechanism, expectation and falsifier, and at "
            "least one evidence edge naming an Observation of this run that "
            "supports it. Put the edge in the top-level evidence list, naming "
            "the claim by hypothesis_ref, or in an evidence list on the claim "
            "itself -- both are read. A claim whose supporting edges do "
            "not survive is rolled back and takes those Observations with it. "
            "Do not say what state a "
            "claim is in. The runtime grades it, and a claim that states its own "
            "grade is refused for saying so."
        )
        if self.kind == "hunt" and self.hypothesis_label is not None:
            prompt = (
                f"{prompt}\n\n"
                f"This Task exists to settle one claim: {self.hypothesis_label}. "
                "Read it with the state tools -- its statement says what is "
                "believed wrong and its rationale says what would show it was "
                "not. If this run can demonstrate the weakness it names, say so "
                "and cite the Receipt that shows it. If it cannot, and one "
                "request often cannot, call mcp__rk2__propose_test once with the "
                f"plan that would: name {self.hypothesis_label}, and give the "
                "actions a baseline, a variant and a control. A hunt that files "
                "neither leaves the claim exactly where it found it.\n\n"
                "Call mcp__rk2__propose_test before mcp__rk2__submit_mission_result, "
                "not after. Submitting is an ending -- it is the first of the stop "
                "conditions above -- so a plan authored after it is a plan this run "
                "never files."
            )
        return self._finishing(self._selected(prompt, playbooks), completion_only)

    def _conclusion(self, head: str, vocabulary: Sequence[str] = ()) -> str:
        """Ticket 156. What a child is told when the measuring is already done.

        The other kinds are asked to establish something. This one is asked to
        name something already established: the claim is supported because the
        runtime replayed the Test that settles it and the replay held, and all
        that is missing is what the settled claim is a Finding OF.

        So the paragraph the other kinds get is not appended. It tells a child
        to send a request, read the answer and submit Observations, and a child
        that did that here would spend its turns re-measuring a claim the
        runtime has already settled -- and would end the run without ever
        calling the one tool the Task was opened for.

        Ticket 163: the vocabulary is written out here rather than referred to.
        "A vulnerability class from this harness's vocabulary" named a table the
        child has no route to, so it guessed, and `propose_finding` refuses a
        guess by name three times and then stops carrying proposals at all.
        Thirty-seven short words cost less than one refused proposal, and they
        come from the table on every attempt so that seeding a new class cannot
        leave this paragraph describing the old list.
        """
        classes = (
            "\n\nThe classes are, and are only:\n"
            f"{', '.join(vocabulary)}.\n\n"
            "Name one of those ids exactly. A word that is not on that list is "
            "refused for not being on it, however well it describes the weakness. "
            "If none of them names this one, do not reach for the nearest synonym: "
            "say so in mcp__rk2__submit_mission_result, naming the ids you weighed, "
            "and let the run end without a Finding. That is an answer this harness "
            "can act on; three refusals of three spellings of the same absent word "
            "is not."
            if vocabulary
            else ""
        )
        return (
            f"{head}"
            f"The claim {self.hypothesis_label} is supported. The runtime replayed "
            "the Test written to settle it and the replay held, so nothing further "
            "needs to be measured and nothing you send will change the verdict.\n\n"
            "What is missing is the name. Call mcp__rk2__propose_finding once, "
            f"naming {self.hypothesis_label} by that label, a vulnerability class "
            "from this harness's vocabulary, and a title a person will read. You do "
            "not name the run that settled the claim: the claim names it, and no "
            "other run would be accepted.\n\n"
            "Read the claim with the state tools before you choose the class. Its "
            "statement says what was believed wrong and the Test says what was "
            "shown; the class is which kind of weakness that is, and it is the one "
            "part of this a person cannot correct later without reopening the "
            "Finding. If seeing the target once would settle which class it is, "
            "send that one request with mcp__rk2__http_request first -- and if it "
            f"would not, do not send it.{classes}\n\n"
            "The runtime answers created, merged or refused. Merged means a Finding "
            "is already open on this cell and your claim was added to it, which is a "
            "result and not a rejection."
        )

    @staticmethod
    def _finishing(prompt: str, completion_only: bool) -> str:
        """Ticket 165's second dispatch: the same Task, told to finish it.

        The first attempt under this dispatch spent the whole ceiling and closed
        nothing, and the ceiling is not a token budget -- a turn's request is the
        whole prefix, so what it buys is turns. Sending the same instruction
        again buys the same turns and spends them the same way, which is what
        `rk2hunt20`'s T6 did twice.

        So the retry is not a wider budget, it is a narrower job: the packet it
        already has, no fresh looking, and the calls that end the Task. Said as
        the last paragraph because it is the one that has to survive a model
        skimming the middle.
        """
        if not completion_only:
            return prompt
        return (
            f"{prompt}\n\n"
            "This Task has already run out of tokens once, doing exactly this. Its "
            "ceiling buys turns rather than tokens -- every turn re-sends the whole "
            "transcript -- so this attempt is for finishing it and nothing else. "
            "Work from the Mission packet you were given: it is the same packet, and "
            "reading the world again to confirm it is how the last attempt ended with "
            "nothing filed. Do not explore, do not re-read what the packet already "
            "carries, and send no request that would only tell you what it says. Call "
            "the verbs that submit what this Task owes, in the order named above, and "
            "end. A partial answer that is filed beats a complete one that is not."
        )

    @staticmethod
    def _selected(prompt: str, playbooks: Sequence[playbook_module.Projection]) -> str:
        """The Playbooks, appended to whichever objective was built above."""
        if not playbooks:
            return prompt
        selected = "\n\n".join(one.text() for one in playbooks)
        return (
            f"{prompt}\n\n"
            f"The runtime selected {len(playbooks)} Playbook(s) for this subject and "
            "recorded the selection against this Task. They are how to ask the "
            "question, not what to report; the paragraph above is still what you "
            f"owe back.\n\n{selected}"
        )

    def facts(self) -> dict:
        return {
            "task": {
                "id": self.task_id,
                "label": self.task_label,
                "kind": self.kind,
                "attempts": self.attempts,
                "subject": self.subject_label,
                "subject_type": self.subject_type,
            },
            "agent_run": {
                "id": self.agent_run_id,
                "label": self.agent_run_label,
                "role": self.role,
                "stop_reason": None,
                # What the claim reserved, and what the run turned out to cost.
                # Nothing rather than zero until a child reports: a run whose
                # child never answered spent an amount nobody measured, and the
                # closing leaves the column alone rather than recording a zero
                # the reservation would then be settled against.
                "token_cap": self.token_cap,
                "input_tokens": None,
                "output_tokens": None,
                # Ticket 165's numbers, absent for the same reason and filled
                # from the child's report where there is one. `attempt_profile`
                # is the exception: it describes the dispatch rather than the
                # run, so it is known before the child starts and is written
                # whether or not one answers.
                **dict.fromkeys(SPEND),
                "attempt_profile": None,
            },
        }


class Heartbeat:
    """One run saying it is still here, for as long as its child runs.

    A thread, because what this has to outlast is a blocking wait on a
    subprocess and there is nothing else in that window to hang a timer on. It
    shares the runtime's connection rather than opening one, and that is safe
    for one reason worth stating: the main thread is inside `_child` for the
    whole life of this thread and touches nothing until `__exit__` has joined
    it. Overlap is not avoided by a lock here, it is not possible.

    That join is unbounded, and `BEAT_TIMEOUT` is why it can be. Bounding the
    join instead would trade a wait for two threads on one stream, which is the
    one thing the paragraph above rules out; bounding the statement leaves the
    beat to fail like any other, and a thread with an error to report stops on
    its own.

    A beat that comes back refused stops the beating and is not retried. The
    database answers `beat: false` when the Task Lease has already lapsed, and
    at that point some reconciliation is entitled to this run's work -- may have
    taken it already. Beating harder at that would be this process arguing with
    the only clock either half of the Lease has.

    A beat that raises stops it too, and stops it quietly. The child is still
    running and the attempt is still worth finishing; what a failed heartbeat
    costs is the Lease, which lapses on its own, and the closing reports it.
    """

    def __init__(
        self,
        connection: pg.Connection,
        ledger: Ledger,
        claimed: Claimed,
        facts: dict,
        every: float,
    ):
        self.connection = connection
        self.ledger = ledger
        self.claimed = claimed
        self.facts = facts
        self.every = every
        self.beats = 0
        self.identities: int | None = None
        self.lapsed: str | None = None
        self.failure: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._beat, name=f"heartbeat-{claimed.agent_run_label}", daemon=True
        )
        self._started = False

    def __enter__(self) -> Heartbeat:
        if self.every > 0:
            self._thread.start()
            self._started = True
        return self

    def __exit__(self, *exception) -> bool:
        self._stop.set()
        if self._started:
            self._thread.join()
        self.facts["heartbeat"] = {
            "every": self.every,
            "beats": self.beats,
            "identities": self.identities,
            "lapsed": self.lapsed,
            "failure": self.failure,
        }
        self._report()
        return False

    def _beat(self) -> None:
        # `wait` and not `sleep`: the child usually ends between two beats, and
        # a sleeping thread would hold the attempt open for the rest of an
        # interval that no longer has anything to keep alive.
        while not self._stop.wait(self.every):
            try:
                with self.connection.transaction():
                    self.connection.execute(BEAT_TIMEOUT)
                    _actor(self.connection)
                    answer = proxy.as_object(
                        self.connection.execute(
                            HEARTBEAT, (self.claimed.agent_run_id,)
                        ).scalar()
                    )
            except (pg.DatabaseError, pg.ConnectionError_) as error:
                # Both, because they are siblings rather than one deriving from
                # the other: the server refusing is a `DatabaseError` and the
                # stream going away is a `ConnectionError_`, and a thread that
                # caught only the first would die with its exception unread,
                # leaving the closing to report a Lease it did not renew.
                self.failure = str(error)
                return
            if not answer.get("beat"):
                self.lapsed = str(answer.get("reason"))
                return
            held = int(answer.get("identity_leases") or 0)
            if self.identities is not None and held < self.identities:
                # The Task half renewed and the Identity half did not come with
                # it. Nothing in this corpus should be able to do that, which is
                # exactly why it is worth saying: what a run holds is one hold,
                # and half of one is the disagreement the Lease exists to
                # prevent. Stopping is the same answer as a lapse, for the same
                # reason -- this process no longer holds what it claimed as.
                self.lapsed = (
                    f"the Identity half of the Lease went from {self.identities} "
                    f"hold(s) to {held}"
                )
                return
            self.identities = held
            self.beats += 1

    def _report(self) -> None:
        if self.failure is not None:
            self.ledger.fail(
                "heartbeat",
                f"{self.claimed.agent_run_label} stopped renewing its Lease after "
                f"{self.beats} beat(s): {self.failure}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        if self.lapsed is not None:
            self.ledger.fail(
                "heartbeat",
                f"{self.claimed.agent_run_label} no longer holds what it claimed after "
                f"{self.beats} beat(s): {self.lapsed}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        if not self._started:
            # Nothing beat and nothing was going to: `_heartbeat` already failed
            # the same assertion saying why. A hold here would be a second
            # assertion under the same name contradicting the first.
            return
        self.ledger.hold(
            "heartbeat",
            f"{self.claimed.task_label} and the {self.identities or 0} Identity Lease(s) "
            f"taken with it were held through {self.beats} beat(s), "
            f"one every {self.every:.0f}s",
        )


@dataclass(frozen=True)
class Slice:
    """One attempt at one Task, and everything an attempt needs to be made.

    `launch` and `state` are the two seams. The first is how a test runs the
    sequence without an engine: the launcher is a callable of the same shape as
    `agent.agent_run`, and everything either side of it is the part worth
    testing. The second is a second connection string, because the Mission
    packet is compiled as the agent role -- what a child may read is decided by
    row level security on that role, and a packet compiled on the runtime's own
    connection would be a packet whose bounds nothing enforced.
    """

    boundary: isolation.AgentContainer
    state: pg.Settings
    launch: Callable[..., agent.AgentRunResult] = agent.agent_run
    timeout: float = agent.TIMEOUT
    #: Where the Artifact bytes are, so the packet can carry the readable head
    #: of each one. Optional because the rest of a pass does not need it: a
    #: machine that names no store still offers, claims and runs, and its
    #: packet says `not_staged` for every Artifact instead of quoting one.
    artifacts: Path | None = None
    #: The image the registered tools are in, for the runs a child asks for
    #: while it is going. Optional for the same reason and with the same
    #: consequence: a machine that names none still runs, and both tool-run
    #: tools answer that there is nothing to run one with. It needs the store
    #: as well -- a run whose output could not be filed is a run that leaves no
    #: evidence -- so neither on its own serves anything.
    tools: isolation.ToolContainer | None = None
    #: Ticket 99: the image a browser mission runs in, and the authority whose
    #: leaf key the browser is told to pin. Its own image and not `tools`, for
    #: the reason `browser.IMAGE_VARIABLE` is its own variable: one holds a
    #: browser and its libraries and the other holds the registered binaries,
    #: and pointing either at the other starts whichever answered. Optional
    #: exactly as `tools` is -- a machine that names neither still runs every
    #: child, and `mcp__rk2__browse` answers that there is no browser to run a
    #: mission with.
    browser: isolation.ToolContainer | None = None
    authority: Path | None = None
    #: The Program configuration, for the one kind this runtime performs itself.
    #: `replay.run` loads it to resolve the Program and to bind the schema
    #: revision the Test was authored under, so a machine that names none can
    #: claim a `perform` Task and will refuse it with that as the reason.
    #: Optional for the same reason the store and the image are: every other
    #: kind runs without it.
    configuration: Path | None = None
    #: Where the door is, as this machine sees it. A second address for the one
    #: door and not a second door: `boundary.proxy_url` is the child's, a
    #: container name on the Agent network, and the runtime is not on that
    #: network. Ticket 153. Given rather than derived, because rewriting the
    #: child's host to a loopback one would be a guess about a port mapping this
    #: process did not make. Optional like the rest: only `perform` spends a
    #: capability from here, and it refuses by name when this is absent.
    proxy_url: str | None = None
    #: A read-only Door/Program check supplied by the production command. Tests
    #: with an in-process launcher leave it absent; production never does.
    preflight: Callable[[isolation.AgentContainer, pg.Connection, str], str] | None = None

    def attempt(self, ledger: Ledger, connection: pg.Connection, program_id: str) -> dict:
        """Reconcile, offer, claim, run, promote, close. Once, and closed either way.

        The session is bound to the Program first and stays bound: every
        scheduler function refuses an unbound session, and binding per statement
        would be four chances to bind the wrong one.

        The campaign is rotated at the end in a `finally` and not on the way out
        of the happy path, for the reason the attempt's own closing is: a
        session that reached a ceiling during this pass should be closed while
        this runtime is still awake. `open_orchestrator_session` asks again on
        the way in, so a supervisor killed between the two loses nothing -- but
        a supervisor that is never run again would otherwise leave the campaign
        open at a ceiling with no Event saying it ended.
        """
        facts = {
            "reconciliation": None,
            "staleness": None,
            "retests": None,
            "slate": [],
            "choice": None,
            "task": None,
            "agent_run": None,
            "target": None,
            "playbooks": None,
            "selections": None,
            "packet": None,
            "heartbeat": None,
            "tool_run": None,
            "receipt": None,
            "replay": None,
            "proposal": None,
            "promotion": None,
            "closure": None,
        }
        connection.execute(proxy.BIND, (program_id,))
        if not self._door_ready(ledger, connection, program_id):
            return facts
        try:
            self._pass(ledger, connection, program_id, facts)
        finally:
            self._rotate(ledger, connection)
        return facts

    def _door_ready(
        self, ledger: Ledger, connection: pg.Connection, program_id: str
    ) -> bool:
        """The production preflight, immediately before each launch boundary."""
        if self.preflight is None:
            return True
        try:
            ready = self.preflight(self.boundary, connection, program_id)
        except (isolation.Unavailable, pg.DatabaseError, pg.ConnectionError_) as error:
            ledger.fail(
                "door_preflight",
                f"no Agent run was started because the Door and runtime could not "
                f"be matched to this Program: {error}",
                code=INVALID_CONFIGURATION,
                source="door",
            )
            return False
        ledger.hold("door_preflight", ready)
        return True

    def _pass(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        facts: dict,
    ) -> None:
        """The pass itself, written into `facts` because every step of it stops."""
        facts["reconciliation"] = self._reconcile(ledger, connection)
        facts["staleness"] = self._stale(ledger, connection)
        facts["retests"] = self._retests(ledger, connection, program_id)

        offered = self._offer(ledger, connection)
        if offered is None:
            return
        facts["slate"] = offered
        if not offered:
            ledger.hold("slate", self._unready(connection))
            return

        chosen = self._choose(ledger, connection, program_id, offered)
        if chosen is not None:
            facts["choice"] = chosen.facts()
        # A choice the runtime cannot honour is where the pass stops, and both
        # ways of not honouring one stop it the same way: `off_slate` because
        # the entry went while the model was thinking, `UNRECORDED` because the
        # write that would have made it the outstanding pick did not happen.
        # `REFUSED` says which, and the reason it is one branch rather than two
        # is that the walk below is the answer to "nobody chose" in both cases
        # and to "the choice was refused" in neither.
        if chosen is not None and chosen.outcome in REFUSED:
            ledger.hold(
                "claim",
                f"{chosen.agent_run_label} chose {chosen.task_label}, which "
                f"{REFUSED[chosen.outcome]}; nothing was claimed",
            )
            return

        claimed = self._claim(ledger, connection, program_id, len(offered))
        if claimed is None:
            return
        facts.update(claimed.facts())
        ledger.hold(
            "claim",
            f"{claimed.task_label} ({claimed.kind}) claimed as {claimed.agent_run_label}, "
            f"attempt {claimed.attempts}",
        )

        try:
            self._run(ledger, connection, program_id, claimed, chosen, facts)
        finally:
            facts["closure"] = self._finish(ledger, connection, claimed, facts)
            facts["selections"] = self._settle(ledger, connection, claimed)

    def _rotate(self, ledger: Ledger, connection: pg.Connection) -> dict | None:
        """Close the campaign if this pass spent the last of it.

        Reported and never fatal: the pass is over, everything it did is
        committed, and a rotation that could not be written is one the next
        pass's open will write instead. What it must not do is take the pass
        down with it -- the session is closed by arithmetic, and arithmetic that
        cannot be recorded is not a reason to fail work that already succeeded.

        Ticket 161 asked when a session closed on `tokens` is meant to rotate,
        and this pair of calls is the answer as it stands: **the pass that
        spends a ceiling closes the session, and the next pass opens its
        successor**. No operator is in it, and nothing rotates mid-pass -- a
        turn is an Agent run and a run is not restarted halfway through. What
        `rk2hunt17` shows is not a rotation that failed but a successor nobody
        asked for: one row at generation 1, `close_reason` `tokens`,
        `rotated_from` null, because `hunt.sh` read the pass's
        `nothing_to_execute` as the campaign being finished and never ran the
        pass that would have opened generation 2. So the fix is the stop reason
        rather than the rotation, and this hold says which of the two happened
        so an operator does not have to read the table to find out.
        """
        try:
            with connection.transaction():
                _actor(connection)
                answer = connection.execute(ROTATE).scalar()
        except pg.DatabaseError as error:
            ledger.fail(
                "rotation",
                f"the campaign could not be rotated at the end of the pass: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return None
        if answer is None:
            return None
        closed = proxy.as_object(answer)
        ledger.hold(
            "rotation",
            f"{closed.get('session')} reached its {closed.get('reason')} ceiling "
            f"and was closed at the end of the pass; the next pass opens the "
            f"successor that continues this campaign",
        )
        return closed

    # -- the slate ---------------------------------------------------------

    def _reconcile(self, ledger: Ledger, connection: pg.Connection) -> dict | None:
        """What an owner that stopped beating left behind, before anything is offered.

        Here rather than in the restart sweep, and explicitly rather than inside
        a read. `resume_program` runs once per `rk run` and answers the question
        for what was in flight when this process started; a sibling that dies
        while this one is working is nobody's restart, and the pass that is
        about to ask what is ready is the first thing that would otherwise walk
        past its Tasks. It reports what it declined to touch as well as what it
        recovered -- a live owner is an answer, not an absence.

        A failure is reported and does not stop the pass. Reconciliation is
        recovery of somebody else's work; this run can still do its own.
        """
        with connection.transaction():
            _actor(connection)
            try:
                answer = proxy.as_object(connection.execute(RECONCILE).scalar())
            except pg.DatabaseError as error:
                ledger.fail(
                    "reconciliation",
                    f"expired Leases could not be reconciled: {error}",
                    code=INTEGRITY_FAILED,
                    source="database",
                )
                return None
        # Every arm of the settling, because each of the three is a Task taken
        # off an owner that stopped beating: offered again, retired for its
        # attempts, or closed because the runtime had already accepted a result
        # of it and only the closing was lost.
        recovered = sum(
            int(answer.get(arm) or 0)
            for arm in ("tasks_returned", "tasks_retired", "tasks_settled_done")
        )
        ledger.hold(
            "reconciliation",
            f"{recovered} Task(s) recovered from lapsed Leases, "
            f"{answer.get('tasks_left_to_live_owners')} left to the runs still holding them",
        )
        return answer

    def _stale(self, ledger: Ledger, connection: pg.Connection) -> dict | None:
        """Which live selections lost the Playbook under them, before anything is offered.

        Beside the reconciliation and for the same reason it is there: this is a
        sweep over what other passes left in flight, and the selection this pass
        is about to make should be made against a catalogue whose expiries have
        already been written down. Not narrowed to the Program this pass is
        bound to, because the catalogue is not: `playbooks` is a program-global
        table, so a review date that has passed has passed for every hunt at
        once, and a sweep that only ever reached the Program somebody happened
        to run would leave the rest to whichever pass came next.

        Reported and never fatal. Nothing acts on `went_stale_at`: selection
        drops an expired Playbook on its own, and what the stamp buys is an
        operator being told that a live mission is running on a text the
        catalogue has stopped standing behind.
        """
        try:
            with connection.transaction():
                _actor(connection)
                marked = int(connection.execute(SWEEP_STALE).scalar() or 0)
        except pg.DatabaseError as error:
            ledger.fail(
                "staleness",
                f"live Playbook selections could not be swept for staleness: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        ledger.hold(
            "staleness",
            f"{marked} live selection(s) had their Playbook expire under them",
        )
        return {"marked": marked}

    def _retests(
        self, ledger: Ledger, connection: pg.Connection, program_id: str
    ) -> dict | None:
        """What the Surface moving has put back in question, before anything is offered.

        The third sweep, beside the reconciliation and the staleness stamp, and
        here for the reason both of those are: it is a walk over what earlier
        passes left standing, and the offer immediately below is its first
        reader. A claim this lane reopens goes back to `testable`, which is what
        stops `cancel_reason_for` abandoning its Task as `answered` and what
        lets `novelty_for` score it above zero -- so a lane run after the ranking
        would put every retest one whole pass late, and a lane run after the
        claim would put it a pass late forever.

        Two writes and then a read of what they did, in one transaction because
        the read is only true of the transaction that wrote it. Arming is first
        for the reason `ARM_WATCHES` states: a watch carries the fingerprint it
        was armed at, so one armed here compares equal in the refresh below and
        waits for the Surface to move, which is what a watch is.

        Reported and never fatal, like the two sweeps beside it. A Program whose
        retest lane will not run is a Program that repeats work it has already
        done, which is expensive and is not a reason to refuse to do any.
        """
        try:
            with connection.transaction():
                _actor(connection)
                armed = proxy.as_object(connection.execute(ARM_WATCHES).scalar())
                refreshed = proxy.as_object(
                    connection.execute(REFRESH_NEGATIVES).scalar()
                )
                due = [
                    _due_retest(row)
                    for row in connection.execute(
                        DUE_RETESTS, (program_id, RETEST_ROWS)
                    ).rows
                ]
                moved = [
                    _surface_move(row)
                    for row in connection.execute(
                        SURFACE_MOVES, (program_id, RETEST_ROWS)
                    ).rows
                ]
        except pg.DatabaseError as error:
            ledger.fail(
                "retests",
                f"the retest lane could not be run: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        answer = {
            "armed": int(armed.get("armed") or 0),
            "watching": int(armed.get("watching") or 0),
            "unwatched": int(armed.get("unwatched") or 0),
            "due": int(refreshed.get("due") or 0),
            "by_reason": refreshed.get("by_reason") or {},
            "reopened": int(refreshed.get("reopened") or 0),
            "watches_fired": int(refreshed.get("watches_fired") or 0),
            "negative_knowledge": due,
            "surface_deltas": moved,
        }
        ledger.hold(
            "retests",
            f"{answer['armed']} claim(s) newly watched and {answer['watching']} "
            f"watching; {answer['due']} refutation(s) became due and "
            f"{answer['reopened']} claim(s) went back to testable",
        )
        return answer

    def _offer(self, ledger: Ledger, connection: pg.Connection) -> list[dict] | None:
        """One scheduler pass: rank, advance the quota, offer.

        One transaction, because the three are one pass. A ranking that
        committed and an offer that did not would leave priorities computed
        against a slate nobody was given, and the next pass would rank them
        again from the same rows.

        The entries come back as the database named them. `None` is the pass
        failing, which an empty slate is not.
        """
        with connection.transaction():
            _actor(connection)
            try:
                connection.execute(RANK)
                connection.execute(QUOTA)
                return [_slate_entry(row) for row in connection.execute(OFFER).dicts()]
            except pg.DatabaseError as error:
                ledger.fail(
                    "slate",
                    f"the scheduler could not offer a slate: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return None

    @staticmethod
    def _unready(connection: pg.Connection) -> str:
        """The empty Slate, with the wall the pass hit named on it.

        Ticket 208. "no Task is ready; nothing was claimed" was the whole of
        what an operator got, and it reads as a campaign that finished. On
        `rk2here` it was a campaign holding 685 pending Tasks whose two working
        lanes had each spent all but one run's worth of a 200,000,000-token
        ceiling -- so `hunt.sh` printed "no work left" and stopped, and 1.6
        billion tokens of the Program's own budget sat unspent behind a lane
        deckel nobody could see from the report.

        The sentence keeps its opening words: that half is a true statement
        about the Slate and three cases in the suite read it. What follows is
        the reason, or nothing where the pass genuinely has no pending Task to
        have a reason about.

        Held and never failed, and a read that raises is swallowed for the same
        reason: this is a sentence about a pass that already ended, and a
        Program whose empty Slate could not be explained is not a Program whose
        pass went wrong.
        """
        sentence = "no Task is ready; nothing was claimed"
        try:
            with connection.transaction():
                rows = connection.execute(UNREADY).rows
        except pg.DatabaseError:
            return sentence
        if not rows:
            return f"{sentence}; no Task is pending"
        return f"{sentence}; " + ", ".join(f"{int(count)} {reason}" for reason, count in rows)

    # -- the decision ------------------------------------------------------

    def _choose(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        offered: list[dict],
    ) -> Chosen | None:
        """One orchestrator decision over the offered Slate, recorded either way.

        Nothing about the claim depends on this succeeding. A session that
        could not be opened, a child that would not start and a model that
        answered nothing all leave the pass exactly where it was -- with a
        Slate and no pick -- and `claim_task` walks it, which is what the
        runtime did before there was an orchestrator. That is the property
        worth stating: the decision is an input to the claim and never a
        precondition for it.

        `None` is only the case where there is no session to record against.
        Every outcome that has one is written, including the ones that say the
        model produced nothing usable, because a pass that claimed nothing has
        to say why it claimed nothing.
        """
        session = self._session(ledger, connection)
        if session is None:
            return None

        result = self._planner(ledger, connection, program_id, session, offered)
        outcome, task, detail = self._answered(result)
        try:
            return self._record(ledger, connection, session, outcome, task, detail, result)
        finally:
            # In a `finally` for the reason the attempt's closing is: this run
            # holds no Task and no reservation, but it does hold an open row
            # that the next pass's reconciliation would otherwise have to reap,
            # and its tokens are not counted against the Program until it closes.
            self._close_session(ledger, connection, session, result)

    def _session(self, ledger: Ledger, connection: pg.Connection) -> Session | None:
        """The Task-less Agent run this decision is made in, or nothing.

        A failure here is reported and is not the pass failing. The one thing
        it costs is the choice, and the claim below covers exactly that case.

        One statement, and the rotation is inside it: `open_orchestrator_session`
        closes a campaign that has reached a ceiling before it opens the turn, so
        this runtime neither decides when to rotate nor has a second place where
        it could forget to. What it does with the answer is say so, because a
        closed campaign is the one thing about this pass an operator reading the
        Ledger cannot see anywhere else in it.
        """
        try:
            with connection.transaction():
                _actor(connection)
                opened = Session.from_row(
                    proxy.as_object(connection.execute(OPEN_SESSION).scalar())
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "choice",
                f"no orchestrator session could be opened to choose in: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return None
        if opened.rotated:
            ledger.hold(
                "rotation",
                f"{opened.closed} reached its {opened.closed_reason} ceiling and was "
                f"closed; {opened.session_label} continues it at generation "
                f"{opened.generation}",
            )
        return opened

    def _planner(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        session: Session,
        offered: list[dict],
    ) -> agent.AgentRunResult | None:
        """The one child that chooses, started with the capsule and no capability.

        No `egress`, and that is a property of the run rather than of the
        request: the roster withholds `net.request` from the orchestrator, so
        there is no capability to mint and nothing served that could spend one.
        Planning that reached a target would be testing nobody scheduled.

        Every failure is the same answer -- no result -- because the caller does
        one thing with all of them. A refused startup, an unavailable boundary
        and a child that died differ in what the Ledger says and not in what
        the pass does next, which is to fall back to the runtime's own walk.
        """
        mission = self._packet(
            ledger,
            connection,
            program_id,
            packet_module.Bounds(
                tokens=session.token_cap,
                subagents=session.subagent_cap,
                turns=roster.ROLES[roster.ORCHESTRATOR].max_turns,
                stop_conditions=PLANNING_STOPS,
            ),
        )
        if mission is None:
            return None
        resume = self._capsule(ledger, connection, program_id, session, offered)
        if resume is None:
            return None
        request = agent.AgentRunRequest(
            agent_run_id=session.agent_run_id,
            objective=PLANNING.format(
                # What `get_slate` will actually serve, which is the capsule's
                # slate section and not the offer it was compiled from: a
                # compaction that dropped entries would otherwise have the
                # objective promise a number the tool cannot produce.
                count=len(resume.slate()),
                session=resume.session or session.label,
                generation=resume.generation,
                capsule=json.dumps(resume.brief(), separators=(",", ":"), default=str),
            ),
            container=self.boundary,
            role=roster.ORCHESTRATOR,
            program_id=program_id,
            packet=mission,
            egress=None,
            timeout=self.timeout,
            subagent_cap=session.subagent_cap,
            token_cap=session.token_cap,
            capsule=resume,
        )
        try:
            return self.launch(request)
        except agent.StartupRefusal as refusal:
            ledger.refuse(
                "startup_assertion",
                f"the choosing child was refused in {refusal.phase} by "
                f"{len(refusal.violations)} vector(s)",
                agent.diagnostics(refusal).violations,
            )
        except isolation.Unavailable as error:
            ledger.fail(
                "boundary",
                f"the Agent boundary could not be provided to choose in: {error}",
                code=INVALID_CONFIGURATION,
                source=f"environment:{IMAGE}",
            )
        except RuntimeError as error:
            ledger.fail(
                "choice",
                f"{session.label} left no account of the choice it was asked to make: "
                f"{error}",
                code=INTEGRITY_FAILED,
                source="agent",
            )
        return None

    @staticmethod
    def _answered(result: agent.AgentRunResult | None) -> tuple[str, str | None, str | None]:
        """What the session answered, as one of the four words the verb takes.

        `off_slate` is not among them on purpose: whether the Slate still
        carries a label is the database's question, asked inside `record_choice`
        by the same function the model would have called. A runtime that decided
        it here would be deciding it against a copy of the Slate with no lock on
        it, and would refuse a choice the claim would have honoured.

        Ticket 161: a session cut off before it answered is still `no_choice` to
        the database, because that vocabulary is a migration's and there is no
        fifth word to write. What changes is that the stop reason stops being
        dropped -- it goes into the detail the Event carries, and `cut_off`
        carries it out to the pass, so the two ways of picking nothing are
        legible in the record and in what the command reports.
        """
        if result is None:
            return "unavailable", None, "no session answered"
        if result.choice:
            return "chosen", result.choice, None
        if result.pick_attempts:
            return (
                "malformed",
                None,
                f"{result.pick_attempts} pick(s) carried no task label",
            )
        stopped = cut_off(result)
        if stopped is not None:
            return "no_choice", None, f"the session stopped as {stopped} before it chose"
        return "no_choice", None, None

    def _record(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        session: Session,
        outcome: str,
        task: str | None,
        detail: str | None,
        result: agent.AgentRunResult | None,
    ) -> Chosen | None:
        """Make the decision durable, in the words the runtime will act on.

        The answer is the database's: `record_choice` returns the outcome it
        recorded, which is the one this runtime dispatches on. Reading back what
        was sent instead would miss the only word it can change -- the
        downgrade to `off_slate` -- and the pass would claim a Task the choice
        was refused for.

        A write that failed is the one case this runtime answers for itself, and
        it answers `UNRECORDED` rather than nothing. Nothing would let the
        fallback walk take entry one on behalf of a session that named a
        different Task, which is a substitution however the write failed -- and
        the substituted Task would run with the choice that lost to it nowhere
        in the record. Only a session that named a Task has anything to refuse:
        one that named none is exactly what the walk is the answer to.
        """
        try:
            with connection.transaction():
                _actor(connection)
                recorded = proxy.as_object(
                    connection.execute(
                        CHOICE, (session.agent_run_id, outcome, task, detail)
                    ).scalar()
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "choice",
                f"the choice {session.label} made could not be recorded: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            if task is None:
                return None
            return Chosen(
                agent_run_id=session.agent_run_id,
                agent_run_label=session.label,
                outcome=UNRECORDED,
                task_label=task,
                attempts=0 if result is None else result.pick_attempts,
                detail=str(error),
                cut_off=cut_off(result),
            )
        chosen = Chosen(
            agent_run_id=session.agent_run_id,
            agent_run_label=session.label,
            outcome=str(recorded.get("outcome")),
            task_label=(
                None if recorded.get("offered_task") is None
                else str(recorded["offered_task"])
            ),
            attempts=0 if result is None else result.pick_attempts,
            detail=None if recorded.get("detail") is None else str(recorded["detail"]),
            cut_off=cut_off(result),
        )
        ledger.hold(
            "choice",
            f"{session.label} answered {chosen.outcome}"
            + (f" ({chosen.task_label})" if chosen.task_label else "")
            + f" after {chosen.attempts} pick(s)"
            + (
                ""
                if chosen.cut_off is None
                else f", having stopped as {chosen.cut_off} rather than declined the Slate"
            ),
        )
        return chosen

    def _close_session(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        session: Session,
        result: agent.AgentRunResult | None,
    ) -> None:
        """Close the session that chose, and charge the Program what it spent.

        The same call the attempt closes with, which is deliberate: a run with
        no Task is a case `finish_task_attempt` already answers, and a second
        closing verb would be a second place the token settlement is written.
        """
        try:
            with connection.transaction():
                _actor(connection)
                usage = spent(result)
                connection.execute(
                    FINISH,
                    (
                        session.agent_run_id,
                        "aborted" if result is None else stopped_as(result.stop_reason),
                        None if result is None else result.input_tokens,
                        None if result is None else result.output_tokens,
                        *charged(usage),
                        # A session holds no Task, so there is no attempt to
                        # profile: what ticket 165 counts is budget ends on one
                        # Task under one unchanged dispatch.
                        None,
                    ),
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "choice",
                f"the orchestrator session {session.label} could not be closed: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )

    def _claim(
        self, ledger: Ledger, connection: pg.Connection, program_id: str, offered: int
    ) -> Claimed | None:
        """One Task off the slate, described by the run the claim opened.

        A refused claim is reported and not retried, because the walk down the
        slate belongs to `claim_task` and has already happened. Called with no
        argument it takes the first entry that is still claimable when the
        claim's own transaction rechecks it, so a NULL here means every entry
        was rechecked and every one had gone -- and a raise here means the pass
        itself is unusable, which retrying would not mend.
        """
        with connection.transaction():
            _actor(connection)
            try:
                label = connection.execute(CLAIM).scalar()
            except pg.DatabaseError as error:
                ledger.fail(
                    "claim",
                    f"the claim against a {offered}-Task slate failed: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return None
            if label is None:
                ledger.hold(
                    "claim", f"{offered} Task(s) offered and none of them was claimable"
                )
                return None
            rows = connection.execute(STARTED, (str(label), program_id)).rows
        if not rows:
            ledger.fail(
                "claim",
                f"{label} was claimed and no run of that name can be read back",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        # A scheduler with no active weights row, named as the configuration it
        # is. The claim itself does not refuse one -- `claim_task` reads the row
        # into an all-NULL record and every comparison against it is unknown --
        # so the first place it can be said out loud is here, where the cap the
        # child would run under is missing rather than wrong.
        if rows[0][12] is None:
            ledger.fail(
                "claim",
                f"{label} was claimed with no active scheduler_weights row to cap it",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return None
        return Claimed.from_row(rows[0])

    # -- the attempt -------------------------------------------------------

    def _run(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        claimed: Claimed,
        chosen: Chosen | None,
        facts: dict,
    ) -> None:
        """Everything between the claim and the closing, in the one order.

        Nothing here raises past `attempt`: each step that cannot continue says
        why and returns, and the `finally` above closes what was opened. A step
        that threw instead would still be closed -- but the report would carry
        a traceback where it should carry the reason.
        """
        if not self._dispatchable(ledger, claimed, chosen):
            return
        # Before every check below it, because none of them is about this kind.
        # A `perform` Task is not dispatched: there is no packet, no capability
        # minted here, no Playbook and no child, because a replay walks a
        # specification a hunt already authored and the runtime is what walks it.
        if claimed.kind == PERFORM:
            self._replay(ledger, connection, claimed, facts)
            return
        if claimed.url is None:
            self._retire(
                ledger,
                connection,
                claimed,
                "target",
                f"the {claimed.subject_type} {claimed.subject_label} carries no address "
                "to send a request to; only applications and endpoints do",
            )
            return
        facts["target"] = {"url": claimed.url, "method": claimed.method}

        role = roster.ROLES.get(claimed.role)
        if role is None or not role.allowed_tools(agent.SERVED):
            # The launcher's own rule, asked here rather than found out there.
            # `agent.assess` refuses a renderer and refuses a role whose served
            # surface is empty -- `validator` holds only `validate.judge`, which
            # nothing serves yet -- and asking after the capability was minted
            # would spend an authorisation on a child that was never going to
            # start.
            self._retire(
                ledger,
                connection,
                claimed,
                "role",
                f"{claimed.agent_run_label} is a {claimed.role} run, which this runtime "
                "cannot start as an isolated child",
            )
            return
        if NET not in role.tool_groups:
            # A capability is minted per attempt and this one could not be
            # spent: the roster withholds the request tool from this role on
            # purpose -- an analyst that fetches is a hunter with the wrong
            # quota -- so a Tool run opened for it would be an authorisation
            # nobody may use, sitting live until the closing swept it.
            self._retire(
                ledger,
                connection,
                claimed,
                "role",
                f"a {claimed.role} run holds no {NET}; this slice serves one "
                f"target request and {claimed.task_label} needs a role that may make it",
            )
            return

        # Before the packet and before the capability, which is what the
        # migration that built the selection is named for: a Playbook chosen
        # after the child started would be a Playbook it did not read.
        selected = self._playbooks(ledger, connection, program_id, claimed, facts)
        if selected is None:
            return

        # Read here for the same reason the Playbooks are: a vocabulary the
        # child is shown after it has started is a vocabulary it proposed
        # without.
        vocabulary = self._vocabulary(ledger, connection, claimed)
        if vocabulary is None:
            return

        mission = self._packet(
            ledger,
            connection,
            program_id,
            packet_module.Bounds(
                tokens=claimed.token_cap,
                subagents=claimed.subagent_cap,
                turns=role.max_turns,
                stop_conditions=MISSION_STOPS,
            ),
        )
        if mission is None:
            return
        facts["packet"] = {
            "revision": mission.revision,
            "sections": {
                name: len(section.rows) for name, section in mission.sections.items()
            },
        }

        # Ticket 165, and after the packet because the packet is part of it: two
        # attempts that read different documents are two attempts, however alike
        # the rest of the dispatch looks. Before the capability, because a Task
        # this pass is about to end should not have one minted for it.
        profile = attempt_profile(claimed, mission, role)
        facts["agent_run"]["attempt_profile"] = profile
        ended = self._budget_ends(ledger, connection, claimed, profile)
        if ended is None:
            return
        if ended >= 2:
            # `rk2hunt20`'s T6: two full-cap runs, still `pending`, still at the
            # top of the ranking. A third identical attempt is the second one
            # again, and the campaign pays for it out of the same capacity.
            self._retire(
                ledger,
                connection,
                claimed,
                "budget",
                f"{claimed.task_label} ended on its token ceiling twice under this "
                f"dispatch and nothing about it has changed since, so a third would "
                f"end the same way: budget_exhausted_twice, profile {profile[:12]}",
            )
            return
        objective = claimed.objective(selected, vocabulary, completion_only=ended == 1)

        # The pass-level check is immediately before the choosing run. Ask
        # again immediately before the worker: the Door is a long-lived process
        # and the two Agent runs are separate launch boundaries.
        if not self._door_ready(ledger, connection, program_id):
            facts["agent_run"]["stop_reason"] = "error"
            facts["agent_run"]["error_detail"] = (
                "the Door preflight failed immediately before the worker launch"
            )
            return

        opened = self._authorize(ledger, connection, program_id, claimed, selected, facts)
        if opened is None:
            return
        tool_run_id, door, lifetime = opened

        outcome = "error"
        try:
            # The beating stops before anything else in this transaction's
            # sequence resumes, which is what makes sharing the connection with
            # it safe -- and before the closing releases the Lease, which is the
            # one thing a late beat could contradict.
            try:
                with self._heartbeat(ledger, connection, claimed, facts):
                    result = self._child(
                        ledger, claimed, objective, mission, door, lifetime, program_id,
                        # Always, now. This used to read the settings only where
                        # a tool image was described, on the argument that a
                        # machine serving no tool call needs no connection --
                        # true when the supervisor answered only tool calls, and
                        # false since it began answering `propose_test`,
                        # `propose_finding` and `mint_callback`, which are rows
                        # rather than containers.
                        connection.settings,
                    )
            except agent.StartupRefusal as refusal:
                # Before the `RuntimeError` arm, which it is one of: a machine
                # that would not start the child is not a child that died, and
                # the two endings settle the Task differently.
                facts["agent_run"]["stop_reason"] = "refusal"
                facts["closure"] = self._refused(
                    ledger, connection, program_id, claimed, refusal
                )
                return
            except RuntimeError as error:
                # The container ran and its account of itself did not survive:
                # a child killed at its timeout, or one that died mid-session.
                # `aborted` and not `error`, because the two words settle
                # differently -- what this run spent is real and unmeasurable,
                # so the closing charges it what its claim reserved, and the
                # word is how the trigger tells that ending from a run that
                # never started.
                facts["agent_run"]["stop_reason"] = "aborted"
                facts["agent_run"]["error_detail"] = (
                    str(error)[:2048] or "the child process failed without detail"
                )
                ledger.fail(
                    "agent_run",
                    f"{claimed.agent_run_label} left no account of itself: {error}",
                    code=INTEGRITY_FAILED,
                    source="agent",
                )
                return
            if result is None:
                facts["agent_run"]["stop_reason"] = "refusal"
                return
            facts["agent_run"]["stop_reason"] = stopped_as(result.stop_reason)
            facts["agent_run"]["input_tokens"] = result.input_tokens
            facts["agent_run"]["output_tokens"] = result.output_tokens
            facts["agent_run"].update(spent(result))
            # Which verbs the child actually reached for, and which it was
            # refused. The launcher has collected both since ticket 86 and
            # nothing has ever read them: `AgentRunResult.as_dict` has no
            # caller, so a run that was served a tool and never called it looked
            # from here exactly like a run that called it and was denied. That
            # is the difference between a prompt to rewrite and a permission to
            # fix, and it cost this engagement two live hunts to tell apart.
            facts["agent_run"]["tools_called"] = sorted(set(result.tools_served))
            facts["agent_run"]["denials"] = [dict(one) for one in result.denials]
            outcome = self._exchange(ledger, connection, program_id, tool_run_id, facts)
            self._promote(ledger, connection, program_id, claimed, result, facts)
        finally:
            # Before the closing call sweeps it. That call closes whatever is
            # still running as `error`, which is the right word for a row nobody
            # accounted for and the wrong one for this row: this runtime knows
            # what the request did, and the Receipt above is what it knows it
            # from.
            self._close(ledger, connection, claimed, facts["tool_run"], outcome)


    def _replay(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        claimed: Claimed,
        facts: dict,
    ) -> None:
        """Perform the Test this Task names, inside the run the claim opened.

        Ticket 152. `replay.run` has been the performer since ticket 35 and its
        only caller was `rk test replay`, which an operator cannot use after the
        fact: a replay is attributed to an Agent run that has not ended, and by
        the time a person can type the command every run this harness opened has
        ended. The claim is what fixes that -- it opens a run, and this is called
        inside it -- so the Task is the caller the lane always needed.

        A second connection, opened by `replay.run` out of the same settings.
        Held to be safe here and nowhere else in this method: nothing above this
        line leaves a transaction open on the runtime's own connection, so the
        `FOR UPDATE` the replay takes on the claim cannot be waiting on a lock
        this process is holding. Sharing the connection instead would mean
        threading one through a module whose every path opens and closes its own,
        which is a larger change to the performer than the caller is worth.

        The Task's ending is the Test run, not this report. A Test that ran and
        settled nothing reports `inconclusive` and fails -- correctly, because
        somebody has to run it again -- while the Task that performed it is done:
        it did the work it was minted for, and `task_result_accepted` reads the
        `test_runs` row rather than the verdict in it.
        """
        run = facts["agent_run"]
        if claimed.test_label is None:
            ledger.fail(
                "replay",
                f"{claimed.task_label} is a {PERFORM} Task naming no Test; "
                "only `derive_test_performances` mints one, and it writes the "
                "Test on every row it creates",
                code=INTEGRITY_FAILED,
                source="database",
            )
            run["stop_reason"] = "error"
            return
        if self.configuration is None:
            ledger.fail(
                "replay",
                f"{claimed.test_label} cannot be performed: this machine names no "
                "Program configuration, and the replay resolves the Program from one",
                code=INVALID_CONFIGURATION,
                source="argument:--config",
            )
            run["stop_reason"] = "error"
            return
        if self.proxy_url is None:
            ledger.fail(
                "replay",
                f"{claimed.test_label} cannot be performed: this machine names no "
                f"door of its own; ${proxy.PROXY_URL} is the runtime's address for "
                f"the door that ${PROXY_URL} names for a child",
                code=INVALID_CONFIGURATION,
                source=f"environment:{proxy.PROXY_URL}",
            )
            run["stop_reason"] = "error"
            return

        performed = replay_module.run(
            connection.settings,
            self.configuration,
            agent_run=claimed.agent_run_label,
            test=claimed.test_label,
            # Ticket 131: the Task's own selection here too, so that a replay
            # and an egress Tool run opened for the same Task cannot act as two
            # different callers. `None` is what an anonymous selection comes to,
            # which is what every perform Task carries today.
            identity_slot=claimed.identity_slot or None,
            proxy_url=self.proxy_url,
            ca_file=self.boundary.certificate,
        )
        facts["replay"] = performed.as_dict()
        # `test_run` is written by `close_test_replay` in the transaction that
        # settles the claim, so its presence is the whole question: a replay
        # that opened and died leaves a Tool run and no Test run, which is this
        # attempt spent and the Task correctly not done.
        settled = performed.facts.get("test_run") is not None
        # Carried whole rather than summarised. The replay keeps its own ledger
        # because it is an operator command in its own right, and a pass that
        # reported only "it failed" would be hiding the one document that says
        # which precondition, which action or which assertion it was.
        #
        # Ticket 183. One exception, and it is the verdict itself. `_conclude`
        # spends `INVALID_CONFIGURATION` on a Test that settled `inconclusive`
        # and on a conclusion the epistemic machine withheld. That is right for
        # `rk test replay`, where an operator asked for a Test and has to run it
        # again, and it claims the wrong thing here: this method's own contract
        # is that the Task's ending is the Test run and not the verdict in it,
        # and `settled` is already the test of that. A settled Test that could
        # not reach its conclusion is the measurement the Task was minted to
        # take. Left as a violation it ends the pass loop and `evaluation._repeat`
        # then discards the whole repeat, every variant of it, exactly as ticket
        # 177's refused request did -- so a playbook whose bar a fixture cannot
        # meet would void the measurement that says so.
        #
        # Only that one sentence is demoted, and it is demoted whole rather than
        # dropped: `_conclude` is the sole writer of a `run` assertion and the
        # sole writer of a `test_run` violation once a Test run exists, so the
        # pair moves together and no assertion is left without the violation
        # behind it. A replay that died before settling keeps every violation it
        # raised, including the `test_run` one `_abandon` writes when
        # `close_test_replay` itself was refused.
        for assertion in performed.assertions:
            if settled and not assertion.ok and assertion.name == "run":
                ledger.hold(assertion.name, assertion.detail)
            else:
                ledger.assertions.append(assertion)
        ledger.violations.extend(
            violation
            for violation in performed.violations
            if not (settled and violation.source == "test_run")
        )
        run["stop_reason"] = "completed" if settled else "error"

    def _budget_ends(
        self, ledger: Ledger, connection: pg.Connection, claimed: Claimed, profile: str
    ) -> int | None:
        """How often this exact dispatch has already run out of tokens. 165.

        `None` is a read that failed, which stops the attempt: dispatching
        anyway would be spending the ceiling on the question this read exists to
        answer, and the retry that follows would be the same run a third time.
        """
        try:
            ended = int(
                connection.execute(BUDGET_ENDS, (claimed.task_id, profile)).scalar() or 0
            )
        except pg.DatabaseError as error:
            ledger.fail(
                "budget",
                f"what {claimed.task_label} has already spent under this dispatch "
                f"could not be read: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        if ended:
            ledger.hold(
                "budget",
                f"{claimed.task_label} has ended on its token ceiling {ended} time(s) "
                f"under this dispatch; this attempt is "
                + ("completion only" if ended == 1 else "not made"),
            )
        return ended

    def _retire(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        claimed: Claimed,
        step: str,
        detail: str,
    ) -> None:
        """End a Task this runtime cannot dispatch, and let the pass go on.

        Ticket 143. These three refusals used to be `ledger.fail`, and a pass
        that fails is `ok: false` and exit 3. `_pass` claims one Task per pass,
        so the same Task came back to the top of the ranking and refused the
        next pass in the same words, and the one after that: `rk2hunt4` lost the
        rest of a campaign to a single `analyze` Task opened by hand.

        Held rather than failed, because nothing went wrong with the run. The
        Task is well-formed and this installation cannot serve it, which is a
        sentence about the Task and not about the pass that read it.

        Ended rather than skipped, because skipping is the same wedge more
        slowly: the Task stays at the top, spends an attempt a pass, and is
        parked as `attempts_exhausted` several passes later under a reason that
        names the wrong thing. `retire_task` says `undispatchable` once and
        writes the sentence into a `task.retired` Event.

        A database that will not take the ending is reported as one. That is a
        genuine failure -- the Task is still live and the next pass meets it
        again -- and it is the one case here that keeps `ledger.fail`.
        """
        try:
            with connection.transaction():
                _actor(connection)
                status = connection.execute(RETIRE, (claimed.task_id, detail)).scalar()
        except pg.DatabaseError as error:
            ledger.fail(
                step,
                f"{detail}; and {claimed.task_label} could not be retired: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        ledger.hold(step, f"{detail}; {claimed.task_label} is {status} as undispatchable")

    def _dispatchable(
        self, ledger: Ledger, claimed: Claimed, chosen: Chosen | None
    ) -> bool:
        """Whether what is about to be dispatched is what was committed.

        Two invariants, both of them the database's and neither of them
        therefore expected to fail: `claim_task` prefers the outstanding pick
        and refuses it when it has gone stale, so a committed choice and a
        claimed Task that are different Tasks is a claim that honoured neither;
        and `role_task_kinds` is unique on kind, so the role the claim wrote is
        the one role the roster gives that kind.

        Checked anyway, and checked here, because this is the last statement
        before a child is started with a Lease and a reservation: a Task
        substituted between the choice and the dispatch is exactly what
        criterion 5 says cannot happen, and an invariant nothing asserts is a
        claim about the code rather than about the run. Reported and returned
        rather than raised -- the caller's `finally` closes the attempt, which
        gives the Task back with its attempt spent rather than leaving it
        claimed by a run that never started.
        """
        if chosen is not None and chosen.committed and chosen.task_label != claimed.task_label:
            ledger.fail(
                "dispatch",
                f"{chosen.agent_run_label} chose {chosen.task_label} and the claim took "
                f"{claimed.task_label}; nothing may be dispatched against a Task nobody "
                "committed",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return False
        expected = roster.ROLE_FOR_KIND.get(claimed.kind)
        if expected != claimed.role:
            ledger.fail(
                "dispatch",
                f"{claimed.task_label} is a {claimed.kind} Task, which the roster gives "
                f"to {expected or 'no role'}, and it was claimed as {claimed.role}",
                code=INTEGRITY_FAILED,
                source="roster",
            )
            return False
        return True

    def _heartbeat(
        self, ledger: Ledger, connection: pg.Connection, claimed: Claimed, facts: dict
    ) -> Heartbeat:
        """How often this run says it is here, from the TTL it was given.

        A TTL this runtime cannot read leaves the interval at zero, which starts
        no thread at all. That is the honest degradation: the Lease still
        expires on its own, the run still finishes, and the report says nothing
        beat rather than claiming a renewal that never happened.
        """
        try:
            ttl = float(str(connection.execute(LEASE_TTL).scalar()))
            if ttl <= 0:
                raise ValueError(f"the active weights declare a TTL of {ttl}s")
        except (pg.DatabaseError, pg.ConnectionError_, TypeError, ValueError) as error:
            ledger.fail(
                "heartbeat",
                f"the Lease TTL could not be read, so {claimed.agent_run_label} will "
                f"not renew what it holds: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            ttl = 0.0
        return Heartbeat(connection, ledger, claimed, facts, ttl / BEATS_PER_TTL)

    def _close(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        claimed: Claimed,
        tool_run: dict,
        outcome: str,
    ) -> None:
        """One Tool run closed as what it did, which is what revokes it.

        The cause is set beside the close and not once at the top of the
        attempt: `set_cause` is transaction-local by construction, so every
        transaction that emits an Event has to say again which run it was
        caused by. Without it this row's settling Event names a Program and no
        run, and criterion 2 asks the rows and the log to name the same one.

        A failure is reported rather than raised. This is called from a
        `finally`, and an exception here would replace the reason the attempt
        ended with the reason the cleanup did.
        """
        try:
            with connection.transaction():
                _actor(connection)
                connection.execute(CAUSE, (claimed.agent_run_id, claimed.task_id))
                connection.execute(proxy.CLOSE_TOOL_RUN, (tool_run["id"], outcome))
        except pg.DatabaseError as error:
            ledger.fail(
                "revocation",
                f"{tool_run['label']} could not be closed as {outcome}: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        ledger.hold(
            "revocation",
            f"{tool_run['label']} closed as {outcome}; its capability no longer resolves",
        )

    def _vocabulary(
        self, ledger: Ledger, connection: pg.Connection, claimed: Claimed
    ) -> tuple[str, ...] | None:
        """The vulnerability classes a `conclude` child may name. Ticket 163.

        Asked only where the objective uses it, because the other kinds propose
        no Finding and a read they never spend is a read they should not make.
        `None` is a refusal to dispatch: a `conclude` child sent out without the
        vocabulary is the run `rk2hunt17` had six of -- it calls the one tool
        the Task was opened for, is refused for a word nobody showed it, and
        ends with the Task exactly where it started.
        """
        if claimed.kind != CONCLUDE:
            return ()
        try:
            rows = connection.execute(CLASSES).rows
        except pg.DatabaseError as error:
            ledger.fail(
                "vocabulary",
                f"the vulnerability classes {claimed.task_label} has to name one of "
                f"could not be read: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        classes = tuple(str(row[0]) for row in rows)
        if not classes:
            ledger.fail(
                "vocabulary",
                "vulnerability_classes is empty, so no Finding this Program proposes "
                "could name a class; the schema is seeded by a migration",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        ledger.hold(
            "vocabulary",
            f"{len(classes)} vulnerability class(es) travel in {claimed.task_label}'s "
            "objective, so the child names one rather than guessing at one",
        )
        return classes

    def _playbooks(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        claimed: Claimed,
        facts: dict,
    ) -> tuple[playbook_module.Projection, ...] | None:
        """Which Playbooks this attempt runs under, chosen and written down.

        Chosen in the database and read back out of it, because the selection is
        a decision about this Task and not a filter this process may apply
        privately. `record_playbook_selection` writes the kept rows and the
        dropped ones with their reasons, and freezes the two digests as they
        stand; those rows are what `rk playbook evaluate` grades a run against.
        A set assembled here and never recorded would leave every verdict keyed
        on `playbook_sha256` measuring the harness instead of the Playbook.

        Keeping nothing is an answer and not a failure. A subject whose facts
        match no trigger has no strategy in the corpus, and the hunt goes ahead
        under the Task's own instructions -- which is the state every run before
        this one was in, said out loud rather than by omission. Said with the
        near misses beside it since ticket 164: "nothing in the corpus is about
        this subject" was true of a Drupal login page and a corpus holding a CMS
        Playbook, and an operator could not tell that from a corpus that really
        had nothing to say.

        What is refused is a selection that cannot be shown: a row naming a path
        this installation does not carry, or one whose frozen digest is not the
        digest of the text about to be handed over. Either way the record would
        describe something other than what the model read, and a grading run
        against it would be reading the wrong document.
        """
        try:
            with connection.transaction():
                _actor(connection)
                demoted = 0
                if not connection.execute(RECORDED, (claimed.task_id,)).scalar():
                    demoted = int(connection.execute(DEMOTE).scalar() or 0)
                    connection.execute(
                        RECORD_SELECTION, (claimed.task_id, claimed.subject_entity_id)
                    )
                rows = connection.execute(SELECTED, (claimed.task_id,)).rows
        except pg.DatabaseError as error:
            ledger.fail(
                "playbooks",
                f"no Playbook could be selected for {claimed.task_label}: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return None

        kept = []
        for row in rows:
            path, source_sha256, version = str(row[0]), str(row[1]), str(row[2])
            one = playbook_module.BY_PATH.get(path)
            if one is None or one.sha256 != source_sha256 or one.version != version:
                ledger.fail(
                    "playbooks",
                    f"{claimed.task_label} was selected {path}, which this installation "
                    "does not carry at the digest the selection froze",
                    code=INTEGRITY_FAILED,
                    source="corpus",
                )
                return None
            kept.append(one)

        facts["playbooks"] = [
            {"path": one.path, "sha256": one.sha256, "version": one.version} for one in kept
        ]
        if demoted:
            # Said out loud because it is a change to the catalogue, made by a
            # hunt that was only asking what to run. The rows are in
            # `playbook_demotions` either way; this is so the operator reading
            # one pass can see that the shape of the corpus moved under it.
            ledger.hold(
                "playbooks",
                f"{demoted} stable Playbook(s) were demoted before this selection: "
                "their own test fails or their review date has passed",
            )
        if kept:
            ledger.hold(
                "playbooks",
                f"{claimed.task_label} runs under " + ", ".join(one.path for one in kept),
            )
        else:
            ledger.hold(
                "playbooks",
                f"{claimed.task_label} runs under no Playbook: nothing in the "
                "corpus is about this subject" + self._near(connection, program_id, claimed),
            )
        return tuple(one.projection for one in kept)

    @staticmethod
    def _near(connection: pg.Connection, program_id: str, claimed: Claimed) -> str:
        """What this subject would have had to carry, or nothing to add.

        Read after the selection's transaction closed and outside any of its
        own, because it decides nothing: a hunt whose corpus said nothing is a
        hunt that goes ahead under the Task's own instructions either way. That
        is also why a database that will not answer this is not a failure here.
        The run is not worse off for a diagnostic it could not print, and
        failing it would turn the sentence that explains a quiet run into a new
        way for the run to stop.
        """
        try:
            rows = connection.execute(NEAR_MISSES, (program_id, claimed.subject_entity_id)).rows
        except pg.DatabaseError:
            return ""
        if not rows:
            return ""
        return "; one fact short: " + ", ".join(
            f"{row[0]} wants {row[1]}" for row in rows
        )

    def _packet(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        bounds: packet_module.Bounds,
    ) -> packet_module.Packet | None:
        """What the child may read, compiled as the role whose reads are bounded.

        Two connections, because the ceiling and the rows are read by different
        roles. The limits come off the runtime connection this pass already
        holds -- `rk2_state` cannot see the weights row, and should not -- and
        the rows come off an agent-scoped one, where row level security decides
        which Program they belong to.
        """
        limits = self._packet_limits(connection)
        session = migrate.open_connection(ledger, self.state)
        if session is None:
            return None
        with session:
            if not state_module.assert_agent_connection(ledger, session):
                return None
            with session.transaction():
                session.execute("SET TRANSACTION READ ONLY")
                if not state_module.bind_agent_session(ledger, session, program_id):
                    return None
                try:
                    return packet_module.compile(
                        session, limits=limits, bounds=bounds, load=self._excerpt_loader()
                    )
                except packet_module.PacketError as error:
                    ledger.fail(
                        "packet",
                        f"the child could not be told what it may read: {error}",
                        code=INVALID_CONFIGURATION,
                        source="database",
                    )
                    return None

    def _packet_limits(self, connection: pg.Connection) -> packet_module.Limits:
        """The configured ceiling one packet is fitted to.

        Decision 11 asks for a configured ceiling and not a defaulted one, so
        this is a read rather than a constant. A weights row that is not there
        is the module's own numbers, which is what the columns default to
        anyway: both callers refuse a pass with no active weights row well
        before this, so an empty answer here is a shape to have rather than a
        second setting to keep in step.
        """
        rows = connection.execute(PACKET_LIMITS).rows
        if not rows:
            return packet_module.Limits()
        return packet_module.Limits(
            byte_limit=int(rows[0][0]), token_limit=int(rows[0][1])
        )

    def _excerpt_loader(self) -> Callable[[str], bytes | None] | None:
        """How the packet reads an Artifact's bytes, or nothing if there is no store.

        The store is content-addressed and the runtime is the side that may
        address it that way -- the child has no route to it at all, which is
        why the head of each Artifact travels inside the packet or not at all.

        Every failure answers `None` rather than raising. A hash the store does
        not hold and a hash whose bytes no longer match it are both "this
        Artifact has no readable head here", and a compile that raised on one
        would lose the packet over a single missing file.
        """
        if self.artifacts is None:
            return None
        keep = store.Store(self.artifacts)

        def load(sha256: str) -> bytes | None:
            try:
                return keep.load(sha256)
            except (store.Missing, store.Corrupt, OSError):
                return None

        return load

    def _capsule(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        session: Session,
        offered: list[dict],
    ) -> capsule_module.Capsule | None:
        """What this session inherits, compiled because nothing else survives.

        On the runtime connection and not the agent one, unlike the packet: the
        campaign, the budgets and the Tasks waiting to run are not on the state
        read surface, and a session choosing between Tasks is not reading inside
        one.

        A capsule that cannot be built is the choice not happening, like every
        other failure on this path: the pass keeps its Slate, `claim_task` walks
        it, and the Ledger says why nobody was asked. A capsule so tight that
        the compaction dropped every Slate entry is the same failure by a
        quieter route -- a session asked to choose from a list it cannot be
        shown -- so it is refused here rather than sent, and the runtime's own
        walk claims the entry a model was never offered.
        """
        try:
            with connection.transaction():
                built = capsule_module.compile(
                    connection,
                    program_id,
                    session=session.session_label,
                    generation=session.generation,
                    limits=session.limits(),
                    slate=offered,
                )
        except (capsule_module.CapsuleError, pg.DatabaseError) as error:
            ledger.fail(
                "capsule",
                f"{session.label} could not be given what it inherits: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return None
        if offered and not built.slate():
            ledger.fail(
                "capsule",
                f"{session.label} was left no Slate entry to choose from: "
                f"{len(offered)} offered, {built.limits.byte_ceiling} byte(s) of capsule",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return None
        ledger.hold(
            "capsule",
            f"{built.session or session.label} resumes at generation "
            f"{built.generation} from {len(built.rows())} row(s), "
            f"{built.document_bytes} byte(s), about {built.document_tokens} token(s)",
        )
        return built

    def _authorize(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        claimed: Claimed,
        selected: tuple[playbook_module.Projection, ...],
        facts: dict,
    ) -> tuple[str, agent.Egress, float] | None:
        """One Tool run naming the Task, one verdict, one capability with a clock.

        Committed before the verdict is asked for, because the gate resolves the
        row on a session of its own and cannot see an uncommitted one -- and
        asked for before the child starts, because a child handed no capability
        is a child that can do nothing with the turns it would spend finding out.

        Every statement is inside the guard, including the two reads. A verdict
        this runtime could not obtain is a reason to report and close the
        attempt, and a traceback out of here would leave `rk run` answering with
        one where it owes a Ledger.

        The Playbooks come in because one of the four things written into the
        Tool run's args is derived from them. `body_allowed` is ticket 96's rule
        stated at the moment the risk class is computed and a human is asked, so
        that the answer a person gives is an answer about a run whose authority
        is already settled rather than about one that could grow it afterwards.
        """
        try:
            with connection.transaction():
                _actor(connection)
                connection.execute(CAUSE, (claimed.agent_run_id, claimed.task_id))
                opened = connection.execute(
                    OPEN_TOOL_RUN,
                    (
                        program_id,
                        claimed.agent_run_id,
                        claimed.task_id,
                        proxy.TOOL,
                        json.dumps(
                            {
                                "url": claimed.url,
                                "method": claimed.method,
                                # Ticket 131. The Task's own selection, written
                                # before the digest is taken -- which is the
                                # whole of why it is the Task's and not the
                                # door's: `gate_tool_call` grades an empty slot
                                # `constrained` and a filled one
                                # `approval_required`, and a slot chosen after a
                                # human answered would spend a real account
                                # outside the answer that was given.
                                "identity_slot": claimed.identity_slot,
                                "body_allowed": _body_allowed(selected),
                            }
                        ),
                    ),
                ).rows[0]
            tool_run_id, label = str(opened[0]), str(opened[1])
            facts["tool_run"] = {"id": tool_run_id, "label": label, "decision": None}

            gate = proxy.as_object(
                connection.execute(proxy.AUTHORIZE_TOOL_RUN, (tool_run_id,)).scalar()
            )
            decision = str(gate.get("decision") or "")
            facts["tool_run"]["decision"] = decision
            capability = gate.get("capability")
            lifetime = (
                0.0
                if not capability
                else float(connection.execute(LIFETIME, (tool_run_id,)).scalar() or 0.0)
            )
        except pg.DatabaseError as error:
            ledger.fail(
                "authorization",
                f"no capability could be minted for {claimed.task_label}: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None

        if not capability:
            self._unauthorized(ledger, connection, claimed, facts["tool_run"], gate, decision)
            return None
        ledger.hold(
            "authorization",
            f"{label} is {gate.get('risk_class')}/{decision} by {gate.get('rule')}",
        )
        door = agent.Egress(
            capability=str(capability),
            program_id=program_id,
            proxy_url=self.boundary.proxy_url,
            # Ticket 136: the same value the Tool run's args were opened with,
            # and read from the same place, so the answer a child gets back
            # names the Identity the door resolved rather than a second opinion
            # about which one this run should have spent.
            identity=claimed.identity_slot,
        )
        return tool_run_id, door, lifetime

    def _unauthorized(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        claimed: Claimed,
        tool_run: dict,
        gate: dict,
        decision: str,
    ) -> None:
        """A verdict that minted nothing, closed as what it was.

        `ask` is filed rather than treated as a refusal, by the same call the
        proxy uses: the answer is that a person decides this one, and a runtime
        that closed it as denied would have decided it -- in the direction that
        leaves no question behind. Ticket 206: filing it is also all this
        reports, because a pass that asked is a pass that worked.

        Every other verdict is a refusal and stays one. `forbidden` and a gate
        that answered nothing at all are both a Task this Program may not do,
        and an operator has a configuration to go and look at.
        """
        label = tool_run["label"]
        if decision == ASK:
            try:
                with connection.transaction():
                    _actor(connection)
                    connection.execute(CAUSE, (claimed.agent_run_id, claimed.task_id))
                    pending = str(
                        connection.execute(proxy.PARK_TOOL_RUN, (tool_run["id"],)).scalar()
                    )
            except pg.DatabaseError as error:
                ledger.fail(
                    "authorization",
                    f"the gate answered ask for {label} and the question could not "
                    f"be filed: {error}",
                    code=INTEGRITY_FAILED,
                    source="database",
                )
                return
            # Held and not failed -- ticket 206, the half of it inside the pass.
            # `outcome.AWAITING_DECISION` says what this is: the gate answered
            # `ask`, the question is filed, and nothing has gone wrong. Filing
            # it as a refused configuration made `_report` call the whole pass
            # `refused` and `rk run` exit 3, so a driver loop counted a campaign
            # asking a person toward its consecutive-fault streak and stopped
            # after three of them. The pass did claim a Task, dispatch it and
            # park it -- `closure.task_status` reads `parked` -- and that is
            # work, not a fault. The question is durable and the next pass
            # reports it under `pending_decisions`.
            #
            # `rk proxy send` still refuses on the same event and should: there
            # the operator asked for one response and this is the command
            # answering that it sent none.
            ledger.hold(
                "authorization",
                f"{label} is {gate.get('risk_class')}/ask by {gate.get('rule')}: "
                f"filed as {pending} for a human to answer",
            )
            return
        self._close(ledger, connection, claimed, tool_run, "denied")
        ledger.fail(
            "authorization",
            f"the gate answered {decision or 'nothing'} for {label}: "
            "no capability was minted and no child was started",
            code=INVALID_CONFIGURATION,
            source="database",
        )

    def _child(
        self,
        ledger: Ledger,
        claimed: Claimed,
        objective: str,
        mission: packet_module.Packet,
        door: agent.Egress,
        lifetime: float,
        program_id: str,
        runtime: pg.Settings | None,
    ) -> agent.AgentRunResult | None:
        """The one child, started inside the boundary with the one capability.

        No connection is passed to the launcher, which takes one only to record
        a startup refusal. It cannot have this one: the heartbeat is beating on
        it for as long as this call runs, and the single reason sharing it with
        that thread is safe is that nothing else touches it until the thread is
        joined. So the refusal is left to leave here as an exception, and the
        caller closes it a line later, on the other side of that join.

        `runtime` is the same connection's settings and travels for exactly that
        reason. A tool run the child asks for is opened, performed and filed by
        the supervisor while the child waits, which is a second writer -- so it
        opens a connection of its own from these rather than sharing the one the
        heartbeat has.
        """
        timeout = min(self.timeout, lifetime) if lifetime > 0 else self.timeout
        request = agent.AgentRunRequest(
            agent_run_id=claimed.agent_run_id,
            objective=objective,
            container=self.boundary,
            role=claimed.role,
            program_id=program_id,
            packet=mission,
            egress=door,
            timeout=timeout,
            subagent_cap=claimed.subagent_cap,
            token_cap=claimed.token_cap,
            # The connection alone is enough. Until 2026-08-22 this also
            # required a tool image and an Artifact store, which was the same
            # statement back when the supervisor answered only the two tool-run
            # verbs. It now answers `propose_test`, `propose_finding` and
            # `mint_callback` as well, and those need a database and nothing
            # else -- so an installation that named no image had no channel, and
            # every Test and every Finding a child ever proposed was answered
            # `no_tooling` by a supervisor that was never built. The image and
            # the store travel as they are, and `_Tools` refuses the two verbs
            # that need them.
            tooling=(
                None
                if runtime is None
                else agent.Tooling(
                    container=self.tools,
                    root=self.artifacts,
                    runtime=runtime,
                    state=self.state,
                    browser=self.browser,
                    authority=self.authority,
                    # Ticket 131's selection, carried rather than re-decided:
                    # `open_browser_run` checks a live Lease on whatever slot it
                    # is given, and the one this Agent run holds is the one the
                    # Task was claimed under. `""` is the anonymous selection
                    # and comes to `None`, which is a mission that acts as
                    # nobody rather than one that names a slot it does not hold.
                    identity_slot=claimed.identity_slot or None,
                )
            ),
        )
        try:
            result = self.launch(request)
        except isolation.Unavailable as error:
            ledger.fail(
                "boundary",
                f"the Agent boundary could not be provided: {error}",
                code=INVALID_CONFIGURATION,
                source=f"environment:{IMAGE}",
            )
            return None
        ledger.hold(
            "agent_run",
            f"{claimed.agent_run_label} stopped as {stopped_as(result.stop_reason)} "
            f"after {result.answers} answer(s), {result.mission_attempts} submission(s)",
        )
        return result

    @property
    def serves_tools(self) -> bool:
        """Whether a child's tool call can be answered on this machine at all.

        Both parts or neither: an image with nowhere to file what a run produced
        is a run that could start and could not be kept, so a machine holding
        one of them serves the same nothing as a machine holding neither.
        """
        return self.tools is not None and self.artifacts is not None

    def _refused(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        claimed: Claimed,
        refusal: agent.StartupRefusal,
    ) -> dict | None:
        """End an attempt this machine would not start, without charging it.

        Story 55 asks a startup refusal to return the Task to pending without
        consuming an attempt, and the ordinary closing cannot say that:
        `finish_task_attempt` settles the attempt as spent, which is the honest
        arithmetic for a child that ran and the wrong one for a child that was
        never started. Three refusals on one machine would otherwise abandon a
        Task as `attempts_exhausted` that nothing had yet attempted, and no
        Event would say what actually happened -- the refusal is a property of
        this host, and the Task is as ready as it was.

        `close_refusal` is what says it: the Task goes back to pending with its
        attempt returned, the bindings and Leases are released, and one
        redacted `startup.refused` Event records the phase and the vectors. Its
        `False` means there was nothing open left to close, and the answer to
        that is to let the ordinary closing run rather than to report a
        refunded attempt that nobody refunded.
        """
        ledger.refuse(
            "startup_assertion",
            f"the child was refused in {refusal.phase} by "
            f"{len(refusal.violations)} vector(s)",
            agent.diagnostics(refusal).violations,
        )
        try:
            closed = agent.close_refusal(
                connection, program_id, claimed.agent_run_id, refusal
            )
        except pg.DatabaseError as error:
            ledger.fail(
                "closure",
                f"the refused attempt on {claimed.task_label} could not be returned "
                f"to pending: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        if not closed:
            ledger.hold(
                "closure",
                f"{claimed.agent_run_label} was already closed when the refusal was "
                "recorded; the ordinary closing settles it",
            )
            return None
        ledger.hold(
            "closure",
            f"{claimed.task_label} is pending again, still on attempt "
            f"{claimed.attempts}, which the refusal did not spend",
        )
        return {"task_status": "pending", "startup_refusal": True}

    # -- what it produced --------------------------------------------------

    def _exchange(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        tool_run_id: str,
        facts: dict,
    ) -> str:
        """What the door recorded, and therefore how the Tool run closes."""
        rows = connection.execute(EXCHANGE, (program_id, tool_run_id)).rows
        if not rows:
            ledger.hold(
                "egress", "the capability was never spent; the door wrote no Receipt"
            )
            return "error"
        label, decision, status = str(rows[0][0]), str(rows[0][1]), rows[0][2]
        facts["receipt"] = {
            "label": label,
            "decision": decision,
            "status_code": None if status is None else int(status),
        }
        if decision != "allowed":
            # Ticket 177. A hold and not a failure. A child that asks for a verb
            # its Tool run does not carry is the boundary working, not the
            # operator misconfiguring it -- and `INVALID_CONFIGURATION` claimed
            # the second. The claim was load-bearing: a violation ends the pass
            # loop and `evaluation._repeat` then discards the whole repeat,
            # every variant of it, so one refused request threw away a
            # measurement that had already completed on the other half.
            #
            # Nothing quiet is introduced by this. A lane whose door cannot mint
            # a capability at all still fails loudly in `_authorize`, one call
            # earlier; what arrives here is a capability that was minted and a
            # request that did not match it, which is a fact about the run and
            # is on the Receipt either way. The Tool run still closes `denied`.
            #
            # Except where nothing refused it. `denied` is the word for a request
            # the door turned away; a target that did not answer is the target's
            # state, and this run's own `decision` column still says the gate
            # allowed it. A run whose every block is a target fault therefore
            # claims a refusal nobody made -- which is precisely what arm (i) of
            # `check_receipt_integrity` refuses, and that gate runs in `rk run`
            # before anything is written. So one unreachable host used to stop
            # every later run of the campaign until the row was corrected by
            # hand. `error` is the word 20260812T000000Z put on the rows this
            # produced before, and it is the word for them here.
            #
            # Read over every Receipt and not the newest, because arm (i) is:
            # one run that really was refused and separately met an unreachable
            # target closed as denied for a reason that is on the record.
            blocked = [row for row in rows if str(row[1]) == "blocked"]
            if blocked and all(str(row[3]) in proxy.TARGET_FAULT for row in blocked):
                ledger.hold(
                    "egress",
                    f"the target did not answer: {label} is {decision}"
                    f" for {rows[0][3]}",
                )
                return "error"
            ledger.hold(
                "egress",
                f"the door refused the child's request: {label} is {decision}",
            )
            return "denied"
        ledger.hold("egress", f"{label} records a {status} answer through the door")
        return "success"

    def _promote(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        claimed: Claimed,
        result: agent.AgentRunResult,
        facts: dict,
    ) -> None:
        """Stage what the child submitted, then promote what grounds.

        Two calls and not one, because they answer different questions and both
        answers are worth keeping: staging records what was claimed and why each
        element was dropped, and promotion records what of the rest became
        canonical. A child that submitted nothing is not a failure to report
        here -- the Task simply does not close, which `finish_task_attempt`
        decides from the absence of a promoted proposal.

        Staging is given no cause and needs none: 0030 files `proposals` as an
        audit table -- "the commit it becomes is what emits" -- so the write
        emits no Event for a cause to name. `promote_proposal` sets its own,
        inside the transaction that writes the Observations, which is the only
        place one would survive to be read.

        Topology is the third call and shares the second one's transaction:
        `record_receipt_topology` joins the address a Receipt pinned to the
        Domain that answered with it and the Application it serves, and both of
        those ends are rows the promotion has just written -- so a pass before
        it would find nothing to attach to.

        The fingerprint is the last call and shares that transaction too: 022
        asks for one after recon, and a promotion that committed without one
        would leave the Surface changed and nothing recording that it had.
        """
        if result.mission_result is None:
            ledger.hold(
                "proposal",
                f"{claimed.agent_run_label} submitted no result; nothing was staged",
            )
            return
        try:
            staged = proposal.stage(
                connection,
                proposal.Result(payload=dict(result.mission_result)),
                program_id=program_id,
                agent_run_id=claimed.agent_run_id,
                task_id=claimed.task_id,
            )
        except (pg.DatabaseError, ValueError, KeyError) as error:
            ledger.fail(
                "proposal",
                f"the submitted result could not be staged: {error}",
                code=INVALID_CONFIGURATION,
                source="agent",
            )
            return
        facts["proposal"] = {
            "id": staged.proposal_id,
            "label": staged.label,
            "status": staged.status,
            "completion": staged.completion,
            "drops": [
                {"element": drop.element_path, "reason": drop.reason}
                for drop in staged.drops
            ],
        }
        ledger.hold(
            "proposal",
            f"{staged.label} staged as {staged.completion} with {len(staged.drops)} drop(s)",
        )

        try:
            with connection.transaction():
                _actor(connection)
                connection.execute(CAUSE, (claimed.agent_run_id, claimed.task_id))
                promotion = proxy.as_object(
                    connection.execute(PROMOTE, (staged.proposal_id,)).scalar()
                )
                # Ticket 159, after the promotion for the reason the
                # docstring gives: the Domain and the Application the two edges
                # attach to are what promotion just wrote. Read out of Receipts
                # this harness wrote itself, which is why the runtime records it
                # rather than a child proposing what the door already pinned.
                topology = proxy.as_object(connection.execute(TOPOLOGY).scalar())
                # In the same transaction, because "after recon" means after
                # the rows exist and before anything reads them: a fingerprint
                # taken in a later transaction would be a fingerprint of
                # whatever else had happened by then. 022 makes it one Event per
                # Application rather than a side effect of the promotion.
                swept = proxy.as_object(
                    connection.execute(FINGERPRINT).scalar()
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "promotion",
                f"{staged.label} could not be promoted: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        observations = list(promotion.get("observations") or ())
        # The Tasks the promotion opened out of this result's suggestions, read
        # back rather than decided here: 142 puts that walk beside the other
        # five in SQL, and what this side owes is a report. Named in the pass so
        # that "the run suggested nothing" and "everything it suggested was
        # refused" do not read the same way to an operator, which is what they
        # did for the whole of the six hunts that stopped after two recon Tasks.
        opened = list(promotion.get("tasks") or ())
        facts["promotion"] = {
            "status": promotion.get("status"),
            "repeated": bool(promotion.get("repeated")),
            "observations": observations,
            "tasks": opened,
            "refused": int(promotion.get("refused") or 0),
        }
        facts["topology"] = {
            "hosts": int(topology.get("hosts") or 0),
            "resolves_to": int(topology.get("resolves_to") or 0),
            "serves": int(topology.get("serves") or 0),
        }
        facts["fingerprint"] = {
            "applications": int(swept.get("applications") or 0),
            "changed": int(swept.get("changed") or 0),
        }
        ledger.hold(
            "promotion",
            f"{staged.label} is {promotion.get('status')}: {len(observations)} "
            f"Observation(s) canonical, {len(opened)} Task(s) opened, "
            f"{promotion.get('refused')} refused",
        )
        ledger.hold(
            "topology",
            f"{facts['topology']['hosts']} Host(s) recorded, "
            f"{facts['topology']['resolves_to']} resolves_to and "
            f"{facts['topology']['serves']} serves edge(s) written",
        )
        ledger.hold(
            "fingerprint",
            f"{facts['fingerprint']['applications']} Application(s) fingerprinted, "
            f"{facts['fingerprint']['changed']} changed",
        )

    def _finish(
        self, ledger: Ledger, connection: pg.Connection, claimed: Claimed, facts: dict
    ) -> dict | None:
        """The one call that ends the attempt, whatever happened above it.

        Unless the attempt has already ended. A startup refusal closes its own
        run, because returning the Task with its attempt unspent is the one
        ending `finish_task_attempt` cannot express, and calling both would be
        two closings racing over one row -- the second of them charging the
        attempt the first had just given back.

        Its answer is the report's, not this runtime's opinion: the Task's
        status comes from whether a proposal was promoted, and a runtime that
        reported what it hoped for would be reporting the one thing the trigger
        exists to stop it deciding.

        The usage goes in the same call because the reservation this run was
        claimed under is settled off the row that call closes. Reported here and
        not written separately: a second statement afterwards is a window in
        which the reservation has already been given back against a run whose
        cost had not been recorded yet.
        """
        already = facts.get("closure")
        if already is not None:
            return already
        run = facts.get("agent_run") or {}
        stop_reason = run.get("stop_reason") or "error"
        try:
            with connection.transaction():
                _actor(connection)
                closure = proxy.as_object(
                    connection.execute(
                        FINISH,
                        (
                            claimed.agent_run_id,
                            stop_reason,
                            run.get("input_tokens"),
                            run.get("output_tokens"),
                            *charged(run),
                            run.get("attempt_profile"),
                        ),
                    ).scalar()
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "closure",
                f"the attempt on {claimed.task_label} could not be closed: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        ledger.hold(
            "closure",
            f"{claimed.task_label} is {closure.get('task_status')}; "
            f"{closure.get('runs_closed')} run(s), {closure.get('tool_runs_closed')} "
            f"tool run(s) and {closure.get('leases_released')} lease(s) closed",
        )
        return closure

    def _settle(
        self, ledger: Ledger, connection: pg.Connection, claimed: Claimed
    ) -> dict | None:
        """What the Playbooks this Task ran under produced, once the Task is settled.

        After the closing and in a transaction of its own, because it is a read
        of what the closing decided. `finish_task_attempt` is what says whether
        the Task is done, abandoned or back on the Slate, and this settlement
        turns on that word rather than on the runtime's opinion of how the
        attempt went -- so it cannot share the transaction that is still
        deciding it. Sharing one would also put a settlement failure in front of
        the closing, which is the one call an attempt must not lose.

        A Task back on the Slate is answered and not written: it will be run
        again under these same rows, and a Playbook retired for a container that
        would not start is retired for the rest of the hunt. A settled Task gets
        `produced` on every kept Playbook that declares a class this subject now
        carries a hypothesis on and `exhausted` on the rest, and `exhausted` is
        the half worth having -- it is the only memory the next selection has
        that this Playbook has already been tried against this subject.
        """
        try:
            with connection.transaction():
                _actor(connection)
                settled = proxy.as_object(
                    connection.execute(SETTLE_SELECTION, (claimed.task_id,)).scalar()
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "selections",
                f"what {claimed.task_label} ran under could not be settled: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        if settled.get("settled"):
            ledger.hold(
                "selections",
                f"{claimed.task_label} is {settled.get('task_status')}: "
                f"{settled.get('produced')} Playbook(s) produced and "
                f"{settled.get('exhausted')} are exhausted on this subject",
            )
        else:
            ledger.hold(
                "selections",
                f"{claimed.task_label} is {settled.get('task_status')} and may be run "
                "again; its Playbook selection stays open",
            )
        return settled


def _actor(connection: pg.Connection) -> None:
    """Who the database records as writing. Transaction-local by construction."""
    connection.execute("SELECT set_actor('runtime', $1)", (program.ACTOR,))


def _body_allowed(selected: Sequence[playbook_module.Projection]) -> bool:
    """Whether this attempt may put bytes in front of the target's parser.

    A body is framing, not an effect. GraphQL selections, JSON filters, gRPC
    frames and form-encoded searches can all be readings even though their
    protocol puts bytes after the headers. `bb:effects` continues to state what
    a Playbook may change and continues to feed the risk floor; using it as a
    body switch would silently make those read-only techniques impossible.

    The grant still comes from the selection rather than from the later call:
    selecting at least one Playbook opens the attempt for the request shapes its
    procedure may require. The door records that grant on the Tool run and
    refuses a body when no Playbook was selected.

    No Playbook at all is a run under the Task's own instructions and nothing
    else, and that is opened read-only. A corpus that said nothing about this
    subject has not said that bytes may be sent to it, and the honest reading of
    silence on a permission is that it was not granted.
    """
    return bool(selected)


def _rotation(value: object) -> Mapping[str, object] | None:
    """The rotation payload the open answered with, or nothing.

    A key of a jsonb object arrives here already decoded, so the ordinary answer
    is a mapping. Anything else is a payload this runtime does not recognise,
    and the honest reading of that is that nothing it can report was closed --
    the Event is written and the campaign is rotated either way.
    """
    return value if isinstance(value, Mapping) else None


def _slate_entry(row: Mapping[str, object]) -> dict:
    """One entry of the offered Slate, renamed for whoever is choosing.

    `factors` arrives as the text of a jsonb value -- this client decodes
    booleans, integers and floats and leaves everything else exactly as the
    server sent it -- so it is parsed here rather than handed on as a string a
    reader would have to parse a second time. Everything else is passed through:
    a numeric that keeps its own digits is more faithful than a float that
    rounds them, and the expiry is already the timestamp the server rendered.
    """
    return {
        "ordinal": row["ordinal"],
        "task": row["task_label"],
        "kind": row["kind"],
        "subject": row["subject_label"],
        "priority": row["priority"],
        "factors": json.loads(str(row["factors"])),
        "entitled": row["entitled"],
        "expires_at": row["expires_at"],
    }


def _due_retest(row: Sequence[object]) -> dict:
    """One refutation the lane has made due, as `v_negative_knowledge` renders it.

    Positionally, because the view is what names the columns and this reads them
    back in the order `DUE_RETESTS` asks for them. `retest` is a jsonb object the
    view assembles -- what made the record due, which delta did it and whether
    the claim went back to `testable` -- and it is parsed here for the reason the
    Slate's `factors` is: a report that handed on the server's text would hand a
    reader something they have to parse a second time.
    """
    return {
        "hypothesis": row[0],
        "hypothesis_status": row[1],
        "subject": row[2],
        "property_class": row[3],
        "application": row[4],
        "reason": row[5],
        "retest": json.loads(str(row[6])) if row[6] is not None else None,
    }


def _surface_move(row: Sequence[object]) -> dict:
    """One recorded Surface delta, as `v_surface_deltas` renders it.

    `subject` is null where the delta's key names no single row -- a removed
    element, or a key two rows answer to -- and it is passed through as null
    rather than filled in, because 022 records the disappearance and reading it
    as a subject would be a guess.
    """
    return {
        "application": row[0],
        "kind": row[1],
        "subject": row[2],
        "subject_key": row[3],
        "property_classes": json.loads(str(row[4])),
        "detected_at": row[5],
    }
