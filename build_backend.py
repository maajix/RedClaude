"""The build backend that makes an installed wheel be the code it claims.

A thin PEP 517 wrapper around setuptools, selected by `pyproject.toml`'s
`build-backend`/`backend-path`. It exists for one defect and one guarantee:

  * setuptools' `build_py` copies a source file into `build/lib` only when the
    source is newer than the staged copy, comparing with `>` on a whole-second
    mtime. A checkout that lands a file on the same second as a stale, gitignored
    `build/lib` from an earlier build ships the stale copy. Purging `build/lib`
    before every build removes the comparison, so the wheel is the working tree
    and nothing `build/` happened to hold.

  * `build_wheel` writes `redkraken/_build.json` into the wheel: the revision it
    was cut from and a SHA-256 of every `.py` and `.sql` module shipped.
    `rk doctor` and `rk proxy serve` recompute those digests against the modules
    on disk and refuse an install whose code is not the code its manifest names.
    See `redkraken.build` for the reading half, whose walk this one calls.

The manifest is written for wheels only. An editable install and an sdist stay
in "source mode" -- no manifest, no digest check -- because a developer's tree
is meant to be edited and is verified by the test suite, not by its own runtime,
and a wheel built later from the sdist mints its own manifest through this same
backend.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from setuptools import build_meta as _origin

# Hooks this wrapper does not touch, re-exported so the frontend sees a whole
# backend. Editable installs pass straight through: no manifest, source mode.
get_requires_for_build_wheel = _origin.get_requires_for_build_wheel
get_requires_for_build_sdist = _origin.get_requires_for_build_sdist
get_requires_for_build_editable = _origin.get_requires_for_build_editable
prepare_metadata_for_build_wheel = _origin.prepare_metadata_for_build_wheel
prepare_metadata_for_build_editable = _origin.prepare_metadata_for_build_editable
build_editable = _origin.build_editable

_ROOT = Path(__file__).resolve().parent
_SOURCE = _ROOT / "src"
_PACKAGE = _SOURCE / "redkraken"
_STAGE = _ROOT / "build" / "lib"

# The package about to be built is also the one that reads what this writes, so
# the walk and the schema come from it rather than from a second copy here that
# would drift. Importing it off the source tree is what setuptools already does
# for `attr: redkraken.__version__`, and `redkraken.build` is stdlib-only, so
# this adds no build dependency.
sys.path.insert(0, str(_SOURCE))

from redkraken import build as _reader  # noqa: E402

_MANIFEST = _PACKAGE / _reader.MANIFEST


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    _purge_stage()
    _write_manifest()
    try:
        return _origin.build_wheel(wheel_directory, config_settings, metadata_directory)
    finally:
        # The wheel carries its copy; the working tree keeps none, so the dev
        # checkout stays in source mode and the manifest is never committed. A
        # build killed outright still leaves one behind, and the checkout would
        # then quietly stop being in source mode -- so the suite asserts the
        # checkout carries no manifest rather than trusting this line alone.
        _MANIFEST.unlink(missing_ok=True)


def build_sdist(sdist_directory, config_settings=None):
    _purge_stage()
    # A source distribution carries no manifest: a wheel built from it runs this
    # backend again and mints a fresh one. Remove any stray copy so the tarball
    # is the source and nothing about the machine that packed it.
    _MANIFEST.unlink(missing_ok=True)
    return _origin.build_sdist(sdist_directory, config_settings)


def _purge_stage() -> None:
    """Delete the staged copy so setuptools re-copies the working tree entire."""
    shutil.rmtree(_STAGE, ignore_errors=True)


def _write_manifest() -> None:
    revision, dirty = _revision()
    manifest = {
        "schema_version": _reader.SCHEMA_VERSION,
        "revision": revision,
        "dirty": dirty,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modules": _reader.digests(_PACKAGE),
    }
    _MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _revision() -> tuple[str | None, bool]:
    """The commit this build was cut from, and whether the tree was dirty.

    `(None, False)` when there is no checkout of *this* tree to ask -- a build
    from an unpacked sdist, or a source tree with no `.git`. git answers about
    the nearest repository at or above where it is pointed, so an sdist unpacked
    inside somebody else's checkout would otherwise mint a manifest naming a
    commit that has nothing to do with this code, and report that stranger's
    uncommitted work as this build's dirty flag. The toplevel has to be this
    tree or there is no revision to state.
    """
    try:
        if Path(_git("rev-parse", "--show-toplevel").strip()).resolve() != _ROOT:
            return None, False
        head = _git("rev-parse", "HEAD").strip()
        status = _git("status", "--porcelain")
    except (OSError, subprocess.CalledProcessError):
        return None, False
    return head or None, bool(status.strip())


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(_ROOT), *arguments], capture_output=True, text=True, check=True
    ).stdout
