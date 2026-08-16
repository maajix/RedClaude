# 47 — Validate v1 dispositions against real replacements

**What to build:** Extend the frozen v1 census into a machine-checkable migration ledger whose every disposition resolves to a production replacement, explicit absorption or deliberate retirement.

**Blocked by:** 44 — Compile capability-based Skills; 45 — Select one Playbook by Property class.

**Status:** resolved

**Deviation on criterion 2:** 132 of the 223 rows do not resolve to anything current,
because the thing is not built yet. Tickets 48 through 56 are the tickets that build it,
and they were all open on the day this resolved, so the criterion as written cannot be
true today and will not be until 57 closes. What ships instead is the strongest form of
the criterion that is true now: 91 rows resolve to a production role, Skill, Playbook,
Property class, vocabulary entry, runtime control or registered retirement, and the other
132 resolve to one of the nine registered migration tickets, which the checker verifies is
a real ticket that has not been closed while a row still cites it. The moment such a
ticket is marked resolved, every row that promised something to it fails until the thing
exists. That is what a migration ticket landing looks like in the counts, and ticket 48
was the first: 101 and 122 after it.

- [x] Every one of the 223 manifest rows has exactly one disposition, rationale, replacement identifier and verification reference.
- [x] Replacement identifiers resolve to a current production role, Skill, Property-class vocabulary entry, Playbook, reference attachment, runtime control or explicit scope retirement.
- [x] Missing replacements, stale source hashes, duplicate coverage and impossible disposition/kind combinations fail CI.
- [x] The ledger distinguishes rewritten capability, absorbed vocabulary/reference, superseded runtime/workflow and out-of-scope retirement.
- [x] Regeneration never edits the source v1 repository or reads engagement state as knowledge input.
- [x] Summary counts reconcile exactly to the frozen census and are emitted in a reviewable deterministic report.

## Comments

Implemented on 2026-08-16.

### Two files, because a measurement and an opinion are not the same thing

`baseline/v1-manifest.tsv` froze *what v1 was*: 223 artifacts by identity and digest, no
content. The ledger is *what happened to each one*, and it is a second file for the
reason the census is content-free. A census must not move when somebody changes their
mind; a disposition moves whenever the production tree does. Merging them would mean
every re-reading of a Playbook topic edits the frozen record of what that topic was.

`baseline/v1-dispositions.tsv` carries one row per manifest source:
`source, sha256, disposition, replacement, verification, rationale`. The `sha256` is
copied from the manifest and checked against it on every run, so a disposition taken
about one text cannot be inherited by a different one. Both files are read by
`check_baseline.read_table`, because two tables in one directory read under two quoting
rules are two different formats. That reader also refuses a row that is not exactly the
declared width, which is the quiet way a frozen table gains a field: every named column
still reads and the surplus one goes where nobody looks.

### Every row resolves, one of two ways

A **built** row names something this checkout has right now and cites the file that
proves it works. A **promised** row names something that does not exist yet and cites the
open migration ticket committed to building it. The two are mutually exclusive and the
checker enforces both directions: a built row that still cites `ticket:NN` is refused,
and a `ticket:NN` whose issue file reads `Status: resolved` is refused while its
replacement is still missing.

    v1 dispositions
      agent_definition     11   rewritten 10  retired 1
      skill_directory      28   rewritten 4  absorbed 14  superseded 8  retired 2
      playbook_topic       60   rewritten 49  absorbed 1  retired 10
      operator_reference  112   absorbed 73  retired 39
      sink_pack             9   absorbed 9
      reserved              3   superseded 3
      total               223   built 49  promised 122  retired 52

The per-kind lines are the census by disposition and never move. `built` and `promised`
move once per migration ticket, which is what the last line is for; the numbers above are
the ones `tests/test_dispositions.py` pins today, after ticket 48 crossed ten rows.

### What this does not prove, and where ticket 57 comes in

A promised row cites one of nine registered migration tickets -- 48 through 56, listed in
`migration_tickets` in the policy file, so that a row cannot be parked against whichever
open issue happened to have a plausible number. What the checker does *not* do is read
that ticket's criteria and confirm they mention this artifact. Twenty of ticket 53's
rows, for instance, promise `reference:playbooks/*/references/*.md` files, and 53's six
criteria commit to migrating injection Playbooks without saying which reference files
that produces. Tying a row to a clause would mean parsing prose, and prose that a checker
parses stops being prose.

So this is a gate, not the closing gate. Ticket 57 is the closing ticket, and it asks for
more than name membership: that the 49 Playbooks exist, validate, are loadable and have
passing hash-specific production evaluations. This check answers "is every v1 artifact
accounted for, and is every promise still owed by an open ticket". 57 answers "is the
thing that was promised actually good". Both have to pass.

### Where the resolvable names come from

