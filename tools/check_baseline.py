#!/usr/bin/env python3
"""Validate the product boundary and the frozen, content-free v1 census."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import subprocess
import sys
import tokenize
import tomllib
from collections import Counter
from pathlib import Path


CHECKOUT = Path(__file__).resolve().parents[1]
BASELINE = CHECKOUT / "baseline"
MANIFEST = BASELINE / "v1-manifest.tsv"
STATUS = BASELINE / "status.json"
#: What `baseline/` may hold, closed. A baseline directory that tolerates
#: unknown files is one where a second manifest can sit beside the frozen one
#: and nobody can tell which was read. The two disposition files are here rather
#: than beside the code they resolve against for the same reason the census is:
#: they are read by a repository check, never by the application.
BASELINE_FILES = {
    "status.json",
    "v1-manifest.tsv",
    "v1-dispositions.tsv",
    "v1-dispositions.json",
}
FIELDS = ("kind", "source", "lines", "sha256")
EXPECTED_COUNTS = {
    "agent_definition": 11,
    "skill_directory": 28,
    "playbook_topic": 60,
    "operator_reference": 112,
    "sink_pack": 9,
    "reserved": 3,
}
CLASSIFICATIONS = {
    "production",
    "validated_prototype",
    "falsified_prototype",
    "documentation",
}
RESERVED_PLAYBOOKS = {"index.md", "log.md", "SCHEMA.md"}
PLAYBOOK_KINDS = {
    "Playbook": "playbook_topic",
    "Operator Reference": "operator_reference",
    "Sink Pack": "sink_pack",
}


class BaselineError(Exception):
    pass


def file_facts(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data.splitlines()), hashlib.sha256(data).hexdigest()


def directory_facts(path: Path, tracked: list[Path]) -> tuple[int, str]:
    digest = hashlib.sha256()
    lines = 0
    for source in tracked:
        relative = source.relative_to(path).as_posix()
        data = source.read_bytes()
        lines += len(data.splitlines())
        digest.update(relative.encode("utf-8") + b"\0" + data + b"\0")
    return lines, digest.hexdigest()


def tracked_files(v1: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(v1),
            "ls-files",
            "-z",
            "--",
            ".claude/agents",
            ".claude/skills",
            "playbooks",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise BaselineError(f"v1 corpus is not a readable git worktree: {v1}")
    relative_paths = [Path(raw.decode("utf-8")) for raw in result.stdout.split(b"\0") if raw]
    links = [path.as_posix() for path in relative_paths if (v1 / path).is_symlink()]
    if links:
        raise BaselineError("v1 source may not be a symlink: " + ", ".join(links[:5]))
    missing = [path.as_posix() for path in relative_paths if not (v1 / path).is_file()]
    if missing:
        raise BaselineError("v1 tracked source is missing: " + ", ".join(missing[:5]))
    return [v1 / path for path in relative_paths]


def frontmatter_type(path: Path) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0] != "---":
        return ""
    for line in lines[1:]:
        if line == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() == "type":
            return value.strip().strip("\"'")
    return ""


def collect_v1(v1: Path) -> list[dict[str, str]]:
    files = tracked_files(v1)
    relative = {path.relative_to(v1).as_posix(): path for path in files}
    rows: list[dict[str, str]] = []

    for name, path in sorted(relative.items()):
        if (
            name.startswith(".claude/agents/")
            and path.parent == v1 / ".claude/agents"
            and path.suffix == ".md"
        ):
            lines, digest = file_facts(path)
            rows.append({
                "kind": "agent_definition",
                "source": name,
                "lines": str(lines),
                "sha256": digest,
            })

    skill_roots = sorted({
        Path(name).parts[2]
        for name in relative
        if name.startswith(".claude/skills/")
    })
    for skill in skill_roots:
        root = v1 / ".claude/skills" / skill
        sources = sorted(
            path
            for name, path in relative.items()
            if name.startswith(f".claude/skills/{skill}/")
        )
        lines, digest = directory_facts(root, sources)
        rows.append({
            "kind": "skill_directory",
            "source": f".claude/skills/{skill}",
            "lines": str(lines),
            "sha256": digest,
        })

    for name, path in sorted(relative.items()):
        if not name.startswith("playbooks/") or path.suffix != ".md":
            continue
        playbook_path = Path(name).relative_to("playbooks").as_posix()
        if playbook_path in RESERVED_PLAYBOOKS:
            kind = "reserved"
        else:
            kind = PLAYBOOK_KINDS.get(frontmatter_type(path), "unknown")
        lines, digest = file_facts(path)
        rows.append({"kind": kind, "source": name, "lines": str(lines), "sha256": digest})

    return sorted(rows, key=lambda row: (row["kind"], row["source"]))


def read_table(path: Path, fields: tuple[str, ...], noun: str) -> list[dict[str, str]]:
    """One of `baseline/`'s tab-separated tables, keyed by `source`.

    Shared because that directory now holds two of them and they have to be read
    identically: a table read under a different quoting rule is a different
    table, and these are the files that must mean the same thing on every
    machine. The semantics of each stay with its own reader; what is here is the
    file format and the two properties both have, that every row has exactly the
    declared fields and that a source appears once.
    """
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if tuple(reader.fieldnames or ()) != fields:
                raise BaselineError(f"{noun} fields must be: {', '.join(fields)}")
            rows = list(reader)
    except FileNotFoundError as error:
        raise BaselineError(f"missing {noun} file: {path}") from error

    for row in rows:
        # `None` is the key `DictReader` files a long row's surplus under and the
        # value it pads a short one with, so a row that is not exactly the
        # declared width shows up as one or the other. A surplus column reads
        # clean otherwise, which is the quiet way a frozen table gains a field.
        if None in row or any(value is None or "\t" in value for value in row.values()):
            raise BaselineError(f"malformed {noun} row: {row.get('source')}")
    sources = [row["source"] for row in rows]
    duplicates = sorted(source for source, count in Counter(sources).items() if count > 1)
    if duplicates:
        raise BaselineError(f"duplicate {noun} source: " + ", ".join(duplicates))
    return rows


def read_manifest(path: Path = MANIFEST) -> list[dict[str, str]]:
    rows = read_table(path, FIELDS, "manifest")
    counts = Counter(row["kind"] for row in rows)
    if counts != Counter(EXPECTED_COUNTS):
        raise BaselineError(
            f"manifest counts differ: expected {EXPECTED_COUNTS}, found {dict(counts)}"
        )
    for row in rows:
        source = Path(row["source"])
        if (
            not source.parts
            or source.is_absolute()
            or ".." in source.parts
            or source.parts[0] not in {".claude", "playbooks"}
        ):
            raise BaselineError(f"unsafe manifest source: {row['source']}")
        if not row["lines"].isdigit() or len(row["sha256"]) != 64:
            raise BaselineError(f"invalid manifest facts: {row['source']}")
        try:
            int(row["sha256"], 16)
        except ValueError as error:
            raise BaselineError(f"invalid manifest digest: {row['source']}") from error
    return rows


def read_status(path: Path = STATUS) -> dict:
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise BaselineError(f"invalid status registry: {error}") from error
    if status.get("schema") != 1:
        raise BaselineError("status registry schema must be 1")

    classifications = status.get("classifications", [])
    paths = [entry.get("path") for entry in classifications]
    if len(paths) != len(set(paths)):
        raise BaselineError("status registry contains duplicate paths")
    for entry in classifications:
        if entry.get("classification") not in CLASSIFICATIONS:
            raise BaselineError(f"invalid classification for {entry.get('path')}")
        if not (CHECKOUT / entry["path"]).exists():
            raise BaselineError(f"classified path does not exist: {entry['path']}")

    prototype_source = status.get("prototype_root")
    if not isinstance(prototype_source, str):
        raise BaselineError("status registry needs a prototype_root")
    prototype_path = Path(prototype_source)
    if prototype_path.is_absolute() or ".." in prototype_path.parts:
        raise BaselineError(f"unsafe prototype root: {prototype_source}")

    classified = set(paths)
    prototype_root = CHECKOUT / prototype_path
    prototypes = {
        path.relative_to(CHECKOUT).as_posix()
        for path in prototype_root.iterdir()
        if path.is_dir() and any(source.is_file() for source in path.rglob("*"))
    }
    missing = sorted(prototypes - classified)
    if missing:
        raise BaselineError("unclassified prototype: " + ", ".join(missing))
    by_path = {entry["path"]: entry for entry in classifications}
    for prototype in prototypes:
        if by_path[prototype]["classification"] not in {"validated_prototype", "falsified_prototype"}:
            raise BaselineError(f"prototype has non-prototype classification: {prototype}")

    production_roots = status.get("production_roots", [])
    for root in production_roots:
        path = Path(root)
        if not path.parts or path.is_absolute() or ".." in path.parts:
            raise BaselineError(f"unsafe production root: {root}")

    forbidden_roots = status.get("forbidden_dependency_roots", [])
    if (
        not isinstance(forbidden_roots, list)
        or len(forbidden_roots) != 4
        or len(forbidden_roots) != len(set(forbidden_roots))
        or not all(isinstance(root, str) and root for root in forbidden_roots)
    ):
        raise BaselineError("status registry needs four unique forbidden dependency roots")

    # Four *unique* roots is not four *meaningful* roots: the list could be four
    # names nothing is called, and the scan below would then find nothing to
    # complain about while still reporting that it ran. What the roots are for is
    # pinned against the one directory this same registry already names and this
    # same function already resolves against the filesystem -- every component of
    # the path to the prototypes has to be one of them, because a production file
    # may not reach the prototype tree and may not reach the tree it sits in
    # either.
    unguarded = [part for part in prototype_path.parts if part not in set(forbidden_roots)]
    if unguarded:
        raise BaselineError(
            f"the prototype tree is reachable from production: {prototype_source} "
            f"is not covered by the forbidden dependency roots ({', '.join(unguarded)})"
        )

    regressions = status.get("regressions", [])
    regression_ids = [entry.get("id") for entry in regressions]
    if len(regression_ids) != len(set(regression_ids)):
        raise BaselineError("status registry contains duplicate regression ids")
    if set(regression_ids) != {f"RK-REG-{number:03d}" for number in range(1, 8)}:
        raise BaselineError("status registry must contain RK-REG-001 through RK-REG-007")
    for entry in regressions:
        if not entry.get("description") or not entry.get("required_tickets"):
            raise BaselineError(f"incomplete regression: {entry.get('id')}")
    registered = set(regression_ids)
    for entry in classifications:
        unknown = set(entry.get("regressions", [])) - registered
        if unknown:
            raise BaselineError(f"unknown regression on {entry['path']}: {', '.join(sorted(unknown))}")
    return status


def shipped_source_roots(repo: Path) -> list[str]:
    """The directories the wheel takes its code from, per the packaging metadata.

    Read from `pyproject.toml` rather than from the registry, because the point
    is to have a second author. The registry says what is scanned; this says what
    is shipped, and it says it to a build backend that would notice if it were
    wrong. A boundary check whose entire notion of "production" comes from one
    editable file is a check that can be switched off by editing that file.
    """
    manifest = repo / "pyproject.toml"
    try:
        packaging = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise BaselineError(f"cannot read the packaging metadata: {error}") from error
    found = (
        packaging.get("tool", {}).get("setuptools", {}).get("packages", {}).get("find", {})
    )
    where = found.get("where", ["."])
    if not isinstance(where, list) or not all(isinstance(entry, str) and entry for entry in where):
        raise BaselineError("packaging metadata declares no source directory")
    return where


def unscanned_shipped_roots(repo: Path, scanned: list[str]) -> list[str]:
    """The shipped directories no scanned target covers.

    Covered means the target *is* the directory or contains it, which is the same
    reach the scan itself has -- it walks each target with `rglob`. Anything left
    is code that goes in the wheel and past this check without being read.
    """
    targets = {Path(target) for target in scanned}
    missing = []
    for root in shipped_source_roots(repo):
        path = Path(root)
        if not any(path == target or target in path.parents for target in targets):
            missing.append(root)
    return missing


def forbidden_reference(
    value: str,
    forbidden_roots: list[str],
    scan_bare_tokens: bool = False,
) -> bool:
    value = value.replace("\\", "/").strip()
    prefixes = (" ", "\"", "'", "=", "(", "[", ",")
    words = (
        value.translate(
            str.maketrans({character: " " for character in "\"'()[]{}=,:"})
        ).split()
        if scan_bare_tokens
        else []
    )
    for root in forbidden_roots:
        root = root.replace("\\", "/").rstrip("/")
        variants = (root, root + "/") if root.startswith("/") else (
            root,
            root + "/",
            root + ".",
            "./" + root + "/",
            "../" + root + "/",
        )
        if value == root or value.startswith(variants[1:]):
            return True
        if any(prefix + variant in value for prefix in prefixes for variant in variants[1:]):
            return True
        if not root.startswith("/") and (
            f"/{root}/" in value
            or value.endswith(f"/{root}")
            or f".{root}." in value
            or value.endswith(f".{root}")
        ):
            return True
        if root in words:
            return True
    return False


def forbidden_python_dependencies(
    path: Path,
    source: str,
    forbidden_roots: list[str],
) -> list[str]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        return [f"{path}: cannot inspect invalid Python: {error.msg}"]
    errors = []
    forbidden_modules = {root for root in forbidden_roots if root.isidentifier()}
    docstrings = {
        id(owner.body[0].value)
        for owner in ast.walk(tree)
        if isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and owner.body
        and isinstance(owner.body[0], ast.Expr)
        and isinstance(owner.body[0].value, ast.Constant)
        and isinstance(owner.body[0].value.value, str)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        for module in modules:
            if module.split(".", 1)[0] in forbidden_modules:
                errors.append(f"{path}: forbidden import {module}")
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            value = os.fsdecode(node.value)
            if (
                id(node) not in docstrings
                and forbidden_reference(value, forbidden_roots)
            ):
                errors.append(f"{path}: forbidden tree reference {value}")
    return errors


def production_boundary_errors(
    repo: Path,
    production_roots: list[str],
    production_paths: list[str],
    forbidden_roots: list[str],
) -> list[str]:
    errors: list[str] = []
    targets = dict.fromkeys([*production_roots, *production_paths])
    for relative_target in targets:
        root = repo / relative_target
        if not root.exists() and not root.is_symlink():
            continue
        paths = [root] if root.is_file() or root.is_symlink() else sorted(root.rglob("*"))
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            if path.is_symlink():
                relative = path.relative_to(repo)
                errors.append(f"{relative}: forbidden symlink target")
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(repo)
            data = path.read_bytes()
            first_line = data.splitlines()[0].lower() if data.splitlines() else b""
            is_python = path.suffix == ".py" or first_line.startswith(b"#!") and b"python" in first_line
            if is_python:
                try:
                    with tokenize.open(path) as handle:
                        source = handle.read()
                except (SyntaxError, UnicodeError) as error:
                    errors.append(f"{relative}: cannot decode Python source: {error}")
                    continue
                errors.extend(forbidden_python_dependencies(relative, source, forbidden_roots))
                continue
            try:
                source = data.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"{relative}: non-UTF-8 production file")
                continue
            for line_number, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", "//", "--")):
                    continue
                if forbidden_reference(stripped, forbidden_roots, scan_bare_tokens=True):
                    errors.append(f"{relative}:{line_number}: forbidden tree dependency")
    return errors


def implementation_claim_errors(repo: Path, classifications: list[dict]) -> list[str]:
    errors = []
    for entry in classifications:
        if entry["classification"] == "production":
            continue
        root = repo / entry["path"]
        sources = [root] if root.is_file() else root.rglob("*.md")
        for source in sources:
            lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
            for line_number, line in enumerate(lines, 1):
                status = line.strip().replace("**", "").lower()
                if status in {"status: implemented", "status: production", "status: shipping"}:
                    errors.append(
                        f"{source.relative_to(repo)}:{line_number}: "
                        "non-production work claims shipping status"
                    )
    return errors


def compare_manifest(expected: list[dict[str, str]], actual: list[dict[str, str]]) -> list[str]:
    expected_by_source = {row["source"]: row for row in expected}
    actual_by_source = {row["source"]: row for row in actual}
    errors = [
        f"missing v1 artifact: {source}"
        for source in sorted(expected_by_source.keys() - actual_by_source.keys())
    ]
    errors.extend(
        f"added v1 artifact: {source}"
        for source in sorted(actual_by_source.keys() - expected_by_source.keys())
    )
    for source in sorted(expected_by_source.keys() & actual_by_source.keys()):
        if expected_by_source[source] != actual_by_source[source]:
            errors.append(f"changed v1 artifact: {source}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=CHECKOUT, help="production tree to inspect")
    parser.add_argument("--v1", type=Path, help="recompute the v1 census in memory and compare it")
    arguments = parser.parse_args(argv)
    try:
        if not arguments.repo.is_dir():
            raise BaselineError(f"production tree does not exist: {arguments.repo}")
        if any(path.is_symlink() for path in BASELINE.iterdir()):
            raise BaselineError("baseline files may not be symlinks")
        if {path.name for path in BASELINE.iterdir()} != BASELINE_FILES:
            raise BaselineError(
                "baseline directory may hold only: " + ", ".join(sorted(BASELINE_FILES))
            )
        status = read_status()
        manifest = read_manifest()
        production_paths = [
            entry["path"]
            for entry in status["classifications"]
            if entry["classification"] == "production"
        ]
        # The checkout, not `--repo`. The question is whether this registry
        # describes the boundary honestly, and the registry and the packaging
        # metadata it is checked against are both this checkout's; `--repo` is a
        # tree handed in to be read with them.
        unscanned = unscanned_shipped_roots(
            CHECKOUT, [*status["production_roots"], *production_paths]
        )
        if unscanned:
            raise BaselineError(
                "packaged source is outside the scanned boundary: " + ", ".join(unscanned)
            )
        errors = implementation_claim_errors(CHECKOUT, status["classifications"])
        errors.extend(
            production_boundary_errors(
                arguments.repo.resolve(),
                status["production_roots"],
                production_paths,
                status["forbidden_dependency_roots"],
            )
        )
        if arguments.v1:
            try:
                drift = compare_manifest(manifest, collect_v1(arguments.v1.resolve()))
            except BaselineError as error:
                raise BaselineError(f"v1 census differs from frozen manifest\n{error}") from error
            if drift:
                errors.append("v1 census differs from frozen manifest")
                errors.extend(drift)
        if errors:
            raise BaselineError("\n".join(errors))
    except (BaselineError, OSError) as error:
        print(f"baseline failed: {error}", file=sys.stderr)
        return 1

    print(
        "baseline ok: "
        f"classifications={len(status['classifications'])} "
        f"regressions={len(status['regressions'])} "
        f"artifacts={len(manifest)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
