# Kotlin sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

**Server-side Kotlin only.** Android was retired as a scope: one Agent
definition, two Skills, ten Playbook topics and thirty-nine operator references,
with the reason and the reversal registered in
`baseline/v1-dispositions.json`. This pack does not carry `Intent`,
`WebView`, `ContentProvider` or any other device sink, and adding them here
would reintroduce the scope through a file rather than through a decision.

An Artifact of this kind is usually a Ktor or Spring Boot tree, or a decompiled
class file whose Kotlin metadata survived. Kotlin runs on the JVM, so
`sinks-java.md` applies in full and is the pack to read alongside this one.
What follows is what is spelled differently in Kotlin, or what Kotlin's own
idioms make easy to miss.

Sources are a Ktor `call.parameters`, `call.receive<T>()`,
`call.request.headers` and `call.request.queryParameters`, or in Spring the
same annotations Java uses on a Kotlin method signature.

## injection.command

* `ProcessBuilder("sh", "-c", user)` and `Runtime.getRuntime().exec(user)`.
* A string template inside either, which is the Kotlin spelling of
  concatenation: `"convert $user out.png"` is one string, not two arguments.

## injection.query_language

* Exposed's `exec("...")` and `wrapAsExpression` with an interpolated string;
  `Op.build` given a raw fragment.
* A string template inside a Spring Data `@Query`, a JDBC `Statement`, or
  `jdbcTemplate.query`.
* String templates are the signal to look for. `"WHERE id = $id"` reads like a
  parameterised query and is not one.

Safe form: Exposed's typed DSL, named parameters, `PreparedStatement`.

## injection.document_parser

* `kotlinx.serialization` `Json.decodeFromString` into a polymorphic hierarchy
  whose `SerializersModule` is open, so the document picks the type.
* `Json { ignoreUnknownKeys = true; isLenient = true }` over a security-relevant
  payload, which accepts more shapes than the type suggests.
* Jackson with the Kotlin module and default typing enabled, SnakeYAML's
  default constructor, and every JVM XML factory left at its defaults. All four
  are `sinks-java.md`'s entries reached through Kotlin syntax.

## injection.template

* SpEL, OGNL, FreeMarker and Velocity as in `sinks-java.md`.
* Ktor's `respondTemplate` given a template name from input.

## injection.path

* `File(base, user)`, `Paths.get(user)`, and Ktor `staticFiles`/`staticFolder`
  mounted over a directory that also holds configuration.
* `call.respondFile(base, user)`.

Safe form: canonicalise, then check the prefix against the canonical base.

## injection.request_forgery

* Ktor `HttpClient().get(userUrl)`, and `HttpClient(CIO) { followRedirects =
  true }`, which is the default.
* Spring `WebClient` and `RestTemplate` as in `sinks-java.md`.

## injection.markup

* `kotlinx.html`'s `unsafe { +rawHtml }`, which is the escape hatch out of the
  builder's escaping.
* Thymeleaf `th:utext` from a Kotlin controller.

## authorization.function_access

* A Ktor route outside an `authenticate { }` block where its siblings are
  inside one. Ktor's authentication is per-route, so an omitted wrapper is an
  unauthenticated route rather than an error.
* `install(CORS) { anyHost() }` together with `allowCredentials = true`, which
  is the reflected-origin shape.
* Spring's annotations missing on a Kotlin controller method, exactly as in
  `sinks-java.md`.

## information_disclosure.error_detail

* `install(StatusPages) { exception<Throwable> { call.respondText(it.toString())
  } }`, which returns the exception to the caller.
* `!!` and `requireNotNull` in a handler, which turn a missing value into an
  exception whose message may carry state.
* `data class` `toString()` logged or returned, which prints every property
  including the ones holding secrets.

## authentication.credential_verification

* A token compared with `==`, which on Kotlin `String` is a content comparison
  and not a constant-time one.
* `Random.nextInt()` or `Random.nextLong()` for a token, against
  `SecureRandom`.

## What a match is not

Kotlin's null safety, immutability and typed builders remove classes of bug
that are not the classes in this pack. A Kotlin tree is not safer against
injection than the Java tree beside it, and a decompiled Kotlin class is still
a JVM class: read `sinks-java.md` before concluding a tree is clean.
