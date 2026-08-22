"""The only module in this application that constructs the Agent SDK.

One module, so the startup assertion has one seam. `tests/test_agent.py` walks
the source tree and fails if any other module imports `claude_agent_sdk`: an
SDK constructed somewhere else would be an Agent run started without crossing
`agent_run`, and the assertion would be a check on one launch path out of two.

This runs as a child process -- `python -m redkraken._launch`, one job document
on standard input, inside the container `redkraken.isolation` verifies -- for a
reason that is not stylistic. The assertion has to be made against the
environment and the filesystem the child *actually* got, and the only way to be
sure nothing leaked in is to build them from a list out there and then measure
them here, in the process that will use them. It is also why the launch
directory is created here rather than by the supervisor: the supervisor's
filesystem is not this one, so a directory it made would be a directory this
child could not be given.

The order is the whole point. Facts, then one options value, then the pre-spawn
assertion against that value, then the transport built from the same value,
then the init message, and only then a tool the model can call. Every one of
those steps is a gate on the next; a refusal at any of them leaves the steps
after it un-run rather than undone.

The import below is the application's only third-party one, and it is
deliberately not a declared dependency (see `pyproject.toml` and
`doctor.REQUIRED_DISTRIBUTIONS`). What this runtime requires is not a package
but a *pair* -- an SDK version and the CLI version it bundles, held in
`_startup.KNOWN_RUNTIME` -- and a requirement specifier cannot name the second
half of that. Declaring the first
half would state the same fact twice, in a weaker form that a resolver is free
to satisfy with a pair nothing has measured. So the requirement is enforced
where it is decidable: an SDK that is absent, or present at another version, is
an unmeasured runtime and refuses at the assertion.
"""

from __future__ import annotations

import asyncio
import http.client
import importlib.metadata
import json
import os
import ssl
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn

from redkraken import agent, capsule, isolation, packet, proxy, roster, scope, tls


try:
    import claude_agent_sdk
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        ResultMessage,
        SystemMessage,
        create_sdk_mcp_server,
        query,
        tool,
    )
except ImportError:
    # Not an error here. An SDK that is not installed is an unmeasured runtime
    # pair, which is a refusal the assertion already knows how to make -- and
    # making it there rather than raising here keeps one refusal path.
    claude_agent_sdk = None


#: The distribution the runtime pair is measured against.
DISTRIBUTION = "claude-agent-sdk"

#: Where the SDK keeps the CLI it was published with.
BUNDLED = ("_bundled", "claude")

#: The messages that may reach the runtime before init has been corroborated.
#: A positive list, because the pair is pinned: on a measured runtime the set
#: of things the transport can emit is fixed, so anything not named here
#: arriving first is an Agent run that did work before it was assessed.
BEFORE_INIT = ("RateLimitEvent",)

#: How the CLI announces itself, and the subtype the announcement must carry.
INIT = "init"

#: Why an init message was never read: something else was produced first, or
#: the run ended without the CLI ever announcing itself.
PREMATURE = "first_message"
ABSENT = "absent"

#: What the child writes when it refuses, on standard error, as one line.
REFUSAL = "startup_refusal"

#: How much of the final answer crosses back. A bound rather than a budget: the
#: result document travels through a pipe and this is proof the run finished,
#: not a transcript. What is kept of it is Promotion's business, not this pipe's.
ANSWER = 1500

#: How much of one response's header list a child may read. The body has had a
#: ceiling since it was first answered and a header list without one is the same
#: hole a second time: it is a document the target wrote, arriving in a model's
#: context, at whatever length the target chose, and a target that would rather
#: fill this run's context than be measured by it needs only to answer with a
#: thousand headers. The same 4096 bytes the body gets, because the two are the
#: same kind of bound on the same kind of reading -- and it is more than an
#: honest response spends on headers, so what it cuts is the answer that was
#: already unusual. Nothing is lost when it cuts: the exact list of every
#: exchange is in the sealed wire Artifact the Receipt already names, which is
#: where a reading that needs all of it goes.
HEADERS_EXCERPT = 4096

#: Why a request tool call reached no target. Tokens rather than prose, for the
#: same reason the door's decision header is a token: the model reads one of
#: these and the runtime reads the same one out of the transcript, and a reason
#: reworded later would silently change what either concluded.
NO_CAPABILITY = "no_capability"
UNUSABLE_TARGET = "unusable_target"
DOOR_UNREACHABLE = "door_unreachable"

#: And why a tool call reached no supervisor. The other three are about a run
#: that had no capability to spend; this one is about a run whose installation
#: described no tool image and no store, which is the same kind of fact and the
#: same kind of answer -- a refusal the model can read, rather than a tool that
#: is missing and cannot be asked about.
NO_TOOLING = "no_tooling"

#: And why a Finding proposal was not carried to the runtime at all. The same
#: kind of token as the three above, because it is the same kind of fact: the
#: run asked for something the runtime will not do for it, and the honest answer
#: is the reason rather than silence or an exception.
SPENT_PROPOSALS = "proposals_spent"

#: What `open_finding` calls the outcome of a proposal it would not open a
#: Finding from. Held here because it is the word this side counts on, and a
#: word spelled out at the counting site would be a second statement of the
#: database's own vocabulary that could come to disagree with it.
REFUSED = "refused"

#: How many refused proposals one Agent run may make before the tool stops
#: carrying them. Three, and the number comes from the refusal itself rather
#: than from taste: `rk2_finding_refusal` is eight arms deep and exactly two of
#: them are about the proposal rather than about the evidence behind it -- the
#: word is not in the vocabulary, and the title is empty. Those two are the only
#: refusals a child can do anything about by asking again, so three attempts is
#: one more than the number of mistakes that are correctable, and a fourth
#: refusal is a run repeating itself.
#:
#: Refused attempts are what is counted, and created and merged ones are not,
#: because they are different acts. A refusal costs the Program a
#: `finding_proposals` row and the run a turn's worth of its own context and
#: leaves nothing behind that anybody wanted; a merge is a second claim landing
#: on a cell that already holds a Finding, which is a hunter that got it right
#: twice, and it is the outcome that says two independent claims about one cell
#: both held. Counting a merge against this ceiling would make the run that
#: found the most into the run that is cut off first.
REFUSED_PROPOSALS = 3


class Closed(RuntimeError):
    """A tool was called while the runtime's tool surface was not open."""


class Surface:
    """The tool surface, and the count that makes `exactly once` checkable.

    A flag would answer "is it open"; the criterion is that it opens once, and
    the difference matters -- a surface reopened by a second init message is a
    child whose authentication was corroborated twice and believed both
    times. So opening increments, and being open means having opened exactly
    once.
    """

    def __init__(self) -> None:
        self.opened = 0
        self.served: list[str] = []

    @property
    def ready(self) -> bool:
        return self.opened == 1

    def open(self) -> None:
        self.opened += 1

    def serve(self, name: str) -> None:
        if not self.ready:
            raise Closed(f"{name} was called before the runtime's tool surface opened")
        self.served.append(name)


