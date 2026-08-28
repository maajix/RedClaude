---
type: Skill
title: "analyse-source"
description: "Read a stored source Artifact and ground every route, parameter and endpoint in the bytes it came from. Use when a bundle, a source map or a configuration document has been stored and the question is what it says the application exposes."
resource: ../../../src/redkraken/skills/analyse-source/SKILL.md
tags: [skill, successful_tool_run]
generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }
status: stable
stale_after: 2027-08-28T00:00:00Z
bb:roles: [js_analyst]
bb:evidence_profile: successful_tool_run
bb:version: bf2397fa870c0956f62b1e5725f05dbc9661a86fa4434f597d0874b617178407
bb:sha256: b131d9b8f503c2e153b0eac8542f0d44db5159bb7648b5fbb122d24fc6c24b1d
sources:
  - id: analyse-source--code-review
    resource: /references/analyse-source--code-review.md
    title: "Reading source: what a sink is worth, and what it is not"
    author: human:maintainer
  - id: analyse-source--sinks-csharp
    resource: /references/analyse-source--sinks-csharp.md
    title: "C# and .NET sinks"
    author: human:maintainer
  - id: analyse-source--sinks-go
    resource: /references/analyse-source--sinks-go.md
    title: "Go sinks"
    author: human:maintainer
  - id: analyse-source--sinks-java
    resource: /references/analyse-source--sinks-java.md
    title: "Java sinks"
    author: human:maintainer
  - id: analyse-source--sinks-js
    resource: /references/analyse-source--sinks-js.md
    title: "JavaScript and TypeScript sinks"
    author: human:maintainer
  - id: analyse-source--sinks-kotlin
    resource: /references/analyse-source--sinks-kotlin.md
    title: "Kotlin sinks"
    author: human:maintainer
  - id: analyse-source--sinks-php
    resource: /references/analyse-source--sinks-php.md
    title: "PHP sinks"
    author: human:maintainer
  - id: analyse-source--sinks-python
    resource: /references/analyse-source--sinks-python.md
    title: "Python sinks"
    author: human:maintainer
  - id: analyse-source--sinks-ruby
    resource: /references/analyse-source--sinks-ruby.md
    title: "Ruby sinks"
    author: human:maintainer
  - id: analyse-source--sinks-rust
    resource: /references/analyse-source--sinks-rust.md
    title: "Rust sinks"
    author: human:maintainer
---

# Read a stored source Artifact and ground every route, parameter and endpoint in the bytes it came from. Use when a bundle, a source map or a configuration document has been stored and the question is what it says the application exposes.

## Which roles may load it

- `js_analyst`

## What it may call


Runtime tools it reaches through `run_tool`:

- `jq`

## Scripts it owns

- `extract_paths.py`

## Playbooks that load it

- [external-resources](/playbooks/external-resources.md)
- [supply-chain](/playbooks/supply-chain.md)

## Maintainer references

- [code-review.md](/references/analyse-source--code-review.md)[^analyse-source--code-review]
- [sinks-csharp.md](/references/analyse-source--sinks-csharp.md)[^analyse-source--sinks-csharp]
- [sinks-go.md](/references/analyse-source--sinks-go.md)[^analyse-source--sinks-go]
- [sinks-java.md](/references/analyse-source--sinks-java.md)[^analyse-source--sinks-java]
- [sinks-js.md](/references/analyse-source--sinks-js.md)[^analyse-source--sinks-js]
- [sinks-kotlin.md](/references/analyse-source--sinks-kotlin.md)[^analyse-source--sinks-kotlin]
- [sinks-php.md](/references/analyse-source--sinks-php.md)[^analyse-source--sinks-php]
- [sinks-python.md](/references/analyse-source--sinks-python.md)[^analyse-source--sinks-python]
- [sinks-ruby.md](/references/analyse-source--sinks-ruby.md)[^analyse-source--sinks-ruby]
- [sinks-rust.md](/references/analyse-source--sinks-rust.md)[^analyse-source--sinks-rust]

[^analyse-source--code-review]: Reading source: what a sink is worth, and what it is not
[^analyse-source--sinks-csharp]: C# and .NET sinks
[^analyse-source--sinks-go]: Go sinks
[^analyse-source--sinks-java]: Java sinks
[^analyse-source--sinks-js]: JavaScript and TypeScript sinks
[^analyse-source--sinks-kotlin]: Kotlin sinks
[^analyse-source--sinks-php]: PHP sinks
[^analyse-source--sinks-python]: Python sinks
[^analyse-source--sinks-ruby]: Ruby sinks
[^analyse-source--sinks-rust]: Rust sinks
