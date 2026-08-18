# 14 — Accept one explicitly configured callback Observation

**What to build:** Turn one correlated inbound callback on an operator-configured channel into a provenance-backed Observation without authorizing general callback infrastructure discovery.

**Blocked by:** 06 — Store and read a redacted Artifact; 08 — Compile and enforce one Scope Policy.

**Status:** resolved

- [x] Only callback channels declared in the current Program policy can be provisioned or read.
- [x] A runtime-generated correlation token binds the inbound record to one Program, Test or Tool run without becoming Agent-visible credential material.
- [x] The exact inbound bytes are stored as an appropriate Artifact and promoted into an immutable Observation through runtime validation.
- [x] Missing, expired, fabricated and cross-Program correlation tokens cannot confirm a Hypothesis.
- [x] Unconfigured hosts, wildcard channels and adjacent infrastructure remain refused.
- [x] The acceptance test is entirely synthetic and does not contact an external callback provider.
- [x] One recorded arrival is one Interaction and one Observation however many times it is
      handed to `rk callback accept`, and the second call says so. Added by 67 after a live
      installation produced `CB1`/`O1` and then `CB3`/`O3` from the same file; the identity of
      an arrival is `callback_interactions_arrival_key` and the moment in it is the listener's,
      stated with `--at`.

## Comments

Implemented on branch `implementation/startup-assertion`.

### How it was built

This is the one Observation the harness does not fetch. Everywhere else the
evidence is a request the installation made and a Receipt the door wrote for it;
here the request is somebody else's, arriving at a name we published, and the
only thing tying it to a Program is a correlator that went out in a payload and
came back in a query. So the whole ticket is about attribution, and the schema is
`20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql`.

Four rules, each with a table or a trigger behind it:

- **A channel is declared or it does not exist.** `program_callback_channels` is
  projected from the compiled policy alongside `program_scope_versions`, keyed on
  `(program_id, version, ord)` and immutable with the version it belongs to. A
  channel the operator withdraws is absent from the next version and stops
  admitting arrivals the moment that version goes live, without anything being
  deleted — which is the reason the list is per version rather than per Program.
- **A correlator is minted by the runtime and stored as a digest.**
  `callback_correlators` holds `correlator_sha256`, never the plaintext.
  `mint_callback_correlator` takes the plaintext, digests it in the server and
  returns a row id, so a caller cannot state the digest of a correlator it did
  not generate. It must be one lower-case DNS label, because that is the only
  shape one can arrive in — a correlator that could never match the name it
  travels in is a canary that quietly does not work. Each correlator names its
  subject entity and, optionally, the Tool run or Test run it was minted for —
  one or the other, not both.
- **An arrival resolves a correlator or it is not written.**
  `record_callback_interaction` is one transaction: resolve the correlator,
  register the exact bytes, write the arrival, promote it into an Observation.
  Beneath it, `callback_interactions_attribution` is an `ENABLE ALWAYS` trigger
  that re-asks every question the writer asks — live correlator, this Program,
  the channel it was minted on, a name that channel admits, and the label that
  name carries digesting to the correlator the row is filed under. The writer is
  the convenience; the trigger is the guarantee.

  Two of those arms are less obvious than they look. Liveness is judged against
  the clock, not against `received_at`: that column is the caller's, so an
  expiry arm reading it would be a guard the guarded row could answer by
  backdating itself. And the last arm is the one that decides *whose* canary
  fired: every live correlator of a Program is admitted by the same channel, so
  without it an arrival at subject B's name could be filed under subject A's
  correlator, and the Observation would be a true fact about the wrong entity.
- **The Observation names the arrival.** `observations` gained a third
  provenance arm, `callback`, and a kind `callback_interaction` whose
  `allowed_provenance` is `{callback}` alone. The existing two-arm CHECK is
  dropped by catalogue lookup rather than by name, because those names are
  PostgreSQL's rather than the corpus's.

`rk callback provision` mints a correlator and prints the address to embed,
`<correlator>.<channel host>`; `rk callback accept` takes an arrival the
operator's own listener recorded, recovers the correlator from the name it came
in at, and asks the database to admit it. `redkraken/callback.py` does parsing
and byte handling and no deciding: names go through `scope.normalize_host` and
`scope.decide_callback`, the same two functions the proxy asks, so a name
admitted at the CLI is a name admitted at the door.

### The correlator is a correlator, not a credential

Criterion 2 says the token must not become "Agent-visible credential material",
and the honest reading is that it is not credential material at all: holding one
authorises no read, no write and no request. What it does is make an arrival
attributable, and what would be worth having is not the token but the knowledge
that a canary is armed and where. So the arrangement keeps that off the agent
surface rather than pretending the string is a secret:

- only the SHA-256 reaches canonical state;
- neither `callback_correlators` nor `callback_interactions` has a
  `state_read_surface` row, so `rk2_state` cannot read either at all — the
  absence is the grant;
- `observed_host` is redacted in the event log;
- the Observation's summary and metadata name the channel, the byte count and
  the artifact label, and never the host the arrival came in at.

One residual limit, stated rather than argued away: the arrival is registered
`agent_visible`, so an agent that reads the stored bytes may recover the
correlator from them. That is the direct consequence of criterion 3 — the exact
inbound bytes are what must be kept — and a real DNS canary carries its
correlator in the query name. It buys an agent nothing it can act on: writing an
arrival is a privilege no agent-reachable session holds, minting one is the
runtime's verb, and the correlator expires. What it does hand over is the
knowledge that a canary is armed at a particular label.