def runtime_facts() -> dict[str, str | None]:
    """The SDK version, the CLI it bundles and the executable that would run.

    Resolved rather than configured. Each one is read from the installed
    package, so a launch is measured against what is on this machine and not
    against what a caller says is on it. Anything unreadable stays `None` and
    becomes an unmeasured runtime in the assertion.
    """
    facts: dict[str, str | None] = {"sdk_version": None, "cli_version": None, "cli_path": None}
    if claude_agent_sdk is None:
        return facts
    try:
        facts["sdk_version"] = importlib.metadata.version(DISTRIBUTION)
    except (importlib.metadata.PackageNotFoundError, ValueError):
        pass
    try:
        from claude_agent_sdk import _cli_version

        facts["cli_version"] = _cli_version.__cli_version__
    except (AttributeError, ImportError):
        pass
    package = getattr(claude_agent_sdk, "__file__", None)
    try:
        if package:
            facts["cli_path"] = str(Path(package).resolve().parent.joinpath(*BUNDLED))
    except (OSError, TypeError, ValueError):
        pass
    return facts


class Submission:
    """The one result a run may submit, and the count of the tries.

    One, because the Spec says one: "Agents submit one Mission result". A
    second submission is not merged and does not overwrite -- the first is what
    the run proposed, and a later contradiction of it is the run arguing with
    its own output. The attempt is still counted, so a model that tried twice
    is distinguishable from one that submitted once.

    Named for what it holds rather than for the run. `CONTEXT.md` gives
    "Mission" to the packet and tells the rest of us to avoid it -- "a payload,
    not a lifecycle" -- and this is the lifecycle side: one latch and one
    counter. The `mission_result` key it fills keeps the word because the tool
    it comes from is `submit_mission_result` and renaming half of that pair
    would leave a key nothing on the wire is called.
    """

    def __init__(self) -> None:
        self.result: dict | None = None
        self.attempts = 0

    @property
    def submitted(self) -> bool:
        return self.result is not None

    def submit(self, arguments: Mapping[str, object]) -> dict:
        self.attempts += 1
        if self.result is not None:
            return {
                "accepted": False,
                "reason": "already_submitted",
                "attempts": self.attempts,
            }
        self.result = dict(arguments)
        return {
            "accepted": True,
            "attempts": self.attempts,
            # Not "staged". Nothing is staged yet: the row is written by the
            # runtime after this process ends and after its provenance is
            # checked, and telling the model otherwise would be this handler
            # promising something it is not the one to do.
            "note": "received; staging and provenance are the runtime's step",
        }


class Choice:
    """The Task an orchestrator session named, and the tries it took to name it.

    Superseding rather than latching, and that is the difference from
    `Submission` above: a result is a claim about what happened and the first
    one stands, while a choice is a preference and the current one is whatever
    was said last. `pick_task` in the database supersedes for the same reason --
    it calls `supersede_pick` before it writes -- so a session that changes its
    mind gets the same answer here as it would there.

    Membership is checked and does not decide. A label the offered Slate does
    not carry is answered as refused, which is what lets the model correct
    itself while it is still running, and it is still what comes back: the
    Slate this process holds is a copy that travelled in a job document, and
    the authority on what may still be picked is the transaction that picks it.
    Refusing here as well would be this process deciding an outcome the
    database is the only one able to decide.
    """

    def __init__(self, offered: Sequence[Mapping[str, object]] = ()) -> None:
        self.entries = [dict(entry) for entry in offered]
        self.offered = [
            str(entry["task"]) for entry in self.entries if entry.get("task")
        ]
        self.task: str | None = None
        self.attempts = 0

    def pick(self, arguments: Mapping[str, object]) -> dict:
        self.attempts += 1
        label = arguments.get("task_label")
        if not isinstance(label, str) or not label:
            return {
                "accepted": False,
                "reason": "no_task_label",
                "attempts": self.attempts,
            }
        self.task = label
        if label not in self.offered:
            return {
                "accepted": False,
                "reason": "off_slate",
                "offered": list(self.offered),
                "attempts": self.attempts,
                "note": "the runtime will refuse this; pick one of the offered tasks",
            }
        return {
            "accepted": True,
            "task": label,
            "attempts": self.attempts,
            # Not "claimed". The claim is a transaction the runtime opens after
            # this process ends, and it re-checks every condition the offer was
            # made under -- so a pick that is accepted here is a pick that may
            # still be refused there, and saying otherwise would be this handler
            # promising a Task nothing has taken yet.
            "note": "recorded; the claim and its revalidation are the runtime's step",
        }


class Judgement:
    """The one packet a validator session may read, and the one answer it gives.

    Latching rather than superseding, which is `Submission`'s side of the
    distinction `Choice` is on the other side of: a verdict is a claim about
    evidence and the first one stands. A session that answers `insufficient` and
    then, having thought about it more, `confirmed`, is a session arguing with
    itself about a document that did not change in between -- and the second
    answer is the one produced by having already produced the first, which is
    exactly the reasoning the blindness exists to keep out.

    The packet is held rather than fetched. There is no database on this side of
    the boundary, so what the session may consider is what the job document
    carried: `rk2_validation_packet` selected it through a column allowlist a
    migration states, and this class hands over that document unchanged.

    The label is checked and does not decide. A Finding this session was not
    given is answered as refused with the one it was given named, so a model
    that misread its packet can correct itself while it is still running -- and
    the answer still crosses back, because `record_verdict` re-checks every
    condition the packet was served under and is the only thing able to decide
    what became of it.
    """

    def __init__(self, packet: Mapping[str, object] | None = None) -> None:
        self.packet = dict(packet or {})
        self.answer: dict | None = None
        self.attempts = 0
        self.reads = 0

    @property
    def finding(self) -> str | None:
        stated = self.packet.get("finding")
        if not isinstance(stated, Mapping):
            return None
        label = stated.get("label")
        return label if isinstance(label, str) and label else None

    def read(self, arguments: Mapping[str, object]) -> dict:
        self.reads += 1
        asked = arguments.get("finding_label")
        if self.finding is None:
            return {"served": False, "reason": "no_packet"}
        if asked != self.finding:
            return {"served": False, "reason": "other_finding", "finding": self.finding}
        return {"served": True, "finding": self.finding, "packet": self.packet}

    def judge(self, arguments: Mapping[str, object]) -> dict:
        self.attempts += 1
        if self.answer is not None:
            return {"accepted": False, "reason": "already_judged", "attempts": self.attempts}
        if arguments.get("finding_label") != self.finding:
            return {
                "accepted": False,
                "reason": "other_finding",
                "finding": self.finding,
                "attempts": self.attempts,
            }
        failed = arguments.get("failed_assertion_ids") or []
        self.answer = {
            "finding_label": self.finding,
            "verdict": str(arguments.get("verdict") or ""),
            "failed_assertion_ids": [str(named) for named in failed],
        }
        return {
            "accepted": True,
            "attempts": self.attempts,
            # Not "recorded". The row and the Finding's status are one
            # transaction the runtime opens after this process ends, and it
            # rebuilds the packet first: an answer accepted here is one that
            # may still be filed as stale there.
            "note": "received; the row and what the Finding becomes are the runtime's step",
        }


