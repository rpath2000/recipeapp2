# Security Notes for app/security

## SEC-001: No Authentication or Authorization

This application implements **no authentication and no authorization**.
Every HTTP route exposed by every component (including `app.web`'s
`/recipe` page and `POST /recipe` handler, and any JSON API routes) is
**publicly accessible**. This is a deliberate, scoped decision tracked as
**SEC-001** in the requirements traceability matrix, not an oversight.

Consequences accepted under SEC-001:

- Anyone with network access to the service can create, read, and update
  recipes.
- There is no per-user data isolation.
- There is no audit trail of *who* performed an action, only *what*
  happened and *when* (see structured logging below).

If authentication/authorization is added in the future, this document and
the traceability matrix must be updated as part of that change, per the
"Security Review Gates" requirement in the universal engineering standards
(human approval required for authentication/authorization changes).

## SQL Injection Prevention

- `app.services.recipe.RecipeService` (owned by another component) is
  required to use SQLAlchemy ORM queries exclusively, with bound
  parameters supplied via ORM attribute filters (e.g.
  `db.query(Recipe).filter(Recipe.id == id)`), and construction of `Recipe`
  model instances via keyword arguments. No raw SQL string concatenation
  or string-formatted queries are permitted anywhere in the codebase.
- `app/security` does not issue any database queries itself; it only
  provides logging helpers.

## XSS Prevention

- All server-rendered HTML is produced via Jinja2 (`app.integrations.templates.templates`),
  which has autoescaping enabled by default for `.html` templates.
  User-supplied recipe `name` and `ingredients` values must never be
  rendered through the `|safe` filter or `Markup(...)` — doing so would
  bypass autoescaping and reintroduce XSS. This module does not render any
  templates itself, but documents and tests this expectation.

## Structured Security Logging

`app.security.logging` provides:

- `setup_logging()` — the exported seam. Configures the root logger with a
  single stdout `StreamHandler` emitting single-line JSON records
  (timestamp, level, logger, message, plus structured `extra` fields).
  Idempotent; safe to call multiple times.
- `log_validation_failure(field, reason, value)` — call this whenever a
  `ValidationError` (from `app.contracts`) is raised so that validation
  failures (including SQL-injection-shaped or XSS-shaped input) are
  visible in the logs for later analysis.
- `log_unhandled_exception(context, exc)` — call this from exception
  handlers to record unhandled exceptions with full context and stack
  trace, without ever logging secrets or credentials (there are none in
  this application).
- `log_request(method, path, status_code, duration_ms)` — intended for use
  by HTTP middleware wired in the entrypoint to produce structured access
  logs correlating method, path and response status for every request,
  regardless of the (nonexistent) authentication state.

No passwords, tokens, secrets, or personal data are ever logged by this
module, consistent with the universal engineering logging standard.
