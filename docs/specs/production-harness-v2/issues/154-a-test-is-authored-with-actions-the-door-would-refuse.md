# 154 — A Test is authored with actions the door would refuse

**What to build:** The scope walk at the moment a Test is written, so a hunt
learns its specification is unrunnable while it can still author another one.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt13`, 2026-08-22, the first
      lap that reached `replay.run` from a `perform` Task. The claim opened,
      the replay started, and `rk2_replay_plan` refused it:

      ```
      the registry refused this replay: the Test reaches outside the
      current scope: http://www.yekta-it.de/
      ```

      Both Tests the hunts authored are unrunnable, and for the same reason:

      ```
      TST1 | https://yekta-it.de/ , http://yekta-it.de/ , ...
      TST2 | https://www.yekta-it.de/ , http://www.yekta-it.de/ , ...
      ```

      The Program admits two hosts on https and 443 only, which the schema
      agrees with:

      ```
      scheme|host            |port|class
      https |yekta-it.de     |443 |target
      http  |yekta-it.de     |80  |denied
      https |www.yekta-it.de |443 |target
      http  |www.yekta-it.de |80  |denied
      ```

      So a hunt spent a whole run writing a specification that could never be
      performed, and nothing said so until a second Task claimed it a pass
      later. `test_proposals` recorded both as `created`.

- [x] **The walk happens where the Test is written.** `rk2_replay_plan` already
      walks `setup`, `actions` and `cleanup` and classes every URL. The verb
      that files a Test does not, so the two disagree about whether a row may
      exist: one admits it and the other refuses to act on it.

- [x] **The refusal reaches the author, not the performer.** A hunt that is
      told at authoring time can write a second specification inside the same
      run. A hunt that is told nothing has ended by the time anybody finds out.

- [x] **The claim is not left settled by the refusal.** A Test that was never
      written leaves its Hypothesis `testable`, which is what it is: nothing
      about it has been decided.

## What was built

`rk2_test_scope_problem(uuid, jsonb)` walks `actions`, `setup` and `cleanup`
in the order `rk2_replay_plan` walks them and returns the first URL the scope
does not admit, as the sentence its author is answered with. It returns rather
than raises, because `propose_test` already has a channel for a refusal: a
`refused` row in `test_proposals` carrying the reason.

`propose_test` asks it after `rk2_test_spec_problem` and before it writes
anything. Second, because the shape has to hold before the URLs inside it can
be parsed at all.

Measured on the two Tests that provoked the ticket, after the migration:

```
label|problem
TST1 |the Test reaches outside the current scope: http://yekta-it.de/
TST2 |the Test reaches outside the current scope: http://www.yekta-it.de/
```

and an https-only specification against the same Program answers NULL.

## The test that would go red

`tests/test_database.py::ScopedSpecificationTest` -- five tests over one
Program: the in-scope specification is written, the out-of-scope one is refused
with the sentence, no `tests` row follows it, both attempts are on the record in
`test_proposals`, and the claim is left `testable`.

**Note.** The transport claim this hunt was written to settle is about what
`http://` does, so under this Program it is unsettleable by construction. That
is a scope decision and not a defect: whether port 80 belongs in scope is the
operator's to state. This ticket is about the harness admitting a row it will
later refuse to use.