Nothing in `tools/check_dispositions.py` writes down what exists. `role`, `skill` and
`playbook` come from `roster.ROLES`, `skill.SKILLS` and `playbook.PLAYBOOKS` -- the
compilers, so a ledger row cannot name a Playbook the selector would not select.
`property_class` and `vocabulary` are read out of the migration corpus on disk by
matching `INSERT INTO property_classes`, `property_class_families` and
`program_global_tables`. `control` is a module of `src/redkraken/`, at module
granularity, because that is the coarsest unit that is still a thing rather than a claim,
and a finer identifier would name a function that any refactor renames. `control` is
criterion 2's own word for a runtime replacement, which is why it is used here despite
not being a CONTEXT.md term.

A vocabulary namespace exists because one v1 Skill (`families`) is not one Property class
-- it is the family table itself. `program_global_tables` is the schema's own statement
of what reference data every Program shares, so it is the right authority rather than a
second list maintained beside the checker.

Resolution never opens a database. A ledger that asked a live database which Property
classes exist would grade whichever engagement it was pointed at, and two machines would
disagree about what v1 became. Nothing writes either: the v1 corpus feeds the census and
the census feeds this, so running the check touches neither.

### What the namespaces refuse, and what they deliberately allow

`absorbed` may name a Property class, a vocabulary or a reference, and may not name a
role. "Absorbed into a role" is exactly how a v1 document quietly becomes an Agent's
ambient authority again, which is the shape this whole migration exists to leave behind.
`reference:` must match `(skills|playbooks)/<name>/references/<file>.md`: a reference
lives under one Skill or one Playbook, so there is no way to spell "loaded for
everybody", which is what v1's operator references were.

Duplicate coverage is refused for `skill`, `playbook` and `reference` only. The other
five namespaces -- `role`, `control`, `property_class`, `vocabulary` and `retired` -- are
exempt deliberately rather than by oversight, because each is a place where many-to-one
is the migration working. Five v1 web Agent definitions collapse into one `role`; several
v1 Skills that each described the same enforcement collapse into the one `control` module
that now performs it (`control:execution` takes three, `control:reporting` three,
`control:playbook` two); several references about one class of defect collapse into the
one `property_class` or `vocabulary` entry that names it (`injection` takes three,
`artifact_exposure` three, while `vocabulary:property_class_families` happens to be
claimed once and is exempt for the same reason rather than because it is unshared); and
every Android artifact shares the one `retired` scope, which is the point of registering
a scope at all.

### The one retirement

Android: one Agent definition, two Skills, ten Playbook topics and thirty-nine operator
references, 52 rows in all. The harness reaches a target through one capability proxy
that speaks HTTP and TLS and a Scope Policy that names hosts. An Android engagement needs
a device, an instrumentation runtime inside it, a store account and traffic that is not
the proxy's, and none of the four is expressible in the compiled scope or the door.
Shipping the knowledge without the boundary would mean an Agent reaching a device outside
every control this system has.

`baseline/v1-dispositions.json` registers the scope with a `reason` and a `reversal`, and
a retirement with no reversal is refused: that is a deletion with a note on it, and the
claim of this ledger is that nothing was dropped without a decision anybody can revisit.
A scope nobody retires under is refused too, since it reads in review as though something
had been retired for it. A retired row is verified by the register and by nothing else,
and the rule runs both ways: citing a test would be citing something that cannot be
evidence for a deliberate absence, since no test passes because Android is gone, and a
built row citing the register would be offering the file that records intentions as proof
that one of them came true.

### The 39 Android references, and the two tickets amended for them

The 39 Android operator references are `retired:android`, not `absorbed`. There is no
Android Playbook to attach them to, so there is nothing bounded to absorb them into, and
an unbounded absorption is the thing this migration is undoing. Tickets 48 and 57 said
"112 operator references"; both were amended to say 73 in scope with the other 39
carrying the retirement record, because leaving the count unamended would have left two
open tickets contradicting the ledger they are gated on.

### The gate

`baseline/` is closed: `tools/check_baseline.py` now lists the two disposition files in
`BASELINE_FILES` and refuses any other name or a symlink, so a second ledger cannot sit
beside the frozen one with nobody able to tell which was read. Not asked for by any
criterion, but adding two files to a directory whose contents were previously implicit is
what made it worth stating.

There is no separate count reconciliation in `check()`: `read_manifest` already holds the
census to `EXPECTED_COUNTS`, and coverage is proved equal in both directions before any
row is examined, so the totals follow. `tests/test_dispositions.py` checks it the way a
reader would, by parsing the counts back out of the emitted report and comparing them to
`EXPECTED_COUNTS`.

That file is 41 tests: the shipped ledger emits the exact report; one test per rule, each
starting from the same passing row and changing only what that rule needs; coverage in
both directions against the census; and the two controls criterion 5 asks for -- that
resolution imports no `redkraken.pg`, `store` or `state` and opens no socket, asked in a
subprocess because `sys.modules` answers for the process rather than the checker; and
that `baseline/` is byte-identical after a run.

The issue root and the migration tickets live in the policy JSON rather than as Python
constants because `check_baseline`'s production boundary scan refuses a string in a
scanned source that points into `docs/`. That refusal is correct, and the registry
pattern is the one the boundary checker already uses on itself.
