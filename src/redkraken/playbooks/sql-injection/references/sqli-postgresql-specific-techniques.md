# PostgreSQL: the dialect facts, minus the escalation path

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The PostgreSQL companion to the MSSQL page. Dialect first -- `||` for
concatenation, `pg_sleep()`, `version()`, `LIMIT`/`OFFSET`, dollar quoting
(`$$text$$`) as a way to write a string with no quote characters in it,
`::text` casts, and the strict typing that makes PostgreSQL error where MySQL
would silently coerce. Then `pg_catalog` and `information_schema`. Then the
escalation half: `COPY ... FROM PROGRAM` for command execution, large-object
functions for file reads and writes, and `dblink` for outbound connections.

## The half the Playbook uses

**The dialect, to build a control that parses**, exactly as with MSSQL:

* Concatenation is `||`. A control written with `+` produces a type error on
  PostgreSQL, and the reading then measures its own mistake.
* The timing pair is `pg_sleep(2)` against `pg_sleep(0)`.
* Strict typing is a feature of the reading, not an obstacle. PostgreSQL will
  refuse `'1' = 1` where MySQL accepts it, so a boolean arm has to be written in
  compatible types -- which is why the Playbook's fingerprint step runs before the
  boolean step rather than after.

**Dollar quoting, for one narrow use.** Where a filter strips or escapes quote
characters, `$$` delimits a string without one. Used once, as the
custom-tampering note's diagnostic probe, it separates "the filter ate the quote"
from "there is nothing to inject". Not used to land anything.

**One structural observation:** PostgreSQL's numeric strictness makes the
numeric-context probe unusually clean here. `id=7` against `id=8-1` either
returns the same row -- arithmetic was performed by the engine -- or errors,
because the value was bound as text. Both answers are informative and neither
needs a quote.

## The half that stays out, and why

**`COPY ... FROM PROGRAM`.** Command execution on the database host. Out for the
same reason `xp_cmdshell` is out, with the additional note that it requires a
superuser role and that the readings which find it usually find it on a managed
instance where the role was granted by default years ago. The finding is the
injection; the role is a sentence in the report.

**Large-object file read and write.** `lo_import`, `lo_export`, and the
`pg_read_file` family. Reading is out because it puts the target's files in this
harness's evidence store; writing is out because the Playbook is `read_only`.

**`dblink` and outbound connections.** They leave the Program's scope from inside
the database, where no proxy is applying the rate limit and no scope check is
watching.

**The catalogue walk.** `pg_catalog` enumeration is extraction with a
PostgreSQL-shaped name.

## The trap in the whole technique

PostgreSQL's helpfulness is the trap. Its errors are precise -- they name the
expected type, quote the position of the failure, and frequently include a
`HINT:` line suggesting the fix. That is wonderful when you are writing SQL and
misleading when you are reading a response, because a verbose, quoted, positioned
error looks exactly like proof that your value was parsed as SQL.

It often is. It is also what you get when a route casts a query parameter to an
integer and the cast fails, which is a route behaving correctly and telling you
so in detail.

The separator is the same as everywhere else in this pack: the neutralised
control. If the control -- same value, same length, metacharacters inert --
produces the same error, the error is about the type and not about an injection.
The Playbook requires that pairing before an `error_detail` observation supports
anything.
