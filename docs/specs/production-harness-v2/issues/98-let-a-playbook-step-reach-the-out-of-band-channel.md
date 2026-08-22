# 98 — Let a playbook step reach the out-of-band channel

**What to build:** The agent half of out-of-band observation: a verb that mints a
correlator for the run that will plant it, a name for the interaction on the
evidence surface, and a positive control that makes silence mean something.

**Blocked by:** nothing. Tickets 14 and 69 are resolved and they built the
recording half; this is the half neither of them owned.

**Status:** ready-for-agent

- [x] The state this ticket starts from is stated rather than re-discovered:
      **the record and the channel are built and sound, and the agent-facing
      half does not exist at all.** Ticket 14 shipped `callback_correlators` and
      `callback_interactions` with the correlator stored as a SHA-256 and never
      as plaintext, a third `provenance_kind` of `'callback'`, and the
      evidential observation kind `callback_interaction`
      (`20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:150`,
      `:208`, `:297-301`, `:319-334`, `:348-350`). Ticket 69 shipped the
      publisher, the tunnel and the rebindable name (`oob.py:604`, `:716`,
      `:844`, `:896`). What is missing is everything a step would use.
- [x] A Playbook step can obtain a correlator by a tool call. Today no Contract
      in `roster.CONTRACTS` (`roster.py:592-845`) mints or reads one -- the only
      occurrence of the word in that file is the label prefix
      `"callback_interactions": "CB"` at `roster.py:176` -- and `rk callback
      provision` is CLI-only (`callback.py:92`). The new Contract belongs with
      the request-shaped verbs rather than in `state.read`, because it mints
      state; it takes the channel name and the subject label, it returns the
      address to embed and the correlator id, and it binds the correlator to the
      calling run, which `mint_callback_correlator` already accepts
      (`callback.py:82-84`). Without it `playbooks/webhooks/playbook.md:36`
      names a capability that does not exist.
- [x] Nothing hands a correlator to a child today, and after this ticket
      something does. `identity_slot` and a correlator address were both
      searched for in `src/redkraken/packet.py` and neither is there.
- [x] Provenance `callback` gets a name the way the other two have one. The
      evidence view registers `receipt_label` and `tool_run_label` and no
      callback label (`20260812T063000Z__the_evidence_view_the_agent_reads.sql:71-81`),
      so an agent reads `provenance_kind = 'callback'` and a dead end. The
      interaction table itself stays off the read surface, because
      `observed_host` carries the correlator and the table comment says so
      (`20260812T040000Z…:235`, `:262-265`).
- [ ] **There is a positive control, and before it silence proved nothing.**
      `_listening` proves our own publisher answers `/health` on loopback before
      a name is bound (`oob.py:1080-1099`); nothing proves the bound public name
      is reachable from outside, and no proof-of-life arrival is ever recorded,
      so a dead tunnel and an uninteresting target are the same observation. The
      control is an arrival recorded through the ordinary publisher path
      (`oob.py:432-480`), the correlator that carries it is marked as a control
      so it is non-evidential for the target, `provision` refuses to mint
      against a channel with no control arrival inside a freshness window, and a
      negative reading cites the control beside it. That is what turns
      `playbooks/webhooks/playbook.md:61` -- "No arrival inside the declared
      window is not a refutation on its own" -- from a caveat into a finding.

      **NOT BUILT.** This is the one criterion of the eight that is not in the
      tree, and it is not a decision or a judgement call: every part of it lives
      in a file this work was not given. A proof-of-life arrival has to be
      recorded through the publisher's own request handler, which is
      `oob.py:432-480` (`_answer`, and `_record` beneath it); the thing it would
      replace is `_listening` at `oob.py:1080-1099`; and the refusal that makes
      silence mean something belongs in `provision` at `callback.py:92-217`,
      whose agent-facing twin `request_callback_correlator` would take the same
      clause. `oob.py` and `callback.py` are both outside the file list this
      work owns, so nothing here touched either.

      What the rest of the ticket left in place for it: the mint verb built
      below already refuses on five conditions and answers each in a sentence,
      so a sixth -- "this channel has no control arrival inside the window" --
      is one more arm of the same block and one more sentence in the same
      shape. The `is_control` column a control correlator would need does not
      exist either, and `callback_correlators` is 014's table, so that part is a
      migration on top of these. Until it is built, the sentence in
      `playbooks/webhooks/playbook.md` step 3 is still the honest one: no
      arrival is the absence of a refutation and not a refutation.
