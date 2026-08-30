# 225 — The door announces no version to anything

**What to build:** `rk doctor` reports a door process older than the newest
applied migration, so the operator learns it from a check rather than from a
Test that grades nothing.

**Blocked by:** nothing.

**Status:** ready-for-agent

## Where this came from

Ticket 220's fourth criterion, deferred there on purpose and named here so the
deferral is a decision. 220 changed the word: a Receipt carrying no header or
body digest now says the door predates the column and to restart it, instead of
saying the headers differ. That makes the outage a one-command one for an
operator who is already reading a refusal.

It does not make the outage visible before a Test is graded. Nothing asks the
door what it is running.

## What is measured today, and what is not

`check_server_baseline` (`20261003T000000Z:402`) checks `no_pending_migrations`
at `:470` -- whether the *schema* has caught up with the files on disk. Nothing
checks whether the *processes writing to that schema* have.

`door.py`'s only statement against the database is `PROGRAM_VISIBLE` (`:574`),
so the door announces no version to anything. There is no column, no header and
no handshake to read one out of.

The cost of not knowing, measured on `rk2here` 2026-08-29: three days, 2494
Receipts, 86 lap reports naming the wrong fault, 0 of 44 assertions evaluated.

## The shape

The door has to say something the runtime can compare. Two ways, and the ticket
asks for a decision before code.

1. **The door writes its version onto every Receipt it opens.** One column, one
   writer, and `rk doctor` compares the newest Receipt's value against
   `rk2_meta.schema_migrations`. Reads a fact rather than asking a question, so
   a door that is up but wedged is still caught. Costs a column on a hot table.
2. **The door answers a version on a health route.** `rk doctor` asks it. No
   schema change, and it works before any Receipt exists. Costs a route on the
   door and an answer that is only true of the process that answered.

Shape 2 is the smaller diff. Shape 1 is the one that cannot lie about a
different process than the one doing the writing.

## Acceptance criteria

- [ ] The decision between the two shapes is recorded in this file, with the
      price of the one not taken.
- [ ] `rk doctor` fails, with a message naming the door and the word `restart`,
      when the door process is older than the newest applied migration.
- [ ] `rk doctor` passes when they match, and says which version it compared.
- [ ] A door that is not running is a different message from a door that is old.
      An operator who reads "restart the door" about a door that was never
      started has been sent to the wrong command, which is 220's whole fault
      repeated one level up.
