# Reading source: what a sink is worth, and what it is not

Maintainer and analyst notes, attached to one Skill. Nothing here reaches a
model at run time: `Read` is forbidden to every role in the roster, so a file
beside `SKILL.md` is material a person opens and never text an Agent loads. It
is hashed into this Skill's dependency manifest, so editing a pack moves the
Skill's version and every Task that recorded the old one still says which text
it ran under.

It is a reference rather than part of `SKILL.md` for the reason the whole
migration exists. v1 shipped `playbooks/code-review/` -- one README and nine
language sink lists -- as Agent context, so every Agent carried nine languages
of sink names into every Task, including the ones that never saw a byte of
source. Attached here the material belongs to the one technique that reads
source, and that bound is what makes it safe to keep at all.

## What these packs are, and are not

The v1 texts are not in this repository. `baseline/v1-manifest.tsv` froze what
v1 was by identity and digest and deliberately not by content, so each pack is
written fresh to the scope of the row it answers rather than copied from it.
The `sha256` in `baseline/v1-dispositions.tsv` still ties each row to the text
the decision was taken about, which is the part that had to survive.

## What source review produces here

A source Artifact is bytes already stored under a hash: a bundle, a source map,
a configuration document, a repository that was left reachable. Reading it
produces two things and no third.

1. **Attack Surface.** Routes, parameters and endpoints the bytes say exist.
2. **A Property class, and a reason.** A sink is a reason to ask one question
   about one subject, and the class is what selects a Playbook.

It does not produce a Finding and it does not produce reachability. Source says
what the application refers to; it never says what answers. That boundary is
step 4 of `SKILL.md`, and it is why this material is safe to hold: a sink list
read as a verdict list is a generator of invalid reports.

## Three things before a Hypothesis

A match is worth a Hypothesis when all three hold, and worth a note when they
do not:

* the **sink** is in the bytes, cited by Artifact hash and by the Tool run that
  showed it;
* a **parameter reaches it**, in the bytes, rather than in the framework's
  conventions;
* the **Property class** is one the vocabulary already has, so that something
  downstream can select on it.

The second is where source review usually fails. `exec` on one line and a
request parameter on another are not a data flow, and calling them one is a
claim about code nobody read.

## Choosing a pack

Pick by what the Artifact is, not by what the target is said to run. A
`sourceMappingURL` that resolves gives original paths and usually the build's
framework; a module map names its bundler; a configuration document names its
runtime.

| Artifact | Pack |
|---|---|
| Browser bundle, source map, Node service | `sinks-js.md` |
| Django, Flask, FastAPI, a `.py` tree | `sinks-python.md` |
| Laravel, WordPress, a `.php` tree | `sinks-php.md` |
| Spring, Jakarta, a `.java` tree or decompiled `.jar` | `sinks-java.md` |
| Ktor, Spring Kotlin, a `.kt` tree | `sinks-kotlin.md` |
| ASP.NET, a `.cs` tree, a decompiled assembly | `sinks-csharp.md` |
| A Go module, or a binary's embedded paths | `sinks-go.md` |
| Rails, Sinatra, a `.rb` tree | `sinks-ruby.md` |
| A Cargo workspace or a `.rs` tree | `sinks-rust.md` |

Android is not in the table and is not a gap. One Agent definition, two Skills,
ten Playbook topics and thirty-nine operator references were retired as a
scope, with the reason and the reversal registered in
`baseline/v1-dispositions.json`. Kotlin is here as a server language only.

## The shape every pack has

Each pack is headed by Property class, because that is the vocabulary the rest
of the system selects and reports in: a match then arrives already carrying the
word a Playbook triggers on, instead of carrying an API family name that
somebody has to translate later.

Under each class the pack gives the sink, the shape that makes it one, and the
safe form. The safe form is the useful half. Most matches in a real tree are
the safe form, and a pack that lists only dangerous names produces an analyst
who reports every match it finds.