- [x] The stale refusal in the vocabulary is superseded.
      `0018_vocabularies.sql:251-269` still reads as a live refusal: it says an
      out-of-band kind "cannot be in the vocabulary, because its
      `allowed_provenance` would be empty" and that it goes back in "when the
      collector that generates its provenance exists". The collector exists, the
      third provenance record exists, and the kind was inserted by
      `20260812T040000Z…:348-350` -- so the comment describes a decision that
      was reversed and is the most misleading line in the schema on this
      subject. A comment-only migration supersedes it so nobody re-litigates it.
- [x] The `label`-versus-`path` disagreement is settled in one direction and
      only one. `oob.py:642-650` refuses any placement but `path`, because "a
      publisher serves one hostname, which has no labels to vary", while
      `playbooks/ssrf-url-routing/playbook.md:34` tells a step to use "a second
      label under it". One of the two moves; a quick tunnel serves one hostname,
      so the honest answer is probably the Playbook.
- [x] The limits the channel needs are the channel's and not the model's: the
      runtime mints the label, one channel per Program, and an expiry. A
      correlator planted in a target's system is a durable artefact whose
      lifetime we do not control.

## Why

Capability F in
`docs/research/playbook-state-of-the-art/09-capability-matrix.md` -- 14 of the
131 techniques, and file `08` calls it "the highest-leverage single addition in
this document" because it is the only way any blind class is detectable at all:
blind SSRF, blind XXE, blind command injection and JNDI-style lookups have no
other oracle. The phase-1 list above is
`docs/research/harness-capabilities/12-out-of-band-observation.md`, section
"Phase 1 — make what exists citable, and make silence mean something", whose own
verdict on the tree is "partial: the channel and the evidence record exist and
are sound; the agent-facing half does not exist at all, so today no playbook
step can cite an arrival without an operator standing in the middle".

Nothing here needs a new observation kind, and that is the point of doing it
now: `callback_interaction` is evidential and backed by `{callback}` alone, so
the citation chain from a correlator to an Observation to the stored inbound
bytes is already sound. Every link in it is currently reachable only by an
operator.

A DNS listener, a channel that can answer, SMTP and LDAP are all named in the
research and all deliberately out of this ticket. The first needs a delegated
domain and an authoritative server rather than a quick tunnel; the second is
capability G and is a different publisher, because today's mapping is fixed at
startup by design (`oob.py:144-160`).

## What was built

Seven of the eight criteria. The one that is not is the positive control, and
the reason is recorded on the criterion itself: every file it lives in is
outside this work's file list.

**The Contract, at `src/redkraken/roster.py`.** `mcp__rk2__mint_callback` is a
`REQUEST` in the `state.propose` group, writing `callback_correlators`. It is
in `state.propose` beside the Finding ask and not in `net.request`, because the
door is not involved in any of it: the correlator travels out inside a request
the model composes for itself, and the arrival comes back to a listener that is
nobody's tool call. `_check_authority` already keeps `state.propose` and
`sched.pick` off one role, so the three roles that hunt hold it and the
orchestrator, the validator and the reporter do not.

Two arguments, and the three things that are not arguments are the ticket's
last criterion. The channel and the subject label are names the child can
already read; the correlator, its lifetime and the choice of channel are not
its to make. A canary is planted in somebody else's system and outlives the run
that planted it, so the parts a model could get wrong are the parts it is not
given. The `channel` pattern is `program_callback_channels.name`'s own check
constraint, restated so that a name no channel could carry is refused by the
closed schema rather than by a query that finds nothing.

**The verb, at
`migrations/20260928T010000Z__a_step_mints_its_own_correlator.sql`.**
`request_callback_correlator` is the caller's half of
`mint_callback_correlator`, in exactly the relationship `propose_finding` has
to `open_finding`. It exists because minting is the smallest part of the work:
what a correlator needs first is the live scope version, the Program's one
declared channel, that channel's live binding, the subject Entity and the Tool
run that will carry the name out -- five lookups, each of which is a refusal a
child should be told about in words. Written in the supervisor that would be
five round trips and five sentences in a second language.

"One channel per Program" is enforced here and it is a count, not a guess. The
scope compiler admits several channels and `mint_callback_correlator` would
take any of them; this verb refuses to pick, and says how many there are and
what they are called. That is the same rule `program_callback_channels` states
for itself when it refuses two channels on one host -- "which channel admitted
this arrival" is not a question about row order.

