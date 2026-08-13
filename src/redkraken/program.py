"""`rk run`: open a Program from a configuration, or resume the one it opened.

The command is the boundary between a file an operator edits and a Program the
database owns. Everything downstream — a Task, a Receipt, a Finding — cites a
Program and, through it, the policy that authorised the work. So the whole of
this module is one question asked carefully: is this the same Program running
the same policy, or is it something else wearing the same name?

Three properties make the answer trustworthy, and each one is a refusal rather
than a convention:

* Identity is the slug, and it is read, decided on and written under one lock
  in one transaction, so two runs starting together cannot both create it.
* Policy is the canonical hash. A changed policy is refused, not adopted: the
  operator says so explicitly and gets a new revision, because a Finding citing
  revision 1 has to keep meaning what it meant.
* Nothing is written until the database has said it is ready. The integrity
  gate runs first, on the runtime's own connection, so a refusal leaves the
  database exactly as it was found.

There is no execution loop here yet. The command opens or resumes the Program,
reports what is durable and stops, which is what `stop_reason` says.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from redkraken import config, integrity, migrate, pg, scope
from redkraken.outcome import (
    DATABASE_UNREACHABLE,
    INTEGRITY_FAILED,
    INVALID_CONFIGURATION,
    SCHEMA_DRIFT,
    Ledger,
    Report,
    report,
)


COMMAND = "run"

#: What `rk run` does after the Program is open: one ledger to record against,
#: the runtime connection it was opened on, and the Program it opened. The
#: answer is whatever the caller wants reported under `execution`, and this
#: module does not look inside it beyond asking whether a Task was attempted.
Execute = Callable[[Ledger, pg.Connection, str], dict]

#: Who the database records as having written. A run is a runtime actor: there
#: is no model in the loop yet, and the operator is not writing these rows by
#: hand. `events` carries the kind and not the identifier, so no row this
#: command writes holds the string below today; it is passed because
#: `set_actor` otherwise defaults `app.actor_id` to the login role, and the
#: first table that does record one should read `rk run` rather than
#: `rk2_runtime`, which is every connection the runtime opens.
ACTOR = "rk run"

#: The four answers `decide` can give, and the whole vocabulary of what one run
#: does to a Program.
CREATE = "create"
RESUME = "resume"
REVISE = "revise"
REFUSE = "refuse"

#: Why the command stopped. `nothing_to_execute` covers both ways of having
#: nothing to do: a machine with no execution slice configured, and one whose
#: scheduler offered nothing ready. `task_attempted` says one attempt was made
#: and is deliberately silent about how it went -- what the Task became is in
#: the execution facts, and a stop reason that summarised it would be a second
#: answer to a question the database has already answered.
STOPPED_REFUSED = "refused"
STOPPED_AWAITING_DECISION = "awaiting_decision"
STOPPED_NOTHING_TO_EXECUTE = "nothing_to_execute"
STOPPED_TASK_ATTEMPTED = "task_attempted"

#: Everything the command reports, and the reason the list is written down: a
#: run answers with durable identifiers, what state the Program is in, why it
#: stopped, what a human is being asked and whether the database still holds.
#: Anything else — a host, a header, a slot reference — is the operator's own
#: file being read back to them out of a log that other connections can see.
FACTS = (
    "program_id",
    "program_slug",
    "configuration",
    "scope",
    "lifecycle",
    "stop_reason",
    "pending_decisions",
    "integrity",
    "execution",
)

#: The advisory lock a run holds while it decides. The two-integer key space is
#: disjoint from the single-bigint one `migrate.LOCK_KEY` uses, so a run and a
#: migration cannot collide on a key by accident; the class id below is
#: arbitrary and only has to stay fixed.
LOCK_CLASS = 20260809

#: The runtime's own startup assertion, and the one the corpus wrote for it:
#: eight properties of this connection, defaulting to whoever is asking.
RUNTIME_ASSERTION = "check_runtime_connection(text)"

#: What a resume writes into its event, so a reader can tell an idle restart
#: from one that swept a Program clean.
RESUME_EVENT = "run.resumed"
EVENT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Revision:
    """One configuration revision as the database holds it."""

    revision: int
    schema_version: int
    source_sha256: str
    canonical_sha256: str

    def summary(self) -> dict:
        return {
            "revision": self.revision,
            "schema_version": self.schema_version,
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
        }


@dataclass(frozen=True)
class Program:
    """The root row and the newest policy recorded against it."""

    id: str
    slug: str
    closed_at: str | None
    purge_after: str | None
    revision: Revision | None

    @property
    def lifecycle(self) -> str:
        return lifecycle(self.closed_at, self.purge_after)


class _Refused(Exception):
    """Leaves the transaction without committing what it was about to write."""


def decide(
    current: Revision | None, configuration: config.Configuration, *, accept_change: bool
) -> str:
    """What this run does to the Program, given what is already recorded.

    The comparison is over the canonical hash, never the source hash: reflowing
    the file, reordering its tables or adding a comment produces different bytes
    and the same policy, and a revision recorded for that would claim a change
    that did not happen. `accept_change` is the operator saying, in the command
    line, that the change is theirs — without it a changed policy is refused,
    because silently adopting one rewrites what every earlier Finding cites.
    """
    if current is None:
        return CREATE
    if current.canonical_sha256 == configuration.canonical_sha256:
        return RESUME
    return REVISE if accept_change else REFUSE


def lifecycle(closed_at: str | None, purge_after: str | None) -> str:
    """The Program's state in one word, from the two timestamps that say it."""
    if purge_after is not None:
        return "retired"
    if closed_at is not None:
        return "closed"
    return "open"


