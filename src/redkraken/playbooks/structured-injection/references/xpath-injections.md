# XPath injection: the query half of the document parser

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The XML analogue of SQL injection. An application keeps data in an XML document
and selects from it with an XPath expression built by concatenation:

```
//user[username/text()='$user' and password/text()='$pass']
```

The page showed the same arc the SQL pages show: `' or '1'='1` to make the
predicate always true, the metacharacters that matter (`'`, `"`, `[`, `]`, `/`,
`|`, `(`, `)`), the boolean-blind extraction with `substring()` and
`string-length()`, and the XPath 2.0 extras -- `doc()` to read another document,
which turns the injection into a file read or an outbound request.

## The half the Playbook uses

**The boolean predicate pair, and the observation that XPath has no comment
syntax.**

The second point is the one that separates a real XPath reading from a SQL
reading with different payloads. There is no `--` in XPath 1.0. You cannot
truncate the rest of the expression, so a payload has to leave the remaining
predicate syntactically valid and logically satisfied. That is why the canonical
payload ends with `or '1'='1` rather than a comment, and it is why a
half-remembered SQL payload produces a syntax error here and a reading that
concludes "not injectable" from it is wrong.

So the Playbook's step sends a matched pair that both parse:

```
' or '1'='1        -- widens the node set
' or '1'='2        -- leaves it as it was
```

Same length, same metacharacters, one differing digit. The differential between
them is the evidence, and the second arm is the neutralised control in the
strongest available sense: it contains every character the first one does.

**The error channel.** XPath engines produce short, distinctive messages naming
the expression position. That makes `error_detail` productive here, and the
Playbook's evidence rows pair it with a `response_invariant` control for the
usual reason -- a parser error proves a parser saw the value, not that the value
changed the query.

**Where it surfaces.** XPath-backed authentication is rarer now than the page
implied, but XPath expressions are alive and well in configuration lookups, in
SOAP request routing, and in XSLT. Those are the surfaces to point a reading at,
and they are the same surfaces the SOAP and XML notes point to.

## The half that stays out, and why

**The extraction loop.** `substring(//user[1]/password,1,1)='a'` in a loop is the
blind SQL loop with different syntax and the same objections: request volume, and
credentials landing in this harness's evidence store.

**Authentication bypass as a demonstration.** The predicate that always matches
logs you in as the first user in the document. Proving the finding by using it
authenticates as a real person.

**`doc()` and the XPath 2.0 external functions.** They read other documents and
open outbound requests. That is the XXE capability arriving through a second
door, and it is refused on the same terms.

## The trap in the whole technique

XPath injection gets diagnosed where it does not exist, because a `'` in a value
breaks all sorts of things and an XML-shaped application makes XPath the first
guess.

The check is the pair above. A route that errors on `'` and errors identically on
`' or '1'='2` is not evaluating a predicate; it is choking on a quote somewhere
that may not be an XPath engine at all. The differential between two payloads
that both parse is the only observation that distinguishes an XPath engine from a
brittle string handler, and it is the one the Playbook requires.
