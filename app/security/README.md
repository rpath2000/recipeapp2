# Security Services

This module implements the cross-cutting security concerns for the
recipe application: enterprise SSO authentication, ownership-based
authorization, TLS/HSTS enforcement, and secrets management.

## Contents

- `sso_middleware.py` — Enterprise SSO authentication middleware.
- `authz.py` — Ownership-based authorization utility for edit/delete operations.
- `tls_config.py` — HTTPS enforcement and HSTS header middleware/config.
- `secrets.py` — Secrets loader (environment variables or AWS Secrets Manager).

## SSO Integration

### How it works

The application expects an upstream enterprise SSO gateway / reverse
proxy (e.g. corporate API gateway, SiteMinder, Shibboleth-fronted proxy)
to authenticate the end user and forward the authenticated identity to
this service via the `X-SSO-User` HTTP header.

`SSOMiddleware`:

1. Intercepts every incoming request (except exempt paths such as
   `/health`, `/docs`, `/openapi.json`, `/redoc`, `/favicon.ico`).
2. Reads the `X-SSO-User` header.
3. If present and non-empty, stores the trimmed value in
   `request.state.user_id` and allows the request to proceed.
4. If missing or empty, immediately responds `401 Unauthorized` with a
   generic error body (no internal details leaked) and logs a
   structured `sso_auth_failed` audit event.
5. On success, logs a structured `sso_auth_success` audit event
   including the resolved `user_id`, `path`, and `method`.

Downstream code (route handlers, services) should retrieve the
authenticated user via:

from app.security.sso_middleware import SSOMiddleware

user_id = SSOMiddleware.get_current_user(request)

or via the equivalent `app.security.authz.get_current_user(request)`
helper, which delegates to the same logic — use whichever import is
more convenient in a given module; both resolve to the same single
source of truth.

### Wiring into the application

In the application entrypoint (`app/main.py`), the middleware is
registered on the FastAPI app, for example:

from fastapi import FastAPI
from app.security.sso_middleware import SSOMiddleware
from app.security.tls_config import HTTPSEnforcementMiddleware

app = FastAPI()
app.add_middleware(HTTPSEnforcementMiddleware)
app.add_middleware(SSOMiddleware)

**Important:** Middleware registered later with `add_middleware` runs
*earlier* in the request lifecycle (Starlette wraps middlewares in
reverse order of registration). Ensure TLS enforcement happens before
SSO extraction if strict ordering is required, and validate the
resulting order in integration tests against the running app.

### Trust boundary

`X-SSO-User` is only trustworthy if the network topology guarantees
that:

- The header can only be set by the trusted SSO gateway/proxy.
- Direct client access to the application (bypassing the proxy) is
  blocked at the network layer.

This is a standard deployment assumption for enterprise SSO
integrations and must be enforced by infrastructure/network
configuration, not by this application alone.

## Authorization Model

Authorization in this application is purely ownership-based:

- A recipe has an `owner_id` field (see `app.contracts.RecipeOut`).
- Only the user whose `user_id` matches a recipe's `owner_id` may
  update or delete that recipe.

Usage in route handlers:

from fastapi import HTTPException
from app.security.authz import get_current_user, verify_ownership

def delete_recipe_handler(recipe_id: str, request: Request, db: Session):
    user_id = get_current_user(request)
    recipe = recipe_service.get_recipe(recipe_id, db)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if not verify_ownership(recipe.owner_id, user_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    recipe_service.delete_recipe(recipe_id, user_id, db)

Every authorization decision (`verify_ownership`) is logged with a
structured audit event: `authz_check_granted` or `authz_check_denied`,
including `requesting_user_id` and `resource_owner_id`. No sensitive
payload data is included in these logs.

## TLS / HTTPS Enforcement

`HTTPSEnforcementMiddleware` enforces the following policy:

- If `ENFORCE_HTTPS=true` (default) and the effective request scheme
  is not `https` (checked via the `X-Forwarded-Proto` header when
  behind a TLS-terminating load balancer, or the request URL scheme
  otherwise), the request is redirected (HTTP 307) to the HTTPS
  equivalent URL.
- Every response — including redirects — has the
  `Strict-Transport-Security` header set, instructing browsers to only
  connect over HTTPS in the future.

### Configuration (environment variables)

| Variable                   | Default                  | Description                                          |
|-----------------------------|---------------------------|-------------------------------------------------------|
| `ENFORCE_HTTPS`             | `true`                   | Enable HTTP → HTTPS redirect enforcement.             |
| `HSTS_MAX_AGE`              | `31536000` (1 year)      | `max-age` directive for the HSTS header.              |
| `HSTS_INCLUDE_SUBDOMAINS`   | `true`                   | Adds `includeSubDomains` to the HSTS header.          |
| `HSTS_PRELOAD`              | `false`                  | Adds `preload` to the HSTS header.                    |
| `TRUSTED_PROXY_HEADER`      | `X-Forwarded-Proto`      | Header used to detect original scheme behind a proxy. |

Actual TLS termination (certificates, cipher suites) is handled by the
deployment's load balancer / ingress; this application enforces
policy at the HTTP layer only.

## Secrets Management

`SecretsLoader` centralizes retrieval of sensitive configuration
values. It never hardcodes secrets and never logs secret values
(only secret *names* are logged, for audit purposes).

### Provider selection

Controlled by `SECRETS_PROVIDER`:

- `env` (default): read directly from environment variables.
- `aws`: fetch a JSON secret blob from AWS Secrets Manager (identified
  by `AWS_SECRET_ID`, optionally scoped by `AWS_REGION`), falling back
  to environment variables for any keys not present in the blob.

### Supported secrets

| Secret                | Env fallback var         | AWS blob key           |
|------------------------|---------------------------|--------------------------|
| Database password      | `DATABASE_PASSWORD`       | `database_password`      |
| S3 access key ID       | `S3_ACCESS_KEY_ID`        | `s3_access_key_id`       |
| S3 secret access key   | `S3_SECRET_ACCESS_KEY`    | `s3_secret_access_key`   |

**Note:** the shared database connection string (`DATABASE_URL`) used
by `app.models.database` is managed separately by that module, as per
the application's single shared database configuration. This
`SecretsLoader` is intended for supplemental credentials (e.g. rotated
passwords fetched at startup, S3 credentials for `app.integrations.s3_client`)
that are not already embedded in `DATABASE_URL`.

Usage:

from app.security.secrets import get_secrets_loader

loader = get_secrets_loader()
db_secret = loader.get_database_password()
s3_secret = loader.get_s3_credentials()

## Audit Logging

All authentication and authorization events are emitted as structured
log records (via the standard `logging` module) under the loggers
`app.security.sso` and `app.security.authz`, including:

- `sso_auth_success` / `sso_auth_failed`
- `authz_check_granted` / `authz_check_denied`
- `secret_loaded` (secret *names* only, never values)
- `insecure_request_redirected`

No passwords, tokens, secrets, or personal data beyond `user_id` are
ever logged, per organizational logging standards.
