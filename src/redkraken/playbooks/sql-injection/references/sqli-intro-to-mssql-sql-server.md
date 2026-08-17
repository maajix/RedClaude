# MSSQL: the dialect facts, minus the escalation path

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Microsoft SQL Server for someone who found an injection in one. Its dialect --
`+` for string concatenation, `--` and `/* */` comments, `@@VERSION`,
`WAITFOR DELAY '0:0:5'` instead of a sleep function, `TOP n` instead of `LIMIT`.
Its catalogue views, `sys.tables` and `sys.columns`. And then the part the page
was really written for: `xp_cmdshell`, linked servers, `OPENROWSET`, impersonation
with `EXECUTE AS`, and the route from a web injection to a Windows domain.

## The half the Playbook uses

**The dialect, for one purpose: building a control that parses.**

A neutralised control has to be syntactically valid on the engine under test or
it is not a control, it is a syntax error dressed as one. Three MSSQL facts carry
that weight:

* Concatenation is `+`, not `||`. A control built with `||` errors on MSSQL and
  the resulting "differential" is entirely the reading's own doing.
* There is no `SLEEP()` and no `pg_sleep()`. The timing control pair is
  `WAITFOR DELAY '0:0:2'` against `WAITFOR DELAY '0:0:0'`.
* `LIMIT` does not exist. A pagination-position probe written for MySQL says
  nothing here.

**The fingerprint step stays minimal.** Enough to pick the control, and no more.
In practice that means one probe over concatenation behaviour, or an error string
if the route happens to leak one. It does not mean `@@VERSION`, which the page
opened with and which is a read of the target's configuration that the reading
does not need.

**One structural observation worth carrying:** MSSQL error messages are unusually
descriptive, frequently quoting the offending fragment and naming the expected
token. That makes `error_detail` a more productive channel here than on other
engines, and it makes the corresponding false positive more likely too, because a
verbose error is easy to mistake for evidence that the statement changed. The
Playbook's error step still requires the neutralised control before it promotes
anything.

## The half that stays out, and why

**`xp_cmdshell` and everything after it.** Command execution on the database
host, and this Playbook is `read_only`. It also crosses out of the web
application and into the target's internal network, which is a different scope,
usually a different Program, and never a thing to do because a step was available.

**Linked servers and `OPENROWSET`.** Both reach machines that are not the
subject. A Program's scope names hosts; a linked-server hop leaves it silently.

**`EXECUTE AS` and impersonation.** Privilege work inside the database, for the
same reason authentication bypass is out on the front end: it acquires an
authority nobody granted.

**NetNTLM coercion.** It has its own note and its own refusal.

## The trap in the whole technique

MSSQL is where an injection stops being a web finding fastest. The engine ships
with genuine operating-system reach, it is usually deployed inside a Windows
domain, and the service account is more privileged than anyone intended.

Which means the temptation to take one more step is strongest exactly where the
consequences of taking it are worst. The step after `WAITFOR DELAY` proves the
injection is not another confirmation of the injection -- it is an action on a
domain-joined host, and it is the kind of action that ends an engagement and
starts an incident response.

The verdict was complete at the differential. Impact belongs in the report's
narrative, argued from what the finding permits, not demonstrated by doing it.