class Channel:
    """The child's half of the pipe it was launched on, used as a question.

    Everything else this module serves is answered from the job document,
    because the container's one network reaches the capability proxy and a
    handler cannot fetch what the runtime did not send.  A tool run cannot be:
    it starts a second container and writes a row, and this process has neither
    a container runtime nor a database.  So it is asked for, on the two file
    descriptors the launch already has -- one object out under `rk2_call`, one
    object back under `rk2_answer`, one line each.

    The lock is not about speed.  Two calls in flight would put two questions on
    one pipe and take the answers in whatever order they arrived, so one call
    holds the pipe until its own answer comes back, and the `id` on both halves
    is what makes that checkable rather than assumed.  The read is blocking, so
    every caller reaches it through a thread: the handlers are on an event loop,
    and a supervisor taking twenty seconds to run a tool would otherwise stall
    every other thing the session has in flight.

    A closed pipe is answered, not raised.  If the supervisor is gone there is
    nothing left to ask and nothing this side can do about it -- but a handler
    that raised would end the turn with a traceback, and a handler that answers
    a refusal lets the model do something else with what is left of the run.
    """

    def __init__(self, out=None, source=None) -> None:
        self._out = sys.stdout if out is None else out
        self._in = sys.stdin if source is None else source
        self._lock = threading.Lock()
        self._calls = 0

    def call(self, verb: str, arguments: Mapping[str, object]) -> Mapping[str, object]:
        """Ask for one thing and wait for the answer to that thing.

        The verb is written last so it is the verb: the arguments are a model's,
        and a call carrying a `verb` of its own must not be able to become a
        call to something else.  The gate refuses an argument no contract
        declares long before this and that is the check; this is one line that
        makes it not the only one.
        """
        with self._lock:
            self._calls += 1
            identifier = self._calls
            frame = {isolation.CALL: {**dict(arguments), "verb": verb}, "id": identifier}
            self._out.write(json.dumps(frame) + "\n")
            self._out.flush()
            while True:
                line = self._in.readline()
                if not line:
                    return {
                        "served": False,
                        "reason": isolation.UNANSWERED,
                        "detail": "the supervisor closed the channel",
                    }
                try:
                    document = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(document, dict) or document.get("id") != identifier:
                    continue
                answered = document.get(isolation.ANSWER)
                if isinstance(answered, Mapping):
                    return answered
                return {
                    "served": False,
                    "reason": isolation.UNANSWERED,
                    "detail": "the supervisor answered with no document",
                }


class Proposal:
    """The Findings this run asked for, and the refusals it has left to spend.

    The one request an executing role makes that is answered while it is still
    running, and the difference from a pick or a verdict is the reason it is:
    those two are preferences the runtime re-decides afterwards, and this is a
    question about rows that already exist and already settle it. `open_finding`
    reads the claim, the run that settled it and the transition between them,
    all three written by the runtime, and answers `created`, `merged` or
    `refused` with the sentence saying why. Nothing this object holds could
    make that answer come out differently, which is why it asks rather than
    deciding.

    What it does decide is how many times it will ask. A refused proposal costs
    the Program an audit row and the run a turn of its own context, and a model
    that has convinced itself will spend the whole run on the same claim -- so
    the count of refusals is kept here and `REFUSED_PROPOSALS` is where asking
    stops. A created or merged proposal is not counted, because it is not the
    thing being bounded: what a ceiling on successes would bound is how much
    one run may find.

    Asking is blocking, because it is the same pipe a tool run goes down, so
    every caller reaches this through a thread for the reason `Channel` gives.
    """

    def __init__(self, channel: Channel | None = None) -> None:
        self._channel = channel
        self.attempts = 0
        self.refused = 0

    def ask(self, arguments: Mapping[str, object]) -> dict:
        """Carry one proposal to the runtime, or say why it was not carried.

        The three declared fields and nothing beside them. Which Agent run and
        which Program this proposal belongs to are the supervisor's to fill in:
        both are decisions that were taken when this run was opened, and a
        child that named either would be naming its own provenance.
        """
        self.attempts += 1
        if self.refused >= REFUSED_PROPOSALS:
            return {
                "served": False,
                "reason": SPENT_PROPOSALS,
                "attempts": self.attempts,
                "refused": self.refused,
                "detail": (
                    f"{self.refused} proposals of this run were refused, which is all it "
                    "may spend; this one was not carried to the runtime"
                ),
            }
        if self._channel is None:
            return {
                "served": False,
                "reason": NO_TOOLING,
                "attempts": self.attempts,
                "detail": (
                    "this run was started with no supervisor to ask; nothing was proposed"
                ),
            }
        answered = dict(
            self._channel.call(
                f"mcp__{agent.SERVER}__propose_finding",
                {
                    "hypothesis_label": str(arguments.get("hypothesis_label") or ""),
                    "vulnerability_class": str(arguments.get("vulnerability_class") or ""),
                    "title": str(arguments.get("title") or ""),
                },
            )
        )
        # Only the database's own word for it counts. A supervisor that could
        # not be reached, or that would not serve the verb, has not refused a
        # proposal -- nobody looked at it -- and charging the run for that would
        # spend a ceiling on the runtime's own trouble.
        if answered.get("outcome") == REFUSED:
            self.refused += 1
        return answered


