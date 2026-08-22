# 128 — Three Python capabilities with no caller

**What to build:** A caller or a removal for each of `Store.holds`,
`skill.check` and `skill.check_all`, and a corrected docstring where one of them
claims a caller it does not have.

**Blocked by:** nothing.

**Status:** resolved

- [x] `Store.holds` (`src/redkraken/store.py:162-171`) is removed, or its
      docstring stops naming a caller it does not have. The docstring
      (`:163-170`) ends "which is what the proxy asks before deciding whether
      withholding a wire view would withhold anything at all". The proxy asks
      the database instead -- `READS = "SELECT program_reads_artifact($1, $2)"`
      at `src/redkraken/proxy.py:1061` -- and the only references to `holds` in
      the tree are four in `tests/test_database.py`. Superseded and never
      removed.
- [x] The Skill corpus is checked by something other than the test suite, or the
      checking is deliberately test-only and says so. `skill.check_all`
      (`src/redkraken/skill.py:477-485`) runs every declared synthetic case in
      the corpus and its docstring says "so a caller can count"; there is no
      caller outside `tests/test_skill.py`. `skill.check`
      (`skill.py:430`) is called only from inside `check_all` (`skill.py:483`),
      so the whole subtree is production-dead.
- [x] `doctor.diagnose` is the candidate caller and the ticket decides for or
      against it explicitly. `doctor.CORPORA` (`src/redkraken/doctor.py:102-106`)
      compiles all three corpora -- playbooks, skills, fixtures -- and compiling
      a Skill is not running its cases, so a shipped Skill script whose declared
      answer no longer holds is never caught on an installation. Either the
      diagnosis runs the cases, or a comment says why running attacker tooling
      during a health check is the wrong trade.
- [x] Nothing is removed on the strength of a cross-reference alone. The
      counter-example is in the same file tree: `jsscan.py`'s entire public
      surface looks orphaned to a Python cross-reference and is not -- it is
      mounted into a tool container and run as a subprocess
      (`src/redkraken/tool.py:118`, `:653`, `:666`). Each of the three above was
      checked for that shape and has none.
- [x] Where a function is kept deliberately uncalled, it is documented the way
      the repo already documents one:
      `src/redkraken/skills/analyse-source/scripts/extract_paths.py:151-157`
      says it is "Not called by `extract`, and here on purpose", names the other
      half of the pair and names the test that holds the two answers equal.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 2.8. Three functions,
none with a comment explaining the absence, and one of them asserting in prose
that a caller exists.

The `skill.check` pair is the one with a cost beyond tidiness. A Skill script is
a program the harness ships and hands to a model; its declared cases are the
only statement of what it does. Running them only in the repo's own test suite
means an installation whose Python, whose container image or whose corpus has
drifted finds out when a hunt uses the Skill.

`ready-for-agent` because each of the three is a small, bounded decision with
the evidence already gathered, and because the removal option is safe: the tests
that reference them are the only callers, so a removal is visible immediately.

## What was built

Three decisions, each measured before it was made.

**`Store.holds` is kept, and its docstring now says what is true**
(`src/redkraken/store.py:162-181`). Measurement: `.holds(` appears four times in
the whole tree and all four are in `tests/test_database.py` -- `:36316`,
`:42635`, `:42665`, `:42683` -- so there is no production caller, which is the
one thing this ticket had right about it. What the docstring claimed is now
stated the way the proxy already states it: `proxy.py:1127-1130` carries the
comment "Asked of the database rather than of the store, because the store is a
content-addressed heap five modules write and a hit in it says the bytes are on
disk, not that this Agent may read them". Two sides of the tree held opposite
accounts of one fact and the proxy's was the correct one, so the store's was
corrected rather than deleted.

It is kept because `load` can only answer the negative by raising, and two of
the four call sites are asserting exactly the negative -- an import that redacted
a secret, and one that refused bytes no longer hashing to the name they arrived
under. A test spelling that `path_for(...).exists()` would be asserting the
filing scheme rather than asking the store. Documented in the
`extract_paths.verb_of` manner the last criterion names: that nothing in
production calls it, why it is here, and what asks the question in production
instead. Removal was the other option and was unavailable in any case -- the four
call sites live in a file this change does not own.

