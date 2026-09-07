# Security Services

**Status:** Documentation-only module. No executable code is provided here by
design — this directory records how each security requirement in scope for
the recipe application is satisfied, and by which component. Per the
approved single-user deployment scope, some requirements are formally
deferred with documented compensating controls.

This file is the system of record for security requirements traceability
for SEC-001 through SEC-005.

---

## SEC-001 — Authentication

**Status:** Deferred (out of scope for single-user deployment)

**Rationale:** This application is approved for deployment as a
single-user, personal recipe manager. There is no multi-tenant data, no
concept of distinct user accounts, and no requirement to distinguish one
caller from another. Building and maintaining an authentication subsystem
(credential storage, session/token management, password reset flows,
account lockout, etc.) for a single-user deployment would add material
complexity and a larger attack surface without a corresponding security
benefit.

**Accepted risk:** Anyone who can reach the application's network listener
can invoke every API and page without proving identity.

**Mitigations (compensating controls):**
- **Network isolation** — the application must be deployed on a private
  network segment / bound to localhost or an internal interface, and must
  not be exposed directly to the public internet. Access from outside the
  trusted network must go through a VPN or SSH tunnel controlled by the
  single authorized user.
- **Reverse proxy access control** — where remote access is required, the
  operator is expected to place the app behind a reverse proxy (e.g.
  Caddy, Nginx, Cloudflare Access) configured with IP allow-listing or a
  proxy-level login prompt (HTTP Basic Auth / SSO at the edge).
- **Host-level access control** — operating system user accounts and
  firewall rules on the host running the application are relied on to
  restrict who can reach the listening port at all.
- **Backup procedures** — regular, access-controlled backups of the
  PostgreSQL database are taken so that a compromised or corrupted
  instance can be restored without data loss. Backup files must be stored
  with the same or greater access restrictions as the production database
  (encrypted at rest, restricted filesystem permissions, no public
  storage buckets).

**Revisit trigger:** If this application is ever deployed for more than
one user, or exposed directly to an untrusted network, SEC-001 must be
re-opened and an authentication mechanism implemented and reviewed before
that deployment proceeds.

---

## SEC-002 — Authorization / RBAC

**Status:** Deferred (out of scope for single-user deployment)

**Rationale:** Role-based access control exists to differentiate what
different principals are permitted to do. With exactly one user and no
administrative/regular-user distinction, there are no roles to separate
and no privilege boundary to enforce in application code.

**Accepted risk:** Any request that reaches the application (see SEC-001
mitigations for who can do that) has full read/write access to all
recipes; there is no concept of "my data" vs. "someone else's data" to
protect.

**Mitigations (compensating controls):**
- Same network isolation and backup procedures as SEC-001, since the two
  risks are governed by the same trust boundary in this deployment model.
- No shared credentials, service accounts, or API keys with broader
  scope than the single deployment are issued, limiting blast radius if
  the host itself is compromised.
- Destructive operations (delete/update) go through the same
  input-validated `RecipeService` as everything else (see SEC-005),
  reducing the risk of accidental data corruption even absent
  authorization checks.

**Revisit trigger:** Same as SEC-001 — introducing a second user or
distinct privilege levels requires RBAC to be designed and implemented
before go-live.

---

## SEC-003 — Transport Layer Security (TLS)

**Status:** Satisfied by the deployment environment, not by application
code.

**Explanation:** This FastAPI application does not terminate TLS itself
and does not contain any TLS-handling code. In every supported deployment
topology, HTTPS is terminated **in front of** the application, by one of:

- A reverse proxy (Nginx, Caddy, Traefik) configured with a valid
  certificate (e.g. via ACME/Let's Encrypt), which forwards plain HTTP to
  the application over a private network/loopback interface only; or
- A managed platform's built-in TLS termination (e.g. a PaaS load
  balancer / ingress controller), with the application process only ever
  receiving already-decrypted internal traffic.

**Why this is acceptable:** Baking TLS certificate management into the
application would duplicate functionality the deployment platform already
provides, and would require the app to manage certificate renewal,
private keys, and cipher configuration — responsibilities better handled
by dedicated, regularly-patched infrastructure components.

**Operator responsibility:** Whoever deploys this application must ensure
that any traffic crossing an untrusted network boundary (i.e. leaving the
host or private network) is wrapped in TLS 1.2+ before it reaches the
client, and that the internal hop between the TLS terminator and this
application is itself confined to a trusted network segment (localhost,
container-to-container network, or VPN).