def run(
    settings: pg.Settings,
    configuration_path: Path,
    *,
    accept_change: bool = False,
    corpus: Path = migrate.CORPUS,
    execute: Execute | None = None,
) -> Report:
    """Create or resume the Program this configuration names, then work it.

    `execute` is a callback rather than an import. The slice that runs a Task
    needs the capability proxy, the proxy needs this module to resolve the
    Program a request is spent against, and a module that imported its own
    caller would close that loop. Passing the work in also keeps the ordering
    honest: nothing can be attempted against a Program this command has not
    already opened, verified and read back.
    """
    ledger = Ledger()
    state = _State()

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return _report(ledger, state)
    state.configuration = configuration
    slug = configuration.document["program"]["name"]
    state.slug = slug
    ledger.hold(
        "configuration",
        f"{slug}, schema {configuration.schema_version}, "
        f"policy {_short(configuration.canonical_sha256)}",
    )

    # Compiled here, before the corpus is read and long before a connection is
    # opened. A configuration that parses and does not compile authorises
    # nothing, so it must not be able to reach a Program: without this the run
    # would create the root row, record the revision and then discover it had no
    # policy to enforce, leaving a Program every entity of which projects denied.
    policy, policy_refusals = scope.compile_policy(configuration)
    if policy is None:
        ledger.refuse(
            "scope_policy",
            f"the configuration does not compile to a scope policy "
            f"({len(policy_refusals)} violation(s)); nothing was written",
            policy_refusals,
        )
        return _report(ledger, state)
    state.policy = policy
    ledger.hold(
        "scope_policy",
        f"{len(policy.rules)} rule(s), {len(policy.channels)} channel(s), "
        f"policy {_short(policy.policy_sha256())}",
    )

    migrations, corpus_refusals = migrate.load(corpus)
    if corpus_refusals:
        ledger.refuse("corpus", f"{len(corpus_refusals)} refused migration file(s)", corpus_refusals)
        return _report(ledger, state)
    ledger.hold("corpus", f"{len(migrations)} migration file(s)")

    connection = migrate.open_connection(ledger, settings)
    if connection is None:
        return _report(ledger, state)

    with connection:
        assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, state)

        # Before anything is written, and on this connection rather than a
        # privileged one: a run that cannot see the database it is about to
        # write to is not ready, whatever a migration run concluded earlier.
        # Two families, not three: the role catalogue is the runner's, and a
        # runtime command that asked for it would depend on the privilege
        # ticket 66 exists to take away.
        gate = integrity.verify(
            connection,
            expected=[item.identity for item in migrations],
            families=integrity.RUNTIME_FAMILIES,
        )
        state.integrity = dict(gate.facts)
        if gate.violations:
            ledger.refuse(
                "integrity",
                f"{len(gate.facts.get('failed', ()))} of {gate.facts.get('checks', 0)} check(s) "
                "failed; nothing was written",
                gate.violations,
            )
            return _report(ledger, state)
        ledger.hold(
            "integrity",
            f"{gate.facts['checks']} check(s) across "
            f"{len(gate.facts['families'])} families hold",
        )

        try:
            _open_program(ledger, connection, state, accept_change=accept_change)
        except _Refused:
            return _report(ledger, state)

        # Past here the rows are committed. Every remaining failure is reported
        # against a Program that exists, so the identifiers stay in the answer.
        _read_durable_state(ledger, connection, state)

        if execute is not None and _workable(ledger, state):
            state.execution = execute(ledger, connection, str(state.program_id))

    return _report(ledger, state)


