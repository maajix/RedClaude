# 62 — Pass fresh-install and release hardening gates

**What to build:** Prove the complete harness can be installed, upgraded, contained, restored and operated at realistic size from a clean checkout without secrets or prototype dependencies.

**Blocked by:** 60 — Deliver the local operator UI; 61 — Prove long-campaign recovery and bounded context; 66 — Narrow the runtime role's privilege surface.

**Status:** resolved

- [x] A clean machine follows one documented install path, starts the supported topology and passes `rk doctor` without prototype or scratch content.
- [x] Empty creation, supported upgrade, integrity, dump, restore and post-restore continuation all pass through production commands.
- [x] Agent and browser container tests prove raw TCP, external DNS, control/provisioning ports and direct HTTP/HTTPS remain inaccessible.
- [x] Secret scanning covers tracked/unignored publishable files, build contexts, generated fixtures, logs, reports and evidence bundles with no findings.
- [x] Realistic corpus and Surface benchmarks meet documented budgets for Slate computation, Playbook selection, bounded reads, graph integrity and report rendering.
- [x] The full offline suite and composed production suite pass twice from clean state with no provider network, operator credentials or real target contact.
- [x] The declared `rk2_runtime` privilege surface from ticket 66 still holds on the installed and restored databases this gate builds, so hardening is verified on the artifacts an operator actually gets.

## What was built

`tools/release_gate.py`, one command, and the thing it is for is what it
refuses to measure. Every check before this one reads the checkout: the suite
imports `src/redkraken`, the repository gates walk the working tree, and all of
them are true of a directory nobody can install. This one exports `HEAD` with
`git archive` into a scratch root, installs it there through the README's
offline path, and then does everything else with that installation. Six stages
in order, each using what the one before it built -- export, install, database,
topology, privileges, suites -- because there is no installed application to
drive a database with until `install` has run.

**Nothing it starts inherits anything.** `Gate.environment` writes `PATH`,
`HOME`, `TMPDIR` and `LANG` and nothing else. A copy of the caller's
environment with the dangerous names removed would be a list of the dangerous
names somebody thought of, and the credential that reaches a child is always
the one nobody thought of. It is also half of criterion 6's "no provider
network, operator credentials": a key exported in the shell that runs the gate
cannot reach the suite the gate runs, and `test_the_written_environment_reaches
_the_child_and_nothing_else_does` asks a real child what it got.

**Every reading is taken from what a command reported, never from whether it
succeeded.** Three of them only exist because of that distinction:

* A second `rk db migrate` on a current database is the upgrade half of
  criterion 2. An installation that reapplied the entire corpus and verified
  afterwards reports exactly the same `ok`, so the reading is `applied`, which
  has to be empty.
* A restore is judged on the campaign, not the schema. The same Program is
  opened on the restored copy and has to come back with the same `program_id`
  and no first Tasks: a restore that produced a readable schema and an unusable
  campaign passes every check before that one.
* A suite exits zero when it skips everything. So both runs of a suite have to
  select the same tests, and the composed run has to skip fewer of them than the
  offline run did -- without a server and an engine behind it, "composed" is a
  second offline run under another name.

**The stages that need a machine fail rather than skip.** `topology` refuses
when there is no container engine or no Agent image. A gate that reported `ok`
having started nothing would be answering a question it never asked, on the one
machine where the answer matters.

**What the install stage looks at is where the failure would actually land.**
`pip list --local` cannot see a third-party requirement satisfied by the base
interpreter, because the environment is built with `--system-site-packages`, so
the artifact's own declaration is read instead: `importlib.metadata.requires`
has to come back empty. And a `src` layout ships a stray `tests` or `docs`
package as a *sibling* of the application in site-packages, not inside it, so
both are walked. The list of what may not be there is read from
`baseline/status.json` rather than written down a second time.

`tests/test_release.py` holds the part that decides -- preconditions, connection
strings, the written environment, the suite counts -- and none of it builds
anything: the stages are exercised by running the gate, which is the point of
it.

### What this does not prove

The upgrade reading is idempotence, not migration across released schema
versions. `rk db migrate` applies every pending migration and has no target
revision, so the only way to build a database at an older revision is to stop
applying the corpus partway, which no production command does. Until there is a
released schema to upgrade *from*, an archive of it is the input this gate would
need. What it does assert is the shape either side of that: the first migrate
applied the whole corpus into an empty database, `rk db status` reports nothing
pending on the migrated database, the second migrate applies nothing, and the
restored copy is not behind the corpus either.

### What it reported

`python3 -m tools.release_gate --superuser-url ...` against `fa9bdd3`, all six
stages, one run:

```
export: fa9bdd3033ae 774 files, tree dirty
install: rk 0.1.0, 227 modules, schema 20260913T010000, corpus 121
database: 121 migrations applied, verified, dumped 2692KB, restored and continued as 01a0164d
topology: rk2-gate-door-33cf9ad5 serving, rk2-gate-agent-33cf9ad5 internal with one peer
privileges: the declared runtime surface holds on both databases
suite offline 1/2: 1830 tests, 147 skipped, in 131s
suite offline 2/2: 1830 tests, 147 skipped, in 129s
suite composed 1/2: 3018 tests, 12 skipped, in 1438s
suite composed 2/2: 3018 tests, 12 skipped, in 1423s
```

The two suite profiles are the reading criterion 6 asks for. Composed selects
1188 more tests than offline -- the live database cases are parameterised per
server -- and skips 12 where offline skips 147, so the boundary, browser,
database and door cases that skip themselves without a server or an engine all
ran. Both profiles selected the same tests on the second pass, which is the
half that says the first pass left the server as it found it.