Closing it properly means ticket 07's shape rather than a flag: the exact bytes
sealed and encrypted, an agent-visible twin with the correlator redacted out,
and therefore an operator key on the accept path. That is a design change to
this ticket's artifact half and is not made here; the migration header records
the limit in the same words.

### Where the proof is

| Criterion | Test |
| --- | --- |
| 1 | `CallbackAdmissionTest.test_the_channels_the_policy_declares_are_projected_with_its_version`, `...test_a_version_that_carries_no_channel_list_yet_is_given_one`, `...test_a_channel_the_live_policy_withdrew_admits_nothing_it_used_to`, `ProvisionTest.test_a_channel_this_program_does_not_declare_is_refused` |
| 2 | `CallbackAdmissionTest.test_a_correlator_is_an_address_beneath_the_channel_it_names`, `...test_an_arrival_carries_the_correlator_it_is_filed_under`, `...test_a_correlator_that_could_never_arrive_is_not_minted`, `...test_the_correlator_reaches_the_database_as_a_digest_and_never_as_itself`, `...test_the_agent_connection_reaches_the_observation_and_neither_table`, `...test_what_the_observation_says_names_the_channel_and_not_the_canary`, `...test_the_event_the_arrival_emitted_carries_no_name_and_no_correlator` |
| 3 | `CallbackAdmissionTest.test_the_exact_inbound_bytes_are_the_artifact_the_observation_cites`, `...test_the_arrival_and_the_observation_it_produced_are_immutable` |
| 4 | `CallbackAdmissionTest.test_no_correlator_but_a_live_one_of_this_program_confirms_anything`, `...test_an_arrival_cannot_backdate_itself_into_a_dead_correlator` |
| 5 | `CallbackAdmissionTest.test_a_name_no_channel_admits_is_refused_wherever_it_is_asked`, `...test_a_wildcard_is_not_a_channel_and_never_becomes_a_program`, `CompilationTest.test_two_channels_at_one_endpoint_are_refused_rather_than_ranked`, `AcceptTest.test_a_name_no_channel_admits_never_opens_a_connection` |
| 6 | The whole of `CallbackAdmissionTest`: the listener is a file this test writes, and nothing in it opens a socket |
| 7 | `CallbackAdmissionTest.test_one_recording_is_one_arrival_however_often_it_is_handed_over`, `...test_the_arrival_is_filed_under_the_moment_the_listener_recorded`, `...test_two_arrivals_that_agree_but_for_the_moment_stay_two_arrivals`, `...test_the_identity_of_an_arrival_is_a_constraint_and_not_a_writer_rule`, `...test_a_moment_outside_the_correlator_s_life_is_refused_through_the_verb`, `MomentTest` |

Criterion 4 is the one the ticket rests on. Four arrivals at a name the policy
does admit — so none of them is refused for being off-channel — each carrying a
correlator that is fabricated, expired, cleared or another Program's, and two
more put straight to the writer stating no correlator at all, which is the case
the command cannot express because it refuses a bare endpoint before opening a
connection. A sixth is put straight to the table stating the instant its
correlator was minted as the time it arrived, which is a live window and a dead
canary. Afterwards the arrival and Observation counts are exactly what they
were.

Two things here are more than the six criteria asked for, kept deliberately.
`clear_callback_correlator` revokes a live canary, because expiry alone means an
operator who mis-embedded one can only wait; it costs a nullable column and one
arm in the resolver. `peer_class` records what the listener could tell about the
peer, because a DNS query arrives from a resolver that may be nowhere near the
target, and an Observation that let a reader assume otherwise would be
misleading about the one thing a callback proves.

The standing check `callback_admission` holds the arrangement in place: the four
verbs are the runtime's alone, no role may `UPDATE` a correlator or `DELETE` an
arrival, neither table is on the agent read surface, all four invariants are
still `ENABLE ALWAYS`, and no stored arrival lacks the correlator and declared
channel that would make it evidence or carries a label that is not the
correlator it was filed under. Five negative controls in
`tests/test_database.py` break one arm each; the last of them writes an arrival
at an undeclared name with the guard dropped, which is the state a restore would
produce and the only state that last arm exists for.

`SELECT` and `INSERT` stay with `rk2_runtime` on both tables, because 0029's
`readwrite_on_every_managed_table` asserts the runtime keeps them everywhere and
narrowing that generally is ticket 66's. Neither is a way in: a hand-written
token can only name a channel some version of this Program's policy declared, and
a hand-written arrival meets the same `ENABLE ALWAYS` trigger the verb does. What
the runtime can do without a verb is mint itself a correlator it could have asked
for anyway.

### What this ticket changed elsewhere

`_project_scope` in `redkraken/program.py` now writes the channel list beside the
rules, and every `rk run` reports `callback_channels`. It writes it on the
no-op path too: a Program already live on an unchanged scope version carries no
channel rows, and without that backfill an existing installation would admit no
arrival until its operator happened to edit the configuration file.

`scope.decide_callback` now names the most specific channel that admits a name,
the way `decide_request` already picked among matching rules. It is the answer
the correlator depends on — beneath a channel declared under another channel, the
label is a canary of the child — and having one function answer it means the
channel a Receipt would cite is the channel the arrival is read under. Alongside
it, `compile_policy` refuses two channels declared at one endpoint: the
projection keys on the host, so a second name for it would make "which channel
admitted this arrival" a question about declaration order, and would leave the
compiler reporting two channels where the database kept one row.

Nothing else in the corpus moved: an `http` channel already compiled to an
`egress_support` rule under ticket 08, which is what stops the harness treating
its own listener as a target, and these rows answer the other question — which
names an arrival may have come in on.