def _workable(ledger: Ledger, state: _State) -> bool:
    """Whether this Program is in a state anything may be attempted against.

    Three refusals rather than one, because they are three different facts and
    an operator reading "nothing happened" deserves to know which. A closed or
    retired Program is not a fault at all, which is why it is held rather than
    failed: the run resumed it correctly and there is nothing left to work on.
    """
    if ledger.violations:
        return False
    if state.pending:
        ledger.hold(
            "execution",
            f"{len(state.pending)} decision(s) are waiting on a human; nothing was claimed",
        )
        return False
    if state.lifecycle != "open":
        ledger.hold("execution", f"the Program is {state.lifecycle}; nothing was claimed")
        return False
    return True


@dataclass
class _State:
    """What the command has established so far, in report terms.

    Carried rather than returned so that a refusal at any depth answers with
    the same keys a completed run answers with: an operator parses one document
    whether the run reached a Program or not.
    """

    slug: str | None = None
    configuration: config.Configuration | None = None
    policy: scope.Policy | None = None
    program_id: str | None = None
    revision: Revision | None = None
    scope: dict | None = None
    lifecycle: str | None = None
    pending: list[dict] | None = None
    integrity: dict | None = None
    execution: dict | None = None


def _report(ledger: Ledger, state: _State) -> Report:
    pending = state.pending or []
    attempted = bool((state.execution or {}).get("task"))
    if ledger.violations:
        stop_reason = STOPPED_REFUSED
    elif pending:
        stop_reason = STOPPED_AWAITING_DECISION
    elif attempted:
        stop_reason = STOPPED_TASK_ATTEMPTED
    else:
        stop_reason = STOPPED_NOTHING_TO_EXECUTE
    return report(
        COMMAND,
        ledger,
        program_id=state.program_id,
        program_slug=state.slug,
        configuration=state.revision.summary() if state.revision else None,
        scope=state.scope,
        lifecycle=state.lifecycle,
        stop_reason=stop_reason,
        pending_decisions=pending,
        integrity=state.integrity,
        execution=state.execution,
    )


def assert_runtime_connection(ledger: Ledger, connection: pg.Connection) -> None:
    """Refuse the wrong connection string before the gate, let alone a write.

    The corpus wrote this assertion for exactly this purpose — eight properties
    of the connection rather than of the schema, defaulting to whoever asks — so
    running as the owner, as a superuser or as a role that can turn triggers off
    is a refusal here instead of a surprise later. Public because every command
    that writes as the runtime needs it, and two copies of "which role is this"
    would be two answers the day one of them is updated.
    """
    if not connection.execute(
        "SELECT to_regprocedure($1) IS NOT NULL", (RUNTIME_ASSERTION,)
    ).scalar():
        ledger.fail(
            "runtime_connection",
            "this database carries no runtime connection assertion; run `rk db migrate`",
            code=SCHEMA_DRIFT,
            source="database",
        )
        return

    user = connection.execute("SELECT current_user").scalar()
    failed = [
        (str(name), str(detail))
        for name, ok, detail in connection.execute(
            "SELECT check_name, ok, detail FROM check_runtime_connection()"
        ).rows
        if not ok
    ]
    if failed:
        ledger.fail(
            "runtime_connection",
            f"connected as {user}, which is not the runtime connection: "
            + "; ".join(f"{name} ({detail})" for name, detail in failed),
            code=INVALID_CONFIGURATION,
            source="database",
        )
        return
    ledger.hold("runtime_connection", f"connected as {user}")


def resolve(ledger: Ledger, connection: pg.Connection, slug: str) -> str | None:
    """The identifier of the Program a configuration names, or a refusal.

    On the runtime connection, always: the agent's cannot read `programs` and is
    not supposed to be able to, so this is the one crossing point where a name an
    operator wrote becomes an identifier a session can be bound to. Public
    because `rk state` and `rk artifact` both need that crossing, and the failure
    they share -- a configuration naming a Program nobody opened -- is one an
    operator should not see worded two ways.
    """
    rows = connection.execute("SELECT id::text FROM programs WHERE slug = $1", (slug,)).rows
    if not rows:
        ledger.fail(
            "program",
            f"no Program is named {slug}; `rk run --config` opens one",
            code=INVALID_CONFIGURATION,
            source="database",
        )
        return None
    ledger.hold("program", f"{slug} resolved on the runtime connection")
    return str(rows[0][0])


