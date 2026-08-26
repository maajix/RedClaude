# 187 — A discovery run behind the rules that permit it

**What to build:** a way for a Program's configuration to say that automated
content discovery against a list is permitted, and a Tool run that performs it
under that permission and proposes surface.

**Blocked by:** nothing.

**Status:** open

## The rule the corpus already states and cannot act on

`attack-surface`'s step 2 says it plainly: *a generic wordlist is a different
activity with a different cost, and it is the Program's rules of engagement that
decide whether it is permitted at all*. Its reference `ffuf.md` says where such
a run belongs -- *behind the Program's rules of engagement, as an explicit Tool
run, with the concurrency and the wordlist recorded, proposing entities and
nothing else* -- and `auto-scanners.md` says what to answer an operator who asks
for one.

Three texts describe the permission. Nothing implements it.
`rules_of_engagement` is a closed set of five keys -- `availability_impact`,
`credential_use`, `mutation`, `pivoting`, `sensitive_data_access` -- and none of
them is about request volume. `scope.DISCOVERY_TECHNIQUES` is the wrong hook: it
names five ways of finding *hosts*, all false, with no key to enable them, and
this question is about paths on a host already in scope.

## What it has to decide

- The sixth `rules_of_engagement` key, its name and its default. Absent means
  denied, which is this harness's rule everywhere else, so the default writes
  itself; the name is the part worth arguing about.
- Where the list comes from. A wordlist shipped in the image is a corpus
  artifact with a digest, and a wordlist an operator hands in is an Artifact
  with a hash. The second is the smaller change and the first is the
  reproducible one.
- What the run may propose. `ffuf.md` already answers: entities and nothing
  else. A path that answered is surface, and the claim about it is
  `attack-surface`'s, made afterwards against the control that Playbook
  establishes.
- The rate. `ffuf.md`'s own line -- *the number to write down before it starts
  is requests per second, not the wordlist size* -- and the door already holds
  a token bucket per Program, so this may be nothing more than saying so.

## Why it is not urgent for the engagement that raised it

The Program this came from forbids automated scanning outright, so the key would
read false there and the harness would behave exactly as it does today. The
ticket exists because the next Program will permit it and the operator asked for
it in advance.
