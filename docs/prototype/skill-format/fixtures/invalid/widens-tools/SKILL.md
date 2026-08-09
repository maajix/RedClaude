---
name: widens-tools
description: Use when proving the validator rejects a skill that grants itself a tool its roles do not have.
allowed-tools: Read, WebFetch
model: opus
bb:evidence_profile: no_such_profile
bb:scripts:
  - name: missing.py
    description: Declared but absent on disk.
    args:
      type: not-a-real-type
bb:notes: "Unknown bb: keys are legal, so this one must not be reported."
weather: sunny
---

# Invalid on purpose

Negative fixture. Every rule this file breaks is one the validator must catch:
R4 (`name`, `model`), R5 (`weather`), R6 (`WebFetch`), R7 (no role loads it),
R8 (unknown profile), R9 (missing file, invalid schema), R10 (the dangling link
below).

See [references/nope.md](references/nope.md).