def _open_program(
    ledger: Ledger, connection: pg.Connection, state: _State, *, accept_change: bool
) -> None:
    """Read, decide and write, once, under one lock.

    The lock covers the deciding and not merely the writing. Two runs of the
    same command starting together would otherwise both read no Program and
    both insert one, and only the unique index on the slug would notice — after
    one of them had already emitted an event for a Program that does not
    survive its own transaction.
    """
    configuration = state.configuration
    policy = state.policy
    assert configuration is not None and policy is not None  # established by the caller
    slug = str(state.slug)

    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock($1::int4, hashtext($2))", (LOCK_CLASS, slug))
        existing = _existing(connection, slug)
        if existing is not None:
            state.program_id = existing.id
            state.revision = existing.revision
            state.lifecycle = existing.lifecycle
            if existing.lifecycle != "open":
                ledger.fail(
                    "program",
                    f"{slug} is {existing.lifecycle} and is not resumed; a closed Program's "
                    "rows are the record of work that finished",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                raise _Refused
            if existing.revision is None:
                # The gate refuses this first — `program_without_configuration`
                # is a standing check — so reaching it means the row appeared
                # between the gate and this lock. Named rather than left to the
                # unique index, which would report it as a duplicate slug.
                ledger.fail(
                    "program",
                    f"{slug} exists with no configuration revision, so nothing records the "
                    "policy it runs under; `rk db verify` names it",
                    code=INTEGRITY_FAILED,
                    source="database",
                )
                raise _Refused

        current = existing.revision if existing else None
        answer = decide(current, configuration, accept_change=accept_change)
        if answer == REFUSE:
            assert current is not None  # `decide` only refuses against a revision
            ledger.fail(
                "program",
                f"{slug} runs under configuration revision {current.revision} "
                f"({_short(current.canonical_sha256)}), and this file is a different policy "
                f"({_short(configuration.canonical_sha256)}); rerun with --accept-change to "
                f"record revision {current.revision + 1}",
                code=INVALID_CONFIGURATION,
                source="config",
            )
            raise _Refused

        connection.execute("SELECT set_actor('runtime', $1)", (ACTOR,))

        if answer == CREATE:
            state.program_id = _create(connection, configuration, slug)
            state.lifecycle = "open"
            reason = "program opened"
        elif answer == REVISE:
            _revise(connection, configuration, str(state.program_id))
            reason = f"policy change accepted by {ACTOR}"
        else:
            reason = ""

        next_revision = 1 if current is None else current.revision + 1
        if answer in (CREATE, REVISE):
            state.revision = _record(
                connection,
                configuration,
                str(state.program_id),
                revision=next_revision,
                reason=reason,
            )

        identity_revision = (
            state.revision.revision if state.revision is not None else next_revision
        )
        _project_identities(
            connection,
            configuration,
            str(state.program_id),
            revision=identity_revision,
        )

        # Every answer that keeps the Program open leaves it running a compiled
        # policy, resume included: a Program opened before this path existed has
        # `scope_version` NULL, and NULL is a Program nothing may be sent to.
        state.scope = _project_scope(
            connection,
            policy,
            str(state.program_id),
            revision=state.revision.revision if state.revision else next_revision,
        )
        ledger.hold(
            "scope_version",
            f"version {state.scope['version']} from configuration revision "
            f"{state.scope['configuration_revision']}, {state.scope['rules']} rule(s), "
            f"policy {_short(state.scope['policy_sha256'])}"
            + ("" if state.scope["compiled"] else " (already live)"),
        )

        if answer in (RESUME, REVISE):
            counts = _resume(connection, str(state.program_id), state.revision)
            detail = ", ".join(f"{name} {value}" for name, value in sorted(counts.items()))
            ledger.hold("program", f"resumed {slug}: {detail}")
        else:
            ledger.hold("program", f"created {slug}")

    if answer == REVISE:
        ledger.hold("configuration_revision", f"recorded revision {next_revision} for {slug}")


def _existing(connection: pg.Connection, slug: str) -> Program | None:
    """The Program this slug names and the newest policy recorded against it."""
    rows = connection.execute(
        "SELECT p.id::text, p.closed_at::text, p.purge_after::text,"
        "       c.revision, c.schema_version, c.source_sha256, c.canonical_sha256"
        "  FROM programs p"
        "  LEFT JOIN LATERAL ("
        "        SELECT revision, schema_version, source_sha256, canonical_sha256"
        "          FROM program_configurations"
        "         WHERE program_id = p.id"
        "         ORDER BY revision DESC"
        "         LIMIT 1) c ON true"
        " WHERE p.slug = $1",
        (slug,),
    ).rows
    if not rows:
        return None
    identity, closed_at, purge_after, revision, schema_version, source, canonical = rows[0]
    return Program(
        id=str(identity),
        slug=slug,
        closed_at=None if closed_at is None else str(closed_at),
        purge_after=None if purge_after is None else str(purge_after),
        revision=(
            None
            if revision is None
            else Revision(
                revision=int(revision),
                schema_version=int(schema_version),
                source_sha256=str(source),
                canonical_sha256=str(canonical),
            )
        ),
    )


@dataclass(frozen=True)
class _Policy:
    """The policy the root `programs` row carries as columns of its own.

    Read in one place because it is written in three -- the row, the row's
    update and the revision that records it -- and three readings of the same
    document are three chances for them to stop being the same values.

    A type rather than a widening tuple: 25 took this from two values to six,
    and six positional values threaded through three call sites is one
    transposition away from a Program running a per-Lane ceiling as its per-run
    one. The revision row still records only the first two, which is why they
    are named rather than splatted at every site.
    """

    platform: str | None
    token_budget: int
    run_token_budget: int
    run_request_budget: int
    lane_token_budget: int
    lane_request_budget: int


def _policy(configuration: config.Configuration) -> _Policy:
    document = configuration.document
    budgets = document["budgets"]
    return _Policy(
        platform=document["program"]["platform"],
        token_budget=budgets["tokens"],
        run_token_budget=budgets["run_tokens"],
        run_request_budget=budgets["run_requests"],
        lane_token_budget=budgets["lane_tokens"],
        lane_request_budget=budgets["lane_requests"],
    )


def _create(connection: pg.Connection, configuration: config.Configuration, slug: str) -> str:
    """The root row. The slug is the identity; the rest is policy it carries."""
    policy = _policy(configuration)
    return str(
        connection.execute(
            "INSERT INTO programs (slug, name, platform, token_budget,"
            " run_token_budget, run_request_budget, lane_token_budget, lane_request_budget)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id::text",
            (
                slug,
                slug,
                policy.platform,
                policy.token_budget,
                policy.run_token_budget,
                policy.run_request_budget,
                policy.lane_token_budget,
                policy.lane_request_budget,
            ),
        ).scalar()
    )


def _revise(connection: pg.Connection, configuration: config.Configuration, program_id: str) -> None:
    """Bring the root row's own policy columns to the accepted configuration.

    The slug is not among them: it is the identity, and a file naming a
    different one is a different Program rather than a revision of this one.

    `programs` emits no event, so this update is invisible in the log on its
    own. What makes it auditable is that the revision recorded in the same
    transaction states the same values, and `check_program_configuration()`
    fails the gate when the row and the newest revision disagree.
    """
    policy = _policy(configuration)
    connection.execute(
        "UPDATE programs SET platform = $2, token_budget = $3, run_token_budget = $4,"
        " run_request_budget = $5, lane_token_budget = $6, lane_request_budget = $7"
        " WHERE id = $1::uuid",
        (
            program_id,
            policy.platform,
            policy.token_budget,
            policy.run_token_budget,
            policy.run_request_budget,
            policy.lane_token_budget,
            policy.lane_request_budget,
        ),
    )


def _record(
    connection: pg.Connection,
    configuration: config.Configuration,
    program_id: str,
    *,
    revision: int,
    reason: str,
) -> Revision:
    """Append the configuration revision. The insert is what emits the event.

    The document is sent in the encoding its canonical hash was taken over, but
    `jsonb` normalises what it stores: key order and whitespace do not survive
    the column, so hashing `document::text` back out would not reproduce
    `canonical_sha256`. A reader that wants to re-derive the hash parses the
    document and canonicalises it again -- which is the check worth making
    anyway, since it re-runs the rule rather than trusting a stored string.

    `platform` and `token_budget` are restated out of the document because they
    are values also written onto the `programs` row, and stating them here is
    what puts that projection in the event log. The four ceilings 25 added get
    no columns of their own here: the document is on this row already, and
    `check_program_configuration()` compares the row against it, so a second
    copy would be a third place the same number lives.
    """
    policy = _policy(configuration)
    connection.execute(
        "INSERT INTO program_configurations"
        " (program_id, revision, schema_version, source_path,"
        "  source_sha256, canonical_sha256, document, platform, token_budget, reason)"
        " VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)",
        (
            program_id,
            revision,
            configuration.schema_version,
            configuration.path,
            configuration.source_sha256,
            configuration.canonical_sha256,
            config.canonical_bytes(configuration.document).decode("utf-8"),
            policy.platform,
            policy.token_budget,
            reason,
        ),
    )
    return Revision(
        revision=revision,
        schema_version=configuration.schema_version,
        source_sha256=configuration.source_sha256,
        canonical_sha256=configuration.canonical_sha256,
    )


def _project_scope(
    connection: pg.Connection,
    policy: scope.Policy,
    program_id: str,
    *,
    revision: int,
) -> dict:
    """Record the compiled policy as a scope version, promote it and reproject.

    The scope version is its own sequence rather than the configuration revision
    number, and the two are joined by a column instead. They mostly move
    together, and the case that separates them is the one that matters: the
    compiler itself changes, the operator's file does not, and the same
    configuration now compiles to different rules. That is a change in what the
    policy *means*, so it is a new version -- receipts cite the version, and
    rewriting one would rewrite what they say. Nothing here ever updates a
    version already written; `scope_versions_immutable` would refuse it anyway.

    Idempotent by digest: a resume whose live version already holds this exact
    policy writes nothing at all, which is what lets `rk run` be run repeatedly
    without filling the version history with identical rows.
    """
    live, live_digest, live_at = connection.execute(
        "SELECT p.scope_version, sv.policy_sha256, sv.configuration_revision"
        "  FROM programs p"
        "  LEFT JOIN program_scope_versions sv"
        "    ON sv.program_id = p.id AND sv.version = p.scope_version"
        " WHERE p.id = $1::uuid",
        (program_id,),
    ).rows[0]
    digest = policy.policy_sha256()
    unchanged = (
        live is not None
        and str(live_digest) == digest
        and live_at is not None
        and int(live_at) == revision
    )
    if unchanged:
        # One exception to writing nothing, and it is the reason the helper
        # takes a version rather than assuming a fresh one: a version compiled
        # before callback channels existed carries none of its own, and the
        # digest that makes this run a no-op is the digest of a policy that
        # already declared them. Without this, a Program installed against an
        # earlier corpus admits no arrival until the operator happens to change
        # the configuration file. Idempotent, so a second run writes nothing.
        _project_channels(connection, program_id, int(live), policy)
        return {
            "version": int(live),
            "configuration_revision": revision,
            "policy_sha256": digest,
            "rules": len(policy.rules),
            "required_headers": len(policy.headers),
            "callback_channels": len(policy.channels),
            "compiled": False,
            "reprojected": 0,
        }

    version = int(
        connection.execute(
            "SELECT coalesce(max(version), 0) + 1 FROM program_scope_versions"
            " WHERE program_id = $1::uuid",
            (program_id,),
        ).scalar()
    )
    controls = dict(policy.controls)
    budgets = dict(policy.budgets)
    connection.execute(
        "INSERT INTO program_scope_versions"
        " (program_id, version, policy, policy_sha256, configuration_revision, reason,"
        "  availability_impact, credential_use, mutation, pivoting, sensitive_data_access,"
        "  budget_burst, budget_concurrency, budget_requests, budget_window_seconds)"
        " VALUES ($1::uuid, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $10, $11,"
        "         $12, $13, $14, $15)",
        (
            program_id,
            version,
            config.canonical_bytes(policy.document()).decode("utf-8"),
            digest,
            revision,
            f"compiled from configuration revision {revision} by grammar "
            f"{policy.grammar_version}",
            # Named one by one rather than splatted, so a sixth control added to
            # the loader fails here instead of being dropped on the way in.
            controls["availability_impact"],
            controls["credential_use"],
            controls["mutation"],
            controls["pivoting"],
            controls["sensitive_data_access"],
            # And the four limits the egress door enforces, for the same reason.
            # A limit missing here is a NULL column, and a NULL column refuses
            # every request rather than admitting an unbounded one.
            budgets["burst"],
            budgets["concurrency"],
            budgets["requests"],
            budgets["window_seconds"],
        ),
    )
    # One statement per table, whatever the rule count: the ordinals and the
    # digest are already fixed by the compiler, so the rows are a projection of
    # the document rather than a second decision made here.
    connection.execute(
        "INSERT INTO program_scope_rules"
        " (program_id, version, ord, effect, effect_rank, pattern_kind, pattern_text,"
        "  match_key, protocol, port, path_prefix, spec_kind, spec_len)"
        " SELECT $1::uuid, $2, r.ord, r.effect, r.effect_rank, r.pattern_kind,"
        "        r.pattern_text, r.match_key, r.protocol, r.port, r.path_prefix,"
        "        r.spec_kind, r.spec_len"
        "   FROM jsonb_to_recordset($3::jsonb) AS r("
        "        ord integer, effect text, effect_rank smallint, pattern_kind text,"
        "        pattern_text text, match_key text, protocol text, port integer,"
        "        path_prefix text, spec_kind smallint, spec_len smallint)",
        (program_id, version, _encode([rule.row() for rule in policy.rules])),
    )
    if policy.headers:
        connection.execute(
            "INSERT INTO program_required_headers (program_id, version, ord, name, value_ref)"
            " SELECT $1::uuid, $2, h.ord, h.name, h.value_ref"
            "   FROM jsonb_to_recordset($3::jsonb) AS h(ord integer, name text, value_ref text)",
            (
                program_id,
                version,
                _encode(
                    [
                        {"ord": index + 1, "name": header.name, "value_ref": header.value_ref}
                        for index, header in enumerate(policy.headers)
                    ]
                ),
            ),
        )
    _project_channels(connection, program_id, version, policy)
    moved = int(
        connection.execute(
            "SELECT count(*) FROM set_scope_version($1::uuid, $2)", (program_id, version)
        ).scalar()
    )
    return {
        "version": version,
        "configuration_revision": revision,
        "policy_sha256": digest,
        "rules": len(policy.rules),
        "required_headers": len(policy.headers),
        "callback_channels": len(policy.channels),
        "compiled": True,
        "reprojected": moved,
    }


def _project_channels(
    connection: pg.Connection, program_id: str, version: int, policy: scope.Policy
) -> None:
    """The declared callback channels, beside the rules rather than inside them.

    An http channel also compiles to an `egress_support` rule, which is what
    stops the harness treating its own listener as a target; these rows answer
    the other question -- which names an arrival may have come in on -- and they
    are what `mint_callback_correlator` and the admission trigger join against. A
    channel withdrawn from the configuration is therefore absent from the next
    version, and stops admitting arrivals the moment that version goes live.

    `DO NOTHING` because this is also called for a version already live, where
    the rows are either already exactly these or missing entirely. It cannot
    rewrite one: the ordinals and hosts are the compiler's, the version is
    immutable under `callback_channels_immutable`, and a conflicting row would
    mean two compilations of one digest disagreed.
    """
    if not policy.channels:
        return
    connection.execute(
        "INSERT INTO program_callback_channels (program_id, version, ord, name, kind, host)"
        " SELECT $1::uuid, $2, c.ord, c.name, c.kind, c.host"
        "   FROM jsonb_to_recordset($3::jsonb) AS c("
        "        ord integer, name text, kind text, host text)"
        " ON CONFLICT DO NOTHING",
        (
            program_id,
            version,
            _encode(
                [
                    {"ord": index + 1, **channel.summary()}
                    for index, channel in enumerate(policy.channels)
                ]
            ),
        ),
    )


def _project_identities(
    connection: pg.Connection,
    configuration: config.Configuration,
    program_id: str,
    *,
    revision: int,
) -> None:
    """Project configured Identity labels without making slot references readable.

    The configuration document is the operator's declaration of which stable
    labels exist.  ``secret_ref`` retains only the control-side ``slot://``
    reference, and the state role's column grant excludes it.  Updating the
    redacted entity metadata in the same transaction gives a configuration
    change one Event without copying that reference into the Event payload.
    """
    configured = {
        str(item["name"]): str(item["slot_ref"])
        for item in configuration.document["identity"]
    }
    rows = connection.execute(
        "SELECT i.entity_id::text, i.slot_name, i.secret_ref, i.invalidated_at IS NOT NULL,"
        "       e.metadata ->> 'configuration_revision'"
        "  FROM identities i JOIN entities e ON e.id = i.entity_id"
        " WHERE i.program_id = $1::uuid"
        "   AND e.metadata ->> 'source' = 'program_configuration'",
        (program_id,),
    ).rows
    existing = {str(row[1]): row for row in rows}

    for label, reference in configured.items():
        current = existing.get(label)
        metadata = json.dumps(
            {
                "configuration_revision": revision,
                "source": "program_configuration",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if current is None:
            entity_id = connection.execute(
                "INSERT INTO entities (program_id, type, dedup_key, metadata)"
                " VALUES ($1::uuid, 'identity', $2, $3::jsonb) RETURNING id::text",
                (program_id, f"configured-identity:{label}", metadata),
            ).scalar()
            connection.execute(
                "INSERT INTO identities (entity_id, slot_name, class, secret_ref)"
                " VALUES ($1::uuid, $2, 'user', $3)",
                (str(entity_id), label, reference),
            )
            continue

        entity_id, _, prior_reference, invalidated, _ = current
        if str(prior_reference) == reference and not bool(invalidated):
            continue
        connection.execute(
            "UPDATE identities SET secret_ref = $2, invalidated_at = NULL"
            " WHERE entity_id = $1::uuid",
            (str(entity_id), reference),
        )
        connection.execute(
            "UPDATE entities SET metadata = $2::jsonb WHERE id = $1::uuid",
            (str(entity_id), metadata),
        )

    for label, current in existing.items():
        if label in configured or bool(current[3]):
            continue
        entity_id = str(current[0])
        metadata = json.dumps(
            {
                "configuration_revision": revision,
                "source": "program_configuration",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            "UPDATE identities SET invalidated_at = now() WHERE entity_id = $1::uuid",
            (entity_id,),
        )
        connection.execute(
            "UPDATE entities SET metadata = $2::jsonb WHERE id = $1::uuid",
            (entity_id, metadata),
        )


def _encode(rows: list[dict]) -> str:
    """One statement's worth of rows, in the encoding `jsonb_to_recordset` reads."""
    return json.dumps(rows, sort_keys=True, separators=(",", ":"))


def _resume(connection: pg.Connection, program_id: str, revision: Revision | None) -> dict:
    """The reconciliation sweep, and the one event that records it happened.

    `resume_program()` is the corpus's single path for every abort — a crash, a
    rate limit, an operator stop — and it returns what it swept without saying
    anywhere that it ran. The event is written here because a restart that
    changed nothing is still a fact about the Program: it is how a reader tells
    an idle restart from one that unclaimed twelve tasks.
    """
    counts = json.loads(str(connection.execute(
        "SELECT resume_program($1::uuid)", (program_id,)
    ).scalar()))
    payload = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "configuration_revision": revision.revision if revision else None,
        "canonical_sha256": revision.canonical_sha256 if revision else None,
        "counts": counts,
    }
    connection.execute(
        "INSERT INTO events (program_id, type, actor_kind, payload)"
        " VALUES ($1::uuid, $2, 'runtime', $3::jsonb)",
        (program_id, RESUME_EVENT, json.dumps(payload, sort_keys=True, separators=(",", ":"))),
    )
    return counts


def _read_durable_state(ledger: Ledger, connection: pg.Connection, state: _State) -> None:
    """What the Program is, read back from the database that now holds it.

    Read after the commit rather than assembled from what was just written, so
    the answer is the durable one. A failure here is reported against a Program
    that exists: the identifiers stay in the report, and the assertion says
    where to look, because the alternative is an operator who cannot tell a
    Program that was never created from one they cannot currently see.
    """
    program_id = str(state.program_id)
    try:
        closed_at, purge_after = connection.execute(
            "SELECT closed_at::text, purge_after::text FROM programs WHERE id = $1::uuid",
            (program_id,),
        ).rows[0]
        state.lifecycle = lifecycle(
            None if closed_at is None else str(closed_at),
            None if purge_after is None else str(purge_after),
        )
        state.pending = [
            {
                "id": str(row["id"]),
                "question_code": str(row["question_code"]),
                "created_at": str(row["created_at"]),
            }
            for row in connection.execute(
                "SELECT id::text AS id, question_code, created_at::text AS created_at"
                "  FROM pending_decisions"
                " WHERE program_id = $1::uuid AND answered_at IS NULL"
                " ORDER BY created_at, id",
                (program_id,),
            ).dicts()
        ]
    except (pg.DatabaseError, pg.ConnectionError_) as error:
        ledger.fail(
            "durable_state",
            f"the Program was written and committed as {program_id}, and reading it back "
            f"failed: {error}. Its rows are durable; `rk db verify` inspects them",
            code=(
                DATABASE_UNREACHABLE
                if isinstance(error, pg.ConnectionError_)
                else INTEGRITY_FAILED
            ),
            source="database",
        )
        return
    ledger.hold(
        "durable_state",
        f"{state.lifecycle}, {len(state.pending)} pending decision(s)",
    )


def _short(digest: str) -> str:
    """Enough of a hash to read in a refusal, never enough to mistake for one."""
    return digest[:12]
