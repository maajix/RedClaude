# 68 — Make an installed harness be the code it claims

**What to build:** Stop `pip install .` from shipping a stale `build/lib` copy, and make the running installation state which revision it was built from, so a door that is not the source is a refusal rather than a discovery.

**Blocked by:** 02 — Boot an installable `rk doctor`.

**Status:** resolved

**Reading on the How:** all four steps as written, plus one the How did not
foresee. The wheel and the reader have to walk the tree the same way or the
manifest is a second opinion rather than a check, so `build_backend.py` puts
`src/` on its path and calls `redkraken.build.digests` -- the same walk `rk
doctor` and the door verify with. There is one answer to "what is a shipped
module", and the manifest cannot disagree with the verification by construction.

- [x] Installing the working tree ships the working tree, whatever `build/` contains. `build_backend.py` removes `build/lib` before delegating to `setuptools.build_meta`; `tests/test_packaging.py::InstallationTest::test_a_stale_staging_directory_does_not_decide_what_ships` stages a poisoned `outcome.py` under `build/lib`, builds a wheel through the backend, and asserts the wheel carries the source bytes.
- [x] `rk doctor` reports the revision the installed package was built from and the digest of the modules it is running. `doctor.diagnose` carries a `build` block from `build.record`; asserted offline in `tests/test_doctor.py::ReadinessTest::test_the_build_it_is_running_is_reported` and end to end through the installed script in `tests/test_packaging.py::InstallationTest::test_the_installed_command_reports_its_version_and_diagnoses`.
- [x] A build whose manifest does not match the modules on disk is a failed assertion, not a warning. One `build_mismatch` violation, one assertion name, whichever caller asks: `tests/test_build.py::RecordedAssertionTest`, `tests/test_doctor.py::DistinctOutcomeTest::test_a_build_that_is_not_its_manifest_is_its_own_outcome`, and the door in `tests/test_build.py::ProxyServeBuildTest::test_serve_refuses_to_listen_when_the_install_does_not_match`.
- [x] The failure mode below has a regression test that does not need a git checkout to reproduce. `InstallationTest.copied()` copies `pyproject.toml`, `README.md`, `build_backend.py` and `src/` and nothing else, so the build under test runs outside a repository and the manifest it writes states `revision: null`. The reader's own cases in `tests/test_build.py::ManifestReadingTest` drive a fabricated `Traversable` and touch neither git nor an install.

## Why

This one cost a live test run and produced two findings that were not real.

On 2026-08-12 an installation was made with `uv pip install /home/majix/redKrakenV2`
from a clean tree at `a4ab808`. The door it installed was **not that tree**:

| File | Installed | Tree |
| --- | --- | --- |
| `proxy.py` | 124541 bytes, byte-identical to `build/lib/redkraken/proxy.py` | 149364 bytes |
| `outcome.py`, `seal.py` | same story | |
| `migrations/*.sql` | current | current |

The installed `proxy.py` matched commit `adacaea`, from before `446a65d FEAT:
tell a target that did not answer apart from a capability that was refused`. So
the door had no `target-unreachable` token, no strict-then-downgraded TLS retry,
and answered `407 capability-refused` for a target with an expired certificate.
The client closed those Tool runs as `denied` against a `decision='allow'` row,
`denied_without_a_refusal` fired, `rk db verify` failed, and `rk run` refused
every configuration with exit 9. Three hours of a live test were spent
characterising a defect that HEAD does not have: rebuilt from the same tree with
`build/` removed, the same request answers `200`, and an unresolvable in-scope
host answers `502 target-unreachable` with the Tool run closed as `error`.

The mechanism is ordinary and will happen again. `build/` is gitignored, so it
survives branch switches; setuptools' `build_py` copies a source file into
`build/lib` only when it is *newer* than the copy already there, and `copy_file`
compares with `>`, not `>=`. A checkout that lands a file with the same
mtime-second as the stale copy is not newer, so the stale copy is what goes into
the wheel. `--reinstall --no-cache` does not help: the staleness is upstream of
the cache.

