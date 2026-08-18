"""Reading the build manifest: is this install the code it claims to be?

The build backend (`build_backend.py` at the repo root) writes `_build.json`
into every wheel: the revision the wheel was cut from and a SHA-256 of every
`.py` and `.sql` module it ships. This module reads that manifest back and
recomputes the digests against the modules actually on disk, so `rk doctor` can
report what an install is running and `rk proxy serve` can refuse to run one
whose code is not the code its manifest names.

The walk that produces those digests is `digests()` here, and the backend
imports it rather than carrying its own: two walks that had to agree would
eventually not, and the symptom would be every install refusing at once.

An install with no manifest is running "from source" -- a developer's editable
checkout, a tree on `sys.path`, an unpacked sdist. That is not a fault: there is
nothing to verify against, and the source is verified by the test suite instead.
`verify` says so rather than inventing a mismatch it cannot substantiate.

Stdlib only, like everything the harness runs in production. The revision is
read out of the manifest, never asked of git: the reading half runs where there
may be no checkout to ask.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable

from redkraken.document import BYTECODE_DIR, digest
from redkraken.outcome import BUILD_MISMATCH, Ledger

#: The manifest resource, written into the wheel by `build_backend`.
MANIFEST = "_build.json"

#: What both callers call this assertion. One name, so an operator reading a
#: diagnosis and an operator reading a refused door are reading about the same
#: statement about the same install.
ASSERTION = "build"

#: The manifest schema this reader understands. A manifest from a newer build is
#: a mismatch, not a warning: an install this code cannot verify is one it must
#: not vouch for.
SCHEMA_VERSION = 1

#: A digest is recorded for every module of these kinds -- the code the harness
#: runs and the schema it applies.
HASHED_SUFFIXES = (".py", ".sql")


class ManifestError(ValueError):
    """The build manifest is present but cannot be read as one."""


@dataclass(frozen=True)
class Verification:
    """What recomputing the manifest against the modules on disk observed.

    One value carries every case: source mode (no manifest), a clean match, a
    manifest that could not be read, and a first-difference path when the disk
    has drifted from what was shipped. The two fields every case has are the
    ones the disk answers on its own; the rest come from a manifest and default
    to the absence of one. `problem` reduces the two faults to the one shape
    both callers refuse on; `summary` is the line they record otherwise.
    """

    tree_digest: str
    module_count: int
    source_mode: bool = False
    revision: str | None = None
    dirty: bool | None = None
    built_at: str | None = None
    mismatch: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when this install is the code its manifest claims, or is source."""
        return self.mismatch is None and self.error is None

    def problem(self) -> tuple[str, str] | None:
        """`(source, detail)` when the install is not what it claims, else None.

        One shape for both callers -- `doctor` and `proxy serve` -- so a build
        that does not match is the same refusal wherever it is caught.
        """
        if self.error is not None:
            return f"build:{MANIFEST}", self.error
        if self.mismatch is not None:
            return (
                f"build:{self.mismatch}",
                f"installed module {self.mismatch} is not the one "
                f"{self._built_from()} shipped",
            )
        return None

    def summary(self) -> str:
        """The line a caller records when the install is trustworthy."""
        if self.source_mode:
            return (
                f"running from source: {self.module_count} modules, "
                f"tree {self.tree_digest[:12]}"
            )
        return (
            f"{self.module_count} modules match {self._built_from()}, "
            f"tree {self.tree_digest[:12]}"
        )

    def as_dict(self) -> dict:
        """The `build` block `rk doctor` reports: what was shipped and running."""
        return {
            "source": self.source_mode,
            "revision": self.revision,
            "dirty": self.dirty,
            "built_at": self.built_at,
            "digest": self.tree_digest,
            "modules": self.module_count,
        }

    def _built_from(self) -> str:
        if self.revision is None:
            return "the build"
        return self.revision[:12] + (" (dirty)" if self.dirty else "")


def record(ledger: Ledger, anchor: Traversable | None = None) -> Verification:
    """Verify this install and record the assertion on `ledger`.

    `rk doctor` and the door make the same statement about the same install and
    differ only in what they do next -- one reports it, one stops -- so the
    assertion's name, its outcome class and its sentence are written once here
    rather than at two call sites free to drift apart. The `Verification` comes
    back because each caller does go on differently.
    """
    verification = verify(anchor)
    problem = verification.problem()
    if problem is None:
        ledger.hold(ASSERTION, verification.summary())
    else:
        source, detail = problem
        ledger.fail(ASSERTION, detail, code=BUILD_MISMATCH, source=source)
    return verification


