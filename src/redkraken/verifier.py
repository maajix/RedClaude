"""The check an evidence bundle carries with it.

This module imports nothing from this package, and nothing outside the standard
library. That is the whole of its design: `rk evidence export` writes a copy of
this file into every bundle as `verify.py`, and the person who receives one has
this repository, this database and this harness's key material nowhere. A
verifier that needed any of them would be a verifier only the party being
checked could run.

    python3 verify.py path/to/bundle

The five questions it answers are the five a recipient cannot answer by reading:

  * is every file the manifest names here, and is it the bytes the manifest says
  * is every file that is here named by the manifest
  * does the manifest still say what it said when it was written
  * do the bundle's two indexes agree about the artifacts they both describe
  * did the redaction actually run, or does the material it was written to
    remove survive somewhere in the bundle

Nothing here decides whether the *claim* in the report is true. That is what a
triager is for. This decides whether the evidence in front of them is the
evidence this harness produced.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path


#: What a bundle written by this version declares itself to be. A verifier that
#: guessed the layout of a schema it did not know would answer confidently about
#: a document it had misread, so an unknown schema stops the check rather than
#: being interpreted.
SCHEMA = "rk2-evidence/1"

#: The index, which is not one of the files it indexes: a document cannot carry
#: its own hash.
MANIFEST = "manifest.json"

#: The verifier itself. Named here because it is the one packaged file the
#: secret scan does not read -- see `_scanned`.
VERIFIER = "verify.py"

#: The key holding what is true of this export rather than of the rows it was
#: made from. Excluded from the manifest digest, which is what makes criterion
#: 5's "deterministic apart from explicitly excluded packaging metadata" a thing
#: a recipient can check rather than a promise.
PACKAGING = "packaging"

#: What a redaction leaves in place of what it removed: which rule took it and
#: how much it took. Both are facts about the redaction rather than about the
#: person, which is the line this marker exists on.
#:
#: The digest of the removed range is deliberately not here. It would let a
#: triager holding the full artifact prove an excerpt was not doctored, and it
#: would also let anybody holding the bundle recover the value: a telephone
#: number, a national identifier or a card number is a preimage space small
#: enough to walk through offline in seconds, so publishing SHA-256 of one is
#: publishing it. The range is still answerable -- the manifest names the
#: unredacted artifact's digest and each mark carries its offset and length --
#: which needs the full artifact, and that is the point.
#:
#: Written here, beside the pattern that reads it, because the exporter and this
#: are the only two things that will ever care and they must not disagree: a
#: marker this cannot recognise is a marker the scan below reads as residue.
MARKER_FORM = "[redacted rule={rule} bytes={bytes}]"
MARKER = re.compile(r"\[redacted rule=[a-z_]+ bytes=[0-9]+\]")

#: The index of what was packaged, cross-checked against the manifest below.
#: Named here because it is the one packed document that repeats something the
#: manifest also says, and two indexes that can disagree are two indexes one of
#: which is wrong.
ARTIFACTS = "artifacts.json"

#: The rendered document, and the one file in a bundle that a row outside the
#: bundle can also name. When the manifest says which rendering it is, this is
#: the file that claim is about.
REPORT = "report.md"


def digest(data: bytes) -> str:
    """The identifier of some bytes, in the one form the whole tree uses."""
    return hashlib.sha256(data).hexdigest()


def canonical(document: Mapping) -> bytes:
    """The manifest as one sequence of bytes, independent of how it was written.

    Sorted keys and no incidental whitespace. The file on disk is indented so a
    person can read it; the digest is over this, so re-indenting the manifest
    does not change what it is a digest of.
    """
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_digest(document: Mapping) -> str:
    """What identifies a bundle: everything the manifest says except two keys.

    Its own digest cannot be inside itself, and the packaging object is the wall
    clock. Every other key is a fact about the rows the bundle was made from,
    which is what criterion 5 says two exports of unchanged rows must agree on.
    """
    return digest(canonical({k: v for k, v in document.items() if k not in ("digest", PACKAGING)}))


def verify(root: Path) -> dict:
    """Hold one unpacked bundle against its own manifest.

    Every problem found is reported rather than the first: a recipient running
    this once wants the list, and a bundle with two broken hashes is a different
    thing from a bundle with one.
    """
    root = Path(root)
    problems: list[dict] = []
    try:
        document = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _answer(root, 0, [_problem("manifest_missing", MANIFEST, f"no {MANIFEST} in {root}")])
    except (OSError, ValueError) as error:
        return _answer(root, 0, [_problem("manifest_unreadable", MANIFEST, str(error))])

    if document.get("schema") != SCHEMA:
        return _answer(
            root,
            0,
            [
                _problem(
                    "schema_unknown",
                    MANIFEST,
                    f"written under {document.get('schema')!r}, and this verifier "
                    f"knows {SCHEMA!r}",
                )
            ],
        )

    if document.get("digest") != manifest_digest(document):
        problems.append(
            _problem("manifest_digest_mismatch", MANIFEST, "the manifest is not what it says it is")
        )

    listed = {str(item["path"]): item for item in document.get("files", ())}
    problems.extend(_missing_from_manifest(root, listed))
    for path in sorted(listed):
        problems.extend(_file(root, path, listed[path]))
    for path in document.get("required", ()):
        if path not in listed:
            problems.append(
                _problem("required_file_unlisted", path, "the manifest owes this file and omits it")
            )
    problems.extend(_artifacts(root, listed))
    problems.extend(_rendering(root, listed, document.get("rendering")))
    problems.extend(_residue(root, listed, document.get("redaction_rules", ())))
    return _answer(root, len(listed), problems)


def _file(root: Path, path: str, entry: Mapping) -> list[dict]:
    """One named file: that it is here, that it is the size and the bytes named."""
    try:
        data = (root / path).read_bytes()
    except FileNotFoundError:
        return [_problem("file_missing", path, "the manifest names it and it is not here")]
    except OSError as error:
        return [_problem("file_unreadable", path, str(error))]
    found = digest(data)
    problems = []
    if len(data) != entry.get("bytes"):
        problems.append(
            _problem("file_size_mismatch", path, f"{entry.get('bytes')} recorded, {len(data)} here")
        )
    if found != entry.get("sha256"):
        problems.append(
            _problem("file_hash_mismatch", path, f"{entry.get('sha256')} recorded, {found} here")
        )
    return problems


def _missing_from_manifest(root: Path, listed: Mapping[str, Mapping]) -> list[dict]:
    """Files that are here and that the manifest does not account for.

    The direction that matters most and is easiest to leave out. A bundle whose
    hashes all check out and that carries one extra file is a bundle somebody
    added something to, and every per-file check in this module would pass.
    """
    return [
        _problem("file_unlisted", name, "present in the bundle and named by no manifest entry")
        for name in sorted(
            item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()
        )
        if name != MANIFEST and name not in listed
    ]


def _artifacts(root: Path, listed: Mapping[str, Mapping]) -> list[dict]:
    """Whether the artifact index and the manifest describe the same bytes.

    `artifacts.json` names each packaged file and the digest of what is in it,
    and the manifest names every file and its digest. The same export writes
    both, which is exactly why a recipient should not be made to assume they
    agree: a bundle where they disagree is one where an artifact moved after one
    of the two was written, and every other check in this module passes.
    """
    try:
        entries = json.loads((root / ARTIFACTS).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []  # `_file` already reports it against the manifest entry
    except (OSError, ValueError) as error:
        return [_problem("artifact_index_unreadable", ARTIFACTS, str(error))]

    problems: list[dict] = []
    for entry in entries if isinstance(entries, list) else ():
        path = str(entry.get("path"))
        if path not in listed:
            problems.append(
                _problem("artifact_unlisted", path, f"{ARTIFACTS} names it and the manifest does not")
            )
        elif (entry.get("sha256"), entry.get("bytes")) != (
            listed[path].get("sha256"),
            listed[path].get("bytes"),
        ):
            problems.append(
                _problem(
                    "artifact_hash_disagrees",
                    path,
                    f"{ARTIFACTS} records {entry.get('bytes')} byte(s) under "
                    f"{str(entry.get('sha256'))[:12]} and the manifest records "
                    f"{listed[path].get('bytes')} under {str(listed[path].get('sha256'))[:12]}",
                )
            )
    return problems


def _rendering(root: Path, listed: Mapping[str, Mapping], named: object) -> list[dict]:
    """Whether the report shipped is the rendering the manifest says it is.

    The one claim in a bundle about something outside it. `report.md` can be a
    document a human read and approved, and an approval names exact bytes; when
    the exporter says which rendering those were, a recipient can hold the file
    against that hash without this harness in the middle -- which is the only
    way the claim is worth anything, since every other hash here was written by
    the same export that wrote the file.

    A bundle with no `rendering` key makes no such claim and is not failed for
    it: a chain has no rendering row, and a Finding nobody has read has none
    either.
    """
    if not isinstance(named, Mapping):
        return []
    stated = str(named.get("content_sha256"))
    entry = listed.get(REPORT)
    if entry is None:
        return [_problem("rendering_unlisted", REPORT, "the manifest names a rendering and no report")]
    if entry.get("sha256") != stated:
        return [
            _problem(
                "rendering_mismatch",
                REPORT,
                f"the manifest names rendering {str(named.get('id'))} at {stated[:12]} "
                f"and ships {str(entry.get('sha256'))[:12]}",
            )
        ]
    return []


def _scanned(path: str) -> bool:
    """Whether the secret scan reads this file.

    One packaged file is furniture rather than evidence and would fail the scan
    for a reason that says nothing about a target: this verifier is code, and
    the patterns it matches with are written in it. Everything else a bundle
    carries is read. The manifest is not decided here at all -- it is the index
    and is in no manifest entry, so the caller never offers it.
    """
    return path != VERIFIER


def _residue(root: Path, listed: Mapping[str, Mapping], rules: object) -> list[dict]:
    """Whether anything the redaction was written to remove survived it.

    The markers are removed before the scan. What replaces a redacted range
    carries the length of what it took, a long body is a long run of digits, and
    a run of digits is a telephone number as far as `phone` is concerned -- so
    scanning the markers would report the redaction as the thing that needs
    redacting.

    A rule this Python cannot compile is itself a finding. The pattern is stored
    as a POSIX regular expression and the exporter applies it with `re`; if the
    two disagree here, the bundle was redacted by something other than what the
    manifest says redacted it.
    """
    problems: list[dict] = []
    for rule in rules if isinstance(rules, list) else ():
        try:
            pattern = re.compile(str(rule["pattern"]))
        except (KeyError, re.error) as error:
            problems.append(_problem("rule_unusable", str(rule.get("id")), str(error)))
            continue
        for path in sorted(name for name in listed if _scanned(name)):
            try:
                text = (root / path).read_bytes().decode("latin-1")
            except OSError:
                continue  # already reported by `_file`
            found = pattern.search(MARKER.sub("", text))
            if found is not None:
                problems.append(
                    _problem(
                        "redaction_incomplete",
                        path,
                        f"{rule.get('label', rule['id'])} survives at offset {found.start()}",
                    )
                )
    return problems


def _problem(code: str, path: str, detail: str) -> dict:
    return {"code": code, "path": path, "detail": detail}


def _answer(root: Path, checked: int, problems: list[dict]) -> dict:
    return {
        "schema": SCHEMA,
        "root": str(root),
        "files": checked,
        "ok": not problems,
        "problems": problems,
    }


def main(argv: list[str]) -> int:
    """The command a recipient runs. One argument, one JSON document, one status."""
    if len(argv) != 1:
        sys.stderr.write("usage: verify.py <bundle-directory>\n")
        return 2
    answer = verify(Path(argv[0]))
    sys.stdout.write(json.dumps(answer, indent=2, sort_keys=True) + "\n")
    return 0 if answer["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
