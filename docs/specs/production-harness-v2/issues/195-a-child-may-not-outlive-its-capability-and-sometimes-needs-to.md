# 195 — A child may not outlive its capability, and sometimes needs to

**What to build:** An operator's answer to how long one capability lives, instead of five minutes written into a function.

**Blocked by:** nothing.

**Status:** open

- [ ] **The measurement is in the ticket.** Database `rk2here`, 2026-08-26,
      lap 09 of a fresh sitting:

      ```
      lap 09 -> refused | ok False | exit 3
      violations: [{"code": "invalid_configuration",
                    "source": "environment:RK_AGENT_IMAGE",
                    "detail": "the Agent boundary could not be provided: the
                               Agent container exceeded its 299.995s runtime"}]
      ```

      The source names the image, which is not what went wrong. Nothing is
      wrong with the image: the child was killed for running longer than its
      capability lives.

- [ ] **Where the number is.** `authorize_tool_run` mints the capability with

      ```sql
      v_expires_at := clock_timestamp() + interval '5 minutes';
      ```

      and `execution._launch` takes `timeout = min(self.timeout, lifetime)`.
      `agent.TIMEOUT` is 900s, so the ceiling that binds is always the
      capability's, and a child that needs six minutes is stopped at five. The
      interval is a literal inside a function body: there is no setting, no
      column and no environment variable, so an operator who wants a different
      answer has to write a migration.

- [ ] **What it costs, measured.** One lap in twelve on this engagement. The
      Task is not lost — the next lap's reconciliation returns it and `hunt.sh`
      tolerates three consecutive non-zero laps — so the price is the lap, about
      2.5 minutes, and the work the child had done inside it.

- [ ] **And the other thing the same number does.** A request still on the wire
      when the token expires loses its capability, because
      `resolve_egress_capability` answers only for a run that is still running.
      That is ticket 194, whose fix keeps the Receipt attributed but does not
      change the fact that a 30-second connect towards a dead host can outlive
      the credential that authorised it.

- [ ] **It drops work, and that is the part that is not a preference.** A Task
      is retried and then abandoned:

      ```
      label | kind  | state      | status    | attempts | subject
      T42   | recon | _anonymous | abandoned |        3 | APP27
      T13   | recon | _anonymous | abandoned |        3 | APP101
      T21   | recon | _anonymous | abandoned |        3 | APP109
      ```

      Three applications that were never mapped, dropped quietly, because the
      work they need does not fit in five minutes. Nothing in the record says
      "this subject was abandoned for want of time" — the rows say `abandoned`
      the way an unworkable Task says it.

- [ ] **And it stopped the sitting.** `hunt.sh` breaks on three non-zero laps in
      a row, which is the right rule for three refusals and the wrong one for
      three ceilings: the harness is working, the child simply ran out of clock.
      The loop now counts them separately and stops at twelve. That keeps a
      sitting alive; it does not make the ceiling right.

- [ ] **What the decision is.** Longer is fewer stopped children and a longer
      window for a leaked capability. The window is worth stating plainly
      before anyone picks a number: a capability is only usable through this
      door, which independently checks scope, budget, Halt and Lease on every
      request and receipts all of them, so what a leaked one buys is in-scope
      requests at the Program's own rate — not a wider reach, just a longer one.
      That is an operator's call and not a default this file should pick.

## Why

Five minutes is a good number. Being a literal is what makes it a problem: it
is a security parameter with no place to say it, and the first person who needs
a different one will discover it as a refusal naming the wrong thing.

The refusal naming the wrong thing is its own half of this. `source:
environment:RK_AGENT_IMAGE` sends an operator to look at the image, and the
image is fine. A child stopped by its own capability's clock should say so.