def verify(anchor: Traversable | None = None) -> Verification:
    """Recompute the shipped digests against the modules on disk.

    `anchor` is the package root to read; it defaults to the installed
    `redkraken` package and is a parameter so a test can point it at a fabricated
    tree without a git checkout. Returns a `Verification` in every case: source
    mode when there is no manifest, an unreadable-manifest error, a first-
    difference path when the disk has drifted, or a clean match.
    """
    root = anchor if anchor is not None else resources.files(__package__)
    on_disk = digests(root)
    tree = _root_digest(on_disk)

    try:
        manifest = _load(root)
    except ManifestError as error:
        return Verification(tree, len(on_disk), error=str(error))
    if manifest is None:
        return Verification(tree, len(on_disk), source_mode=True)
    return Verification(
        tree,
        len(on_disk),
        revision=manifest["revision"],
        dirty=manifest["dirty"],
        built_at=manifest["built_at"],
        mismatch=_first_difference(manifest["modules"], on_disk),
    )


def digests(root: Traversable) -> dict[str, str]:
    """SHA-256 of every module under `root`, keyed by its path within it.

    Written against `Traversable` rather than `pathlib` so one function serves
    the installed package (`resources.files`), the source tree the backend hands
    it a `Path` for, and a test's fabricated directory. `__pycache__` is skipped
    so a compiled artefact never counts as a module the wheel was meant to ship.

    Walking the package and walking what the wheel carries are the same walk
    because every `.py` and `.sql` under the package is shipped, which is what
    `test_packaging.test_every_file_the_package_carries_is_shipped_with_it`
    holds true. A file that stopped being shipped would make every install
    refuse, so that test is load-bearing here and not only there.
    """
    found: dict[str, str] = {}
    _walk(root, "", found)
    return found


def _load(root: Traversable) -> dict | None:
    """The parsed manifest, or None when the install carries none (source mode).

    Raises `ManifestError` when a manifest is present but malformed or from a
    schema this reader does not know: an install this code cannot verify is one
    it must refuse, not one it waves through. Every key `verify` goes on to read
    is checked here, because a `KeyError` out of the door's first statement is a
    crash where the whole point was a refusal.
    """
    resource = root.joinpath(MANIFEST)
    if not resource.is_file():
        return None
    try:
        manifest = json.loads(resource.read_bytes())
    except (ValueError, OSError) as error:
        raise ManifestError(f"{MANIFEST} is not readable JSON: {error}") from error
    if not isinstance(manifest, dict):
        raise ManifestError(f"{MANIFEST} is not an object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(
            f"{MANIFEST} declares schema {manifest.get('schema_version')!r}, "
            f"this build reads {SCHEMA_VERSION}"
        )
    absent = sorted({"revision", "dirty", "built_at"} - set(manifest))
    if absent:
        raise ManifestError(f"{MANIFEST} does not state {absent}")
    modules = manifest.get("modules")
    if not isinstance(modules, dict) or not all(
        isinstance(path, str) and isinstance(value, str) for path, value in modules.items()
    ):
        raise ManifestError(f"{MANIFEST} has no readable module table")
    return manifest


def _walk(node: Traversable, prefix: str, found: dict[str, str]) -> None:
    for child in node.iterdir():
        name = child.name
        if name == BYTECODE_DIR:
            continue
        path = f"{prefix}{name}"
        if child.is_dir():
            _walk(child, f"{path}/", found)
        elif name.endswith(HASHED_SUFFIXES):
            found[path] = digest(child.read_bytes())


def _root_digest(found: dict[str, str]) -> str:
    """One digest over the whole module tree, stable under path order."""
    return digest("".join(f"{path} {found[path]}\n" for path in sorted(found)).encode())


def _first_difference(expected: dict[str, str], actual: dict[str, str]) -> str | None:
    """The first path, in sorted order, whose digest differs or is missing.

    Covers a changed module, one the manifest names that the disk lacks, and one
    on disk the manifest never listed. Returns None when every module matches.
    """
    for path in sorted(set(expected) | set(actual)):
        if expected.get(path) != actual.get(path):
            return path
    return None
