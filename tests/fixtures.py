"""The Program configuration the runtime tests are written against."""

import atexit
import shutil
import tempfile
from pathlib import Path


VALID = """\
schema_version = 1

[program]
name = "acme-web"
platform = "hackerone"

[rules_of_engagement]
mutation = true

[budgets]
requests = 5000
tokens = 2000000
concurrency = 2
window_seconds = 3600

[[scope.include]]
host = "app.example.com"
ports = [443]
protocols = ["https"]
paths = ["/api/"]

[[scope.exclude]]
host = "admin.example.com"
ports = [443]
protocols = ["https"]
paths = ["/"]

[[identity]]
name = "member"
slot_ref = "slot://identity/member"

[[required_header]]
name = "X-Bounty-Id"
value_ref = "slot://header/bounty-id"

[[callback]]
name = "oob-dns"
kind = "dns"
host = "oob.example.net"
"""


def scratch() -> Path:
    """A directory of this run's own, removed when the run ends."""
    return Path(tempfile.mkdtemp(dir=_ROOT))


def write(text: str, name: str = "program.toml") -> Path:
    """Put one configuration in a directory of its own, so writes are visible."""
    source = scratch() / name
    source.write_text(text, encoding="utf-8")
    return source


#: One root for everything the suite writes, so a run leaves nothing behind.
_ROOT = tempfile.mkdtemp(prefix="redkraken-tests-")
atexit.register(shutil.rmtree, _ROOT, ignore_errors=True)
