# 227 — The scheduler cannot tell a critical claim from a header

**What to build:** A per-property-class impact prior, so that the value term
`20261129T000000Z` gave a floor can also say what a claim is worth. Today it
says only what a *kind* is worth, and every `hunt` Task in every program
therefore carries the same value.

**Blocked by:** nothing. `20261129T000000Z` built the prior mechanism, the
coalesce chain and the closure check this ticket extends by one link.

**Status:** resolved

## What was measured, 2026-08-30

`rk2here`, after five days and 1165 Tasks. The campaign has produced nine
Findings: eight `candidate/info` and one `validated/low`. Not one reached
`medium`, which is the bar the engagement was opened to clear.

The pending `hunt` queue, grouped by the family of the claim each Task tests,
reading `direct_value` and `novelty` off the rows `rank_pass` last wrote:

```
family                   n   direct_value  novelty  priority
information_disclosure  205     0.700       0.333    0.517
transport               202     0.700       0.333    0.517
authentication           21     0.700       0.333    0.517
session_handling         18     0.700       0.333    0.517
business_logic            3     0.700       0.333    0.517
authorization            15     0.700       0.250    0.388
injection                 3     0.700       0.250    0.388
```

`direct_value` is 0.700 on all 464. The two families that can pay out at
`high` or `critical` -- authorization and injection -- are the two at the
bottom, and 428 Tasks that cannot exceed `medium` stand in front of them.

The ordering is not a value judgement. It is novelty alone:

```
0.250 / 0.333 = 0.7507        (the novelty ratio)
0.388 / 0.517 = 0.7505        (the priority ratio)
```

`priority = novelty * confidence * (direct_value + w_unlock * unlock) / cost`,
and with `direct_value` constant and `unlock_value` 0 on all 1165 rows, the
only term left that varies across families is `novelty_for`, which is
`1.0 / (1 + n_ev)` -- one over the evidence already on the claim. An
authorization claim carries three evidence rows where a header-policy claim
carries two, so the harness ranks the claim it has looked at hardest *last*.

Every high-value hypothesis on the program has `tests = 0`: H68, H70, H73
(`authorization.edge_rule`), H66, H77 (`authorization.parallel_route`), H223
(`business_logic.replay`), H82 (`injection.markup`), H62 (`session_handling
.cross_origin_read`), H249 (`session_handling.csrf`). 171 of 183 testable
hypotheses have never been tested at all.

## WALL

`value_for(tasks, scheduler_weights)`, read from `pg_proc.prosrc` on the live
database and against `20261129T000000Z:...:109`:

```sql
SELECT coalesce(t.expected_information_gain, (w.gain_prior   ->> t.kind)::numeric),
       coalesce(t.potential_impact,          (w.impact_prior ->> t.kind)::numeric)
```

Both ends read. The sender: nothing in `src/redkraken/` ever writes
`tasks.potential_impact` -- `grep -rn potential_impact src/` returns no
assignment, and the column is NULL on 1165 of 1165 rows. The receiver:
`w.impact_prior` is keyed by `t.kind`, so `authorization.object_ownership`
and `transport.header_policy` resolve to the same 0.70.

`property_classes` is `(id, family_id, name, description)`. It holds no
number. `severity_unlock_weights` prices a severity *after* a Finding carries
one; nothing prices a claim before it is tested.

`20261129T000000Z` names this itself in its own header: *"Ticket 196 lists
three [ways out]. This is the second: a per-kind prior."* The per-kind prior
was the right first move and it is the reason a priority exists at all. This
ticket is its successor, not its correction: impact is a property of the
claim, and `kind` was never able to carry it.

## PRICE

One migration. No Python, no new verb, no backfill.

* `scheduler_weights` gains `class_impact_prior jsonb`, in the place
  `gain_prior` and `impact_prior` already live, written under the same
  `DISABLE TRIGGER ... ENABLE ALWAYS` shape `20261129T000000Z` uses so old
  version rows stay replayable.
