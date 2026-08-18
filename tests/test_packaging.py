import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
import unittest
import zipfile
from pathlib import Path

import redkraken
from redkraken import build, doctor, migrate
from tests import ROOT
from tests.fixtures import VALID, scratch, write


def environment() -> dict[str, str]:
    """A clean environment, so an installed command cannot reach the checkout."""
    keep = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
    return {name: os.environ[name] for name in keep if name in os.environ}


class PackagingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_one_application_exposes_the_operator_command(self):
        self.assertEqual("redkraken", self.pyproject["project"]["name"])
        self.assertEqual({"rk": "redkraken.cli:main"}, self.pyproject["project"]["scripts"])
        self.assertEqual(["src"], self.pyproject["tool"]["setuptools"]["packages"]["find"]["where"])

    def test_only_the_application_is_shipped(self):
        self.assertEqual(
            ["redkraken*"], self.pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
        )

    def test_auth_resolution_manifest_is_shipped_with_the_application(self):
        self.assertIn(
            "measurements/*.json",
            self.pyproject["tool"]["setuptools"]["package-data"]["redkraken"],
        )

    def test_every_file_the_package_carries_is_shipped_with_it(self):
        # `packages.find` ships the modules; anything that is not a module is
        # shipped only if a package-data glob names it. So a corpus added under
        # `src/redkraken/` without a glob installs as an empty directory, and
        # the failure is at the first `compile_corpus()` on an installed `rk`
        # rather than in the checkout, where the files are always there. This
        # asks the question the other way round: every file, is it covered.
        #
        # A `.py` file is a module only where its directory is a package. The
        # fixture corpus is the case that makes the distinction load-bearing:
        # `fixtures/*/app.py` is Python that `find` will not ship, because the
        # directory holding it has no `__init__.py` and a name no import
        # statement could spell. Excluding every `.py` suffix would let it
        # install as nothing at all, silently, which is the failure this test
        # exists to catch.
        patterns = self.pyproject["tool"]["setuptools"]["package-data"]["redkraken"]
        package = ROOT / "src" / "redkraken"
        unshipped = sorted(
            str(path.relative_to(package))
            for path in package.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not (path.suffix == ".py" and (path.parent / "__init__.py").exists())
            and not any(path.relative_to(package).match(one) for one in patterns)
        )
        self.assertEqual([], unshipped)

    def test_the_version_has_one_source(self):
        self.assertEqual(
            {"attr": "redkraken.__version__"},
            self.pyproject["tool"]["setuptools"]["dynamic"]["version"],
        )
        self.assertEqual(["version"], self.pyproject["project"]["dynamic"])

    def test_the_supported_interpreter_range_is_declared_once(self):
        self.assertEqual(doctor.supported_python(), self.pyproject["project"]["requires-python"])

    def test_production_dependencies_are_declared_as_exact_pins(self):
        self.assertEqual(
            [f"{name}=={version}" for name, version in doctor.REQUIREMENTS.distributions],
            self.pyproject["project"]["dependencies"],
        )

    def test_the_build_is_reproducible_from_pinned_requirements(self):
        requirements = self.pyproject["build-system"]["requires"]

        self.assertTrue(requirements)
        for requirement in requirements:
            self.assertIn("==", requirement, f"{requirement} is not an exact pin")

    def test_the_build_goes_through_the_in_tree_wrapper(self):
        # The wrapper purges a stale `build/lib` and writes the manifest; a build
        # that reached setuptools directly would do neither.
        system = self.pyproject["build-system"]
        self.assertEqual("build_backend", system["build-backend"])
        self.assertEqual(["."], system["backend-path"])

    def test_the_build_manifest_is_shipped_with_the_application(self):
        self.assertIn(
            build.MANIFEST,
            self.pyproject["tool"]["setuptools"]["package-data"]["redkraken"],
        )

    def test_the_checkout_itself_carries_no_build_manifest(self):
        # `build_wheel` writes the manifest into the package because that is the
        # only place `package-data` can ship it from, and removes it on the way
        # out. A build killed outright leaves one behind, and since it is
        # gitignored nothing about the checkout would say so: the tree would
        # quietly stop being in source mode, and `rk proxy serve` from it would
        # refuse to listen the moment anybody edited a module. Asserting it here
        # is what turns that into a failure somebody sees.
        self.assertFalse((ROOT / "src" / "redkraken" / build.MANIFEST).exists())


