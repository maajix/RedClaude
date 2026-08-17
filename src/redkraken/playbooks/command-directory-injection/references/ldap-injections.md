# LDAP injection: attached here, graded elsewhere

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The "directory" half of v1's command-and-directory pack. A route builds an LDAP
filter out of a caller's value:

```
(&(uid=$user)(userPassword=$password))
```

and the page showed what happens when `$user` is `*` or `admin)(&))` or
`*)(uid=*`: the filter's own parentheses close early, the appended clause is
ignored, and a bind that should have compared a password becomes a bind that
matches anybody. It listed the metacharacters -- `( ) * \ NUL /` -- the two
places a value lands (the filter and the distinguished name), and the blind
variant where the response is a yes or a no and an attribute is read out one
character at a time with `(uid=a*)`, `(uid=b*)`.

## Where it is graded in v2, and why not here

`injection.query_language` -- "input reaches a database query (SQL, NoSQL, LDAP,
XPath)" -- names LDAP explicitly. The Playbook that claims that class is
`sql-injection`, and an LDAP filter injection found on a live Program is
recorded there.

This file is attached to `command-directory-injection` because that is the
Playbook that replaces the v1 pack this page shipped in, and the disposition
ledger records a reference where its source lived. Attaching it to the Playbook
that grades it would be tidier and would make the ledger lie about where the v1
material was.

## The half either Playbook uses

The shape of the reading, which is the same shape `sql-injection` runs and worth
stating in the vocabulary of a directory:

* The neutralised control is the value with its metacharacters present but inert
  -- an escaped `\2a` where a bare `*` was sent -- rather than a different value.
  A control that changes the value as well as its encoding is comparing two
  searches.
* A wildcard that widens a result set is a boolean differential and it is read as
  one: same request, one character different, different set returned.
* An LDAP server's error text is distinctive and short, and it is an
  `error_detail` observation. It is not on its own a finding, for the reason
  every error is not: a route that returns a parser error has told you a parser
  saw the value, not that the value changed the query.

## The half that stays out, and why

**Everything that reads out the directory.** The blind extraction loop -- one
request per character per attribute -- is thousands of requests against an
authentication path, and what it produces is other people's account data held by
this harness. The reading stops at the differential that shows the filter is
built by concatenation.

**Bind bypass as a demonstration.** Logging in as somebody else proves the
finding and also authenticates as a person who did not consent. Where the
Program's rules of engagement admit it, it is an `authentication` reading with
its own Playbook and its own grant, not a step in an injection reading.

## The trap in the whole technique

A `*` that widens a search is not always injection. Plenty of directory-backed
search boxes pass a wildcard through on purpose, and a route that returns more
results for `*` may simply be a search route that supports wildcards -- which is
a feature its documentation names.

What separates them is the second character. A value that breaks the filter's
parentheses, or that changes the result of a clause the caller was never given,
is injection. A value the search grammar documents is a search.