#: What each served tool tells the model it is for. One sentence each, and each
#: one says the bound out loud: a description that promised the whole Program
#: would be a description of a tool this runtime does not have.
DESCRIPTIONS = {
    "get_attack_surface": (
        "List this Program's known Entities -- hosts, endpoints, parameters and the "
        "rest -- from the bounded packet this run was started with. Returns record "
        "revisions, digests, counts and omission markers."
    ),
    "get_hypotheses": (
        "List this Program's Hypotheses, optionally for one subject Entity or one "
        "status, from the bounded packet this run was started with."
    ),
    "get_evidence": (
        "List the evidence edges tying Observations to one Hypothesis or one Finding, "
        "with each Observation's provenance label."
    ),
    "get_receipts": (
        "With no labels, list the Receipts this run's packet reached. With labels, "
        "fetch those. A label that is not in this run's packet comes back as an "
        "omission marker rather than as an error."
    ),
    "get_artifact": (
        "With no label, list the Artifacts this run's packet reached. With one, fetch "
        "that Artifact -- its metadata and, where its head was staged as text, a byte "
        "range of it. The hash is reported, never asked for. Whole large Artifacts "
        "are analysed by a tool run, not read into this context."
    ),
    "get_slate": (
        "List the Tasks this decision may choose between: their kind, subject, "
        "priority, the factors behind it and when the offer stops being good. It is "
        "the whole of the choice -- what the runtime did not offer is not yours to "
        "reach and not yours to name."
    ),
    "pick_task": (
        "Name the one offered Task to run next, by its label. Calling it again "
        "replaces your previous answer; not calling it at all leaves the choice to "
        "the runtime, which takes the first entry that still holds. The runtime "
        "re-checks the Task before it claims it and refuses a label this Slate no "
        "longer carries."
    ),
    "get_validation_packet": (
        "Fetch the one validation packet this session was started with: the Finding "
        "as facts, the claim it rests on, the Test's actions and assertions, both "
        "Test runs with their Receipts, and the Artifacts they name by hash. It is "
        "the whole of what you may consider. There is no other read, no way to reach "
        "the reasoning that produced the Finding, and nothing here is prose somebody "
        "wrote to persuade you."
    ),
    "submit_verdict": (
        "Answer the one Finding you were given: confirmed if the packet shows the "
        "behaviour reproducing, refuted if it shows it does not, insufficient if the "
        "packet cannot tell you either way. Name the identifiers of the assertions "
        "that failed. Calling it again is refused; the first answer is the one that "
        "stands. Your answer is an input -- the runtime rebuilds the packet, checks "
        "it has not changed, and the database decides what the Finding becomes."
    ),
    "http_request": (
        "Send one HTTP request to a target through the capability proxy, which "
        "decides it against this Program's scope and writes the Receipt and the "
        "response Artifact. Answers the status, the Receipt label to cite, the "
        "target's response headers and a bounded excerpt of the body; both the "
        "headers and the body are bounded excerpts of the transcript that Receipt "
        "names, so an Observation about a header cites that same Receipt. Headers "
        "carrying credentials the target issued are not among them. A refusal "
        "names the door's decision rather than pretending the request happened.\n\n"
        "A body is the bytes you want sent after the headers, spelled exactly, "
        "with their Content-Type given as a header. Do not set Content-Length: "
        "the door measures the bytes it forwards and states that number itself, "
        "and a chunked request body is refused rather than re-framed. Whether "
        "this run may send a body at all was decided when it was opened, from "
        "the effects the Playbooks chosen for its Task declare; a run whose "
        "reading is entirely read-only is refused a body at the door, with a "
        "Receipt saying so."
    ),
    # The element lists stay open -- `roster.OPEN_ARGUMENTS` says why -- so this
    # sentence is the only place a child is told which fields promotion reads
    # out of them. A field name it has to guess is a drop row with
    # `malformed_field` on it and no way for the model to learn the spelling.
    "submit_mission_result": (
        "Submit this run's one result: proposed Entities, Relationships, "
        "Hypotheses, Observations with the Receipt or Tool Run each cites, evidence "
        "edges, suggested Tasks and a completion claim. It is staging data. The "
        "runtime checks provenance and decides what becomes canonical; nothing here "
        "is true because it was submitted.\n\n"
        "Every element cites its evidence with exactly one of receipt_label or "
        "tool_run_label. An entity carries type and the typed fields of that type: "
        "domain fqdn and wildcard; host hostname and address; service parent_ref "
        "with port and protocol; application base_url and kind; endpoint parent_ref "
        "with method and path_template; parameter parent_ref with name and "
        "location; technology name and version; identity slot_name. A service, an "
        "endpoint and a parameter name their containment parent by parent_ref or "
        "parent_label; give an entity a ref of your own and later elements can "
        "point at it by that name before it has a label. A relationship carries "
        "type with src_ref or src_label and dst_ref or dst_label, and containment "
        "is never one of them."
    ),
    "run_tool": (
        "Run one registered offline tool over Artifacts this Program already holds, "
        "and get back the Tool Run label to cite, what it exited with and the first "
        "few kilobytes of what it printed. Name each argument the tool declares; an "
        "argument that takes an Artifact takes its label, never its hash. The whole "
        "output is filed as an Artifact of this Program -- the excerpt here is proof "
        "of what ran, not the place to read a large answer."
    ),
    "propose_finding": (
        "Ask the runtime to open a Finding from one Hypothesis of this Program that "
        "has reached supported. Name the claim by its label, a vulnerability class "
        "from this harness's vocabulary, and a title a person will read. You do not "
        "name the run that settled the claim: the claim names it, and no other run "
        "would be accepted.\n\n"
        "The runtime decides. It reads the claim, the replay that settled it and the "
        "transition between them -- rows it wrote itself, none of which you can "
        "change by asking again -- and answers created, merged or refused. Merged "
        "means a Finding is already open on this cell and your claim was added to "
        "it, which is a result and not a rejection. Refused comes back as one "
        "sentence saying what is wrong; only two of the things it can say are about "
        "your proposal rather than about the evidence, so a refusal about the "
        "evidence is not worth re-sending. This run may have three proposals refused "
        "and no more, after which the tool stops carrying them."
    ),
    "run_skill_script": (
        "Run one script that ships with a Skill you hold, over Artifacts this Program "
        "already holds. Name the Skill, the script's filename, and each argument the "
        "script declares by the label of the Artifact it reads. The script is handed "
        "each Artifact whole -- nothing is truncated on the way in -- and what comes "
        "back is the Tool Run label to cite, what it exited with and the first few "
        "kilobytes of what it printed, with the whole of it filed as an Artifact."
    ),
}


def server(
    surface: Surface,
    reader: packet.Reader,
    submission: Submission,
    door: agent.Egress | None = None,
    choice: Choice | None = None,
    judgement: Judgement | None = None,
    channel: Channel | None = None,
    proposal: Proposal | None = None,
):
    """Five reads, a request, two tool runs, a result, a Finding, a choice, a judgement.

    Every handler goes through `surface.serve` first, which refuses while the
    surface is not open. That is ticket 16's property and it is load-bearing
    here for a new reason: a state read answered before init would be a read
    served by a child whose authentication this runtime had not corroborated.

    The schemas come from `roster.CONTRACTS` rather than from here. They are
    closed -- `additionalProperties: false` -- and the CLI validates against
    them before `PreToolUse` runs, so an argument the roster does not declare
    is refused before the gate and long before a handler. The gate checks the
    same properties again afterwards. Two checks of one statement, which is the
    arrangement, rather than two statements.

    Every tool is built for every run, including the two only an orchestrator
    may call. What a run may reach is the roster's allowlist and not this list,
    for the reason `net.request` is served unconditionally: an allowlist that
    varied with the job would be an allowlist the startup assertion could not
    check against the roster. A worker's Slate is empty, which is the honest
    answer for a run that was offered no choice.
    """
    reads = {
        "get_attack_surface": reader.attack_surface,
        "get_hypotheses": reader.hypotheses,
        "get_evidence": reader.evidence,
        "get_receipts": reader.receipts,
        "get_artifact": reader.artifact,
    }
    picking = Choice() if choice is None else choice
    judging = Judgement() if judgement is None else judgement
    # Built from the same channel the tool runs go down when the caller does not
    # hand one over, because it is the same question asked of the same party:
    # this process has no database, and what it can do is ask the side that has
    # one. A run with no supervisor gets a `Proposal` that says so.
    proposing = Proposal(channel) if proposal is None else proposal
    tools = [_read(surface, name, answer) for name, answer in reads.items()]
    tools.append(_request(surface, door))
    tools.append(_tool_run(surface, channel, "run_tool"))
    tools.append(_tool_run(surface, channel, "run_skill_script"))
    tools.append(_propose(surface, submission))
    tools.append(_finding(surface, proposing))
    tools.append(_slate(surface, picking))
    tools.append(_pick(surface, picking))
    tools.append(_packet(surface, judging))
    tools.append(_judge(surface, judging))
    return create_sdk_mcp_server(name=agent.SERVER, version=agent.SERVER_VERSION, tools=tools)


