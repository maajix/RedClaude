# Filter bypasses: the whole page is refused, and the argument is about what a bypass proves

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

A catalogue of ways to get a value past a front end that inspects requests.
Change the case. Change the encoding, then double it. Insert comments a parser
strips and a matcher does not. Split the value across two carriers. Move it into a
multipart part whose content type the inspector skips. Pad the body past whatever
size the inspector stops reading at. Chunk it so the matcher sees fragments.
Change the content type to one the inspector has no parser for. Add a header some
deployments treat as a trusted-source marker. Then a list of vendor-specific
quirks, page after page, each a spelling that one product's rule set missed.

## Why the Playbook refuses all of it

**A defeated filter is not a defect found.** This is the whole argument. The front
end is not the thing under test; the application behind it is. A reading that
spends its requests finding a spelling the inspector missed has established
something about a product the Program probably bought, and has established nothing
about whether the application does anything wrong with the value once it arrives.
If the value is harmless behind the filter, the bypass is a note for the vendor. If
it is harmful, the harm is the finding and it has its own class and its own
Playbook.

**It inverts the reading's own discipline.** Every Playbook in this corpus works by
changing one thing and measuring. A bypass hunt changes the spelling repeatedly
until an answer changes, which means the variable under test is whatever finally
worked, and the reading has no baseline it did not move.

**It is a scan wearing a smaller word.** Twenty spellings of one value against one
route is twenty requests whose purpose is to be refused. Against a write route,
which is this Playbook's subject, it is twenty attempts to create something.

**The results rot immediately.** A vendor quirk list is accurate for the rule set
version it was written against, and nothing in a finding can say which version was
in front of the target. Knowledge whose expiry is invisible is the kind this
corpus keeps behind `stale_after` and, in this case, does not keep at all.

## What the Playbook kept

One rule, in the ceiling, in the negative: where a front end refuses the arm, that
is the answer. Record the refusal, quote it, and stop. Do not re-encode the value,
change its case, split it across carriers a third way or move it into a multipart
part.

And one framing worth having. A refusal from the front end is itself an
observation about the deployment -- something is inspecting requests, and it
matched this one. That belongs in the Task note, because it changes what any later
reading against the same surface should expect, and it is free.

## The one legitimate neighbour

Where two hops disagree about what a path spells, so a rule enforced in front is
not enforced behind, the class is `authorization.edge_rule` and `deployment` is
the Playbook. That reading looks like a bypass and is not one: the variable is the
spelling of a path both hops resolve, the arms are bounded at three, each has a
control on an unrestricted path, and the claim is about the disagreement rather
than about having got past something. The difference is that it is measuring two
programs against each other, not searching for a string that works.
