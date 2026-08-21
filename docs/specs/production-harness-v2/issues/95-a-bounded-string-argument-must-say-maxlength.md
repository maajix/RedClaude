# 95 — A bounded string argument must say maxLength

**What to build:** `Argument.schema` emitting `maxLength` and `minLength` for a
string whose bound is declared, so that the schema a pair is served and the gate
this runtime enforces ask the same question of the same value. A bug, found by
the research that needs the first bounded string this roster will ever ship.

**Blocked by:** nothing. It is a prerequisite rather than a follow-up: ticket 96
declares `body` as a bounded string and cannot be correct on top of this.

**Status:** resolved

- [x] `Argument("string", bounds=(0, 65536)).schema()` carries `maxLength` and
      `minLength`. Today it carries `maximum` and `minimum` for every kind --
      `body["minimum"], body["maximum"] = self.bounds` (`roster.py:372-373`) --
      which is JSON Schema's vocabulary for numbers and says nothing about a
      string. A pair reading that schema is told a rule that cannot apply to the
      value it is about to send.
- [x] The gate is unchanged, because the gate is already right: `_check` reads
      `measure = value if isinstance(value, int) else len(value)`
      (`roster.py:1432-1436`), so a bounded string is refused by length here
      whatever the schema said. The defect is the disagreement, and the
      docstring at `roster.py:358-366` is what it disagrees with -- "the schema
      is the pair's promise and the gate is ours".
- [x] An integer argument still serialises as `minimum` and `maximum`. All four
      bounded arguments in the shipped roster are integers -- the `limit` on
      `get_attack_surface`, `get_hypotheses`, `get_evidence` and `get_receipts`,
      each `Argument("integer", bounds=_PAGE)` (`roster.py:600`, `:610`, `:620`,
      `:635`) -- so nothing in the corpus exercises the broken half today and
      the fix must not move the half that works.
- [x] Something in `tests/` fails if either half regresses: a bounded string
      that serialises as a number, and a bounded integer that serialises as a
      length, are the two ways back in.
- [x] `Argument.constrained` still answers true for a bounded string
      (`roster.py:348-356`), so `_check_argument` (`roster.py:1766-1776`) still
      accepts one without an `OPEN_ARGUMENTS` entry. This is stated as a
      criterion because it is the property ticket 96 depends on and it is
      reachable from the same code the fix touches.

## Why

Found while designing the request primitive and recorded in
`docs/research/harness-capabilities/11-request-primitive-design.md`, in the two
implementation notes under "Proposed contract": "`bounds` on a string does not
serialise correctly today ... This is a two-line fix and it is a prerequisite,
not a follow-up."

It is latent rather than live -- no shipped contract declares a bounded string,
so the wrong keyword has never been served to anybody -- and it stops being
latent on the first line of ticket 96. Fixing it separately keeps the two apart:
this one is a defect in how a promise is written down, and that one is a
decision about what may be sent.

## What was built

`Argument.schema` branches on the kind it is describing. A bounded `string`
serialises `minLength` and `maxLength`; everything else keeps `minimum` and
`maximum` (`roster.py:372-382`). The gate is untouched: `_value_fault` already
measured a string by `len` and always did.

The ticket names the gate `_check`. The function is `_value_fault`
(`roster.py:1416`), and the bounds branch is at the lines the ticket cites. The
same code, under its real name.

## What was left alone, and why it is worth writing down

`KINDS` also admits `array` and `object`, and the gate measures both of those by
`len` too. A bounded array therefore still serialises `minimum` and `maximum`
where JSON Schema says `minItems` and `maxItems`, which is the identical defect
one kind over. No shipped contract declares a bounded array, so it is latent in
the way this ticket's own defect was latent until ticket 96. It stays latent
until something needs it, on the same reasoning that kept this fix out of 96:
the fix belongs to the contract that first needs it, so that the decision and
the defect are argued separately.

## What it is asserted with

`tests/test_roster.py`, three cases. `ContractSchemaTest` holds both halves in
one test, because the point is the disagreement and not either side of it: a
bounded string carries the length keywords and neither number keyword, and
`get_attack_surface.limit` carries `_PAGE` as `minimum` and `maximum` and
neither length keyword. `GateTest` asserts the gate still refuses a bounded
string by length, at both ends. `CompileTest` asserts a bounded string is
`constrained`, so it compiles with no `OPEN_ARGUMENTS` entry, which is the
property ticket 96 rests on.
