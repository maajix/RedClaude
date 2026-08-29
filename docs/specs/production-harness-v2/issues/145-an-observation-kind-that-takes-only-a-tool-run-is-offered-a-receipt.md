# 145 — An observation kind that takes only a tool run is offered a receipt

**What to build:** The part of the `observations` element shape that stops a run
citing a Receipt for a kind whose `allowed_provenance` is `{tool_run}` alone, or
the recorded decision that this stays a promotion-time refusal.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt6`, 2026-08-22: two of
      fifteen drops are `incompatible_provenance` citing `content_match`. Both
      elements were well formed and named a real Receipt:

      ```json
      {"ref": "o_content", "kind": "content_match", "receipt_label": "R3",
       "subject_label": "APP2", "statement": "The page embeds a schema.org ..."}
      ```

      `observation_kinds` says `content_match|{tool_run}`. A Receipt is a
      request and its answer; a content match is a claim about what was found
      inside a body, which the schema holds is a tool's reading and not the
      request's own record.

- [x] **The choice is made rather than assumed.** JSON Schema cannot express
      "if `kind` is `content_match` then `receipt_label` is forbidden" in the
      one-level element shape the roster renders, so the honest options are two:
      split the argument so that kinds taking a tool run are a separate list, or
      leave it as a promotion refusal and make the refusal say what to cite
      instead. The second is cheap and is what the drop already almost does.

- [x] **Checked by something that would go red.** Whichever is chosen,
      `VocabularyAgreementTest` should fail if `observation_kinds`'
      `allowed_provenance` ever disagrees with what the roster tells a run.

## Why

Small, and deliberately filed apart from 144. Thirteen of `rk2hunt6`'s fifteen
drops are the rationale shape and two are this. It costs a Program two
Observations per run and stops nothing: it is the kind of residue worth knowing
about rather than the kind worth blocking a hunt on.

## Resolution, 2026-08-29

The second option, and the price is what decided it rather than the ticket's
hint. Both ends of the interface were read this session.

**WALL.** The rule is a relation between two fields of one element, and neither
end of the interface enforces it while a run can still act.

*What a run may send.* `roster._ELEMENTS["observations"]`
(`src/redkraken/roster.py:1091`) names `kind`, `subject_ref`, `subject_label`
and `summary` -- not `receipt_label`, not `tool_run_label`. The argument is
`free_text=True` (`roster.py:1390`) and `Argument.schema`
(`roster.py:724-735`) renders the element subschema deliberately open: no
`required`, no `additionalProperties: false`, no `type: object`. `refuses`
(`roster.py:755-765`) is the one key-level refusal there is, and it is
unconditional -- `receipt_label` is honest on nine of sixteen kinds, so it
cannot be listed.

*What refuses.* Promotion. `promote_proposal`'s Observation walk reads
`observation_kinds.allowed_provenance` and writes
`reason = 'incompatible_provenance'`, `cited = v_kind`
(`src/redkraken/migrations/20261008T000000Z__a_suggested_task_becomes_a_task_or_a_drop.sql:1090-1113`).
`proposal.review` -- the Python half, `src/redkraken/proposal.py:151-214` --
checks existence, Program, run and lane, and does not know about kinds at all;
`incompatible_provenance` is not in its `REASONS` (`proposal.py:53-62`).

*Who reads the refusal.* Nobody who can act on it. `Submission.submit`
(`src/redkraken/_launch.py:332-349`) latches the payload and answers
`"received; staging and provenance are the runtime's step"` -- it validates
nothing. Staging and promotion run in `execution.Slice._promote`
(`src/redkraken/execution.py:3389-3458`), after `result.mission_result` exists,
which is after the child has ended; the drops reach `facts["proposal"]["drops"]`
as `{element, reason}` and `cited` is not even carried. The codebase already
says so in its own words at `_launch.py:1918-1924`: *"the runtime promotes it
after the run has ended, where a dropped element leaves a `proposal_drops` row
nobody is left to read."*

So the second half of option two -- "make the refusal say what to cite instead"
-- buys nothing at the place the ticket implies. The drop is read by an operator
after the fact, never by the run that made the mistake.

**PRICE.** Splitting the argument is not two lists but four. `roster.py:278-295`
groups the sixteen kinds as seven `{receipt,tool_run}`, seven `{receipt}`, one
`{tool_run}` (`content_match`) and one `{callback}` (`callback_interaction`), so
"kinds taking a tool run are a separate list" does not partition them. Paying it
means a new argument and `OPEN_ARGUMENTS` entry in `roster.py`, a second walk in
`proposal.review`, a new `promote_proposal` replacing the ~90-line Observation
walk in the migration above, new `proposal_drops.element_path` prefixes that
every existing consumer indexes by, the description, the playbook corpus, and
the covering classes in `tests/test_database.py`. Against two elements of
fifteen in one run.

The other price is the one the roster had already written down, over
`mcp__rk2__submit_mission_result` at `roster.py:1376-1384`: the CLI validates
the served schema before `PreToolUse` runs, so *"a value outside an enum fails
the whole call rather than losing one element, and a run that cannot get its
result accepted files nothing at all ... only what is certainly refused is
refused here, where it costs a retry the model can actually make."* The gate
would refuse the same way -- `_argument_fault` returns one denial for the call,
`roster.py:2635-2656`. Trading two dropped elements for a risk of losing all
fifteen is the wrong direction, and it is the repo's own ordering rule that says
so.

**PURPOSE.** The deliverable is a Program that files the Observations it earned.
The workaround serves it: the element is dropped at promotion and the other
thirteen still land. What does not serve it is a rule the run cannot read in
time -- which is the half that was actually broken.

**RULE.** *Schema before callers*, applied at the wall: the statement of the
rule moves to the one place a run reads before it composes the call, and stays
one statement.

### What shipped

The refusal stays where it is. Not one line of the migration corpus changed and
no migration was written.

What moved is the sentence. `roster.observation_provenance` renders
`OBSERVATION_KINDS` as the clause `_launch.DESCRIPTIONS["submit_mission_result"]`
serves, so the rule the model reads is generated from the same values
`tests/test_roster.py` holds to `observation_kinds.allowed_provenance`. The
sentence it replaces named nine kinds and left the other seven as *"the other
seven take either"* -- a set difference the reader had to compute before it
could obey, in the same paragraph a run then got wrong. Every kind is named now,
in the corpus's own words (`receipt`, `tool_run`) rather than in English, so the
word maps onto `receipt_label` and `tool_run_label` without a fourth
restatement to drift. Two clauses were added around it: that a kind taking
`callback` is not one a result can file at all -- `rk2_element_evidence`
(`20260813T090000Z__a_recon_run_becomes_typed_surface.sql:579-597`) reads only
the two labels, and `record_callback_interaction`
(`20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:759-771`) is
what writes that Observation -- and that a mismatch is dropped after the run has
ended, where nothing is left to correct it.

`VocabularyAgreementTest.test_the_provenance_sentence_a_run_reads_is_the_one_the_corpus_seeds`
is the check. It builds the sentence from `allowed_provenance` as the migrations
seed it -- not from `OBSERVATION_KINDS`, which would be the generator agreeing
with itself -- and asserts the served description carries it. The existing
`test_every_observation_kind_carries_the_provenance_its_row_allows` keeps the
constant honest; the parse the two share is now `VocabularyAgreementTest.provenance`.
The class reads the corpus and not a server, so both run without PostgreSQL.
