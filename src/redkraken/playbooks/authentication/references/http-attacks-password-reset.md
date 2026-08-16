# Password reset: the flow the authentication Playbook is not allowed to run

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## Why this is a reference and not a Playbook

Reset is a real class -- `authentication.recovery_flow` in the ticket 18
vocabulary -- and it deserves its own Playbook. It does not have one yet. Until
it does, this note exists so that a run holding a login reading does not reach
sideways into a reset flow and claim it from the wrong evidence.

The `authentication` Playbook's effects are `mutates_session`. A reset changes a
credential, which is `mutates_account`, and the risk floor refuses to run that
at `constrained`. That refusal is the mechanism, not a convention.

## What the eventual Playbook has to measure

Each of these is a separate reading and each needs a control:

* **the token's entropy and derivation.** A reset token that is a timestamp, a
  counter, or a hash of the email is guessable, and the evidence is a second
  token requested a moment later that stands in a predictable relation to the
  first. Two tokens, ours, both accounts we lease.
* **the token's binding.** A token minted for our account accepted for another
  account's reset is the sharpest finding in the family, and it needs two leased
  Identities.
* **the host the link is built from.** A reset email whose link points at a host
  the caller supplied is a token delivered to the caller. The evidence is the
  header sent and the link received, and it needs a mailbox we own. This is the
  one place where reading our own inbox is part of the reading.
* **the token's lifetime and single use.** The same token accepted twice is
  `business_logic.replay`; a token accepted long after issue is
  `session_handling.lifetime` on the reset artifact.

## The rule about other people's mailboxes

Every variant above requests a reset for an address. That address is always one
the Program leased to us. Requesting a reset for a real user's address sends
that person an email they did not ask for, which is the target's users being
touched by our run, and no engagement covers it.

Rate matters too: a reset endpoint is one of the easiest ways to have a Program
suspend an engagement, because it is one of the few endpoints whose abuse is
visible to end users rather than only to logs.
