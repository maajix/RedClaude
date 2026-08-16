# 48 — Rework v1 Agents, Skills, references and sink packs

**What to build:** Preserve the useful operational knowledge from v1 while replacing unsafe Agent authority, routing Skills and global reference loading with the production roster and capability model.

**Blocked by:** 44 — Compile capability-based Skills; 47 — Validate v1 dispositions against real replacements.

**Status:** resolved

**Deviation on criterion 2:** "runnable checks" ships on one of the four rewritten Skills,
not four. A check is a declared stdin/stdout case for a script the Skill owns, so a Skill
with no deterministic transform has nothing to declare and a tick there would be a check
that checks nothing. `analyse-source` gained `extract_paths.py` and two cases because it
had a real gap: its own step 2 admitted that a minified bundle is not JSON and was being
read by eye. `enumerate-surface` runs `jq`, which is a registered runtime tool the Tool
run records rather than a script this corpus owns. `browser-evidence` and
`handle-untrusted-content` are procedures over a live browser and over content whose
whole point is that it is not trusted; neither has a pure function in it to pin. All four
do carry role compatibility and an evidence profile, which the other two thirds of the
criterion asked for, and `skill.check_all()` runs every case there is on every compile.

**Deviation on criterion 5:** 9 of the 82 exist; the 73 do not yet. The nine sink packs
are built here and are files on disk. Every one of the 73 in-scope operator references is
*assigned* -- its row already names one bounded `reference:playbooks/<topic>/references/<file>.md`,
so none is loaded globally and none is unattached -- but the file at that name is written
by the Playbook ticket that owns the topic, which is one of 49 through 56. So the
criterion's word "assigned" is true today and its implication that the material is in the
tree is not, for 73 of 82. The ledger says which is which without reading this: those rows
cite `ticket:NN` and refuse the moment that ticket resolves without the file. The 39
Android references do carry the retirement record, which is the clause that is fully true.

- [x] The 11 v1 Agent definitions reconcile exactly as five web-hunter lenses, two recon lenses, two JS-analyst lenses, one deterministic reporter replacement and one explicit Android retirement.
- [x] The four surviving v1 capability Skills are rewritten in the production format with role compatibility, evidence profile and runnable checks.
- [x] Fourteen routing Skills resolve to Property-class vocabulary, five superseded Skills resolve to runtime/reporting controls, three workflow Skills resolve to scheduler behavior and two Android Skills resolve to retirement.
- [x] Replacement capability Skills needed by Playbooks exist even where no one-to-one v1 Skill survived.
- [x] All 73 in-scope operator references and 9 sink packs are assigned to bounded Skill or Playbook references rather than global Agent context; the other 39 are Android and carry the retirement record instead.
- [x] No v1 tool allowlist, workflow lifecycle, reporter prose authority, credential handling or engagement data is copied into production unchanged.

## Comments

Implemented on 2026-08-16.

### Most of this ticket was already true, and the ledger is what says so

Tickets 44 through 47 built the roster, the Skill corpus, the Playbook selector and the
disposition ledger. This ticket is the one that claims v1's knowledge arrived intact, and
four of its six criteria are counts over rows that already resolve to something on disk:
`check_dispositions` reads `roster.ROLES`, `skill.SKILLS` and `playbook.PLAYBOOKS` and
refuses a row naming anything those compilers would not produce. Criterion 5 is the count
that does not -- see its deviation above -- and criterion 2 is the one clause that needed
building rather than checking. So the work here was to check each criterion's arithmetic
against the ledger rather than restate it, to say plainly where the arithmetic does not
reach, and to build the one group of rows that still promised `ticket:48`.

The eleven Agent definitions split five/two/two/one/one exactly as criterion 1 says:
`abuse-case-adversary`, `boundary-breaker`, `bypass-specialist`, `exploit-agent` and
`web-vuln-hunter` to `role:web_hunter`; `recon-agent` and `surface-archaeologist` to
`role:recon`; `code-auditor` and `code-mapper` to `role:js_analyst`; `reporter` to
`role:reporter`; `mobile-android-hunter` to `retired:android`. Criterion 3's split of the
eight superseded Skills is the ledger's too: `code-audit-loop`, `web-full-pentest` and
`web-pentest-loop` are the three workflow Skills and they resolve to `control:execution`,
which is the scheduler; the five runtime and reporting ones are `web-reporting`,
`severity-calibration`, `draft-bug-bounty-submission`, `scope-guard` and `tool-preflight`.

### The ten rows that were still owed

`playbooks/code-review/` -- one README and nine language sink lists -- was the last group
citing `ticket:48`, and it is the group this ticket had to actually build. They now live
as `src/redkraken/skills/analyse-source/references/`, ten files bound to the one technique
that reads source.

They were written fresh. The v1 corpus is not in this repository -- `baseline/` froze
identity and digest, deliberately without content -- so there was nothing to copy, and
`code-review.md` says so in its own text rather than leaving a reader to assume these are
the v1 texts. Each pack is written to the scope its ledger row names: the sink, the shape
that makes it a sink, the safe form, and a closing section on what a grep match is *not*.
`sinks-kotlin.md` refuses Android sinks explicitly, because Kotlin survives here as a
server language and its Android half is retired.

