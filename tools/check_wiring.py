"""The wiring gate: everything this tree declares has something on the other end of it.

`check_audit` reads the tracker and asks whether every requirement the Spec
states was built and is checked by something that can fail. This file is its
sibling and asks the other half of the same question, one layer down: whether
every *thing* the tree declares -- a Contract, an argument, a granted verb, a
table, a column, a view, a property class, a tool named in a Playbook -- has a
producer, a consumer or a caller, or a recorded reason why not.

Four audits reached that conclusion independently and each ended with a section
naming the queries a gate would run. This is those four sections reconciled into
one set of ten, and the mapping is recorded here so that neither numbering has
to be repeated afterwards:

W1  every Contract is served or declared unserved with a reason -- 21 G1;
W2  every declared argument is consumed end to end -- 21 G2;
W3  every granted SQL verb has a caller, a trigger binding, a standing check or
    an owed row -- 21 G3, 21 G10, 23 G4, 23 G5;
W4  every relation on the agent read surface is read by a tool or declared
    unread -- 21 G4, the read half of 23 G8;
W5  a proposal element list has a read verb that returns it, a result mints no
    handle the read verbs cannot resolve, and a result is not narrower than the
    value it was built from -- 21 G5, G6, G7;
W6  every table has a producer or is registered seed-only, every column a rule
    depends on has a writer, every generated column has a row that makes it
    true, every view has a reader, and every constraint is falsifiable -- 23 G1,
    G2, G3, G6, the write half of G8;
W7  cross-table guard satisfiability -- 23 G7;
W8  a Contract's declared write target has both a writer and a handler -- 23 G9;
W9  every declared property class is emitted, gradeable and satisfiable, every
    closed set is served from the table that declares it, and a migration that
    moves a constraint re-issues the column comment -- 20 G1 through G8;
W10 a Playbook or Skill body names only tools the executing role holds,
    arguments those tools declare, offline programs granted to that role, and no
    artifact the same body earlier described fetching over the wire -- 22's eight
    checks.

## What is answered here and what is answered by the database

`check_audit` reads files and needs no server, and this gate keeps that property,
because a check that answered differently on two machines could not be the thing
a release turns on. Every reading below is taken from `src/redkraken/**/*.py`,
`src/redkraken/migrations/*.sql` and the two corpus directories.

That turns out to be more than the plan expected. A migration corpus is not a
weaker source than a live catalogue for the questions asked here: it *is* where
the grants, the trigger bindings, the standing-check queries, the `CREATE TABLE`
statements and the `INSERT` statements are written, and reading them in file
order with drops and revokes applied answers "what will this database hold" as
exactly as connecting to one. So W3, W6 and W8 are measured here rather than
deferred, and W4 is measured here for the part of the read surface the migrations
name in words.

Three things genuinely need a catalogue and are not reimplemented here, because
`src/redkraken/integrity.py` already owns the idea for SQL checkers -- its own
words, at the top of that file, are "The defect that registry exists to prevent
is a checker with no caller." What belongs there and not here is:

* the part of the agent read surface that `0030_corpus_corrections.sql` seeds
  from `has_column_privilege`, which is a question about privileges that only a
  server holds. W4 measures the relations later migrations name and reports that
  the catalogue-seeded remainder is owed a standing check;
* W6's column-writer and constraint-falsifiability arms, which need every CHECK
  expression resolved against the column defaults a server computes;
* W7 in full, which needs the implication graph of every guard on every table.

For those, this gate asserts that the check is registered in `standing_checks`
and stops there.

## Why this ships with a register rather than with an empty result

Every finding tickets 102 to 129 own is a row this gate reports today, so a gate
with no way to record a known gap would be a gate nobody could switch on, and a
gate somebody switches off measures nothing. The shape already exists twice in
this repository. `roster.FORBIDDEN_BUILTINS` states, for every built-in a role
does not hold, why it does not hold it, and the compile refuses an unclassified
one. `check_audit`'s `owed:NN` names, for a requirement whose work is not
finished, the open ticket that owes the verification.

This file takes the second spelling. A gap is either wired, `owed:NN` or
`decided:NN`, and `OWED_GAPS` below is the whole of the last two. Both
directions fail: a gap this gate finds and the register does not hold is a
defect, and a register row that no longer corresponds to a gap is equally a
defect, because it is the gate excusing something that is fine and it would go
on excusing a regression back into it. An `owed` row naming a ticket that has
been resolved fails for the same reason it does in `check_audit`: work that is
finished cannot owe anything.

`decided:NN` is the answer to a gap that is not work. Some verbs are reached
from a terminal by a human or asserted against by the suite, and both are
callers this gate cannot see; W3 asks "does anything execute this" and gets the
honest answer "nothing this gate can read", which is a finding rather than a
defect. Writing that as `owed` would be promising a caller nobody intends to
build. So the row names the resolved ticket that read the verb and recorded
why, and the ticket number is the pointer to the argument. The rule inverts
with the spelling: a `decided` row must name a ticket that *is* resolved, since
a decision still under discussion is not one. Ticket 138 is the first of these,
for `find_in_database`.

`runtime_verb_surface` is deliberately not that register. It is catalogue-seeded
-- `20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:169-173`
inserts what the live catalogue already granted -- and it answers "may the
runtime execute this", which is a question about privilege. W3 asks "does
anything execute this", which is a question about callers, and a verb registered
there and called by nothing is invisible to it by construction.

Run it as a script with the repository on the path and the user site disabled --
`PYTHONPATH=$PWD python3 -s tools/check_wiring.py` -- because a `tools` package
in site-packages shadows this one and both flags are needed to reach the local
namespace package.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from tools.check_audit import RESOLVED, Ticket, read_tickets, spec_root
from tools.check_baseline import CHECKOUT, BaselineError, read_status


#: The trees this gate reads. Named as paths rather than imported, because a gate
#: that imported the application would need the application's world: a database
#: driver, an agent SDK and an interpreter that has the package installed. The
#: whole point of reading the tree is that the answer is the same everywhere.
PACKAGE = CHECKOUT / "src" / "redkraken"
MIGRATIONS = PACKAGE / "migrations"
PLAYBOOKS = PACKAGE / "playbooks"
SKILLS = PACKAGE / "skills"

#: The prefix a register row writes instead of a fix, and the marker a ticket
#: number is read out of it by. The same two strings `check_audit` uses, so that
#: a reader who knows one register knows this one.
OWED = "owed:"
TICKET = re.compile(r"^owed:(\d+)$")

#: The second spelling, and the only other one. `owed:NN` says an open ticket
#: still has to do the work; `decided:NN` says a resolved ticket read the gap
#: and recorded that there is nothing to do. The two are exact opposites about
#: the ticket -- an `owed` row naming a resolved ticket is a lie, and a
#: `decided` row naming an open one is a decision still being argued -- and
#: identical about the gap: both require it to be present, so neither can go on
#: excusing an absence that has been filled.
DECIDED = "decided:"
DECIDED_TICKET = re.compile(r"^decided:(\d+)$")

#: The role whose surface these audits are about. A verb granted only to an
#: operator role is reached from a terminal by a human, and this gate cannot see
#: that; a verb granted to the runtime is reached by this code or by nothing.
RUNTIME = "rk2_runtime"

#: The one ticket that resolves the split criterion 3 describes, quoted where
#: the reader meets it: the standing checks W4's catalogue half, W6's column and
#: constraint arms and W7 need do not exist yet, and the gate says so rather than
#: pretending the question was asked.
STANDING = "standing check"


class WiringError(Exception):
    """A declaration with nothing on the other end of it, or a register that lies."""


@dataclass(frozen=True)
class Gap:
    """One declared thing with no producer, no consumer or no caller.

    The key is what the register is written against, so it has to be stable
    across runs and across machines: the check that found it and the name of the
    thing, and nothing derived from a line number or a count. The detail is for
    the person reading the refusal and is never compared.
    """

    check: str
    subject: str
    detail: str

    @property
    def key(self) -> str:
        return f"{self.check} {self.subject}"


#: The register. One row per known gap, naming the open ticket that owes the work
#: that closes it, grouped by the check that finds it. Rows are added by measuring
#: the tree, never by guessing: every one of these was reported by this gate
#: before it was written down, which is the only way a register can be honest
#: about what it excuses.
OWED_GAPS: dict[str, str] = {
    # W1. Two Contracts are declared and served by nothing. Ticket 105 decides
    # whether the two queue requests get a handler or a deletion.
    "W1 mcp__rk2__request_report": "owed:105",
    "W1 mcp__rk2__request_validation": "owed:105",

    # W3. The four evidence profiles dispatch off a Task column nothing writes,
    # which is the whole of ticket 120.
    "W3 evidence_profile_allowed_receipt_only": "owed:120",
    "W3 evidence_profile_browser_run_evidence": "owed:120",
    "W3 evidence_profile_identity_differential": "owed:120",
    "W3 evidence_profile_successful_tool_run": "owed:120",
    # The cross-table secret sweep, and the one row in this register that is a
    # decision rather than a debt. Ticket 138 read it: seven callers in
    # `tests/test_database.py` and none in `src/`, which is what it is for. The
    # verb answers about what the *calling* role may read
    # (`20260814T020000Z:791-798`), so a fixed runtime caller would be the one
    # thing it must not have, and a sweep of every column of every table is an
    # operator's command after an incident rather than something a run does.
    "W3 find_in_database": "decided:138",

    # W4. Every relation the migrations put on the agent's own read surface that
    # no Contract reaches, plus the catalogue-seeded remainder that only a
    # standing check can measure. Ticket 129 decides each one either way. It
    # counts twenty-one from a hand reading; this is twenty-seven, because four
    # of the reports tables reach the surface through a statement that selects
    # its columns out of the catalogue and names the relations in a `WHERE`
    # (`0034_reports.sql:1084-1092`), which a reading that only looked at
    # `VALUES` rows would miss, and `state_read_surface` is itself on it.
    #
    # `tool_runs` was on this list and is not any more, and it left by being
    # read rather than by being decided: ticket 107's `refresh_packet` reaches
    # it, so the gap this row recorded is measurably gone. The other three of
    # 129's four -- `tool_run_artifacts`, `tool_run_inputs`, `tool_run_paths` --
    # are untouched, because a `tool_runs` record is not its inputs or its paths.
    "W4 artifact_refs": "owed:129",
    "W4 browser_runs": "owed:129",
    "W4 browser_step_results": "owed:129",
    "W4 browser_steps": "owed:129",
    "W4 entity_provenance": "owed:129",
    "W4 events": "owed:129",
    "W4 finding_chain_step_citations": "owed:129",
    "W4 finding_chain_steps": "owed:129",
    "W4 finding_effects": "owed:129",
    "W4 negative_knowledge": "owed:129",
    "W4 negative_knowledge_retests": "owed:129",
    "W4 program_known_issues": "owed:129",
    "W4 program_required_headers": "owed:129",
    "W4 redaction_rules": "owed:129",
    "W4 relationships": "owed:129",
    "W4 report_blocks": "owed:129",
    "W4 report_effects": "owed:129",
    "W4 report_mechanisms": "owed:129",
    "W4 report_renderings": "owed:129",
    "W4 report_template_blocks": "owed:129",
    "W4 report_templates": "owed:129",
    "W4 surface_facts": "owed:129",
    "W4 test_run_receipts": "owed:129",
    "W4 tool_run_artifacts": "owed:129",
    "W4 tool_run_inputs": "owed:129",
    "W4 tool_run_paths": "owed:129",
    "W4 state_read_surface": "owed:129",

    # W5. An element a proposal accepts and no read verb returns, and a label
    # class an act tool mints and no read verb resolves. The three fields a tool
    # answer dropped on the way to the model are gone: ticket 108 put `stderr`,
    # `timed_out` and `overflowed` on `tool.serve`'s answer, so the three rows
    # that owed them are removed rather than re-pointed.
    #
    # The label class is gone the same way. `tool_run` was here because a run
    # was handed a Tool Run label and had no verb that took one; ticket 107's
    # `refresh_packet` takes `tool_run_labels`, so the row is removed rather
    # than re-pointed. What is left is the one element side of this gate.
    "W5 relationships": "owed:129",

    # W6. Twelve tables nothing inserts into and three views nothing selects.
    # `cross_program_exempt_fks`, `program_isolation_candidates` and `secret_dek`
    # are not among them: all three are read as harmless by the database audit
    # and excluded by name in `producer_gaps`, above `BY_DESIGN`, rather than
    # owed here.
    "W6 agent_sessions": "owed:119",
    "W6 artifacts_due_for_purge": "owed:122",
    "W6 report_queue": "owed:105",

    # W7. The one open contradiction, and the standing check that would have to
    # find the next one. Ticket 116 narrows the two triggers that refuse the one
    # Receipt a probe-only transport claim is allowed to rest on.
    "W7 guard_satisfiability": "owed:116",

    # W8. The declared write target with neither a writer nor a handler.
    "W8 report_queue": "owed:105",

    # W9. Five declared property classes nothing emits, and the four Playbook
    # bodies that name one as though it did. Ticket 100 established that the
    # classes exist and that the missing half is an emitter, and put that work on
    # ticket 101.
    "W9 authentication.recovery_flow": "owed:101",
    "W9 information_disclosure.identifier_oracle": "owed:101",
    "W9 rate_limiting.per_origin": "owed:101",
    "W9 rate_limiting.resource_cost": "owed:101",
    "W9 transport.certificate_trust": "owed:101",
    "W9 api rate_limiting.per_origin": "owed:101",
    "W9 authentication authentication.recovery_flow": "owed:101",
    "W9 graphql rate_limiting.resource_cost": "owed:101",
    "W9 http-desync transport.certificate_trust": "owed:101",

    # W10. The corpus instructs a browser mission through a tool that runs no
    # browser. The other two readings this register carried are both gone, and
    # both left by being answered rather than by being excused.
    #
    # An identity on a request that carries none: ticket 97 settled that
    # `identity_slot` is a property of the Tool run rather than an argument and
    # rewrote the twenty bodies that instructed one, so the twenty rows that
    # owed it are removed rather than re-pointed.
    #
    # An analysis of bytes the same body just told the model to fetch: ticket
    # 106 put `request_artifact` and `response_artifact` on the answer to
    # `mcp__rk2__http_request`, so a body that says fetch and then analyse is
    # now naming a call the run can make. The twenty rows that owed it are gone
    # for the same reason -- and the check itself changed with them, because it
    # had carried "an exchange returns no Artifact label" as a premise in a
    # comment and would have gone on reporting all twenty forever. It reads
    # `_spend`'s answer now.
    "W10 browser-evidence": "owed:99",
}


# ---------------------------------------------------------------------------
# Reading SQL. A migration is not a document a regular expression can be pointed
# at: this corpus writes function names inside comments constantly, quotes whole
# statements inside `COMMENT ON` strings, and carries a hundred and forty
# dollar-quoted bodies with SQL inside them. A scan that did not know which of
# those it was looking at would score every mention of `state_severity` in a
# comment as a caller, which is exactly the false positive that made the audit
# hand-verify its own numbers. So the file is cut into runs first and every
# reading afterwards is taken from the code runs alone.
# ---------------------------------------------------------------------------

DOLLAR = re.compile(r"\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$")
BLANK = re.compile(r"[^\n]")


def segments(sql: str) -> list[tuple[str, int, int]]:
    """One SQL file as runs of code, comment and quoted text, in file order.

    Newlines are what the caller keeps: a run is returned as a span rather than
    as a string so that the masked copy below is the same length as the original
    and a position in one is a position in the other.
    """
    found: list[tuple[str, int, int]] = []
    length, index, start = len(sql), 0, 0
    while index < length:
        character = sql[index]
        if sql.startswith("--", index):
            stop = sql.find("\n", index)
            stop = length if stop < 0 else stop
            kind = "comment"
        elif sql.startswith("/*", index):
            stop = sql.find("*/", index + 2)
            stop = length if stop < 0 else stop + 2
            kind = "comment"
        elif character == "'":
            stop, kind = index + 1, "quoted"
            while stop < length:
                if sql[stop] == "'":
                    if sql.startswith("''", stop):
                        stop += 2
                        continue
                    stop += 1
                    break
                stop += 1
        elif character == "$" and DOLLAR.match(sql, index):
            tag = DOLLAR.match(sql, index).group(0)
            closing = sql.find(tag, index + len(tag))
            stop = length if closing < 0 else closing + len(tag)
            kind = "quoted"
        else:
            index += 1
            continue
        if start < index:
            found.append(("code", start, index))
        found.append((kind, index, stop))
        index = start = stop
    if start < length:
        found.append(("code", start, length))
    return found


def masked(sql: str, runs: list[tuple[str, int, int]]) -> str:
    """The same file with every comment and every quoted run blanked out.

    Blanked rather than removed, so that a match's position in the mask is its
    position in the file and statements can still be applied in the order they
    are written.
    """
    return "".join(
        sql[start:stop] if kind == "code" else BLANK.sub(" ", sql[start:stop])
        for kind, start, stop in runs
    )


def inner(sql: str, start: int, stop: int) -> str:
    """The code inside one dollar-quoted body, with its own comments and strings gone."""
    tag = DOLLAR.match(sql, start).group(0)
    body = sql[start + len(tag):stop - len(tag)]
    return masked(body, segments(body))


CREATE_FUNCTION = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?([a-z0-9_]+)\s*\(", re.I
)
DROP_FUNCTION = re.compile(
    r"DROP\s+FUNCTION\s+(?:IF\s+EXISTS\s+)?(?:public\.)?([a-z0-9_]+)\s*\(", re.I
)
GRANT_FUNCTION = re.compile(
    r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+(?:public\.)?([a-z0-9_]+)\s*\([^)]*\)"
    r"\s*TO\s+([a-z0-9_,\s]+?)\s*;",
    re.I,
)
REVOKE_FUNCTION = re.compile(
    r"REVOKE\s+(?:ALL|EXECUTE)[A-Za-z ,]*\bON\s+FUNCTION\s+(?:public\.)?([a-z0-9_]+)\s*\([^)]*\)"
    r"\s*FROM\s+([a-z0-9_,\s]+?)\s*;",
    re.I,
)
CREATE_TABLE = re.compile(
    r"CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z0-9_]+)", re.I
)
DROP_TABLE = re.compile(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?([a-z0-9_]+)", re.I)
RENAME_TABLE = re.compile(
    r"ALTER\s+TABLE\s+(?:public\.)?([a-z0-9_]+)\s+RENAME\s+TO\s+([a-z0-9_]+)", re.I
)
CREATE_VIEW = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:public\.)?([a-z0-9_]+)", re.I
)
DROP_VIEW = re.compile(r"DROP\s+VIEW\s+(?:IF\s+EXISTS\s+)?(?:public\.)?([a-z0-9_]+)", re.I)
TRIGGER_BINDING = re.compile(
    r"EXECUTE\s+(?:PROCEDURE|FUNCTION)\s+(?:public\.)?([a-z0-9_]+)\s*\(", re.I
)
INSERT_INTO = re.compile(r"INSERT\s+INTO\s+(?:public\.)?([a-z0-9_]+)", re.I)
SELECTED = re.compile(r"\b(?:FROM|JOIN)\s+(?:public\.)?([a-z][a-z0-9_]*)", re.I)

#: How a migration puts a relation on the agent's read surface without writing a
#: row per column: it selects the columns out of the catalogue and names the
#: relations in a `WHERE`. That is still a declaration in words, and the only
#: statement that declares nothing is the one with no relation list at all.
NAMED_RELATIONS = re.compile(r"relname\s+IN\s*\(([^)]*)\)", re.I)
GENERATED = re.compile(r"([a-z0-9_]+)\s+boolean\s+GENERATED\s+ALWAYS\s+AS\s*\(", re.I)
INSERT_COLUMNS = re.compile(r"INSERT\s+INTO\s+(?:public\.)?([a-z0-9_]+)\s*\(([^)]*)\)", re.I)
UPDATE_SET = re.compile(r"UPDATE\s+(?:public\.)?([a-z0-9_]+)\s+SET\s+([a-z0-9_]+)", re.I)
ASSIGNED = re.compile(r"NEW\.([a-z0-9_]+)\s*:=", re.I)
CALL = re.compile(r"\b([a-z][a-z0-9_]*)\s*\(")
IDENTIFIER = re.compile(r"\b([a-z][a-z0-9_]*)\b")

#: The words a generated column's expression is full of that are not columns of
#: the table it is on. Listed rather than resolved against the table's own
#: definition, because the reading that needs them asks whether every column the
#: expression depends on has a writer, and a keyword with no writer is not a
#: finding about anything.
SQL_WORDS = frozenset(
    """and or not is null true false in any all array select from where exists case when
    then else end like between cast as text boolean integer bigint numeric uuid jsonb
    interval timestamptz inet cidr smallint real double precision char varchar coalesce
    nullif length upper lower trim substring position octet_length cardinality unnest
    to_jsonb jsonb_typeof jsonb_array_length jsonb_each row constraint check on""".split()
)


@dataclass(frozen=True)
class Catalogue:
    """The database this migration corpus describes, read in file order.

    One object because the statements only mean anything applied in order: a
    function dropped and recreated in the same file is one function, a grant
    revoked three migrations later is not a grant, and a reader that took the
    statements as a set would report both halves of every correction the corpus
    has ever made.
    """

    #: Every live function, by name, at the migration that last defined it.
    functions: dict[str, str]
    #: What each function's body calls, by name, restricted to live functions.
    calls: dict[str, frozenset[str]]
    #: Which roles hold EXECUTE on each live function.
    grants: dict[str, frozenset[str]]
    #: Every function a `CREATE TRIGGER` binds, and every function a registered
    #: standing check's query names. These are the two root classes that are not
    #: Python, and without them every `check_*` in the corpus is a false positive.
    triggers: frozenset[str]
    standing: frozenset[str]
    #: Live tables and views, and the three kinds of place a row can come from.
    tables: dict[str, str]
    views: dict[str, str]
    inserted_by_function: frozenset[str]
    inserted_by_migration: frozenset[str]
    #: Every column any writer names, as `table.column`.
    written: frozenset[str]
    #: Every relation something selects from, anywhere in the corpus. A view's
    #: own definition never names itself, so a view absent from this is a view
    #: nothing reads.
    selected: frozenset[str]
    #: Boolean generated columns, as `table.column` against the identifiers their
    #: expression reads.
    generated: dict[str, frozenset[str]]
    #: The relations the migrations put on the agent's read surface in words.
    read_surface: frozenset[str]
    #: Whether the read surface is also seeded from the live catalogue, which is
    #: the half of W4 that no file can answer.
    catalogue_seeded: bool
    #: The seeded vocabularies W9 and W10 are measured against.
    property_classes: frozenset[str]
    property_families: frozenset[str]
    unmakeable: frozenset[str]
    evidential: dict[str, bool]
    programs: dict[str, str]
    program_arguments: dict[str, dict[str, str]]
    program_roles: dict[str, frozenset[str]]


def statement(sql: str, start: int) -> str:
    """One statement from where it begins to its semicolon, quotes and all.

    Taken off the original rather than off the mask, because what a seeding
    statement says is in its string literals and the mask is exactly the thing
    that removes them.
    """
    stop = sql.find(";", start)
    return sql[start:] if stop < 0 else sql[start:stop]


def literals(text: str) -> list[str]:
    """Every single-quoted literal in one statement, in the order it writes them."""
    return [found.replace("''", "'") for found in re.findall(r"'((?:[^']|'')*)'", text)]


def rows(text: str, columns: int) -> list[tuple[str, ...]]:
    """A `VALUES` list read as tuples of its leading literals.

    The seeded vocabularies are written as one parenthesised row per line with
    the identifying columns first, so reading each row's opening literals is
    enough to answer what the row is about without parsing an expression
    grammar. A row whose leading columns are not literals is skipped rather than
    guessed at.
    """
    found = []
    for opening in re.finditer(r"\(\s*'", text):
        row = literals(text[opening.start():])
        if len(row) >= columns:
            found.append(tuple(row[:columns]))
    return found


def read_catalogue(root: Path = MIGRATIONS) -> Catalogue:
    """Every migration, applied in the order the runner would apply them."""
    functions: dict[str, str] = {}
    calls: dict[str, set[str]] = {}
    grants: dict[str, set[str]] = {}
    tables: dict[str, str] = {}
    views: dict[str, str] = {}
    triggers: set[str] = set()
    standing: set[str] = set()
    by_function: set[str] = set()
    by_migration: set[str] = set()
    written: set[str] = set()
    selected: set[str] = set()
    generated: dict[str, set[str]] = {}
    surface: set[str] = set()
    seeded = False
    classes: set[str] = set()
    families: set[str] = set()
    unmakeable: set[str] = set()
    evidential: dict[str, bool] = {}
    programs: dict[str, str] = {}
    arguments: dict[str, dict[str, str]] = {}
    program_roles: dict[str, set[str]] = {}

    for path in sorted(root.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        runs = segments(sql)
        code = masked(sql, runs)
        bodies = [(start, stop) for kind, start, stop in runs if kind == "quoted" and sql[start] == "$"]

        # Every statement that changes what the database holds, applied where it
        # is written. A file that drops a function and recreates it three lines
        # later is the corpus's ordinary way of changing a signature, and a
        # reader that applied the drop last would lose the function.
        events: list[tuple[int, str, str, str]] = []
        for found in CREATE_FUNCTION.finditer(code):
            body = next(
                (inner(sql, start, stop) for start, stop in bodies if start >= found.end()), ""
            )
            events.append((found.start(), "function", found.group(1), body))
        for found in DROP_FUNCTION.finditer(code):
            events.append((found.start(), "drop function", found.group(1), ""))
        for found in GRANT_FUNCTION.finditer(code):
            events.append((found.start(), "grant", found.group(1), found.group(2)))
        for found in REVOKE_FUNCTION.finditer(code):
            events.append((found.start(), "revoke", found.group(1), found.group(2)))
        for found in CREATE_TABLE.finditer(code):
            events.append((found.start(), "table", found.group(1), ""))
        for found in DROP_TABLE.finditer(code):
            events.append((found.start(), "drop table", found.group(1), ""))
        for found in RENAME_TABLE.finditer(code):
            events.append((found.start(), "rename", found.group(1), found.group(2)))
        for found in CREATE_VIEW.finditer(code):
            events.append((found.start(), "view", found.group(1), ""))
        for found in DROP_VIEW.finditer(code):
            events.append((found.start(), "drop view", found.group(1), ""))

        for _, kind, name, payload in sorted(events, key=lambda event: event[0]):
            if kind == "function":
                functions[name] = path.name
                calls.setdefault(name, set()).update(CALL.findall(payload))
                by_function.update(INSERT_INTO.findall(payload))
                written.update(_columns(payload))
                selected.update(SELECTED.findall(payload))
            elif kind == "drop function":
                functions.pop(name, None)
                grants.pop(name, None)
                calls.pop(name, None)
            elif kind == "grant":
                grants.setdefault(name, set()).update(re.split(r"[,\s]+", payload.strip()))
            elif kind == "revoke":
                for role in re.split(r"[,\s]+", payload.strip()):
                    grants.get(name, set()).discard(role)
            elif kind == "table":
                tables[name] = path.name
            elif kind == "drop table":
                tables.pop(name, None)
            elif kind == "rename" and name in tables:
                tables[payload] = tables.pop(name)
            elif kind == "view":
                views[name] = path.name
            elif kind == "drop view":
                views.pop(name, None)

        triggers.update(TRIGGER_BINDING.findall(code))
        by_migration.update(INSERT_INTO.findall(code))
        written.update(_columns(code))
        selected.update(SELECTED.findall(code))
        for found in GENERATED.finditer(code):
            depth, index = 0, found.end() - 1
            while index < len(code):
                depth += (code[index] == "(") - (code[index] == ")")
                if not depth:
                    break
                index += 1
            generated[found.group(1)] = set(IDENTIFIER.findall(code[found.end():index]))
        # The seeded rows every reading after this one is measured against. Each
        # is read out of its own `INSERT`, in the order the corpus writes them,
        # so that a later migration correcting an earlier one is the correction
        # and not a second opinion.
        # The read surface is the one seeded table whose statements have to be
        # applied in order as well: the migration that scoped Artifacts deletes
        # two relations and re-inserts them narrowed, in that order and in one
        # file. A statement with no `VALUES` names nothing: it seeds the surface
        # from the live catalogue, which is the half of W4 no file can answer.
        moves = [
            (found.start(), "add", statement(sql, found.start()))
            for found in re.finditer(r"INSERT\s+INTO\s+state_read_surface\b", code, re.I)
        ]
        moves.extend(
            (found.start(), "remove", statement(sql, found.start()))
            for found in re.finditer(r"DELETE\s+FROM\s+state_read_surface\b", code, re.I)
        )
        for _, kind, text in sorted(moves, key=lambda move: move[0]):
            if kind == "remove":
                surface.difference_update(literals(text))
            elif re.search(r"\bVALUES\b", text, re.I):
                surface.update(pair[0] for pair in rows(text, 2))
            elif NAMED_RELATIONS.search(text):
                surface.update(literals(NAMED_RELATIONS.search(text).group(1)))
            else:
                seeded = True
        for table, into in (
            ("property_classes", classes),
            ("property_class_families", families),
        ):
            for found in re.finditer(rf"INSERT\s+INTO\s+{table}\b", code, re.I):
                into.update(row[0] for row in rows(statement(sql, found.start()), 1))
        for found in re.finditer(r"INSERT\s+INTO\s+transport_makeability\b", code, re.I):
            for row in rows(statement(sql, found.start()), 2):
                if row[1] == "unmakeable":
                    unmakeable.add(row[0])
        for found in re.finditer(r"INSERT\s+INTO\s+observation_kinds\b", code, re.I):
            text = statement(sql, found.start())
            for opening in re.finditer(r"\(\s*'([a-z0-9_]+)'\s*,\s*'[^']*'\s*,\s*(true|false)", text):
                evidential[opening.group(1)] = opening.group(2) == "true"
        for found in re.finditer(r"INSERT\s+INTO\s+offline_tools\b", code, re.I):
            text = statement(sql, found.start())
            declared = INSERT_COLUMNS.search(text)
            named = [column.strip() for column in declared.group(2).split(",")] if declared else []
            for row in rows(text[declared.end():] if declared else text, 1):
                programs[row[0]] = "skill" if "skill" in named else "tool"
        for found in re.finditer(r"INSERT\s+INTO\s+offline_tool_arguments\b", code, re.I):
            for row in rows(statement(sql, found.start()), 2):
                arguments.setdefault(row[0], {})[row[1]] = ""
        for found in re.finditer(r"INSERT\s+INTO\s+offline_tool_roles\b", code, re.I):
            for row in rows(statement(sql, found.start()), 2):
                program_roles.setdefault(row[0], set()).add(row[1])
        for found in re.finditer(r"INSERT\s+INTO\s+standing_checks\b", code, re.I):
            standing.update(CALL.findall(statement(sql, found.start())))

    # An argument's kind is the third literal of its row and the second is its
    # name, so the kinds are read in a second pass over the same statements to
    # keep `rows` answering one question.
    for path in sorted(root.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        code = masked(sql, segments(sql))
        for found in re.finditer(r"INSERT\s+INTO\s+offline_tool_arguments\b", code, re.I):
            text = statement(sql, found.start())
            for opening in re.finditer(
                r"\(\s*'([a-z0-9_]+)'\s*,\s*'([a-z0-9_]+)'\s*,\s*\d+\s*,\s*[^,]+,\s*'([a-z]+)'", text
            ):
                arguments.setdefault(opening.group(1), {})[opening.group(2)] = opening.group(3)

    live = frozenset(functions)
    return Catalogue(
        functions=functions,
        calls={name: frozenset(named) & live for name, named in calls.items()},
        grants={
            name: frozenset(roles)
            for name, roles in grants.items()
            if roles and name in functions
        },
        triggers=frozenset(triggers) & live,
        standing=frozenset(standing) & live,
        tables=tables,
        views=views,
        inserted_by_function=frozenset(by_function),
        inserted_by_migration=frozenset(by_migration),
        written=frozenset(written),
        selected=frozenset(selected),
        generated={name: frozenset(reads) for name, reads in generated.items()},
        read_surface=frozenset(surface),
        catalogue_seeded=seeded,
        property_classes=frozenset(classes),
        property_families=frozenset(families),
        unmakeable=frozenset(unmakeable),
        evidential=evidential,
        programs=programs,
        program_arguments=arguments,
        program_roles={name: frozenset(roles) for name, roles in program_roles.items()},
    )


def _columns(code: str) -> set[str]:
    """Every `table.column` some writer in this text fills.

    Three shapes, because there are three ways a row gets a value: an `INSERT`
    that names its columns, an `UPDATE ... SET`, and a trigger assigning to
    `NEW`. The third has no table in it and is answered by name alone, which is
    the honest bound on what a file reader can say: a column called `purpose`
    assigned in some trigger counts as written wherever `purpose` lives.
    """
    found: set[str] = set()
    for insert in INSERT_COLUMNS.finditer(code):
        found.update(
            f"{insert.group(1)}.{column.strip()}"
            for column in insert.group(2).split(",")
            if re.fullmatch(r"\s*[a-z0-9_]+\s*", column)
        )
    found.update(f"{update.group(1)}.{update.group(2)}" for update in UPDATE_SET.finditer(code))
    found.update(ASSIGNED.findall(code))
    return found


# ---------------------------------------------------------------------------
# Reading Python. With `ast` and never by importing, for `check_audit`'s reason
# and one more of its own: importing `redkraken.roster` would pull in the agent
# SDK and a database driver, and this gate has to answer the same on a machine
# that holds neither. Docstrings are not read as references. A docstring is
# prose, and prose naming a function is exactly the thing the audits had to
# hand-verify away before their own numbers meant anything.
# ---------------------------------------------------------------------------

WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def constants(tree: ast.Module) -> dict[str, ast.expr]:
    """Every module-level name bound to an expression, by name."""
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value
    return found


def value(node: ast.expr | None, known: dict[str, ast.expr], depth: int = 0):
    """One literal, with module constants resolved through as far as they go.

    The roster writes its contracts against named constants -- `READ`,
    `ENTITY_TYPES`, `_PAGE` -- so a reader that stopped at `ast.literal_eval`
    would see a name where the declaration is. What it does not do is evaluate:
    a value this cannot resolve comes back as `None` and the reading that wanted
    it says so, rather than being quietly given something else.
    """
    if depth > 8 or node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(value(element, known, depth + 1) for element in node.elts)
    if isinstance(node, ast.Dict):
        return {
            value(key, known, depth + 1): value(item, known, depth + 1)
            for key, item in zip(node.keys, node.values)
        }
    if isinstance(node, ast.Name):
        return value(known.get(node.id), known, depth + 1)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = value(node.left, known, depth + 1), value(node.right, known, depth + 1)
        if isinstance(left, tuple) and isinstance(right, tuple):
            return left + right
        if isinstance(left, str) and isinstance(right, str):
            return left + right
    return None


def references(root: Path, skip: frozenset[str] = frozenset()) -> frozenset[str]:
    """Every name this package's code names, out of its code rather than its prose.

    A SQL function is called from Python inside a string -- `"SELECT
    park_for_human($1::uuid)"` -- so string constants are read for the words in
    them, which is what makes a call site visible at all. Docstrings are the one
    kind of string left out, and leaving them out is what separates a caller from
    a sentence about a caller.
    """
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if path.name in skip:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        prose = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    prose.add(id(first.value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.add(node.name)
            elif isinstance(node, ast.arg):
                found.add(node.arg)
            elif isinstance(node, ast.keyword) and node.arg:
                found.add(node.arg)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) not in prose:
                    found.update(WORD.findall(node.value))
    return frozenset(found)


def python_inserts(root: Path = PACKAGE) -> frozenset[str]:
    """Every table this package writes a row into, out of the statements it holds."""
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        for statement_text in re.findall(
            r"INSERT\s+INTO\s+([a-z][a-z0-9_]*)", path.read_text(encoding="utf-8"), re.I
        ):
            found.add(statement_text)
    return frozenset(found)


def named(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """One function of a module, wherever in it that function is written."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def fields(tree: ast.Module, name: str) -> tuple[str, ...]:
    """The annotated fields of one dataclass, in declaration order."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return tuple(
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            )
    return ()


def carried(node: ast.AST) -> frozenset[str]:
    """Every name one function body mentions, however it mentions it.

    Deliberately generous. The question this answers is whether a field of the
    value the function was handed appears anywhere in what it does with it, and
    a generous reading makes a report of "this field is dropped" hard to argue
    with: the function does not so much as say the word.
    """
    found: set[str] = set()
    for inner_node in ast.walk(node):
        if isinstance(inner_node, ast.Attribute):
            found.add(inner_node.attr)
        elif isinstance(inner_node, ast.Name):
            found.add(inner_node.id)
        elif isinstance(inner_node, ast.arg):
            found.add(inner_node.arg)
        elif isinstance(inner_node, ast.Constant) and isinstance(inner_node.value, str):
            found.add(inner_node.value)
    return frozenset(found)


def answers(tree: ast.Module, name: str) -> frozenset[str]:
    """Every key the dict one function hands a model, one merge deep.

    `carried` above is deliberately generous because it reports a loss, and a
    generous reading makes "this function does not so much as say the word" hard
    to argue with. This one reports the opposite -- that something *is* handed
    over -- so generosity here is the direction that goes wrong quietly: a key
    named in a comment or in a description string would close a gap that is
    still open. So it reads keys and not mentions.

    One level of `**merged()` is followed, because that is how this package
    writes a key that is only sometimes there: the conditional half is built in
    a helper and merged into the answer, and a reading that stopped at the `**`
    would score exactly the keys a ticket just added as absent. One level and
    not a walk -- a helper merging a helper is a shape nothing here has, and
    following it forever would make this a reimplementation of the interpreter.
    """
    body = named(tree, name)
    if body is None:
        return frozenset()
    found: set[str] = set()
    for node in ast.walk(body):
        if isinstance(node, ast.Return):
            found |= _answer_keys(node.value, tree)
    return frozenset(found)


def _answer_keys(node: ast.AST | None, tree: ast.Module, *, follow: bool = True) -> frozenset[str]:
    """The keys one returned expression can carry, for the two shapes this tree writes.

    A literal dict answers with its own literal keys. A dict comprehension
    answers with the names it iterates -- `{key: ... for key in ("a", "b")}` --
    which is how a handler says "these keys, each one only if there is something
    to put in it". Anything else answers nothing, and answering nothing is the
    safe direction: it reports a gap that may have been closed, which somebody
    reads, rather than excusing one that is still open, which nobody does.
    """
    found: set[str] = set()
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                found.add(key.value)
            elif (
                key is None
                and follow
                and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
            ):
                merged = named(tree, value.func.id)
                for inner in ast.walk(merged) if merged else ():
                    if isinstance(inner, ast.Return):
                        found |= _answer_keys(inner.value, tree, follow=False)
    elif isinstance(node, ast.DictComp):
        found |= {
            constant.value
            for generator in node.generators
            for constant in ast.walk(generator.iter)
            if isinstance(constant, ast.Constant) and isinstance(constant.value, str)
        }
    return frozenset(found)


@dataclass(frozen=True)
class Surface:
    """What the Python side of this harness declares a model may do."""

    #: Every model-facing tool, at its group, its direction, what it reads, what
    #: it writes and what it takes.
    contracts: dict[str, dict]
    #: The authority classes and the tools in each.
    groups: dict[str, tuple[str, ...]]
    #: Each role's tool groups.
    roles: dict[str, tuple[str, ...]]
    #: What a launch serves, derived the way `agent.SERVED` derives it.
    served: tuple[str, ...]
    #: The bare names `_launch.server` builds a tool for. `DESCRIPTIONS` is that
    #: list: every tool is built as `@tool(name, DESCRIPTIONS[name], ...)`, so a
    #: tool built without a description does not import and a description with no
    #: tool is what this compares against `served`.
    built: tuple[str, ...]
    #: Every name the package's code names, for the reachability roots.
    names: frozenset[str]
    #: Every table this package's own SQL inserts into, which is the other half
    #: of "has a producer": a table filled from Python has one just as much as a
    #: table filled by a function body does.
    inserts: frozenset[str]
    #: The same, with the module that declares the contracts left out, so that a
    #: declaration cannot be its own consumer.
    consumers: frozenset[str]
    #: The boundaries W5 measures, as the fields a runtime value carries against
    #: the names the function that answers a model mentions.
    boundaries: tuple[tuple[str, tuple[str, ...], frozenset[str]], ...]
    #: Every key the answer to one exchange carries. W10's fetch-then-analyse
    #: reading is about this and about nothing else, and it is read here rather
    #: than stated in that check because a statement about the answer is a thing
    #: a gate cannot notice has stopped being true.
    exchange: frozenset[str]


#: The three places a rich runtime value becomes a model-facing dict, named as
#: the module and function that does the narrowing and the class it narrows.
#: Written down rather than discovered, because "this is a boundary" is a
#: judgement about the design and the gate's job is to hold each one to the rule
#: rather than to guess where they are.
BOUNDARIES = (
    ("tool.serve", "tool.py", "serve", "isolation.py", "ToolProcess"),
    ("_launch._spend", "_launch.py", "_spend", "proxy.py", "Answer"),
)

#: Where one exchange's answer is built. `mcp__rk2__http_request` is served by
#: `_launch._request`, which hands the model whatever `_spend` returns, so the
#: keys of that dict are the whole of what a run learns from a request. W10 asks
#: whether an Artifact label is among them.
EXCHANGE = "_spend"

#: What an Artifact label looks like as a key of an answer: `artifact` itself, or
#: a name qualified with the half it points at. Ticket 106 hands back two --
#: `request_artifact` and `response_artifact` -- because `compare_responses`
#: takes an ordered `first` and `second` and an unordered pair would push that
#: decision onto a model. Either spelling satisfies the reading; the check is
#: that a run holding a Receipt label also holds a name for the bytes.
ARTIFACT_KEY = re.compile(r"(?:[a-z_]+_)?artifact")


def read_surface(root: Path = PACKAGE) -> Surface:
    """The roster, the launch and the boundaries, read once."""
    roster = ast.parse((root / "roster.py").read_text(encoding="utf-8"))
    agent = ast.parse((root / "agent.py").read_text(encoding="utf-8"))
    launch = ast.parse((root / "_launch.py").read_text(encoding="utf-8"))
    declared, launched = constants(roster), constants(launch)

    groups = value(declared.get("TOOL_GROUPS"), declared) or {}
    contracts: dict[str, dict] = {}
    for key, call in zip(declared["CONTRACTS"].keys, declared["CONTRACTS"].values):
        keywords = {word.arg: word.value for word in call.keywords}
        arguments = {}
        entries = keywords.get("arguments", ast.Dict(keys=[], values=[]))
        pending = list(zip(entries.keys, entries.values))
        while pending:
            name, argument = pending.pop(0)
            # A `**NAME` entry is a key of `None` over the name of a module-level
            # dict of arguments. Spliced in place, ahead of what is left, a shared
            # part reads exactly as the same lines written inline would -- which is
            # what the server actually serves, and an argument this could not see
            # is an argument this could not police. `declared` is indexed, not
            # queried: a splice that resolves to nothing is a surface read short,
            # and looping rather than recursing lets a spliced dict splice further
            # at no cost.
            if name is None:
                spliced = declared[argument.id]
                pending[:0] = list(zip(spliced.keys, spliced.values))
                continue
            spelled = {word.arg: value(word.value, declared) for word in argument.keywords}
            arguments[name.value] = {
                "kind": value(argument.args[0], declared) if argument.args else None,
                "enum": spelled.get("enum") or (),
            }
        contracts[key.value] = {
            "group": value(call.args[0], declared),
            "direction": value(call.args[1], declared),
            "reads": value(keywords.get("reads"), declared) or (),
            "writes": value(keywords.get("writes"), declared) or (),
            "arguments": arguments,
        }

    whole = value(constants(agent)["SERVED_GROUPS"], constants(agent)) or ()
    part = value(constants(agent)["SERVED_MEMBERS"], constants(agent)) or {}
    served = sorted(
        {name for group in whole for name in groups.get(group, ())}
        | {name for group, members in part.items() for name in members}
    )

    roles = {}
    for key, call in zip(declared["ROLES"].keys, declared["ROLES"].values):
        keywords = {word.arg: word.value for word in call.keywords}
        roles[key.value] = value(keywords.get("tool_groups"), declared) or ()

    boundaries = []
    for label, module, function, source, holder in BOUNDARIES:
        holds = fields(ast.parse((root / source).read_text(encoding="utf-8")), holder)
        answer = named(ast.parse((root / module).read_text(encoding="utf-8")), function)
        boundaries.append((label, holds, carried(answer) if answer else frozenset()))

    return Surface(
        contracts=contracts,
        groups={name: tuple(members) for name, members in groups.items()},
        roles=roles,
        served=tuple(served),
        built=tuple(sorted(value(launched["DESCRIPTIONS"], launched) or {})),
        names=references(root),
        inserts=python_inserts(root),
        consumers=references(root, skip=frozenset({"roster.py"})),
        boundaries=tuple(boundaries),
        exchange=answers(launch, EXCHANGE),
    )


# ---------------------------------------------------------------------------
# Reading the corpus. Frontmatter and body, and the body is the half nothing in
# this repository has ever read: `playbook._playbook` validates the frontmatter
# and then does `instructions=body` with no inspection beyond refusing an empty
# one. Every W10 reading below is over that body.
# ---------------------------------------------------------------------------

FENCE = "---"
FIELD = re.compile(r"^([A-Za-z][A-Za-z0-9:_-]*):\s*(.*)$")
TOOL_TOKEN = re.compile(r"mcp__rk2__[a-z_]+")
BACKTICKED = re.compile(r"`([^`\n]+)`")
CLASS_TOKEN = re.compile(r"`([a-z_]+\.[a-z_]+)`")
PARAGRAPH = re.compile(r"\n\s*\n")
ARGUMENT_SHAPED = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class Body:
    """One Playbook or Skill: what its frontmatter declares and what its text says."""

    name: str
    kind: str
    front: dict
    text: str


def frontmatter(document: str) -> tuple[dict, str]:
    """One corpus file's frontmatter and its body.

    A field's value is JSON where the corpus writes JSON, which is most of them,
    and the raw line otherwise. No YAML: this gate is standard library only, and
    the corpus already writes every list and every object as JSON precisely so
    that the thing reading it does not have to be a YAML parser.
    """
    if not document.startswith(FENCE + "\n"):
        return {}, document
    closing = document.index(f"\n{FENCE}\n", len(FENCE))
    head, body = document[len(FENCE) + 1:closing], document[closing + len(FENCE) + 2:]
    lines: dict[str, str] = {}
    key = ""
    for line in head.splitlines():
        found = FIELD.match(line)
        if found:
            key = found.group(1)
            lines[key] = found.group(2)
        elif key and line.strip():
            lines[key] += " " + line.strip()
    front: dict = {}
    for key, written in lines.items():
        written = written.strip()
        if written[:1] in "[{":
            try:
                front[key] = json.loads(written)
                continue
            except ValueError:
                pass
        front[key] = written
    return front, body


def read_corpus(playbooks: Path = PLAYBOOKS, skills: Path = SKILLS) -> tuple[Body, ...]:
    """Every Playbook and every Skill, in one sequence because W10 asks both the same thing."""
    found = []
    for kind, root, pattern in (("playbook", playbooks, "*/playbook.md"), ("skill", skills, "*/SKILL.md")):
        for path in sorted(root.glob(pattern)):
            front, text = frontmatter(path.read_text(encoding="utf-8"))
            found.append(Body(name=path.parent.name, kind=kind, front=front, text=text))
    return tuple(found)


@dataclass(frozen=True)
class Wiring:
    """The three readings, gathered once and asked together.

    One object for `check_audit.Audit`'s reason: a check that took them
    separately could be handed a roster from one checkout and a migration corpus
    from another, and the whole value of these readings is that they are of one
    tree at one moment.
    """

    catalogue: Catalogue
    surface: Surface
    corpus: tuple[Body, ...]
    tickets: dict[int, Ticket]
    #: Every relation any Contract declares it reads, gathered once.
    readable: frozenset[str] = field(default_factory=frozenset)

    @property
    def executing(self) -> dict[str, str | None]:
        """The role each corpus body is written for, or None where it is not one.

        A Skill states its roles. A Playbook does not: it states the Skills it
        needs, and the role that executes it is the one role whose Skills are a
        superset of them. That is a derivation rather than a declaration, and
        where it does not land on exactly one role the readings that need it say
        so instead of picking.
        """
        holds: dict[str, set[str]] = {role: set() for role in self.surface.roles}
        for body in self.corpus:
            if body.kind == "skill":
                for role in body.front.get("bb:roles", []):
                    holds.setdefault(role, set()).add(body.name)
        found: dict[str, str | None] = {}
        for body in self.corpus:
            if body.kind == "skill":
                roles = body.front.get("bb:roles", [])
                found[body.name] = roles[0] if len(roles) == 1 else None
                continue
            wanted = set(body.front.get("bb:skills", []))
            candidates = [role for role, skills in holds.items() if wanted <= skills]
            found[body.name] = candidates[0] if len(candidates) == 1 else None
        return found

    def tools(self, role: str | None) -> frozenset[str]:
        """Every model-facing tool one role may call."""
        return frozenset(
            name
            for group in self.surface.roles.get(role or "", ())
            for name in self.surface.groups.get(group, ())
        )

    def reachable(self) -> frozenset[str]:
        """Every SQL function something reaches, from the three roots outwards.

        The roots are the whole of W3's honesty. A Python call site alone would
        make every `check_*` function in this corpus an orphan, because they are
        reached from `standing_checks.query` strings and never named by Python,
        and every constraint trigger would be one too. With all three, what is
        left over is what nothing runs.
        """
        catalogue = self.catalogue
        roots = (
            (self.surface.names & frozenset(catalogue.functions))
            | catalogue.triggers
            | catalogue.standing
        )
        seen: set[str] = set()
        frontier = list(roots)
        while frontier:
            name = frontier.pop()
            if name in seen:
                continue
            seen.add(name)
            frontier.extend(catalogue.calls.get(name, ()))
        return frozenset(seen)


# ---------------------------------------------------------------------------
# The ten checks. Each returns the gaps it found, never a refusal: what is a
# defect and what is a tracked absence is one decision, taken once, against the
# register, so that a check cannot be written to excuse its own findings.
# ---------------------------------------------------------------------------

#: The methods that mean nothing without a body. W2's inverse arm: an enum that
#: offers a verb whose whole content is its payload, on a contract that declares
#: no payload, is an argument set that cannot express what its own enum promises.
BODIED = ("POST", "PUT", "PATCH")

#: How a read Contract says which class of handle it resolves. A label is the
#: only name a model has for a row, so an argument called `<class>_label` is the
#: declaration that this tool can turn one back into the thing it names.
LABEL = re.compile(r"^([a-z_]+?)_labels?$")

#: What a proposal's element lists promote into. The one map in this file that
#: is written rather than read, because the roster does not carry it: an element
#: called `new_entities` becomes a row in `entities`, and only the code that
#: promotes it knows that. Each of these is a canonical relation, and W5 asks
#: whether any tool can read it back.
PROMOTES = {
    "observations": "observations",
    "new_entities": "entities",
    "relationships": "relationships",
    "hypotheses": "hypotheses",
    "evidence": "hypothesis_evidence",
    "suggested_tasks": "tasks",
}

#: The standing checks the three catalogue-side readings need, named so that a
#: gap here is a gap about a missing check rather than about a missing repair.
#: When one of these is registered, `integrity.py` runs it with the rest and this
#: gate stops carrying the question.
REGISTERED = {
    "W4": ("state_read_surface", "the agent read surface against the tools that read it"),
    "W7": ("guard_satisfiability", "no guard requires a row another guard refuses"),
}


def served_gaps(wiring: Wiring) -> list[Gap]:
    """W1: every Contract is served, and every tool served is a tool that exists.

    Two statements about the same list. `roster._check_contracts` checks a
    contract's shape and never asks whether a handler exists; `agent`'s own
    check compares the served list to the groups it claims to be part of and
    never compares it to what `_launch.server` builds. Neither of them closes
    the loop, which is how a Contract comes to be declared, grouped, granted to
    a role and answered by nothing.
    """
    surface = wiring.surface
    bare = {name.rsplit("__", 1)[-1] for name in surface.served}
    gaps = [
        Gap("W1", name, f"{name} is declared and no launch serves it")
        for name in sorted(set(surface.contracts) - set(surface.served))
    ]
    # Not a gap and not owable: a served name with no tool behind it is a
    # launch that does not start, and a built tool nothing serves is a handler
    # no allowlist can reach. Both are contradictions in one file rather than
    # work somebody has not done, so they are reported as themselves.
    gaps.extend(
        Gap("W1", name, f"{name} is served and `_launch.server` builds no such tool")
        for name in sorted(bare - set(surface.built))
    )
    gaps.extend(
        Gap("W1", name, f"`_launch.server` builds {name} and no launch serves it")
        for name in sorted(set(surface.built) - bare)
    )
    return gaps


def argument_gaps(wiring: Wiring) -> list[Gap]:
    """W2: every declared argument is read by something, and every enum is expressible.

    An argument is authority. One that no code downstream of the handler ever
    reads is authority the model is offered and the runtime discards, and the
    reading is deliberately generous -- the name has to appear somewhere in the
    package outside the module that declares it, as a parameter, an attribute or
    a word in a query -- because a generous reading that still finds nothing is
    a finding nobody can argue with.
    """
    surface = wiring.surface
    gaps = []
    for name, contract in sorted(surface.contracts.items()):
        for argument, declared in sorted(contract["arguments"].items()):
            # The one exemption, and it is stated rather than discovered: a
            # proposal's element lists are read through `proposal.Result.elements`,
            # which takes the name as a parameter and says why it holds no copy
            # of them -- "a second copy of those names here is a second copy that
            # could be right about a list the schema no longer accepts". A name
            # scan cannot see a read like that, and the question it would ask
            # wrongly is the question W5 asks properly: not whether the list is
            # read, but whether anything promotes it into a relation.
            if contract["direction"] == "propose" and declared["kind"] == "array":
                continue
            if argument not in surface.consumers:
                gaps.append(
                    Gap("W2", f"{name}.{argument}", f"{name} declares {argument} and nothing reads it")
                )
            if argument == "method" and set(declared["enum"] or ()) & set(BODIED):
                if "body" not in contract["arguments"]:
                    gaps.append(
                        Gap(
                            "W2",
                            f"{name}.body",
                            f"{name} offers {', '.join(BODIED)} and declares no body to send",
                        )
                    )
    return gaps


def verb_gaps(wiring: Wiring) -> list[Gap]:
    """W3: every verb the runtime is granted is reached by something that runs.

    The measurement rather than the claim, which is the whole of this check.
    Ticket 38 states in prose that `open_impact_task` and `state_severity` "are
    called by the CLI and by the tests"; this reading disagrees, and a reading
    that disagrees with a resolved ticket's prose is the reason the check is
    worth its cost. Reachability is transitive, so a helper whose only caller is
    an orphan is an orphan: that is not noise, it is the size of the dead
    subgraph, and a repair that gives the head of it a caller clears the rest.
    """
    reached = wiring.reachable()
    return [
        Gap("W3", name, f"{name} is granted to {RUNTIME} and nothing calls it")
        for name, roles in sorted(wiring.catalogue.grants.items())
        if RUNTIME in roles and name not in reached
    ]


def read_surface_gaps(wiring: Wiring) -> list[Gap]:
    """W4: every relation the agent's own database role may read is read by a tool.

    A relation on `state_read_surface` is a promise in two halves: the role may
    select it, and some tool turns it into something a model receives. The first
    half without the second is a grant nobody uses and a design nobody finished,
    and `negative_knowledge` is the loudest instance -- a whole migration exists
    to keep refutations and make them due for retest, both its tables are on the
    surface, and no tool reads either.
    """
    gaps = [
        Gap("W4", relation, f"{relation} is on the agent read surface and no tool reads it")
        for relation in sorted(wiring.catalogue.read_surface - wiring.readable)
    ]
    if wiring.catalogue.catalogue_seeded:
        # The half of the surface that is seeded from `has_column_privilege`
        # rather than written down. No file can say what it holds, and the
        # honest thing for a file reader to report is that the check which can
        # is not registered.
        check, says = REGISTERED["W4"]
        gaps.append(
            Gap(
                "W4",
                check,
                f"the read surface is catalogue-seeded and no {STANDING} named {check} asks"
                f" whether {says}",
            )
        )
    return gaps


def result_gaps(wiring: Wiring) -> list[Gap]:
    """W5: what a model may propose it may read back, and what it is handed is whole.

    Three readings of one idea. An element list a proposal accepts and no read
    verb returns is a write-only vocabulary: an agent may propose relationships
    it can never read back. A label an act tool mints and no read verb resolves
    is a handle to nothing. And a field a runtime value carries that the answer
    does not is information the model was told about and then not given, which
    is the difference between a tool that failed and a tool run whose stderr
    nobody will ever see.
    """
    surface = wiring.surface
    resolves = {
        LABEL.match(argument).group(1)
        for contract in surface.contracts.values()
        if contract["direction"] == "read"
        for argument in contract["arguments"]
        if LABEL.match(argument)
    }
    gaps = []
    for name, contract in sorted(surface.contracts.items()):
        if contract["direction"] != "propose":
            continue
        for argument, declared in sorted(contract["arguments"].items()):
            if declared["kind"] != "array":
                continue
            relation = PROMOTES.get(argument)
            if relation is None:
                gaps.append(
                    Gap("W5", argument, f"{name} accepts {argument} and nothing promotes it")
                )
            elif relation not in wiring.readable:
                gaps.append(
                    Gap(
                        "W5",
                        argument,
                        f"{name} accepts {argument} and no tool reads {relation} back",
                    )
                )
    for name, contract in sorted(surface.contracts.items()):
        if contract["direction"] != "act":
            continue
        for relation in contract["writes"]:
            # A view is not a handle: an act tool writes rows into tables, and
            # what it hands back is the label of a row.
            if relation in wiring.catalogue.views or not relation.endswith("s"):
                continue
            minted = relation[:-1]
            if minted not in resolves:
                gaps.append(
                    Gap("W5", minted, f"{name} mints a {minted} label and no read verb resolves it")
                )
    for label, holds, mentions in surface.boundaries:
        gaps.extend(
            Gap("W5", f"{label}.{held}", f"{label} drops {held} and declares no reason")
            for held in holds
            if held not in mentions
        )
    return gaps


#: Two relations the database audit itself reads as harmless rather than as a
#: gap, and this check's own file-only reach cannot tell that apart from a real
#: one. `cross_program_exempt_fks` is an override table read by
#: `check_program_isolation` (`0017_program_isolation.sql:328`): it stays empty
#: because it is meant to, an empty override table is full isolation and not a
#: missing writer, and an operator who needs a named exemption inserts a row by
#: hand rather than through a code path this reader would find. Its parallel
#: `INDEX` scan is what caught it here in the first place, so the exemption is
#: named for the finding rather than for a class of table this reader ignores.
#: `program_isolation_candidates` is a view selected twice inside the very
#: migration that defines it (`0017_program_isolation.sql:189`, `:238`), inside
#: a `DO` block this reader's scan does not reach; it generates the isolation
#: constraints at DDL time and has done its one job by the time this file ever
#: runs. `secret_dek` is the third, and ticket 123 is what moved it here from the
#: register: it is the DEK half of an envelope ticket 07 superseded, the audit
#: grades it "harmless-superseded rather than load-bearing", and it is the one of
#: these three whose emptiness is asserted -- `check_wire_artifact_secrecy`
#: grades a wrapped data key in it a violation, so a writer for it is not work
#: anybody owes but work the corpus refuses. All three are named rather than
#: matched by shape, because a shape wide enough to catch them is a shape wide
#: enough to excuse a real one.
BY_DESIGN = frozenset(
    {"cross_program_exempt_fks", "program_isolation_candidates", "secret_dek"}
)


def producer_gaps(wiring: Wiring) -> list[Gap]:
    """W6: a table has a producer, a view has a reader, and a rule has an input.

    Three of the five arms the reconciled check names, and the two that are
    missing are missing on purpose. Whether every column a rule depends on has a
    writer, and whether every constraint can be made false, are questions about
    expressions evaluated against column defaults, and the file reader that
    tried them would answer with the hundred and ninety-four findings the
    database audit already published and no way to tell the fifteen deliberate
    ones apart. Those two belong beside `check_program_isolation` in the standing
    family, where the expressions are the server's to evaluate.
    """
    catalogue, surface = wiring.catalogue, wiring.surface
    produced = catalogue.inserted_by_function | catalogue.inserted_by_migration | surface.inserts
    gaps = [
        Gap("W6", table, f"nothing inserts a row into {table}")
        for table in sorted(catalogue.tables)
        if table not in produced and table not in BY_DESIGN
    ]
    gaps.extend(
        Gap("W6", view, f"nothing selects from {view}")
        for view in sorted(catalogue.views)
        if view not in catalogue.selected and view not in surface.names and view not in BY_DESIGN
    )
    for column, reads in sorted(catalogue.generated.items()):
        gaps.extend(
            Gap(
                "W6",
                f"{column}.{read}",
                f"the generated column {column} is computed from {read} and no writer sets it",
            )
            for read in sorted(reads - SQL_WORDS)
            if not any(
                written == read or written.endswith(f".{read}") for written in catalogue.written
            )
        )
    return gaps


def guard_gaps(wiring: Wiring) -> list[Gap]:
    """W7: no guard requires a row that another guard refuses.

    The one check this file does not attempt. Answering it means building the
    implication graph of every CHECK on every table and chasing it through every
    trigger's requirements and refusals along the foreign keys between them, and
    a file reader that guessed at that would be wrong in the direction that
    matters: it would clear a contradiction that is there. What it can say
    honestly is that the check does not exist, so nothing asks the question at
    all -- and the audits found two contradictions by hand, one of which is open.
    """
    check, says = REGISTERED["W7"]
    if check in wiring.catalogue.standing:
        return []
    return [Gap("W7", check, f"no {STANDING} named {check} asserts that {says}")]


def write_target_gaps(wiring: Wiring) -> list[Gap]:
    """W8: a Contract's declared write target is a real relation with a real writer.

    The place where the Python layer and the schema layer each declare half of a
    feature and neither implements it. `mcp__rk2__request_report` names
    `report_queue` as what it writes; the table exists, carries a CHECK, two row
    policies and a program-scoping registration, and nothing has ever put a row
    in it, because the tool that would has no handler.
    """
    catalogue = wiring.catalogue
    produced = (
        catalogue.inserted_by_function | catalogue.inserted_by_migration | wiring.surface.inserts
    )
    gaps = []
    for name, contract in sorted(wiring.surface.contracts.items()):
        for relation in contract["writes"]:
            if relation not in catalogue.tables and relation not in catalogue.views:
                gaps.append(
                    Gap("W8", relation, f"{name} writes {relation}, which this schema does not hold")
                )
            elif relation in catalogue.tables and relation not in produced:
                gaps.append(
                    Gap("W8", relation, f"{name} writes {relation} and nothing ever inserts into it")
                )
    return gaps


def vocabulary_gaps(wiring: Wiring) -> list[Gap]:
    """W9: a declared class is emitted, and a class named in prose is one that is.

    The corpus half of the vocabulary audit. A property class is a promise that
    some Playbook can produce a finding of that shape; a class nothing emits is a
    promise with no path to it, and the way an operator meets one is in a
    Playbook body that names it as though it were reachable. The escape hatch is
    the one the schema already provides and is not silence: a class declared
    `unmakeable` in `transport_makeability` has said out loud that it is
    unreachable, and that is not this check's business.

    The stale-declaration arm is not here. As the vocabulary audit states it, a
    migration that changes a constraint on a column must re-issue that column's
    comment in the same file, and every widening this corpus has ever made would
    be reported by it -- twenty-two files, of which one is the known instance the
    audit names. The audit grades that arm a warning and calls it partly social,
    and a gate that reports twenty-one corrections to find one stale sentence is
    a gate somebody switches off.
    """
    catalogue = wiring.catalogue
    emitted = {
        emitted
        for body in wiring.corpus
        for emitted in body.front.get("bb:outputs", [])
    }
    absent = catalogue.property_classes - emitted - catalogue.unmakeable
    gaps = [
        Gap("W9", name, f"{name} is declared, no Playbook emits it and nothing declares it unmakeable")
        for name in sorted(absent)
    ]
    for body in wiring.corpus:
        for token in sorted(set(CLASS_TOKEN.findall(body.text))):
            family = token.split(".")[0]
            if token in absent:
                gaps.append(
                    Gap("W9", f"{body.name} {token}", f"{body.name} names {token}, which no Playbook emits")
                )
            elif token not in catalogue.property_classes and family in catalogue.property_families:
                gaps.append(
                    Gap(
                        "W9",
                        f"{body.name} {token}",
                        f"{body.name} names {token}, which is not a property class",
                    )
                )
    for body in wiring.corpus:
        for expectation in body.front.get("bb:evidence", []):
            kind, role = expectation.get("kind"), expectation.get("role")
            if catalogue.evidential.get(kind, True) or role == "context":
                continue
            gaps.append(
                Gap(
                    "W9",
                    f"{body.name} {kind}",
                    f"{body.name} expects {kind} as {role}, and a non-evidential kind is"
                    " refused at that role",
                )
            )
    return gaps


def instruction_gaps(wiring: Wiring) -> list[Gap]:
    """W10: the shipped text names only what the role reading it actually holds.

    The body is the one artefact in this system that nothing checks.
    `playbook._playbook` validates the frontmatter and then takes the body
    whole; `roster._check_skills` reads `bb:runtime-tools` and never opens the
    text under it. So the corpus is free to instruct a browser mission through a
    tool that runs no browser, an identity on a request that carries none, and an
    analysis of bytes the same body has just told the model to fetch and cannot
    name afterwards. Four readings, in the order they cost.
    """
    surface, catalogue = wiring.surface, wiring.catalogue
    executing = wiring.executing
    # What an exchange hands back, read rather than assumed. The fourth reading
    # below used to carry "an exchange returns no Artifact label" as a sentence
    # in a comment, and a sentence is the one thing a gate cannot notice has
    # stopped being true: ticket 106 put `request_artifact` and
    # `response_artifact` on `_spend`'s answer and this check went on reporting
    # twenty bodies, because what it read was the corpus and the tool registry
    # and never the answer. So the answer is what it reads.
    handles = {key for key in surface.exchange if ARTIFACT_KEY.fullmatch(key)}
    gaps = []
    for body in wiring.corpus:
        role = executing.get(body.name)
        held = wiring.tools(role)
        tokens = sorted(set(TOOL_TOKEN.findall(body.text)))
        gaps.extend(
            Gap("W10", f"{body.name} {token}", f"{body.name} names {token}, which is not a Contract")
            for token in tokens
            if token not in surface.contracts
        )
        gaps.extend(
            Gap("W10", f"{body.name} {token}", f"{body.name} names {token}, which {role} does not hold")
            for token in tokens
            if token in surface.contracts and role and token not in held
        )

        # A tool that runs a program is only a capability if the role holds a
        # program to run. `browser-evidence` tells a `web_hunter` to start a
        # browser mission through `run_tool`, and `web_hunter` is granted no
        # `run_tool` program at all.
        for token, kind in (("mcp__rk2__run_tool", "tool"), ("mcp__rk2__run_skill_script", "skill")):
            if token not in tokens or role is None:
                continue
            granted = [
                program
                for program, sort in catalogue.programs.items()
                if sort == kind
                and role in catalogue.program_roles.get(program, ())
                and re.search(rf"\b{program.replace('_', '[_-]')}\b", body.text)
            ]
            if not granted:
                gaps.append(
                    Gap(
                        "W10",
                        body.name,
                        f"{body.name} instructs {token} and names no {kind} {role} is granted",
                    )
                )

        # An argument-shaped name backticked in the same paragraph as a tool is
        # a name the body is telling the model to send. `identity_slot` is the
        # loudest instance and the schema is closed, so a call carrying it is
        # refused before a handler sees it.
        expressible = (
            set(catalogue.programs)
            | {argument for named in catalogue.program_arguments.values() for argument in named}
            | {"true", "false", "null"}
        )
        for paragraph in PARAGRAPH.split(body.text):
            mentioned = [token for token in TOOL_TOKEN.findall(paragraph) if token in surface.contracts]
            if not mentioned:
                continue
            declared = {
                argument
                for token in mentioned
                for argument in surface.contracts[token]["arguments"]
            }
            gaps.extend(
                Gap(
                    "W10",
                    f"{body.name} {token}",
                    f"{body.name} instructs {token} beside {mentioned[0]}, which declares no such"
                    " argument",
                )
                for token in sorted(set(BACKTICKED.findall(paragraph)))
                if ARGUMENT_SHAPED.fullmatch(token)
                and token not in declared
                and token not in expressible
                and not token.startswith("mcp__")
            )

        # The strongest of the four: no instruction may take as input something
        # the same body earlier described fetching over the wire. A body that
        # tells a model to fetch and then to analyse is instructing a call whose
        # `artifact` argument has to be a name the run holds, and the only place
        # such a name can come from is the answer to the fetch -- so the gap is
        # a body that instructs the pair while `handles` above is empty, and it
        # closes when an exchange starts naming the bytes it filed.
        consuming = [
            program
            for program, arguments in catalogue.program_arguments.items()
            if "artifact" in arguments.values()
            and re.search(rf"\b{program.replace('_', '[_-]')}\b", body.text)
        ]
        if consuming and "mcp__rk2__http_request" in tokens and not handles:
            gaps.append(
                Gap(
                    "W10",
                    f"{body.name} fetch-then-analyse",
                    f"{body.name} instructs {consuming[0]} over bytes it fetched, and an exchange"
                    " returns no Artifact label",
                )
            )
    return gaps


#: The ten, in order, each with the reading that produces it. A tuple rather than
#: ten calls in `check`, because the report and the refusal both walk it and a
#: check added to one and not the other would be a check nobody reads.
CHECKS = (
    ("W1", "contracts served", served_gaps),
    ("W2", "arguments consumed", argument_gaps),
    ("W3", "verbs called", verb_gaps),
    ("W4", "read surface", read_surface_gaps),
    ("W5", "results resolvable", result_gaps),
    ("W6", "producers", producer_gaps),
    ("W7", "guards satisfiable", guard_gaps),
    ("W8", "write targets", write_target_gaps),
    ("W9", "vocabulary", vocabulary_gaps),
    ("W10", "corpus instructions", instruction_gaps),
)


# ---------------------------------------------------------------------------
# The register, the report and the refusal.
# ---------------------------------------------------------------------------


def register_errors(gaps: list[Gap], tickets: dict[int, Ticket]) -> list[str]:
    """Reconcile what the tree holds against what the register says is owed.

    Both directions, and the second is the one that makes the register worth
    keeping. A gap with no row is a declaration somebody made and did not
    finish, and the gate refuses it. A row with no gap is work that was done and
    a register that still calls it owed, which is how a tracked absence quietly
    becomes a lie: the row would go on excusing a gap that is not there, and the
    next real one to appear under the same name would be excused with it.
    """
    found = {gap.key: gap for gap in gaps}
    errors = [
        f"unregistered: {gap.detail}"
        for key, gap in sorted(found.items())
        if key not in OWED_GAPS
    ]
    for key, row in sorted(OWED_GAPS.items()):
        number = TICKET.match(row) or DECIDED_TICKET.match(row)
        if number is None:
            errors.append(
                f"register: {key} is recorded as {row!r},"
                f" which is neither an {OWED}NN nor a {DECIDED}NN row"
            )
            continue
        decided = row.startswith(DECIDED)
        ticket = tickets.get(int(number.group(1)))
        if ticket is None:
            errors.append(f"register: {key} names {row} and the tracker holds no such ticket")
        elif decided and not ticket.resolved:
            # A decision that is still open is not a decision. The row would be
            # excusing the gap on the strength of an argument nobody has
            # finished having, which is the same hole an `owed` row naming a
            # resolved ticket leaves, entered from the other side.
            errors.append(
                f"register: {key} names {row}, which is not resolved,"
                " so the decision it cites has not been made"
            )
        elif not decided and ticket.resolved and key in found:
            errors.append(
                f"register: {key} names {row}, which is resolved, and the gap is still here"
            )
        if key not in found:
            errors.append(
                f"register: {key} names {row} and this tree has no such gap; remove the row"
            )
    return errors


def report(wiring: Wiring, gaps: list[Gap]) -> str:
    """One line per check, each carrying what it measured rather than that it passed.

    A gate that prints "ok" ten times tells a reader nothing about whether it
    looked. These lines carry the sizes, so a reading that quietly stopped
    finding anything -- a corpus directory that moved, a migration glob that
    matched nothing -- shows up as a number that fell rather than as continued
    silence.
    """
    catalogue, surface = wiring.catalogue, wiring.surface
    counted = Counter(gap.check for gap in gaps)
    arguments = sum(len(contract["arguments"]) for contract in surface.contracts.values())
    targets = {
        relation for contract in surface.contracts.values() for relation in contract["writes"]
    }
    produced = (
        catalogue.inserted_by_function | catalogue.inserted_by_migration | surface.inserts
    )
    emitted = {name for body in wiring.corpus for name in body.front.get("bb:outputs", [])}
    mentions = sum(len(set(TOOL_TOKEN.findall(body.text))) for body in wiring.corpus)
    derived = sum(1 for role in wiring.executing.values() if role is not None)
    measured = {
        "W1": f"contracts {len(surface.contracts)}  served {len(surface.served)}"
              f"  built {len(surface.built)}",
        "W2": f"arguments {arguments}  read outside the roster "
              f"{len({argument for contract in surface.contracts.values() for argument in contract['arguments']} & surface.consumers)}",
        "W3": f"granted to {RUNTIME} "
              f"{sum(1 for roles in catalogue.grants.values() if RUNTIME in roles)}"
              f"  functions {len(catalogue.functions)}  reached {len(wiring.reachable())}",
        "W4": f"on the read surface {len(catalogue.read_surface)}"
              f"  relations a tool reads {len(wiring.readable)}",
        "W5": f"proposal elements {len(PROMOTES)}  boundaries {len(surface.boundaries)}",
        "W6": f"tables {len(catalogue.tables)}  produced {len(produced & set(catalogue.tables))}"
              f"  views {len(catalogue.views)}"
              f"  selected {len(catalogue.views.keys() & catalogue.selected)}",
        "W7": f"standing checks {len(catalogue.standing)}",
        "W8": f"declared write targets {len(targets)}"
              f"  held by this schema {len(targets & (catalogue.tables.keys() | catalogue.views.keys()))}",
        "W9": f"property classes {len(catalogue.property_classes)}  emitted {len(emitted)}"
              f"  unmakeable {len(catalogue.unmakeable)}",
        "W10": f"corpus bodies {len(wiring.corpus)}  tool mentions {mentions}"
               f"  roles derived {derived}",
    }
    lines = ["wiring"]
    lines.extend(
        f"  {code + ' ' + label:<26}{counted[code]:>4} owed   {measured[code]}"
        for code, label, _ in CHECKS
    )
    lines.append(
        f"  {'register':<26}{len(OWED_GAPS):>4} rows   tickets "
        f"{len(set(OWED_GAPS.values()))}  findings {len(gaps)}"
        f"  distinct {len({gap.key for gap in gaps})}"
    )
    return "\n".join(lines)


def gather() -> Wiring:
    """Read the migrations, the package and the corpus once, for one checkout."""
    surface = read_surface()
    return Wiring(
        catalogue=read_catalogue(),
        surface=surface,
        corpus=read_corpus(),
        tickets=read_tickets(spec_root(read_status())),
        readable=frozenset(
            relation
            for contract in surface.contracts.values()
            for relation in contract["reads"]
        ),
    )


def check() -> str:
    """The wiring gate. Returns the report, or raises with every reason it refused."""
    wiring = gather()
    gaps = [gap for _, _, reading in CHECKS for gap in reading(wiring)]
    errors = register_errors(gaps, wiring.tickets)
    if errors:
        raise WiringError("\n".join(errors))
    return report(wiring, gaps)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        print(check())
    except (WiringError, BaselineError, OSError) as error:
        print(f"wiring failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