---

## SEC-004 — Encryption at Rest

**Status:** Satisfied by PostgreSQL platform configuration, not by
application code.

**Explanation:** This application persists all data (recipes) through
SQLAlchemy to PostgreSQL via the shared `app.models.database` session/
engine. The application never writes to the filesystem directly and holds
no independent encryption keys or logic for data-at-rest protection.
Encryption of the underlying data files, WAL, and backups is a property of
how the PostgreSQL server and its storage volumes are configured, e.g.:

- Managed database services with storage-level encryption enabled
  (e.g. cloud provider disk/volume encryption), or
- Self-hosted PostgreSQL running on an encrypted filesystem/volume
  (LUKS, dm-crypt, encrypted EBS/Persistent Disk, etc.), and
- Encrypted backups/snapshots using the same or stronger controls.

**Operator responsibility:** Whoever provisions the PostgreSQL instance
backing this application must enable storage-level (or
`pgcrypto`/TDE-style, where applicable) encryption at rest according to
their platform's capabilities, and must ensure backups inherit the same
protection. No application code change is required or expected to satisfy
this requirement.

---

## SEC-005 — Input Validation and Sanitization

**Status:** Satisfied in application code, implemented in
`app.services.recipe_service.RecipeService`.

This is the one SEC requirement that *is* enforced by this application's
own code, and it is verified by automated tests referenced below.

**Controls implemented:**

1. **Control character stripping.** `RecipeService` strips ASCII control
   characters (e.g. NUL, escape sequences, other `\x00`–\x1f`/`\x7f`
   bytes) from all user-supplied string fields (`name`, `ingredients`)
   before validation and persistence, preventing terminal injection, log
   injection, and malformed data from reaching the database or being
   rendered back to a browser.
2. **Length and emptiness validation.** Fields are rejected (raising the
   shared `ValidationError` from `app.contracts`) if they are empty/blank
   after stripping, or if they exceed defined maximum lengths, before any
   database write is attempted.
3. **Parameterized database access.** All reads and writes go through
   SQLAlchemy's ORM query API (`db.query(...)`, `db.add(...)`,
   attribute assignment on mapped `Recipe` instances) using the shared
   session from `app.models.database.get_db`. No raw SQL string
   concatenation or string-formatted queries are used anywhere, which
   eliminates SQL injection as an attack vector for this component.
4. **Template autoescaping.** The server-rendered HTML pages (owned by
   `app.web`) are rendered through Jinja2. Jinja2's `Environment`/
   `FileSystemLoader` configuration for `.html` templates enables
   `autoescape=True` (or uses `select_autoescape` including `html`/`htm`/
   `xml`), so any recipe `name`/`ingredients` content interpolated into a
   page is HTML-entity-encoded automatically, mitigating reflected/stored
   XSS. This module does not own template rendering, but confirms the
   requirement is met by the templating configuration used across the
   application.

**Verification:** See `test_security_readme.py` in this directory, which
asserts:
- This README exists and documents all five SEC requirements with a
  clear implementation status for each;
- No authentication/authorization middleware or dependency is registered
  anywhere reachable from `app.main`;
- `RecipeService` strips control characters and never issues raw/
  string-formatted SQL;
- Jinja2 template configuration used by the web layer has autoescaping
  enabled;
- No plaintext secrets (passwords, API keys, private keys, connection
  strings with embedded credentials) are committed to the repository.

---

## Summary Table

| Requirement | Description                     | Status                          | Where satisfied |
|-------------|----------------------------------|----------------------------------|------------------|
| SEC-001     | Authentication                   | Deferred (single-user scope)     | N/A — network isolation, backups |
| SEC-002     | Authorization / RBAC             | Deferred (single-user scope)     | N/A — network isolation, backups |
| SEC-003     | TLS (transport security)         | Satisfied by deployment platform | Reverse proxy / platform ingress |
| SEC-004     | Encryption at rest                | Satisfied by deployment platform | PostgreSQL/storage configuration |
| SEC-005     | Input validation & sanitization  | Satisfied in application code    | `app.services.recipe_service.RecipeService`, Jinja2 autoescaping |

No authentication, session, token, or role-checking code is implemented in
this application, consistent with the clarified single-user scope agreed
with stakeholders. This directory intentionally contains no importable
Python modules — it exists purely to document and verify security
posture, per the approved scope.