The correlator binds to the egress Tool run of the asking Agent run.
`callback_correlators` admits a Tool run or a Test run and neither an Agent run
nor a Task, so that is the narrowest true binding available for a child, and it
is also the run every Receipt for the planting request hangs off. Finding it
means naming `mcp__rk2__net_request` in SQL, which is the far end of the naming
hazard ticket 97 recorded in `roster.py`; the comment there says so.

**The supervisor half, at `src/redkraken/agent.py` and
`src/redkraken/_launch.py`.** `_Tools` grows a fourth arm and `_callback`
generates the correlator with `secrets.token_hex(callback.CORRELATOR_BYTES)` --
128 bits, one DNS label, digested by the database and stored by neither side.
That generation is the one thing this method does that the database could not
do for itself, and it is the reason the tool is safe to hand a model: a child
that could choose the name could plant one it had read somewhere else.
`Correlator` on the child's side is `Proposal` without the ceiling, and the
missing ceiling is deliberate -- a refused mint reaches no table at all, so
counting refusals would bound a run for asking about its own configuration.

**The citation, at
`migrations/20260928T030000Z__an_arrival_has_a_name_the_agent_can_cite.sql` and
`src/redkraken/packet.py`.** `v_evidence` gains `callback_label`, so an
Observation whose provenance is an arrival stops reading as the word `callback`
and two nulls. The obvious shape -- a `LEFT JOIN callback_interactions` -- is
refused, and rightly: the view is `security_invoker`, the join would need a
`state_read_surface` row, and arm (c) of `check_callback_admission` refuses one
for either callback table in any column, because `observed_host` IS the
correlator. So the label comes off a `SECURITY DEFINER` function scoped to
`rk2_program()`. The table stays off the surface; the name comes off it. The
packet's own projection names all three provenance labels now, because that
list is spelled out and a hole there would be the same hole one layer further
in.

**The superseded refusal, at
`migrations/20260928T040000Z__the_out_of_band_refusal_was_reversed.sql`.**
Comments and one assertion. 018 argued at length that an out-of-band kind
cannot be in the vocabulary and named the condition under which the refusal
lapses; ticket 14 met every part of that condition, and 018's note is still
where the column comment sends a reader. A migration cannot edit 018's `--`
lines and should not want to -- what applied, applied -- so what moves is the
pointer. The assertion is the claim the new comments make: that the kind is
there, that it is backed by `{callback}` alone, and that an Observation may
still have callback provenance. If any of that stopped being true these
comments would be as wrong as the note they supersede.

**`label` versus `path`, settled in the Playbook.** `rk oob serve` refuses any
placement but `path` because a publisher serves one hostname, which has no
labels to vary, and that is a fact about quick tunnels rather than a
configuration choice. So `ssrf-url-routing` step 1 stops asking for "a second
label under" the callback host. It now says the channel gives the reading one
of its two names and never both, names `mcp__rk2__mint_callback` as where the
address comes from, and says plainly that a Program declaring only one of the
two controlled hosts leaves this Playbook with nothing for its two arms to
differ by. That is a narrowing, and it is the honest one: the Playbook was
asking for a name the publisher cannot bind.

`webhooks` step 1 names the verb it had been describing in prose since it
shipped, and says the address is embedded exactly as returned.

## Where the ticket was right, and where it was thin

Every line reference in this ticket checked out: `callback.py:82-84` is the
`MINT` statement and `mint_callback_correlator` does take the calling run;
`0018_vocabularies.sql:251-269` is the refusal, word for word;
`oob.py:642-650` is the placement refusal and the quoted sentence is exact;
`roster.py:176` is `"callback_interactions": "CB"` and it was the only
occurrence of the word in that file. `playbooks/webhooks/playbook.md:36` did
name a capability that did not exist.

Two places the ticket is thinner than the tree:

- The third criterion says nothing hands a correlator to a child and that
  something should. What hands one over is the verb, not the packet.
  `packet.py` compiles before the container starts, so a correlator staged into
  a packet would be minted for every Task including the ones that never plant
  one, and would spend part of its life before the model read it. The packet
  did change, but for the fourth criterion -- it carries the arrival's name
  now, which is the other half of the same round trip.
- The eighth criterion's "one channel per Program" is not a fact about the
  schema. `program_callback_channels` is keyed per scope version and nothing
  caps the count, so this had to be built as a refusal rather than assumed as
  an invariant. That is what the verb does: it mints when there is exactly one
  and names both when there are two.