def _read(surface: Surface, name: str, answer):
    """One state read, wired to the reader method that answers it.

    `range` is the one wire name that is a Python builtin, so it is renamed on
    the way in. Renaming it in the contract instead would have made the roster
    describe a tool by a name the tool is not served under.
    """

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        given = dict(arguments or {})
        if "range" in given:
            given["span"] = given.pop("range")
        return _content(answer(**given))

    return handler


def _request(surface: Surface, door: agent.Egress | None):
    """The one call that leaves the boundary, spent through the door or refused.

    Blocking work on a thread, because the request is a socket and the caller is
    an event loop: a synchronous exchange run inline would stall every other
    thing the session has in flight for as long as the target takes to answer.

    Nothing here decides whether the request is allowed. The capability was
    minted against a Tool run by the runtime, the door re-decides the request
    that actually arrives against live policy, and this handler's whole job is
    to carry one to the other and report what came back -- including a refusal,
    which is reported as a refusal rather than as a failure to reach anything.
    """
    name = "http_request"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        given = dict(arguments or {})
        if door is None:
            return _content(
                {
                    "served": False,
                    "reason": NO_CAPABILITY,
                    "detail": "this run was started with no capability; no request was sent",
                }
            )
        return _content(
            await asyncio.to_thread(
                _spend,
                door,
                str(given.get("url") or ""),
                str(given.get("method") or "GET"),
                _headers(given.get("headers")),
                _body(given.get("body")),
            )
        )

    return handler


def _tool_run(surface: Surface, channel: Channel | None, name: str):
    """One registered program, run by the supervisor and reported back here.

    Both tool-run tools are this function, because they differ in exactly one
    thing: which registered row a child names, and by what.  What happens to the
    call is the same either way -- it crosses the channel unchanged, the
    supervisor opens the run, starts the container and files what it produced,
    and what comes back is the answer to the call that was made.

    Nothing here decides whether the run may happen.  The roster refused every
    call that does not fit its contract before this handler was reached, and
    `open_offline_tool_run` decides the call that actually arrives against the
    registry, the Program's Halt state and the role's permission.  This
    handler's whole job is to carry one to the other, including a refusal, which
    is reported as a refusal rather than as a tool that failed.

    On a thread for `_request`'s reason: the exchange is blocking and the caller
    is an event loop.
    """

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        if channel is None:
            return _content(
                {
                    "served": False,
                    "reason": NO_TOOLING,
                    "detail": "this run was started with no tool image; nothing was run",
                }
            )
        return _content(
            await asyncio.to_thread(
                channel.call, f"mcp__{agent.SERVER}__{name}", dict(arguments or {})
            )
        )

    return handler


def _spend(
    door: agent.Egress,
    url: str,
    method: str,
    headers: Mapping[str, str],
    body: bytes = b"",
) -> dict:
    """One exchange through the door, as the four facts a model can act on.

    The Receipt label is the first of them and the reason the rest are bounded:
    an Observation the runtime will promote has to cite a Receipt, and the way
    to say more about the body than fits here is to analyse the Artifact the
    door already wrote rather than to read it into this context.

    The headers go through as the caller wrote them, minus the ones that
    describe a hop: `proxy.spend` drops those, because the capability and the
    Program on this request are the runtime's to state and not the child's.
    What comes back is the target's own, bounded the way the body is and for
    the same reason. It is the reading and not the record: a child that files
    an Observation about a header cites the Receipt it would have cited anyway,
    because the transcript that Receipt names holds every header of the
    exchange exactly and this list is an excerpt of it.

    The body goes through the same way and is not bounded again here. The
    roster bounded it at 64 KiB before the call arrived, the door bounds what
    it will read at its own ceiling, and a third measurement in this handler
    would be a third opinion about a number two layers already hold.
    """
    try:
        listener = proxy.peer(door.proxy_url)
        request = scope.canonical_request(url)
    except (proxy.Refused, scope.PolicyError) as refusal:
        return {"served": False, "reason": UNUSABLE_TARGET, "detail": refusal.detail}

    trust: ssl.SSLContext | None = None
    if request.protocol == "https":
        try:
            trust = tls.trust(Path(door.certificate))
        except (OSError, ssl.SSLError) as error:
            return {"served": False, "reason": UNUSABLE_TARGET, "detail": str(error)}

    try:
        answer = proxy.spend(
            listener,
            url,
            capability=door.capability,
            program_id=door.program_id,
            method=method,
            headers=headers,
            body=body,
            trust=trust,
        )
    except (OSError, http.client.HTTPException) as error:
        return {"served": False, "reason": DOOR_UNREACHABLE, "detail": str(error)}
    except ValueError as error:
        # What `http.client` raises for a header value carrying a line break.
        # The gate refuses those before the call arrives, so reaching this is
        # a request that cannot be put on a wire rather than a door that could
        # not be reached -- and the answer to it is a refusal, not a crashed
        # handler that tells the child nothing.
        return {"served": False, "reason": UNUSABLE_TARGET, "detail": str(error)}

    excerpt = answer.body[: packet.DEFAULT_EXCERPT]
    headers, cut = _readable(answer.headers)
    return {
        "served": answer.decision is None,
        "status": answer.status,
        "receipt": answer.receipt,
        "decision": answer.decision,
        "detail": answer.detail,
        "byte_size": len(answer.body),
        "truncated": len(answer.body) > len(excerpt),
        "headers": headers,
        "headers_truncated": cut,
        "body": excerpt.decode("utf-8", "replace"),
    }


def _readable(headers: Sequence[tuple[str, str]]) -> tuple[list[tuple[str, str]], bool]:
    """The target's response headers as the child reads them, and whether cut.

    What arrives is already the Agent's view of the exchange: the door removed
    the material a target issues as a credential, the door's own three
    statements about the exchange are named fields rather than headers, and
    nothing describing either hop is among these. So the only judgement left
    here is how much of it one exchange may spend, and `HEADERS_EXCERPT` above
    says why there has to be one at all.

    Measured as the list would be written -- name, colon, space, value, newline
    -- because what the ceiling is protecting is a length in a model's context
    and not a number of headers, and a count has no relation to what a header
    costs to read. Whole pairs, and the first one that does not fit ends the
    list, so a child reads a header the target sent rather than the front half
    of one and concludes something about the half it got.

    The flag is the point of stopping rather than a decoration on it. A cut
    list that did not say so is a list a model would read as the whole answer,
    and "this target sends no `Cache-Control`" is exactly the false reading
    that would follow.
    """
    kept: list[tuple[str, str]] = []
    spent = 0
    for name, value in headers:
        spent += len(name) + len(value) + len(": \n")
        if spent > HEADERS_EXCERPT:
            return kept, True
        kept.append((name, value))
    return kept, False