The general form is what makes it a ticket rather than a note. This installation's
whole claim is that the record says what happened. A door running code that is
not in any commit breaks that claim silently: every Receipt it writes is honest
about the request and wrong about the harness.

## How

1. **Build.** A thin PEP 517 wrapper (`backend-path`) that removes `build/lib`
   before delegating to `setuptools.build_meta`. One file, no dependency, and it
   fixes every caller -- `pip`, `uv`, `build` -- rather than one documented
   incantation nobody types under pressure.
2. **Manifest.** The wrapper writes `redkraken/_build.json` into the wheel: the
   revision (`git rev-parse HEAD` plus a dirty flag when the tree is not clean,
   `null` when built outside a checkout), the build timestamp, and a sorted map of
   module path to SHA-256 for every `.py` and `.sql` file shipped.
3. **Assertion.** `rk doctor` gains a `build` assertion: recompute the digests of
   the installed modules and compare them to the manifest. Mismatch is a
   violation, with the first differing path named. It also reports the revision,
   so an operator running against a checkout can see at a glance that the door is
   two commits behind their tree.
4. **Door.** `rk proxy serve` runs the same check at startup and refuses to listen
   when it fails. A door is the one process whose code must be the code the
   Receipt implies.

## Not in scope

Verifying the installed revision *against the operator's checkout*. An installed
package cannot know which tree somebody meant. Reporting the revision it was built
from is the fact that makes the mismatch visible; deciding it is wrong is the
operator's.

## Repair

There is no verb that repairs the rows a defective build wrote. The five
`denied_without_a_refusal` Tool runs from this run are immutable by design and
still fail `rk db verify`, which still blocks `rk run` for every Program in that
installation. That is the correct behaviour for a corrupted record and a bad
outcome for an operator holding a day of real evidence. Whether the answer is a
purge of the affected Program, a restore, or a witnessed repair verb belongs in
its own ticket; this one only stops producing the rows.

## What was built

**One walk.** `redkraken/build.py` holds `digests`, which walks a
`importlib.resources.abc.Traversable` and hashes every `.py` and `.sql` under
it, skipping `__pycache__`. The anchor is a parameter, so the same function
serves `resources.files()` in an install, a `pathlib.Path` in the build backend,
and a tree a test fabricates. `verify` compares that walk against
`redkraken/_build.json`; `record` writes the result onto a `Ledger` as the
`build` assertion. `rk doctor` and `rk proxy serve` both call `record`, which is
why neither states the mismatch wording itself.

**Three states, not two.** No manifest is *source mode*: a checkout running from
`src/` is not a defective install, so it holds and reports what the tree hashes
to. A manifest that matches holds and reports the revision. Anything else --
digest drift, a module the manifest never listed, a manifest that will not parse
or claims a schema version this build cannot read -- is `build_mismatch`, and the
door refuses to listen. An unreadable manifest is deliberately not a fourth
state: an install that cannot say what it is has the same standing as one that
says the wrong thing.

**The revision is the enclosing repository's or nobody's.** `git rev-parse HEAD`
answers from whatever repository encloses the working directory, so building an
unversioned tree nested under one would stamp the wheel with a commit that never
contained it. `_revision` compares `--show-toplevel` against the backend's own
root and reports `null` unless they are the same tree.

**Two failures this ticket exposed rather than caused.** `entries()` skipped
`__pycache__` for the fixture and skill corpora but three callers each wrote
their own stray-name comparison; that is now `document.strays`. And a
`.claude/.cc-writes` scratch directory under `src/redkraken/migrations/`, mode
`0700` and invisible to git because `.gitignore` starts with `.claude/`, was
bind-mounted into the door container and made `ContainedDoorTest` fail with
`PermissionError`. Removed.

**Measured:** full suite 2841 tests, `OK (skipped=12)`; baseline, dispositions
and coverage gates green.
