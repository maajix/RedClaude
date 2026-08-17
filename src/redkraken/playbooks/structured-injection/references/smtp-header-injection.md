# SMTP header injection: the newline that ends a field

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

A contact form builds a mail message. The caller's address goes into a header:

```
From: $email
Subject: $subject
```

and a value containing `\r\n` ends that header and begins another. The page's
payloads added recipients (`\r\nBcc: everyone@example.com`), rewrote the reply
path, and -- with a doubled CRLF -- ended the header block entirely and wrote the
attacker's own body. It covered the generalisation too, which is the reason the
page is attached to this Playbook rather than an email one: the same defect
appears wherever a line-oriented protocol is built by concatenation. HTTP
response splitting is the same bug in a different grammar, and so is log
injection, and so is a `Location` header assembled from a query parameter.

## The half the Playbook uses

**CRLF as a structural probe, and the encoding ladder that goes with it.**

The general question `structured-injection` asks is whether a value becomes
structure in a format the target assembles. A newline in a line-oriented format
is the cleanest instance of that question there is, and it can be asked without
sending mail to anybody.

The ladder matters because the interesting outcome is in the middle of it:

* raw `\r\n`
* percent-encoded `%0d%0a`
* over-encoded `%250d%250a`
* the lone `\n` without its `\r`, which many parsers accept and many filters miss

A route that rejects the raw form and accepts one of the encoded ones is
filtering rather than escaping, and that difference is the finding. It is the
same diagnostic the SQL pack's tampering note describes, in a grammar where it is
easier to observe.

**The observable is usually an error, not a delivered message.** A mail library
that validates its own headers raises when it finds a newline, and the route
returns a 500 or a specific message. That is an `error_detail` observation, it is
the Playbook's primary evidence row for this surface, and it comes with the usual
requirement: the neutralised control is the same value with the newline replaced
by a space, so the length and shape hold and only the structural character
differs.

## The half that stays out, and why

**Sending mail.** Every payload on the v1 page ends with a message arriving in
somebody's inbox. Adding a `Bcc` sends the target's mail to an address the
reading chose; rewriting the body sends content the target did not write, from
the target's own domain, over the target's reputation. That is out on the plainest
reading of any rules of engagement, and it is out here regardless of them.

The Playbook's version stops at the parser. It asks whether the newline changes
the structure, and the answer arrives at the library boundary.

**Header injection into a live HTTP response as a demonstration.** Response
splitting is a real finding and it is the `routing` reading's subject, where the
cache-poisoning consequences can be reasoned about properly. Splitting a response
on a shared cache is a change to what other users receive, which is why it is not
a step here.

## The trap in the whole technique

The success case is invisible from the response. A route that accepts the
injected header often returns exactly what it returned before -- the form
submitted, the confirmation rendered -- because the mail was queued and the
handler does not report on it. The evidence is in a mailbox the reading cannot
see, and the only in-band signal is the error you get when the injection *fails*
validation.

Which inverts the usual reading: on this surface, the clean 200 is the ambiguous
outcome and the exception is the informative one. A reading that treats "no error"
as "no injection" has it exactly backwards, and the honest verdict for a silent
200 is `inconclusive`.