Fidelity to the v1 wording is unverifiable by construction, so nothing claims it. What is
checkable is the shape, and one test checks it rather than the filenames: every `##`
heading in a pack is a Property class the selector can select on, read out of the shipped
vocabulary rather than listed in the test, and every pack ends with its "What a match is
not" section. That is what caught the first draft of `sinks-ruby.md`, which was headed
`filter.bypass_differential` -- an event kind, not a Property class, and exactly the
near-miss a reader would have skimmed past.

### A reference is maintainer material, and that is the whole point

`roster.FORBIDDEN_BUILTINS` forbids `Read` to every role, so there is no file tool and no
progressive disclosure: nothing a running Agent does can open one of these. That is not a
gap in the migration, it is the migration. In v1 these texts were loaded into every
Agent's context, which is the ambient authority this system exists to leave behind. Here
they are hashed into `Skill.version`, so editing one is visible on every Task recorded
afterwards, and they are read by whoever maintains the technique.

Two things follow, both now enforced. `skill.py`'s docstring states it, so the next person
adding a `references/` directory does not ship a Skill body that points at a file the
model cannot open. And `test_no_skill_body_sends_a_model_to_a_file_it_cannot_open` checks
every shipped body for every one of its own reference names and for the directory name,
because that instruction would be an instruction to do the impossible.

### The one new script, and why the other three Skills have none

Criterion 2's "runnable checks" was the one clause that would have been a lie as a tick.
`analyse-source` step 2 said to extract with a tool rather than by eye and then offered
only `jq`, which cannot read a bundle -- so the step ended by conceding that some
extractions are done by reading. `extract_paths.py` closes that: stdin is the one
Artifact, stdout is `{paths, scanned_literals, urls}`, and `scanned_literals` is there so
a short `paths` list reads as the proportion it is rather than as a finished inventory.
It reports *literals*, which is a deliberate distance from routes -- whether the
application requests one is a call graph this does not read, and whether anything answers
is an exchange this role cannot make, which is step 4.

Three declared cases run on every compile through `skill.check_all()`, twice each, in an
empty directory with a two-entry `PATH`. The third exists because the review found the
first two pinned nothing about a query string or a protocol-relative literal:
`/api/orders?id=1&sort=asc` is the parameter half of what this Skill grounds and was being
dropped, and `//cdn.host/app.js` was landing in `paths` when it names somebody's host. The
deviation block above says why the other three rewritten Skills declare none.

What the script does not do is parse. It pairs quotes, so an apostrophe in a comment pairs
with the next quote and `scanned_literals` is an order of magnitude rather than a count --
said in the docstring, because a denominator that is quietly approximate is worse than one
that says so. Nine parsers would buy a better denominator and the same paths.

### The prose exemption in the boundary checker

Adding markdown under `src/` found a real hole. `production_boundary_errors` scanned every
non-Python shipped file with `scan_bare_tokens=True`, so a reference saying "prototype
pollution" or "the docs" failed the build on the word alone. The Python branch has
exempted docstrings from that sweep all along for exactly this reason.

The exemption is for `references/` and not for markdown. That distinction is the whole of
it: a reference is prose a maintainer reads, while `SKILL.md` and `playbook.md` are read by
a model, so a bare `/tmp` in one of those is an instruction to write where this boundary
refuses to go -- and `/tmp` and `.scratch` are spelled without a separator, which is
precisely what only the bare-token sweep catches. The first version of this exempted every
`.md` under `src/`, which would have taken the sweep off the entire model-facing corpus to
serve one line of one reference. Every path-shaped rule still fires everywhere, since the
others need a separator, a leading dot or a quote -- `docs/prototype/SKILL-FORMAT.md` in a
reference is still refused -- and there is a test on each of the three directions.

### The registry had to move with the corpus

`analyse-source` gaining eleven dependency rows and a new manifest digest broke two
`tests/test_database.py` assertions, and correctly: 037 wrote the registry as a copy of
the corpus, and `check_skill_registry` recomputes `version` from the dependency rows, so a
corpus edit without a matching migration is `version_disagrees` at the gate. 038 is that
migration -- a fresh file, because a recorded migration whose bytes changed is schema
drift and `rk db migrate` refuses the whole corpus over it.

The dependency list is deleted and reinserted rather than added to. A manifest is the
whole list: a reference removed from the corpus has to leave the table too, or the version
is a digest over a file nobody ships. This is the shape every ticket from 49 on will
repeat, since each authors Playbook references and Skill text that the registry mirrors.

### What moved in the ledger

The ten rows now cite `tests/test_skill.py` instead of `ticket:48`, which is the crossing
from promised to built, and the report's last line reads `built 49 promised 122 retired 52`.
Ticket 47's Comments quote that report, so its quoted line was updated in the same change
-- a resolved ticket quoting a stale count is a second source of truth about the same
number. Its deviation block was left saying what it said on the day it resolved, with one
sentence added for the count that moved and one corrected clause: it claimed all nine
migration tickets were still open, which stopped being true here. A resolved ticket's
record of what it shipped is not a document to rewrite as the tree moves under it.

48 is the first registered migration ticket to resolve, which turned up a test that had
encoded "registered" as "open". The rule it should have encoded, and now does, is the
checker's: a registered ticket is open, or it is resolved and no row still cites it.
