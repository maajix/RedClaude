# 134 — An address range has no breadth floor

**What to build:** The floor for a CIDR inclusion that a wildcard inclusion has
had since the beginning, or a written decision that a range does not need one.

**Blocked by:** 117 — The CIDR arm of scope evaluation has no writer.

**Status:** needs-triage

- [ ] The asymmetry is stated. A wildcard inclusion must name at least two
      labels of its own, so `*.com` is refused; `README.md` calls it "a floor,
      not a public-suffix rule". A range inclusion has no equivalent. `1.0.0.0/8`
      and `2000::/3` are globally routable at both edges, so `scope._unroutable`
      admits them, and they compile as ordinary inclusions covering sixteen
      million and more addresses.
- [ ] The consequence is followed through rather than asserted. What a Program
      scoped that wide actually does depends on what mints subjects from scope,
      and ticket 117 decided a range mints no configured subject at all, so the
      first effect is on what an Entity discovered later is graded as, not on a
      first Task. This ticket carries that reading, measured, before it proposes
      a number.
- [ ] The decision is written into this ticket before the code is. Either a
      minimum prefix length per family, refused at compile time beside the
      wildcard rule and stated in `README.md` in the same breath as it; or the
      rule that a range is a statement of authority the operator is answerable
      for, and breadth is theirs to declare -- in which case the ticket says
      what stops a typo, because `/8` and `/28` are one keystroke apart.
- [ ] The refusal, if there is one, is at compile time. `scope._unroutable`
      already establishes the shape: refuse where it is written, not at the
      door, because a capability spent against a refused address has already
      cost something.

## Why

Found by the standards axis of the code review on `0759b7b`: *"`*.com` is
refused, but `1.0.0.0/8` and `2000::/3` compile as inclusions. The README
sentence the commit edits is the floor sentence."*
