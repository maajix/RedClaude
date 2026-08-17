# Deserialization attacks: the gadget chain, and why the reading stops before it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The standard tour. How to recognise a serialised blob on the wire -- `rO0` and
`AC ED 00 05` for Java, `gASV` and `80 04 95` for pickle, `O:8:"UserPref"` for
PHP, `{"$type":` for .NET with `TypeNameHandling` on, `<java.beans.XMLDecoder>`
for the XML flavour. Then: run the generator. `ysoserial` for Java with a
chosen chain, `ysoserial.net` for .NET with `TypeConfuseDelegate`, `phpggc` for
PHP with the framework's own name, `pickle.Reduce` written by hand for Python.
Send the blob, get a shell, screenshot it.

Underneath the tooling the page had the correct idea, and it is the one the
Playbook keeps: a serialised object carries a *type*, and if the caller picks
the type then the caller picks which of the process's constructors, setters,
`readObject` methods and finalisers run. Everything else on the page was the
industry's collected list of which of those methods, in which library versions,
happen to end in a `Runtime.exec`.

## Why the Playbook does not run it

**The chain proves nothing the type name did not.** Once two blobs differing only
in a type name produce two different answers, the route reconstructs
caller-chosen types. A gadget chain adds no information to that claim. It adds a
demonstration, and the demonstration is the vulnerability being exploited.

**Every generator produces code execution and nothing smaller.** `ysoserial` has
no mode that constructs an inert object loudly. The chains it ships are chosen
for ending in `exec`, `ProcessBuilder`, `InitialContext.lookup` or a class
loader. There is no dial between "no proof" and "arbitrary command on the host",
which is exactly why a reading that reaches for one has already left the
`read_only` ceiling.

**The chains are unstable in ways that break targets.** A commons-collections
chain that misses on a patched version does not fail quietly: it throws inside a
transformer with half the graph constructed, and what is left behind depends on
what the setters touched on the way. Several published chains open a JNDI lookup
before they fail. On a live target, a chain that "did not work" is not a null
result -- it is an unknown state.

**JNDI and LDAP payloads reach infrastructure nobody in the engagement
controls.** The classic .NET and Java remote-loading chains fetch a class from a
URL. That is an outbound connection from the target's network to a host that has
to be stood up for the occasion, serving code, and it is the technique this
corpus refuses in every other Playbook that could reach for it.

**Detection is a different question.** Sending a blob that names
`TemplatesImpl` to see whether a WAF blocks it is a test of the WAF. It is not a
test of the deserialiser, and the two get confused constantly, which is why the
Playbook's step 5 sends a type name that resolves to nothing at all.

## What is kept

Three things, and they are the substance of the page.

The format table, in step 1. Knowing where the type name sits in a Java stream,
a pickle, a PHP `serialize` string, a Jackson document or an `XMLDecoder`
document is what lets the reading edit one field and leave the state alone.

The insight that the type is the vulnerability. Not the payload, not the chain,
not the library version: the fact that a string on the wire chose which
constructor ran.

The inert-type discipline. The page's own advice for testing whether a
deserialiser is reachable at all -- name a container, a `HashMap`, a `Date`, a
primitive wrapper -- is the one technique on it that is both diagnostic and
harmless, and it is what step 3 does.

## The trap in the whole technique

The blob is often signed, HMAC'd or encrypted, and the page's answer was to go
find the key first -- in a bundle, in a config file, in a repository. That turns
one reading into a hunt for key material, and a reading that finds the key can no
longer tell whether the route trusts the blob because it verified the signature
or because it never checked.

When the blob cannot be edited without breaking a signature, the honest verdict
is `inconclusive`, and it says which signature stopped it. That routes to an
operator with a decision in front of them, which is where a decision of that
size belongs.