* `value_for` gains one link in the coalesce chain it already has: estimate,
  then the class of the Task's hypothesis, then the kind prior. A Task with
  no hypothesis -- `recon`, `report` -- reaches the kind prior exactly as
  today.
* `check_scheduler_closure` gains arm `class_has_no_impact_prior`, so a class
  added to the catalogue without a number is a named defect and not a silent
  0.70.

`gain` stays per-kind and is not touched. Gain is how much uncertainty the
*action* resolves; impact is what the *claim* is worth. Only one of the two
was ever miscategorised.

No backfill, because `rank_pass` recomputes `direct_value` for every pending
Task on every pass: the 735 existing `hunt` rows re-rank on the first pass
after the migration.

## PURPOSE

The harness is meant to find the vulnerabilities worth reporting. It is
currently a novelty search that treats a TLS header and a tenant-isolation
bypass as equally valuable, and it has spent five days proving that it will
report headers.

## RULE

*Capability before catalogue.* The capability -- a value term with a
resolution chain -- was built by `20261129T000000Z`. This adds the catalogue
entry it can read. The chain, the closure check and the CASE that keeps NULL
distinguishable from zero are all reused rather than rebuilt.

## Numbers

Unvalidated, exactly as decision 16 says every number in `scheduler_weights`
is. What they encode is one ordering, and it is the ordering a bounty program
pays: a class is scored by the severity its best case can reach, not by the
severity its average case does.

The three that cross a family boundary are the ones the per-family shortcut
would have got wrong, and they are why this is keyed by class:
`transport.request_framing` is request smuggling and prices at 0.90 in the
family whose median is 0.15; `information_disclosure.credential_material` is
a leaked secret and prices at 0.95 in a family whose median is 0.45;
`injection.formula` is the weakest member of the strongest family.

## Acceptance

Measured against live `rk2here` with the migration applied inside a
transaction and rolled back, over the 467 ready pending `hunt` Tasks:

1. `check_scheduler_closure()` returns no `class_has_no_impact_prior` row,
   over all 61 classes.
2. The number of Tasks standing in front of the best authorization or
   injection Task falls from **428 to 24**, and none of the 24 is
   `transport`. The families, by the best rank each can reach:

   ```
   family                   n   max_value   max_rank
   authentication           21    0.820      0.2733
   business_logic            3    0.730      0.2433
   session_handling         18    0.700      0.2333
   information_disclosure  205    0.670      0.2233
   authorization            15    0.820      0.2050
   injection                 3    0.700      0.1750
   transport               202    0.370      0.1233
   ```

3. A `recon` Task, which names no hypothesis, keeps the priority it has
   today.

## What this does not fix

Authorization does not reach the top, and that is two separate facts.

`authentication` leading it is correct: `authentication.federation_trust`
and `authentication.credential_verification` are both priced 0.90, the same
as `authorization.edge_rule`, and a federation-trust bypass is an account
takeover. The value term now calls them equal and novelty breaks the tie,
which is what novelty is for.

`information_disclosure` leading it by 8% is not correct, and it is
`novelty_for`'s doing rather than this file's: `1.0 / (1 + n_ev)` scores an
authorization claim 0.250 against 0.333, so a claim the harness has already
looked at twice is ranked below one it has looked at once, whatever either is
worth. Left standing on purpose. It is an 8% gap against a 17x improvement,
closing it means reopening the design 127 and 196 settled, and the 24 Tasks
it leaves in front are themselves high-value ones that should run. Worth its
own ticket if the ordering is still wrong after a campaign under these
numbers.

## Verification, 2026-09-02

The migration applies from an empty database in `CleanCreationTest`. Its
apply-time assertions confirm that all 61 property classes have an impact
prior, `value_for` reads `class_impact_prior`, and an authorization claim
cannot remain valued below `transport.header_policy` when both exist. The
complete DB module subsequently ran 1542 tests; its four remaining errors are
the unrelated order-dependent cases recorded in research section D, not the
scheduler migration. Together with the live `rk2here` measurement already
recorded above (428 Tasks ahead reduced to 24, with no transport Task among
them), all three acceptance criteria are satisfied.
