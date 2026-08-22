# 144 — Every Hypothesis a run files is dropped for the shape of its rationale

**What to build:** The `rationale` shape in the `hypotheses` element of
`submit_mission_result`, so that a run writes the object the column takes rather
than the paragraph it currently writes.

**Blocked by:** 139 — A recon mission never asks for the Hypothesis it may
propose. Nothing wrote a `rationale` before 139 asked for one, so this defect
could not be seen. The schema-side machinery exists: `Argument.element`
renders `items.properties`, and `_ELEMENTS["hypotheses"]` already constrains
`property_class` this way.

**Status:** resolved

- [x] **What the run actually wrote is read before the shape is chosen.**
      Measured in `rk2hunt6` on 2026-08-22, the first hunt after ticket 139 put
      the ask in the Mission. Four Hypotheses were filed across two runs and all
      four were dropped `malformed_field` citing *"rationale is not an object"*.
      The content was not the problem. One of them, verbatim from
      `proposals.payload`:

      > "rationale": "Mechanism: the origin emits only X-Content-Type-Options
      > and X-Frame-Options; absent HSTS a first or post-cache-expiry navigation
      > to http:// can be intercepted and downgraded ... Expectation: a hardened
      > Drupal front end would return Strict-Transport-Security with a non-zero
      > max-age ... Falsifier: a response from this origin on any path carrying
      > a Strict-Transport-Security header with max-age>0 and a
      > Content-Security-Policy header would refute the claim."

      All three keys of `rk2_rationale_keys()` are answered and answered well.
      They are in one string because nothing told the run they were three
      fields.

- [x] **The fix is in the schema and not in the prose.** The Mission already
      says *"a rationale answering mechanism, expectation and falsifier"* and
      the run obeyed it to the letter. Six hunts on 2026-08-22 established that
      a rule stated only in prose is followed in spirit and broken in shape;
      `hypotheses_rationale_shape` is a CHECK, and what the model is handed has
      to be a schema. `_ELEMENTS["hypotheses"]` currently constrains one field:

      ```python
      "hypotheses": {"property_class": Argument("string", enum=PROPERTY_CLASSES)},
      ```

- [x] **The cascade is counted, so the value of the fix is not guessed.** The
      four drops took nine `evidence[]` elements with them, dropped `no_subject`
      for citing a hypothesis ref that no longer existed. Thirteen of the
      fifteen drops in `rk2hunt6` trace to this one field. The other two are
      ticket 145.

- [x] **The rest of the element list is read for the same defect.** `statement`,
      `subject_label` and `property_class` all survived; `rationale` is the only
      field of `hypotheses` whose column type is not text. Whether any other
      element in `_ELEMENTS` has a non-scalar column behind a scalar schema is
      part of this ticket's answer.

- [x] **Checked by something that would go red.** `tests/test_roster.py` already
      carries `VocabularyAgreementTest`, which reads the migration corpus rather
      than a live server. A rationale whose keys disagree with
      `rk2_rationale_keys()` is the same class of drift and belongs beside it.

## Why

This is the last thing between the harness and its first Hypothesis. Ticket 139
made a run ask itself the question and it answered; the answer is refused at the
door for the shape of one field. Tickets 140 and 141 are both downstream of a
Hypothesis that survives promotion, so until this lands they are built against
an empty table and land looking correct.

Measured cost of not fixing it: `rk2hunt6` produced 11 Observations, 5 Entities
and zero Hypotheses across three laps, and stopped with `nothing_to_execute` for
the seventh hunt running.

## Closing, 2026-08-22

**The prose already said it, in the words a reader would call unambiguous, and
the model still wrote a paragraph.** `_launch.DESCRIPTIONS` has carried this
sentence since the schema patch landed:

> a rationale object whose only three keys are mechanism, expectation and
> falsifier, all three answered

Four claims were filed under that sentence and four wrote one string. This is
the same finding six hunts produced from the other side and it is worth writing
down once more: a description tells a model what a field is *for*, and a schema
tells it what the field *is*. The two are not substitutes.

### What changed

`roster.RATIONALE_KEYS`, held to `rk2_rationale_keys()` by the corpus test, and
a `rationale` in `_ELEMENTS["hypotheses"]` declared `Argument("object", ...)`
with one bounded string per key. The served subschema is now:

```json
{"type": "object",
 "properties": {"mechanism":   {"type": "string", "minLength": 1, "maxLength": 2000},
                "expectation": {"type": "string", "minLength": 1, "maxLength": 2000},
                "falsifier":   {"type": "string", "minLength": 1, "maxLength": 2000}}}
```

`type: object` is the half that stops the measured failure; the CLI refuses the
call before `PreToolUse` runs, which the model sees as a rejected tool call it
can correct inside the same run rather than as a `proposal_drops` row written
after the run has ended.

`minLength: 1` is the second half and is not decoration. `rk2_gradable_claims`
(ticket 140) will not grade a claim whose mechanism, expectation or falsifier is
empty, so a part sent empty is a claim that promotes cleanly and then sits at
`proposed` forever with nothing saying why.

### Three places the change had to reach

`Argument.schema()` rendered `items.properties` for every `element`, which is
JSON Schema's word for what is in a *list*. An object-shaped argument now
declares `properties` directly.

`_check_argument` refused an object element twice over: `only an array has
elements`, and then `is either constrained or declared unconstrained`, because
`constrained` counts what bounds a *value* and `element` is deliberately not
counted so that an open list can still name one field's vocabulary. An object
that names its fields is the one place those two meet, and it is constrained by
naming them.

`_value_fault` walked `element` only for a list, so the gate would have passed a
string rationale that the schema refused. The gate is the pair's second half and
now checks the same thing.

### Checked by something that would go red

Two tests in `tests/test_roster.VocabularyAgreementTest`: that the keys are
`rk2_rationale_keys()`'s and the rendered subschema is what is written above,
and that the gate refuses a string where an object belongs and an empty part
where a sentence belongs. `tests.test_roster` runs 114 tests, OK; the fast tier
runs 419, OK.

### Not yet measured in a live hunt

The next hunt is what closes the loop 139, 144 and 140 make between them.
