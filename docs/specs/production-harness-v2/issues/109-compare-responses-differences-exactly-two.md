# 109 — `compare_responses` differences two Artifacts where eleven Playbooks ask for more

**What to build:** A decision about the arity of the one comparison program the
harness ships, and then either a script that takes more than two Artifacts or a
corpus that stops asking it to.

**Blocked by:** 107 — A label minted after launch must be resolvable in the run
that minted it.

**Status:** needs-triage

- [ ] The two ends of the mismatch are stated exactly.
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
- [ ] The decision is named rather than assumed, because either answer is
      defensible. Widening the script means `only_in_first` and
      `only_in_second` become an N-way answer, and the registry's own reason for
      the current shape has to be re-argued: "`first` and `second` are not
      interchangeable to a reader of the answer -- `only_in_first` is a
      different claim from `only_in_second` -- so the order is part of the call
      and not a convenience" (`20260922T030000Z...:457-460`). Narrowing the
      corpus means eleven Playbooks say "a baseline against each arm, one call
      per arm", which is expressible today.
- [ ] Ticket 101 is named as the owner of whichever half falls to the corpus.
      This ticket does not rewrite a Playbook body; it settles what the body may
      ask for.
- [ ] The arity question is downstream of the label question and the ticket says
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
