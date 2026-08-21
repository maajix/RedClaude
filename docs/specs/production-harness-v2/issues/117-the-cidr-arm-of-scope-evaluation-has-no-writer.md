# 117 — The CIDR arm of scope evaluation has no writer

**What to build:** A decision, then the code that follows from it: either the
compiler learns to emit `cidr` rules and tiers, or the columns, the index, the
constraints and the matching arms that exist only for them come out.

**Blocked by:** nothing.

**Status:** needs-triage

- [ ] The decision is recorded before anything is changed. Address-range scope
      and effort tiers are both in the schema and in neither compiler, and
      which of the two answers is right is a product question rather than a
      wiring one: a program that scopes by `10.0.0.0/8` is a real bug bounty
      scope, and no configuration file the loader accepts can express one.
- [ ] The gap is stated as it stands. `program_scope_rules` declares `net cidr`
      (`0021_scope_policy.sql:91`), `tier text` (`:94`) and
      `allow_private_ips boolean NOT NULL DEFAULT false` (`:95`).
      `src/redkraken/program.py:910-921` writes the rules with a thirteen-column
      list -- `program_id, version, ord, effect, effect_rank, pattern_kind,
      pattern_text, match_key, protocol, port, path_prefix, spec_kind,
      spec_len` -- and none of those three is in it. The compiler that produces
      the rows produces exactly two pattern kinds, `Pattern(kind="wildcard"...)`
      at `src/redkraken/scope.py:579` and `Pattern(kind="exact"...)` at `:584`.
- [ ] Each thing that is therefore unreachable is named, and the ticket says
      which of them is a defect and which is inert:
      the `'cidr'` arm of `pattern_kind text NOT NULL CHECK (pattern_kind IN
      ('exact','wildcard','cidr'))` (`0021:86`);
      the two paired CHECKs at `0021:109-110`, which assert both directions of
      "a CIDR rule has a `net` and no `match_key`";
      the partial GiST index `scope_rules_net_idx ... WHERE pattern_kind =
      'cidr'` (`0021:119-121`), which indexes a column that is always NULL over
      a predicate that is never true;
      the containment arm of the live classifier,
      `r.pattern_kind = 'cidr' AND r.net >>= (...)::inet`
      (`20260810T193000Z__scope_policy_compilation.sql:341-343`);
      and `allow_private_ips`, which has no writer and no reader anywhere in
      `src/` -- the only occurrence in the tree is its own declaration.
- [ ] The tier half is treated as its own question, because it fails one step
      further along. `tier` is never set on a rule and `default_tier` is never
      set on a version, so the tier expression
      (`20260810T193000Z...:394-399`) always yields NULL, `entities.scope_tier`
      is always NULL, `CHECK (tier IS NULL OR effect = 'target')` (`0021:112`)
      can never fail, and `v_records` publishes `"scope_tier": null` for every
      Entity in the system. An effort policy that is declared, projected,
      published and always NULL is worse than one that is absent, because a
      reader cannot tell the two apart.
- [ ] Whichever way the decision goes, the outcome is testable. If the columns
      stay, a configuration with a CIDR target compiles, projects, and an
      Entity inside the range comes out `target`. If they go, the migration
      that removes them says in its own prose why the design chose host-shaped
      scope only, so the next reader does not re-add them.

## Why

`docs/research/wiring/23-database-wiring.md` section 1.3(c). The report grades
the columns load-bearing rather than harmless, and the reason is that the
schema is the design document here: a `cidr` arm in a CHECK constraint is a
claim that the system evaluates address ranges, and nothing does.

Two corrections. The report cites the classifier arm as `0021:292` and the tier
expression as `0021:333`. Both are in the superseded definition:
`20260810T193000Z__scope_policy_compilation.sql:297` drops
`scope_class_of(uuid, integer, text, integer, text, text)` and `:299` recreates
it with two more arguments, so the live arms are at `:341-343` and `:394-399`.
The `0021` lines are what shipped first and are not what runs. The report also
names the constraints `program_scope_rules_check` and
`program_scope_rules_check1`; those are the names Postgres assigned, and the
CHECKs are written anonymously in the file at `0021:109-110`.

This is a decision, not a defect, which is why it is `needs-triage` rather than
`ready-for-agent`: nothing is broken today, and both answers are defensible.
What is not defensible is leaving it unanswered, because every future reader of
`0021` spends the same hour working out that the arm is dead.
