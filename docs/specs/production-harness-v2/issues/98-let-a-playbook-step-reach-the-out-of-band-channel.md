# 98 — Let a playbook step reach the out-of-band channel

**What to build:** The agent half of out-of-band observation: a verb that mints a
correlator for the run that will plant it, a name for the interaction on the
evidence surface, and a positive control that makes silence mean something.

**Blocked by:** nothing. Tickets 14 and 69 are resolved and they built the
recording half; this is the half neither of them owned.

**Status:** ready-for-agent

- [ ] The state this ticket starts from is stated rather than re-discovered:
      **the record and the channel are built and sound, and the agent-facing
      half does not exist at all.** Ticket 14 shipped `callback_correlators` and
      `callback_interactions` with the correlator stored as a SHA-256 and never
      as plaintext, a third `provenance_kind` of `'callback'`, and the
      evidential observation kind `callback_interaction`
      (`20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:150`,
      `:208`, `:297-301`, `:319-334`, `:348-350`). Ticket 69 shipped the
      publisher, the tunnel and the rebindable name (`oob.py:604`, `:716`,
      `:844`, `:896`). What is missing is everything a step would use.
- [ ] A Playbook step can obtain a correlator by a tool call. Today no Contract
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
- [ ] Nothing hands a correlator to a child today, and after this ticket
      something does. `identity_slot` and a correlator address were both
      searched for in `src/redkraken/packet.py` and neither is there.
- [ ] Provenance `callback` gets a name the way the other two have one. The
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
- [ ] The stale refusal in the vocabulary is superseded.
      `0018_vocabularies.sql:251-269` still reads as a live refusal: it says an
      out-of-band kind "cannot be in the vocabulary, because its
      `allowed_provenance` would be empty" and that it goes back in "when the
      collector that generates its provenance exists". The collector exists, the
      third provenance record exists, and the kind was inserted by
      `20260812T040000Z…:348-350` -- so the comment describes a decision that
      was reversed and is the most misleading line in the schema on this
      subject. A comment-only migration supersedes it so nobody re-litigates it.
- [ ] The `label`-versus-`path` disagreement is settled in one direction and
      only one. `oob.py:642-650` refuses any placement but `path`, because "a
      publisher serves one hostname, which has no labels to vary", while
      `playbooks/ssrf-url-routing/playbook.md:34` tells a step to use "a second
      label under it". One of the two moves; a quick tunnel serves one hostname,
      so the honest answer is probably the Playbook.
- [ ] The limits the channel needs are the channel's and not the model's: the
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