class InstallationTest(unittest.TestCase):
    """The documented installation path, run against a pristine copy.

    Everything else drives the command line from the source tree, which proves
    the code but not the packaging. This installs the application the way the
    README tells an operator to and then runs the shipped `rk` script.
    """

    def builder(self, checkout: Path) -> Path:
        """A fresh interpreter to build `checkout` with.

        A venv over the running one, with `--system-site-packages` because that
        is what makes an offline build possible: the build environment sees
        whatever setuptools this machine already carries rather than fetching
        the pinned one.

        Deliberately not the interpreter running the suite. setuptools installs
        a `.pth` that loads `_distutils_hack` into every process started from
        the environment holding it, and `test_cli`'s containment assertion holds
        that `rk` loads nothing from this tree outside `src/` -- so an
        environment that can build is one the shipped command must not be run
        from.
        """
        if importlib.util.find_spec("ensurepip") is None:
            self.skipTest("building the application needs ensurepip")
        venv = checkout / ".venv"
        created = subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
            env=self.installer(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, created.returncode, created.stderr)
        return venv / "bin" / "python"

    def installer(self) -> dict[str, str]:
        """A home of its own, so an operator's pip configuration cannot decide
        what these tests install or where they look for it."""
        return environment() | {"HOME": str(scratch()), "PIP_CONFIG_FILE": os.devnull}

    def version(self, python: Path, distribution: str) -> str | None:
        """The version of `distribution` that `python` can import, or None."""
        found = subprocess.run(
            [
                str(python),
                "-c",
                "import importlib.metadata as m;"
                f" print(m.version({distribution!r}))",
            ],
            env=environment(),
            text=True,
            capture_output=True,
            check=False,
        )
        return found.stdout.strip() if found.returncode == 0 else None

    def buildable(self, python: Path) -> None:
        """Skip unless `python` can build offline against the pinned backend.

        Without network access the build uses whatever setuptools the machine
        already has, so a machine carrying a different one cannot satisfy the
        pin. That is a fact about the machine, not about the packaging under
        test. Asked of the interpreter that will do the building rather than of
        the one running the suite, because `builder` makes sure they are not the
        same one.
        """
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        for requirement in pyproject["build-system"]["requires"]:
            name, _, pinned = requirement.partition("==")
            if self.version(python, name) != pinned:
                self.skipTest(f"the offline installation path needs {requirement}")

    def copied(self) -> Path:
        """A pristine copy of this checkout: what an operator would build from."""
        checkout = scratch() / "checkout"
        checkout.mkdir()
        # `build_backend.py` is the PEP 517 backend `pyproject.toml` names; the
        # build cannot start without it on the checkout's import path.
        for name in ("pyproject.toml", "README.md", "build_backend.py"):
            shutil.copy(ROOT / name, checkout / name)
        shutil.copytree(
            ROOT / "src", checkout / "src", ignore=shutil.ignore_patterns("__pycache__")
        )
        return checkout

    def test_a_stale_staging_directory_does_not_decide_what_ships(self):
        """Criterion 1: installing the working tree ships the working tree.

        `build_py` stages every module under `build/`, and copies a source file
        over its staged copy only when the source is *newer* -- compared with
        `>` on a whole-second mtime. A checkout that lands a file on the same
        second as a stale staged copy therefore ships the stale one, and
        `build/` is gitignored, so nothing about the checkout says so. Staged
        here with a newer mtime, which is the same defect made deterministic.
        """
        checkout = self.copied()
        python = self.builder(checkout)
        if self.version(python, "setuptools") is None:
            self.skipTest("driving the build backend needs setuptools")
        source = checkout / "src" / "redkraken" / "outcome.py"
        staged = checkout / "build" / "lib" / "redkraken" / "outcome.py"
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b"raise SystemExit('a build nobody asked for')\n")

        wheel = scratch() / "wheel"
        wheel.mkdir()
        built = subprocess.run(
            [
                str(python),
                "-c",
                "import sys; sys.path.insert(0, '.'); import build_backend;"
                f" print(build_backend.build_wheel({str(wheel)!r}))",
            ],
            cwd=str(checkout),
            env=environment(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, built.returncode, built.stderr)

        with zipfile.ZipFile(wheel / built.stdout.strip().splitlines()[-1]) as archive:
            shipped = archive.read("redkraken/outcome.py")
            manifest = json.loads(archive.read(f"redkraken/{build.MANIFEST}"))
            carried = {
                name[len("redkraken/") :]
                for name in archive.namelist()
                if name.startswith("redkraken/") and name.endswith(build.HASHED_SUFFIXES)
            }
        self.assertEqual(source.read_bytes(), shipped)

        # The manifest is written by walking the source package, so what makes
        # it a statement about the wheel rather than about the tree is that the
        # two sets are the same set. A module that stopped being shipped would
        # otherwise make every install refuse, with the first symptom a door
        # that will not listen.
        self.assertEqual(carried, set(manifest["modules"]))

    def test_the_installed_command_reports_its_version_and_diagnoses(self):
        checkout = self.copied()
        python = self.builder(checkout)
        self.buildable(python)
        venv = python.parent.parent
        installer = self.installer()

        installed = subprocess.run(
            [
                str(venv / "bin" / "pip"),
                "install",
                "--no-build-isolation",
                "--check-build-dependencies",
                "--no-index",
                "--no-cache-dir",
                ".",
            ],
            cwd=str(checkout),
            env=installer,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)

        replayed = subprocess.run(
            [
                str(venv / "bin" / "python"),
                "-I",
                "-c",
                "from redkraken import _startup; print(len(_startup.replay_auth_resolution()))",
            ],
            cwd=scratch(),
            env=environment(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual("17\n", replayed.stdout, replayed.stderr)

        rk = str(venv / "bin" / "rk")
        version = subprocess.run(
            [rk, "--version"], env=environment(), text=True, capture_output=True, check=False
        )
        self.assertEqual(f"rk {redkraken.__version__}\n", version.stdout)

        # Ticket 59 criterion 6, and the one command that can only be asked
        # here. `rk version` reads the migration corpus off the installed
        # package, so a wheel that shipped the Python and not the `.sql` files
        # answers this with a refusal -- and the checkout the rest of the suite
        # runs from has the files either way. The digest is compared against
        # this tree's own corpus because that is the claim being made: the
        # installation an operator got is the migrations this checkout has.
        corpus = subprocess.run(
            [rk, "version"], env=environment(), text=True, capture_output=True, check=False
        )
        self.assertEqual(0, corpus.returncode, corpus.stderr)
        installed = json.loads(corpus.stdout)
        migrations, refused = migrate.load()
        self.assertEqual((), refused)
        self.assertTrue(installed["ok"], installed["violations"])
        self.assertEqual(redkraken.__version__, installed["version"])
        self.assertEqual(len(migrations), installed["corpus"])
        self.assertEqual(migrate.revision(migrations), installed["corpus_sha256"])
        self.assertEqual(migrations[-1].identity, installed["schema"])

        report = subprocess.run(
            [rk, "doctor", "--config", str(write(VALID))],
            env=environment(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, report.returncode, report.stderr)
        diagnosed = json.loads(report.stdout)
        self.assertTrue(diagnosed["ok"])
        # The wheel carries a build manifest, so the installed command is not in
        # source mode, and `doctor` verified the modules on disk against what the
        # wheel shipped -- the ticket's guarantee, exercised end to end.
        self.assertFalse(diagnosed["build"]["source"])
        self.assertGreater(diagnosed["build"]["modules"], 0)
        self.assertEqual(64, len(diagnosed["build"]["digest"]))


if __name__ == "__main__":
    unittest.main()
