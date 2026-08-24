# 109 — `compare_responses` differences two Artifacts where eleven Playbooks ask for more

**What to build:** A decision about the arity of the one comparison program the
harness ships, and then either a script that takes more than two Artifacts or a
corpus that stops asking it to.

**Blocked by:** 107 — A label minted after launch must be resolvable in the run
that minted it.

**Status:** resolved

- [x] The two ends of the mismatch are stated exactly.
      `src/redkraken/skills/compare-responses/scripts/compare.py` refuses
      anything but a pair -- "compare takes exactly two artifacts" -- and the
      registry agrees: `offline_tool_arguments` declares `first` at position 0
      and `second` at position 1, both `artifact` kind and both required
      (`20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:462-467`).
      Eleven Playbooks instruct a difference over three or more, or over "sets":
      `agentic-ai:75`, `authentication:74`, `browser-storage:64`,
      `browser-realtime:55`, `identity-lifecycle:63`, `routing:77`,
      `web-cache:71`, `workload-identities:68`, `jwt-jose:82`,
      `request-integrity:73`, `webauthn:60`.
- [x] The decision is named rather than assumed, because either answer is
      defensible. Widening the script means `only_in_first` and
      `only_in_second` become an N-way answer, and the registry's own reason for
      the current shape has to be re-argued: "`first` and `second` are not
      interchangeable to a reader of the answer -- `only_in_first` is a
      different claim from `only_in_second` -- so the order is part of the call
      and not a convenience" (`20260922T030000Z...:457-460`). Narrowing the
      corpus means eleven Playbooks say "a baseline against each arm, one call
      per arm", which is expressible today.
- [x] Ticket 101 is named as the owner of whichever half falls to the corpus.
      This ticket does not rewrite a Playbook body; it settles what the body may
      ask for.
- [x] The arity question is downstream of the label question and the ticket says
      so. `compare_responses` takes two `artifact`-kind arguments and, until
      tickets 106 and 107 land, a run cannot name even one Artifact it produced
      -- so widening the script first would buy nothing for any of the eleven.

## Why

`docs/research/wiring/22-corpus-instruction-wiring.md` section 3.7, and its gate
5: "Every argument name inside a skill-script instruction is a row in
`offline_tool_arguments` for that program, and the count of values the body
instructs does not exceed the count of arguments declared."

The report is unsure which side is wrong, and so is this ticket. What it is not
unsure about is that both sides are shipped: the script is registered, granted
to `web_hunter` and named in thirty-nine Playbook bodies, and eleven of those
bodies ask it a question it refuses at argument parse time.

## The decision, taken 2026-08-22

**B: rewrite the eleven -- in fact thirteen -- Playbook bodies as one call per
arm against a named baseline, and leave `compare_responses` at two. The script is
not widened.**

What decides it is that **not one of the thirteen bodies asks for what an n-way
compare computes.** An n-way compare answers "how do these k things differ from
each other". Every body in this corpus names one thing as the reference and asks
how each of the others differs from *it*: the `authentication` body walks a fixed
credential set against the same endpoint; the `identity-parsing` body walks
encodings of one identifier; the `api` body walks methods against one route. That
shape is k-1 independent two-way comparisons, and running them as k-1 calls loses
nothing, because there is no cross term for the missing calls to have carried.
Widening the script to k arms would compute a k x k matrix of which the bodies use
one row.

**The blocker is not the script's arity; it is that the answer cannot say which
arm it is about.** `skill.envelope` carries the script name, the exit status and
the streams, and no argument name at all
(`src/redkraken/skill.py:170-198`), and `run_skill_script` hands the program its
inputs positionally (`src/redkraken/tool.py:741-748`). So a child that made
thirteen calls today would get thirteen answers it cannot key back to the
credential, encoding or method that produced them, and that is exactly the defect
a widened script would make worse rather than better -- a 13-arm answer with no
arm names is unreadable in a way a 2-arm answer is not. The fix that makes B work
is one field on the envelope naming the inputs, which is smaller than a second
comparison engine and is useful to every other registered program.

**Rejected: A, widen `compare_responses` to n arms.** Beyond computing a matrix
nobody reads, it multiplies the output. The measured two-arm answer is 520 bytes;
a full 13-arm difference set on the same inputs is 78 pairs. Against the packet's
32,768-byte ceiling (`src/redkraken/packet.py:133-134`) that is the arithmetic of
ticket 107 arriving in a place it does not need to.

**Rejected: leave the bodies as they are.** They currently instruct the child to
do something the tool cannot do, which is a Playbook that mints refusals.

## What was measured

Thirty-nine Playbook bodies under `src/redkraken/playbooks/` were read and every
`compare_responses` instruction in them classified by the number of things the
prose puts in the comparison
(`docs/research/decisions/31-inline-values-and-nway-compare.md`, "Ticket 109").
**Thirteen bodies ask for three or more arms.** Twelve of the thirteen are
fan-out against a single named reference; the thirteenth is a pairwise sweep
whose prose still names a reference in the sentence before. **Zero ask for the
arms to be compared to each other.**

## Correction: thirteen bodies, not eleven

The ticket's criterion 3 says "the eleven Playbook bodies". Verified against this
tree: it is thirteen. The two the count misses are
`src/redkraken/playbooks/identity-parsing/playbook.md:84` and
`src/redkraken/playbooks/api/playbook.md:62`. The corpus figure the ticket gives
-- thirty-nine Playbook bodies -- is exactly right. Whoever does the rewrite
should work from a fresh grep and not from the number eleven.

## Comments

**2026-08-24 -- closed on the decision, with nothing left in this ticket's own
scope.**

B stands and the script stays at two Artifacts. Nothing here widened
`compare_responses`, nothing added an argument to `offline_tool_arguments`, and
`compare.py` is the file it was.

The thirteen bodies that ask for three or more arms are ticket 101's, which this
ticket named as the owner before the decision was taken. Arbeitsblock 3
implements 101 for five Playbooks only -- `attack-surface`, `object-ownership`,
`browser-script`, `cookies` and `payment-workflows` -- and **not one of the five
is among the thirteen**, so this settlement rewrote no body and the thirteen are
still owed.

The enabling fix the decision names is also still owed and is deliberately not
built here: an answer from `compare_responses` carries no input digest, so k-1
calls come back as k-1 answers nothing keys to an arm. Building it before the
thirteen bodies are rewritten would be a field nobody reads. Whoever rewrites
them builds it in the same pass; the smallest shape is the two input digests
echoed in the script's own answer, which costs a script digest and a registry
migration and no new authority.
