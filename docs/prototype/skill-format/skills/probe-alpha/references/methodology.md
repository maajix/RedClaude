# Methodology (fixture)

Progressive disclosure target: this file is only read once `probe-alpha` has
been selected, which is the whole point of keeping SKILL.md short.

Ordering that matters:

1. Establish the baseline as one identity before varying anything.
2. Change exactly one of identity, tenant, object owner, or action per request.
3. Treat an unchanged status code with a changed body as a difference.