def stated(bounds: packet.Bounds) -> str:
    """The run's own ceilings, as the first thing the child reads.

    Decision 11 puts budgets and stop conditions in the Mission packet, and
    this is where the packet's copy becomes something the model can act on.
    The alternative is what this replaced: the ceiling was enforced in the loop
    below and never mentioned, so a run learned its budget by being cut off
    mid-answer -- which is the one moment the knowledge is worth nothing.

    Empty for a run that was given no bounds, so a job that carries none reads
    exactly as it did before rather than opening with a paragraph about
    nothing.
    """
    ceilings = [
        f"{value} {noun}"
        for value, noun in (
            (bounds.tokens, "token(s), counted across every turn"),
            (bounds.turns, "turn(s)"),
            (bounds.subagents, "subagent(s) at once"),
        )
        if value is not None
    ]
    said = []
    if ceilings:
        said.append("This run may spend " + ", ".join(ceilings) + ".")
    if bounds.stop_conditions:
        said.append("It ends when " + ", or when ".join(bounds.stop_conditions) + ".")
    return "\n".join(said) + "\n\n" if said else ""


def _headers(given: object) -> dict[str, str]:
    """The headers a call carried, as strings, or none at all.

    Cast rather than trusted, for the same reason the url and the method are:
    the gate has already refused every name and value outside the contract, and
    what this handler acts on is what arrived rather than what was promised.
    """
    if not isinstance(given, Mapping):
        return {}
    return {str(name): str(value) for name, value in given.items()}


def _body(given: object) -> bytes:
    """The bytes a call asked to be sent after its headers, or none at all.

    UTF-8, because that is what the string the model wrote already is by the
    time it has come through JSON, and encoding it back the same way is the
    only spelling that puts the bytes it meant on the wire. What that forbids
    is a body no UTF-8 string can hold -- a binary upload, a filename with a
    null byte in it -- and the honest place for those is an encoding field this
    contract does not have rather than a lossy encode here.

    Cast rather than trusted, for the same reason the url, the method and the
    headers are: the gate has already refused every value outside the
    contract's bounds, and what this handler acts on is what arrived rather
    than what was promised.
    """
    return str(given).encode("utf-8") if isinstance(given, str) else b""


def _slate(surface: Surface, choice: Choice):
    """The bounded set this decision chooses from, as it was offered.

    Answered from the job rather than from the database, because there is no
    database on this side of the boundary: the container's one network reaches
    the capability proxy. What that costs is nothing -- the Slate was written
    by `offer_slate` in the transaction that ranked it, and a second read would
    only tell the model about entries it may not have anyway.
    """
    name = "get_slate"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        return _content({"slate": choice.entries, "count": len(choice.entries)})

    return handler


def _pick(surface: Surface, choice: Choice):
    """The one answer this session gives, latched where the runtime can read it.

    Held in the process rather than sent anywhere, because there is no database
    on this side of the boundary and a pick is not a claim: what comes back here
    is a request, and `record_choice` is where it becomes a row -- or does not,
    if the Slate stopped carrying the label while the model was thinking.
    """
    name = "pick_task"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        return _content(choice.pick(dict(arguments or {})))

    return handler


def _packet(surface: Surface, judgement: Judgement):
    """The one document a validator session may read, served out of the job.

    Out of the job for the reason `get_slate` is: there is no database on this
    side of the boundary. What it costs here is nothing and what it buys is the
    ticket's whole property -- the packet was built by a function whose column
    dependencies a migration asserts, so a session cannot be shown a field by a
    handler that decided to add one.
    """
    name = "get_validation_packet"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        return _content(judgement.read(dict(arguments or {})))

    return handler


def _judge(surface: Surface, judgement: Judgement):
    """The one answer this session gives, latched where the runtime can read it.

    Held rather than written, exactly like a pick: what comes back is a request,
    and `record_verdict` is where it becomes a row -- or does not, because the
    packet the session judged stopped reading the same way while it was
    thinking.
    """
    name = "submit_verdict"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        return _content(judgement.judge(dict(arguments or {})))

    return handler


def _finding(surface: Surface, proposal: Proposal):
    """The one claim this run may ask the runtime to write a Finding from.

    Asked rather than held, which is the difference from every other request on
    this surface. A pick and a verdict are answered after the run because the
    runtime has to re-decide them against state that moved while the model was
    thinking; a Finding proposal is answered now because the rows it turns on
    have already settled and the run can do something with the answer -- go and
    demonstrate the next claim, or stop repeating this one.

    Nothing here decides whether the Finding may be opened. `rk2_finding_refusal`
    is eight rules about rows the runtime itself wrote, and this handler carries
    the proposal to it and reports what came back, including a refusal, which is
    reported as a refusal rather than as a tool that failed. The one thing this
    side decides is when it stops asking, which is a bound on this run's own
    context and not a second opinion about the claim.

    On a thread for `_tool_run`'s reason: the pipe is blocking and the caller is
    an event loop.
    """
    name = "propose_finding"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        return _content(await asyncio.to_thread(proposal.ask, dict(arguments or {})))

    return handler


def _propose(surface: Surface, submission: Submission):
    name = "submit_mission_result"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        return _content(submission.submit(dict(arguments or {})))

    return handler


def _schema(name: str) -> dict:
    return roster.CONTRACTS[f"mcp__{agent.SERVER}__{name}"].schema()


def _content(answer: Mapping[str, object]) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(answer, separators=(",", ":"))}]}


def gate_hooks(gate: roster.Gate) -> dict:
    """The roster's decision, wired to the four events that make it one.

    `PreToolUse` is the decision and the other three are what let it be taken
    honestly. `SubagentStart` records what a delegated agent was started as, so
    a later call carrying that identity is checked against a record rather than
    believed; the two completions give an admitted delegation back, so the
    concurrency ceiling is a ceiling on what is running rather than on what has
    ever run.

    None of the matchers narrows by tool name. A matcher is a filter on which
    calls reach the gate, and a gate that some calls do not reach is not one.
    """

    async def before(payload, tool_use_id, context) -> dict:
        call = roster.Call(
            tool=str(payload.get("tool_name") or ""),
            arguments=payload.get("tool_input") or {},
            agent_id=payload.get("agent_id"),
            agent_type=payload.get("agent_type"),
            ticket=payload.get("tool_use_id") or tool_use_id,
        )
        denial = gate.decide(call)
        if denial is None:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": str(denial),
            }
        }

    async def started(payload, tool_use_id, context) -> dict:
        gate.bind(str(payload.get("agent_id") or ""), str(payload.get("agent_type") or ""))
        return {}

    async def finished(payload, tool_use_id, context) -> dict:
        ticket = payload.get("tool_use_id") or tool_use_id
        if ticket is not None:
            gate.release(str(ticket))
        return {}

    callbacks = {
        "PreToolUse": before,
        "SubagentStart": started,
        "PostToolUse": finished,
        "PostToolUseFailure": finished,
    }
    return {
        event: [HookMatcher(matcher=None, hooks=[callbacks[event]])]
        for event in agent.GATE_EVENTS
    }