**`skill.check` and `skill.check_all` are kept, deliberately test-only, and now
say so** (`src/redkraken/skill.py:477-494`). Measurement: `check_all` is named in
`tests/test_skill.py` at `:372`, `:380`, `:388` and `:516` and nowhere else in
any file of any type -- there is no CI directory in this tree, no entry point, no
`getattr`, no registry row -- and `check` is reached only through `check_all`.
The docstring's "so a caller can count" is now "so the suite can count", which is
what happens: `:516` asserts the exact six-name tuple the shipped corpus
produces.

**`doctor.diagnose` is refused as that caller, and the reason is not the one this
ticket assumed** (`src/redkraken/doctor.py:415-433`). The trade offered here was
"running attacker tooling during a health check". That is not the trade, because
there is no attacker tooling in the corpus: the two scripts this version ships --
`analyse-source/scripts/extract_paths.py` and `compare-responses/scripts/
compare.py` -- are stdin-to-stdout JSON transforms that take no arguments, no
environment and no file beside them, and `check` runs them in an empty directory
under `env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"}` against a synthetic
payload. Nothing there reaches a network or a target.

The real trade was measured instead. `rk doctor` is held to a containment
contract by `tests/test_cli.py`'s
`ContainmentTest.test_diagnosis_creates_no_state_and_sends_no_traffic`: it runs
the command under `sys.addaudithook` and asserts the observed event list is
*empty*, where observed means every `subprocess.`, `socket.`, `urllib.`,
`os.exec`/`fork`/`spawn` event, every `os.mkdir`/`remove`/`rmdir`/`rename` and
every write-mode `open`. Running that same hook over `skill.check_all()` on the
shipped corpus records 38 of them: 12 `subprocess.Popen`, 6 `os.mkdir`, 6
`os.rmdir`, 1 `os.remove` and 13 write-mode `open`s. Wiring the cases into the
diagnosis would break that test and break the promise `doctor`'s own module
docstring opens with -- "It reads; it never creates state, contacts a target or
starts an Agent run". Cost was not the objection and was measured too:
`check_all()` takes 0.283s against `diagnose()`'s 0.062s.

The comment sits on `_assert_catalogue`, where a reader meets "compiled" and
would otherwise ask why not "run", and it carries the structural half as well:
`Corpus` is a name and a compile function precisely so that loop cannot know
which of the three corpora is the skills, and running cases would be that loop
knowing.

**Nothing was removed, so the fourth criterion holds by construction** -- the
`jsscan.py` shape was checked for all three regardless. The only `.py` filenames
any registry row can name are `compare.py`, `extract_paths.py`, `jsscan.py` and
`verify.py` (every such literal in `src/redkraken/migrations/`); the column that
carries them is `offline_tools.analyser`, constrained by
`CHECK (analyser ~ '^[a-z][a-z0-9_]{0,31}\.py$')`; and a staged analyser is run
as a script, not called by function name. No row names `store.py` or `skill.py`,
and neither module has a `main`.

### Where this ticket was wrong

* `READS = "SELECT program_reads_artifact($1, $2)"` is at `proxy.py:1131`, not
  `:1061`. Line 1061 is a comment line about `UNSCOPED`. The claim the wrong
  number was attached to is true, and better evidenced than stated here:
  `proxy.py:1127-1130` already says in the repo's own words why the store is not
  asked.
* "running attacker tooling during a health check" describes nothing in this
  corpus. Both shipped scripts are pure transforms over a synthetic payload.
* The containment contract on `rk doctor` goes unmentioned, and it is the fact
  that decides the third criterion. The third criterion asked for a comment
  giving a reason that is not the operative one.

Everything else checked out: `store.py:162-171` and its `:163-170` docstring,
`skill.py:477-485`, `skill.py:430`, the `check` call at `skill.py:483`,
`doctor.py:102-106`, `tool.py:118`/`:653`/`:666`, `extract_paths.py:151-157`, and
"four in `tests/test_database.py`". (`docs/research/wiring/21-agent-surface-wiring.md:427`
carries stale line numbers for those four and a wrong range for the docstring;
that file is not this ticket's to edit.)

No row in `tools/check_wiring.py`'s `OWED_GAPS` names ticket 128, so none was
removed: the register reported 122 rows before this change and 122 after.
