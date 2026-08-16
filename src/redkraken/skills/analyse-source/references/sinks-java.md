# Java sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

An Artifact of this kind is usually a Spring or Jakarta tree, or a decompiled
`.jar` or `.war`. Routing is annotation-driven, so `@RequestMapping`,
`@GetMapping`, `@PostMapping` and `@Path` are the route table, and the method
signature names the parameters that reach it: `@RequestParam`,
`@PathVariable`, `@RequestBody`, `@RequestHeader`, `@CookieValue`.

Even without source, a `.jar` carries `web.xml`, `application.yml`, dependency
coordinates in `META-INF` and the framework's own annotations, which is often
enough to say what the service is built on.

## injection.document_parser

Deserialisation lives here: a parser that turns bytes into objects is the
document parser class even when the bytes are not a document. On the JVM this
is the highest-value class in the pack, because a gadget chain in a dependency
turns a parse into execution.

* `ObjectInputStream.readObject`, and anything wrapping it: RMI, JMX, a
  session store, a cache client.
* `XMLDecoder.readObject`, which executes by design.
* `XStream.fromXML` without a permitted-type allow-list.
* Jackson with `enableDefaultTyping()` or a `@JsonTypeInfo(use = Id.CLASS)`
  field, which lets the document choose the class.
* SnakeYAML `new Yaml().load(...)`, whose default constructor instantiates
  arbitrary types; `new Yaml(new SafeConstructor())` is the safe form.
* `DocumentBuilderFactory`, `SAXParserFactory`, `TransformerFactory`,
  `SchemaFactory`, `XMLInputFactory` and `Unmarshaller` left at defaults, which
  is the XXE shape. The safe form is
  `setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)` or
  `XMLConstants.FEATURE_SECURE_PROCESSING`.

## injection.template

The vocabulary has no expression class; this is the interpolation-evaluated-
over-attacker-text class, and every item here is that shape.

* SpEL: `new SpelExpressionParser().parseExpression(user)`, and a
  `@Value("#{...}")` or `@PreAuthorize` string built from input.
* OGNL, which Struts 2 evaluates over parameter names as well as values.
* FreeMarker `new Template(name, userString, cfg)` and Velocity
  `evaluate(context, writer, tag, userString)`.
* Thymeleaf when a fragment or view name comes from input
  (`return "redirect:" + user` and `~{__${user}__}`).
* A logging call whose message argument is attacker text on Log4j below 2.15,
  where `${jndi:ldap://...}` in the message was resolved as a lookup.

Safe form: a template chosen from a fixed set, with input passed as a model
value.

## injection.query_language

* `Statement.executeQuery` or `executeUpdate` over a concatenated string.
* JPA `createQuery`/`createNativeQuery` with concatenation, and a Spring Data
  `@Query` whose value is assembled rather than parameterised.
* MyBatis `${}`, which interpolates, against `#{}`, which binds.
* A sort or column name taken from input, which no placeholder can carry.

Safe form: `PreparedStatement` with `?`, JPA named parameters, `#{}` in
MyBatis, and an allow-list for identifiers.

## injection.command

* `Runtime.getRuntime().exec(String)`, which splits on whitespace rather than
  parsing a shell, so quoting behaves differently from what an author expects.
* `new ProcessBuilder("sh", "-c", user)`.

Safe form: `ProcessBuilder` with a fixed argument list.

## injection.path

* `new File(base, user)`, `Paths.get`, `Files.newInputStream`,
  `FileInputStream`, `ResourceUtils.getFile` and `ClassPathResource` over
  input.
* A Spring controller returning a view name or a `Resource` derived from a path
  variable, and `@PathVariable` on a pattern ending `/**`, which lets the
  variable contain separators.
* `ZipEntry.getName()` used as a destination, which is zip slip.

Safe form: resolve, then `startsWith` the canonical base directory
(`toRealPath()` or `getCanonicalPath()`), and compare canonical to canonical.

## injection.request_forgery

* `new URL(user).openConnection()`, `HttpURLConnection`, `RestTemplate`,
  `WebClient`, `HttpClient.send`, and Apache `HttpClient` with a URI from
  input.
* `URI.create` used as validation. Java's `URL.equals` resolves DNS, which
  makes a host check both slow and answerable differently at request time.

## injection.markup

* JSP `<%= %>` and `out.print` over input, and `<c:out escapeXml="false">`.
* Thymeleaf `th:utext`, and a `javascript:` value reaching `th:href`.
* `HtmlUtils.htmlEscape` skipped on a value placed inside an attribute.

## authorization.function_access

* A controller method with no `@PreAuthorize`, `@Secured` or `@RolesAllowed`
  where its siblings have one.
* A `SecurityFilterChain` with `permitAll()` on a broad matcher, an
  `antMatchers`/`requestMatchers` pattern that does not cover a variant path,
  or `csrf().disable()` beside a cookie-based session.
* An actuator exposed: `management.endpoints.web.exposure.include=*` reaches
  `/env`, `/heapdump` and `/mappings`.

## transport.tls_configuration

* An `X509TrustManager` whose `checkServerTrusted` is empty, a
  `HostnameVerifier` returning `true`, or
  `SSLContext.init(null, trustAllCerts, ...)`.

## information_disclosure.artifact_exposure

* A credential literal in `application.properties` or `application.yml`, a
  keystore committed beside the code, or `spring.h2.console.enabled=true`.

## What a match is not

A decompiled jar contains its dependencies. A gadget class on the classpath is
what makes a deserialisation sink reachable, but a gadget alone is not a sink,
and neither is a sink in a dependency the application never enters.