def options_for(
    job: Mapping[str, object],
    runtime: Mapping[str, object],
    mcp_server,
    launch: Path,
    gate: roster.Gate,
) -> object:
    """The one options value this launch is assessed with and started from.

    Built here and handed on unchanged. `cli_path` is whatever the installed
    SDK resolved to and nothing when it resolved to nothing -- the assertion
    refuses that case rather than this function substituting a name the SDK
    would look for on `PATH`. `settings` is the one document in `launch` for
    the same reason: naming the directory and naming the file in it separately
    would be two answers to which document loaded.

    Everything that varies between one role and another is read off `gate.role`
    rather than off the job. A job that could name a model or a turn ceiling
    would be a caller deciding what the roster is for, and the assertion
    checks these fields against the same row this reads them from, so a launch
    that disagreed with the roster would not start.

    `skills` is the roster's grants and `setting_sources` is what it takes to
    read them: the SDK turns each name into an allowed `Skill(name)` rule, and
    the CLI finds the instructions behind that name by reading the project
    location off the working directory -- which `run` staged before this was
    built. Passed as a list rather than left unset because unset is where the
    SDK substitutes both its own defaults, and one of them is the operator's
    home.
    """
    executable = agent.bundled_executable(runtime)
    role = gate.role
    return ClaudeAgentOptions(
        model=role.model,
        effort=role.effort,
        max_turns=role.max_turns,
        tools=role.visible_tools,
        mcp_servers={agent.SERVER: mcp_server},
        allowed_tools=role.allowed_tools(agent.SERVED),
        hooks=gate_hooks(gate),
        skills=list(role.skills),
        setting_sources=agent.setting_sources(role),
        permission_mode=agent.PERMISSION_MODE,
        cwd=str(launch),
        env={},
        sandbox=None,
        settings=str(launch / agent.SETTINGS),
        cli_path=None if executable is None else str(executable),
    )


async def run(
    job: Mapping[str, object],
    *,
    environment: Mapping[str, str] | None = None,
    runtime: Mapping[str, object] | None = None,
    transport=None,
) -> dict:
    """Make the launch directory, assert against it, start, corroborate, serve.

    The directory, its settings document and the role's Skills come first
    because they are part of what is asserted: the assertion's questions are
    "is the working directory the runtime's own" and "what will the CLI load
    from it", and neither can be asked about a directory that does not exist
    yet. So a refused launch leaves a directory behind and nothing else -- no
    transport, no session, no turn. Everything after the assertion is a gate on
    the step after it.

    `environment`, `runtime` and `transport` are parameters so that a refusal
    can be provoked without provoking the machine that would have to be broken
    to cause it -- an exported key, a downgraded SDK, a transport that answers
    wrongly. A child supplies none of them: it reads its own environment, its
    own runtime facts and the SDK's own transport, which is the whole reason
    the assertion is made here rather than in the supervisor. The settings
    locations are not one of those seams and are not passed on: `assess` reads
    `agent.MANAGED_SETTINGS` in the process doing the asserting, which is this
    one, and a caller naming them would be a caller choosing what it sees.
    """
    environment = dict(os.environ) if environment is None else dict(environment)
    runtime = runtime_facts() if runtime is None else dict(runtime)
    role = str(job.get("role") or "")
    launch = agent.launch_directory(str(job["workspace"]), str(job["agent_run_id"]))
    agent.write_settings(launch)
    # The Skills this role holds, on disk before the options value names them
    # and before the assertion reads the directory back. A grant staged after
    # the child started would be a grant the CLI had already finished looking
    # for.
    agent.stage_skills(launch, role)
    surface = Surface()
    reader = packet.Reader(packet.Packet.from_dict(dict(job.get("packet") or {})))
    submission = Submission()
    # Nothing, when the job carried no usable capability block. A run started
    # without one still serves the request tool -- the allowlist is the role's,
    # not the job's -- and the tool answers that it has nothing to spend.
    door = agent.Egress.from_dict(job.get("egress"))
    # Empty for every run that was offered no Slate, which is every run that is
    # executing a Task rather than choosing one. The entries come out of the
    # capsule because that is where they crossed: the runtime compiles the Slate
    # into it as one section, so this process reads the one copy it was given
    # rather than a field beside it that could say something else.
    choice = Choice(_slate_entries(job.get("capsule")))
    # Empty for every run that was not started to judge one, which is every run
    # but a validator's. An empty one serves no packet and latches no answer,
    # which is the honest state for a session nobody gave a Finding.
    judgement = Judgement(_judged(job.get("judgement")))
    # Nothing, when the job says the supervisor is not answering. A run whose
    # installation described no tool image still serves both tool-run tools --
    # the allowlist is the role's, not the job's -- and they answer that there
    # is nothing to run one with. Read off the job rather than tried, because
    # the way to find out by trying is to write into a pipe nobody is reading
    # and wait there until the run's deadline.
    channel = Channel() if job.get("tooling") else None
    # Nothing, when there is no SDK to build it from, and nothing when there is
    # no role to build it for. An options value is a description of what one
    # SDK version would do for one role, so an absent SDK and an unknown role
    # both leave it without a description rather than with a broken one --
    # and `assess` already refuses each of them by name.
    gate = _gate(role, job.get("subagent_cap"))
    options = (
        None
        if claude_agent_sdk is None or gate is None
        else options_for(
            job,
            runtime,
            server(surface, reader, submission, door, choice, judgement, channel),
            launch,
            gate,
        )
    )

    violations = agent.assess(options, environment, runtime, launch_dir=launch, role=role)
    if violations:
        raise agent.StartupRefusal(
            violations, "pre_spawn", runtime.get("sdk_version"), runtime.get("cli_version")
        )
    assert gate is not None

    messages = (transport or query)(
        prompt=stated(reader.packet.bounds) + str(job["objective"]), options=options
    )
    api_key_source = await _corroborate(messages, surface, runtime)

    # What the claim reserved for this run, or nothing when it reserved nothing.
    # Read the same way the cap is: off the job, because this process has no
    # database to ask.
    ceiling = _token_cap(job.get("token_cap"))
    text = ""
    answers = 0
    stop_reason = None
    spent_in = 0
    spent_out = 0
    async for message in messages:
        if isinstance(message, SystemMessage) and getattr(message, "subtype", None) == INIT:
            # A second announcement is a second startup, and the assertion was
            # made against the first. Counted rather than ignored: counting is
            # what closes the surface -- a child that announced itself twice
            # stops being served, and the count crosses back as the evidence.
            surface.open()
        if isinstance(message, AssistantMessage):
            answers += 1
            turn_in, turn_out = _usage(getattr(message, "usage", None))
            spent_in += turn_in
            spent_out += turn_out
            # The ceiling stops the run. Not a warning and not a log line: the
            # tokens past it are ones the Program did not reserve, and a session
            # asked politely to stop is a session that decides whether to.
            if ceiling is not None and spent_in + spent_out > ceiling:
                stop_reason = "budget"
                break
        if isinstance(message, ResultMessage):
            text = str(getattr(message, "result", "") or "")[:ANSWER]
            stop_reason = getattr(message, "stop_reason", None)
            # The session's own totals, which is the number to report when there
            # is one: the per-turn sum is what this loop could see, and a turn
            # the SDK accounted for after the last message it sent is in the
            # result and not in the sum. A result reporting nothing leaves the
            # sum alone rather than overwriting a measurement with a zero.
            result_in, result_out = _usage(getattr(message, "usage", None))
            if result_in or result_out:
                spent_in, spent_out = result_in, result_out
    return {
        "role": gate.role.name,
        "sdk_version": runtime.get("sdk_version"),
        "cli_version": runtime.get("cli_version"),
        "api_key_source": api_key_source,
        "tool_ready": surface.opened,
        "tools_served": list(surface.served),
        "denials": [denial.as_dict() for denial in gate.denials],
        "answers": answers,
        "stop_reason": stop_reason,
        "text": text,
        "mission_result": submission.result,
        "mission_attempts": submission.attempts,
        "input_tokens": spent_in,
        "output_tokens": spent_out,
        "choice": choice.task,
        "pick_attempts": choice.attempts,
        "verdict": judgement.answer,
        "verdict_attempts": judgement.attempts,
    }


def _judged(stated: object) -> Mapping[str, object] | None:
    """The packet a job carried, or nothing where it carried none.

    Anything that is not a mapping is nothing rather than an error, for the
    reason a malformed capsule is an empty Slate: a session with no packet
    serves no read and latches no answer, and the runtime reads that back as a
    validation nobody answered. A raise here would be a run that never started
    over a field most runs do not carry at all.
    """
    return stated if isinstance(stated, Mapping) else None


def _slate_entries(stated: object) -> list[Mapping[str, object]]:
    """The offered entries a job's capsule carried, or none where it carried none.

    A capsule that is not one is no Slate rather than an error, and so is a
    capsule with no Slate section. A malformed one leaves the session with
    nothing to choose from, which the runtime reads back as a session that chose
    nothing and falls back on its own walk -- and that is a working pass, where a
    raise here would be a run that never started.

    `Capsule.from_dict` is the same rebuild the packet gets, so the shape is
    checked once by the value that owns it rather than field by field here.
    """
    if not isinstance(stated, Mapping):
        return []
    try:
        return capsule.Capsule.from_dict(stated).slate()
    except capsule.CapsuleError:
        return []


def _usage(stated: object) -> tuple[int, int]:
    """One message's tokens, as the two numbers the run row records.

    Everything the model was charged for reading counts as input, cache included:
    a cached read is cheaper, not free, and a ceiling that ignored the cache
    would be a ceiling a long session walks straight through. A turn's numbers
    are that turn's own request, prefix and all, which is what the Program is
    charged for making it -- so the session's cost is the sum of the turns, and
    the `ResultMessage` total replaces the sum when the SDK reports one.

    Nothing reported is zero: a message carrying no usage block still happened,
    and absent fields inside a block that is there are zero for the same reason.
    A block that is not a mapping raises, for the reason `_token_cap` raises:
    usage this process cannot read is a ceiling it cannot enforce, and a quiet
    zero here is a session running unbounded.
    """
    if stated is None:
        return (0, 0)
    if not isinstance(stated, Mapping):
        raise TypeError(f"usage is {type(stated).__name__}, not a mapping")
    usage = stated
    return (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
        int(usage.get("output_tokens") or 0),
    )


def _token_cap(stated: object) -> int | None:
    """The most this run may spend, as the claim reserved it.

    Nothing stated is no ceiling: a Program with no total and no per-run number
    reserved nothing, and this process must not invent a bound the scheduler did
    not admit the Task under. A stated value that is not a number raises, which
    fails the run: unlike an unreadable subagent cap, this one cannot degrade to
    a refusal without also degrading to running unbounded.
    """
    return None if stated is None else int(stated)


def _subagent_cap(stated: object) -> int:
    """How many delegations this session may hold, as the claim read it.

    `scheduler_weights.max_concurrent_subagents` travels on the job because
    this process cannot ask: the container's one network reaches the capability
    proxy and no database. Nothing stated gets the roster's default, which is
    the schema's own -- that is a job written before the number travelled, not
    a value this process may prefer to the one the claim read. Anything else
    is converted and not sanitised: a cap this process cannot read is a job it
    cannot honour, and `_gate` turns that into a refusal rather than a guess.
    """
    return roster.DEFAULT_SUBAGENTS if stated is None else int(stated)


def _gate(role: str, subagent_cap: object) -> roster.Gate | None:
    """The gate for this role and cap, or nothing when neither can be had.

    Nothing rather than an exception, because an unknown role is a refusal the
    assertion makes with every other finding beside it, and a traceback here
    would be one finding reported as a crash. A cap the roster refuses -- below
    the one the schema's own CHECK admits, or not a number at all -- arrives at
    the same answer for the same reason: without a gate there is no options
    value, and a launch that cannot be described is one `assess` refuses field
    by field.
    """
    try:
        return roster.Gate(role, _subagent_cap(subagent_cap))
    except (roster.RosterError, TypeError, ValueError):
        return None


async def _corroborate(messages, surface: Surface, runtime: Mapping[str, object]) -> str:
    """Read up to the init message and open the tool surface, or refuse.

    Returns the credential source the CLI reported rather than the one this
    runtime required. They are equal by the time it returns -- that is the
    whole check -- but a run that reports what it read is carrying evidence,
    and one that reports its own expectation is carrying an assumption.

    The transport is closed on refusal rather than left to be collected. A
    child whose authentication this runtime could not corroborate is one that
    must not still be running while the refusal is written.
    """
    while True:
        message = await anext(messages, None)
        if message is None:
            await _refuse(messages, agent.uncorroborated(ABSENT), runtime)
        if isinstance(message, SystemMessage) and getattr(message, "subtype", None) == INIT:
            source = (getattr(message, "data", None) or {}).get("apiKeySource")
            violations = agent.corroboration(source)
            if violations:
                await _refuse(messages, violations, runtime)
            surface.open()
            return str(source)
        if type(message).__name__ not in BEFORE_INIT:
            await _refuse(messages, agent.uncorroborated(PREMATURE), runtime)


async def _refuse(messages, violations, runtime: Mapping[str, object]) -> NoReturn:
    """Close the run down, then raise the refusal that closed it."""
    await _close(messages)
    raise agent.StartupRefusal(
        violations, "init", runtime.get("sdk_version"), runtime.get("cli_version")
    )


async def _close(messages) -> None:
    close = getattr(messages, "aclose", None)
    if close is not None:
        await close()


def main(stream=None) -> int:
    """The child entry point: one job in, one result or one refusal out.

    One line rather than a stream read to its end. A job with a tool channel in
    it leaves the pipe open for the whole run, so reading to the end of standard
    input would be reading until the supervisor gives up on this process.
    """
    job = json.loads((stream or sys.stdin).readline())
    runtime = runtime_facts()
    try:
        result = asyncio.run(run(job, runtime=runtime))
    except agent.StartupRefusal as refusal:
        print(json.dumps({REFUSAL: refusal.as_dict()}), file=sys.stderr, flush=True)
        return agent.REFUSED
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
