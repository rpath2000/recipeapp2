"""Unit tests verifying the security posture documented for this module.

These tests do not exercise any code that lives in ``app/security``
(there is none, by design) — instead they verify:

1. This README documents all five SEC requirements with an implementation
   status for each.
2. No authentication/authorization middleware or dependency has been
   wired into the FastAPI application.
3. ``RecipeService`` strips control characters and uses only parameterized
   (ORM) database access, never raw/string-formatted SQL.
4. Jinja2 template configuration used by the web layer enables
   autoescaping.
5. No plaintext secrets are committed anywhere in the repository.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

THIS_DIR = Path(__file__).resolve().parent          # app/security
APP_DIR = THIS_DIR.parent                            # app
REPO_ROOT = APP_DIR.parent                           # repository root

README_PATH = THIS_DIR / "README.md"


def _repo_python_files() -> list[Path]:
    """Return all tracked-looking .py files under the repository, excluding
    common noise directories (virtualenvs, caches, node_modules, git)."""
    excluded_dir_names = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        "site-packages",
    }
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in excluded_dir_names for part in path.parts):
            continue
        files.append(path)
    return files


def _repo_text_files_for_secret_scan() -> list[Path]:
    """Return a broad set of text-ish files to scan for committed secrets."""
    excluded_dir_names = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        "site-packages",
    }
    allowed_suffixes = {".py", ".env", ".ini", ".cfg", ".yaml", ".yml", ".json", ".toml", ".md"}
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in excluded_dir_names for part in path.parts):
            continue
        if path.suffix.lower() in allowed_suffixes:
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# 1. README documents all five SEC requirements with implementation status
# ---------------------------------------------------------------------------


class TestReadmeDocumentation:
    def test_readme_exists(self):
        assert README_PATH.exists(), "app/security/README.md must exist"

    def test_readme_documents_all_sec_ids(self):
        content = README_PATH.read_text(encoding="utf-8")
        for sec_id in ("SEC-001", "SEC-002", "SEC-003", "SEC-004", "SEC-005"):
            assert sec_id in content, f"README must mention {sec_id}"

    def test_readme_documents_status_for_each_requirement(self):
        content = README_PATH.read_text(encoding="utf-8")
        # Each SEC id should be followed reasonably closely by a status
        # marker (Deferred / Satisfied), demonstrating an explicit status.
        for sec_id in ("SEC-001", "SEC-002", "SEC-003", "SEC-004", "SEC-005"):
            idx = content.index(sec_id)
            window = content[idx: idx + 400]
            assert re.search(r"\*\*Status:\*\*\s*(Deferred|Satisfied)", window), (
                f"Expected an explicit Deferred/Satisfied status near {sec_id}"
            )

    def test_readme_states_auth_and_rbac_deferred_with_mitigations(self):
        content = README_PATH.read_text(encoding="utf-8").lower()
        assert "deferred" in content
        assert "single-user" in content
        assert "network isolation" in content
        assert "backup" in content

    def test_readme_states_tls_handled_by_deployment(self):
        content = README_PATH.read_text(encoding="utf-8").lower()
        assert "tls" in content
        assert "reverse proxy" in content or "platform" in content
        assert "not by application code" in content or "not application code" in content or "not terminate tls" in content

    def test_readme_states_encryption_at_rest_handled_by_postgresql(self):
        content = README_PATH.read_text(encoding="utf-8").lower()
        assert "encryption at rest" in content
        assert "postgresql" in content

    def test_readme_states_input_sanitization_in_recipe_service(self):
        content = README_PATH.read_text(encoding="utf-8")
        assert "RecipeService" in content
        assert "autoescap" in content.lower()
        assert "parameterized" in content.lower()

    def test_readme_directory_has_no_python_source_modules(self):
        """This directory should contain documentation/tests only — no
        importable application modules implementing auth/authz."""
        py_files = sorted(p.name for p in THIS_DIR.glob("*.py"))
        for name in py_files:
            assert name.startswith("test_"), (
                f"Unexpected non-test Python module in app/security: {name}. "
                "This directory must contain only documentation and tests, "
                "per the approved single-user scope."
            )


# ---------------------------------------------------------------------------
# 2. No authentication middleware / dependency wired into the FastAPI app
# ---------------------------------------------------------------------------


class TestNoAuthenticationWired:
    FORBIDDEN_IMPORT_MODULES = {
        "fastapi.security",
        "fastapi_login",
        "fastapi_users",
        "authlib",
        "python_jose",
        "jose",
        "passlib",
        "itsdangerous",
    }

    FORBIDDEN_CALL_NAMES = {
        "OAuth2PasswordBearer",
        "OAuth2PasswordRequestForm",
        "HTTPBasic",
        "HTTPBearer",
        "APIKeyHeader",
        "APIKeyQuery",
        "APIKeyCookie",
    }

    def _iter_app_python_files(self):
        excluded_dir_names = {"__pycache__"}
        for path in APP_DIR.rglob("*.py"):
            if any(part in excluded_dir_names for part in path.parts):
                continue
            # Exclude this test file's own module from the scan of "app
            # source" so mentioning forbidden names in documentation/tests
            # doesn't false-positive.
            if path.name.startswith("test_"):
                continue
            yield path

    def test_no_forbidden_auth_imports_in_app(self):
        for path in self._iter_app_python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_module = alias.name.split(".")[0]
                        full_dotted = alias.name
                        assert full_dotted not in self.FORBIDDEN_IMPORT_MODULES, (
                            f"{path} imports forbidden auth module {full_dotted}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert node.module not in self.FORBIDDEN_IMPORT_MODULES, (
                            f"{path} imports from forbidden auth module {node.module}"
                        )

    def test_no_forbidden_auth_dependency_usage_in_app(self):
        for path in self._iter_app_python_files():
            source = path.read_text(encoding="utf-8")
            for forbidden in self.FORBIDDEN_CALL_NAMES:
                assert forbidden not in source, (
                    f"{path} references forbidden auth construct {forbidden!r}; "
                    "authentication is out of scope for this application."
                )

    def test_no_middleware_named_auth_in_main_entrypoint(self):
        main_path = APP_DIR / "main.py"
        if not main_path.exists():
            pytest.skip("app/main.py not present in this checkout")
        source = main_path.read_text(encoding="utf-8").lower()
        assert "authmiddleware" not in source
        assert "add_middleware(authenticationmiddleware" not in source.replace(" ", "")


# ---------------------------------------------------------------------------
# 3. RecipeService strips control chars and uses parameterized queries only
# ---------------------------------------------------------------------------


class TestRecipeServiceSanitization:
    @property
    def _service_path(self) -> Path:
        return APP_DIR / "services" / "recipe_service.py"

    def test_recipe_service_module_exists(self):
        if not self._service_path.exists():
            pytest.skip(
                "app/services/recipe_service.py not present in this checkout; "
                "cannot verify SEC-005 implementation directly."
            )

    def test_recipe_service_strips_control_characters(self):
        path = self._service_path
        if not path.exists():
            pytest.skip("recipe_service.py not present")
        source = path.read_text(encoding="utf-8")
        # Look for evidence of control-character stripping: a regex targeting
        # control character ranges, or explicit use of a stripping helper.
        control_char_pattern_hits = re.search(
            r"\\x00-\\x1f|\\x7f|control", source, re.IGNORECASE
        )
        assert control_char_pattern_hits, (
            "Expected RecipeService to reference control-character stripping "
            "(e.g. a regex over \\x00-\\x1f/\\x7f or a named control-char helper)."
        )

    def test_recipe_service_has_no_raw_sql_string_formatting(self):
        path = self._service_path
        if not path.exists():
            pytest.skip("recipe_service.py not present")
        source = path.read_text(encoding="utf-8")

        forbidden_patterns = [
            r"\.execute\s*\(\s*f[\"']",     # f-string passed to .execute(
            r"\.execute\s*\(\s*[\"'].*%s",   # % formatted SQL string
            r"text\(\s*f[\"']",              # sqlalchemy.text() with f-string
            r"SELECT\s+.*\+\s*",             # naive string concatenation of SQL
        ]
        for pattern in forbidden_patterns:
            assert not re.search(pattern, source, re.IGNORECASE), (
                f"Found evidence of non-parameterized SQL matching {pattern!r} "
                f"in {path}"
            )

    def test_recipe_service_uses_orm_session_api(self):
        path = self._service_path
        if not path.exists():
            pytest.skip("recipe_service.py not present")
        source = path.read_text(encoding="utf-8")
        # Expect ORM-style, parameterized access via the shared Session API.
        assert "db.query(" in source or "db.add(" in source or "self.db" in source, (
            "Expected RecipeService to use the injected SQLAlchemy Session "
            "(ORM query API) rather than raw SQL."
        )


# ---------------------------------------------------------------------------
# 4. Jinja2 autoescaping enabled wherever templates are configured
# ---------------------------------------------------------------------------


class TestJinjaAutoescape:
    def test_jinja_autoescape_enabled_somewhere_in_web_layer(self):
        web_dir = APP_DIR / "web"
        if not web_dir.exists():
            pytest.skip("app/web not present in this checkout")

        candidates = list(web_dir.rglob("*.py"))
        if not candidates:
            pytest.skip("no python files under app/web to inspect")

        found_jinja_usage = False
        found_autoescape_true = False

        for path in candidates:
            source = path.read_text(encoding="utf-8")
            if "Jinja2Templates" in source or "Environment(" in source or "select_autoescape" in source:
                found_jinja_usage = True
            if re.search(r"autoescape\s*=\s*True", source):
                found_autoescape_true = True
            if "select_autoescape" in source:
                found_autoescape_true = True
            if "Jinja2Templates" in source:
                # Starlette's Jinja2Templates enables autoescape by default
                # for .html/.xml templates; treat its use as satisfying the
                # requirement unless explicitly disabled.
                if not re.search(r"autoescape\s*=\s*False", source):
                    found_autoescape_true = True

        if not found_jinja_usage:
            pytest.skip(
                "No Jinja2 configuration found under app/web; templating "
                "may be owned by a component not present in this checkout."
            )

        assert found_autoescape_true, (
            "Expected Jinja2 template configuration in app/web to enable "
            "autoescaping (autoescape=True, select_autoescape(...), or "
            "Starlette's Jinja2Templates default) to mitigate XSS."
        )


# ---------------------------------------------------------------------------
# 5. No plaintext secrets committed to the repository
# ---------------------------------------------------------------------------


class TestNoPlaintextSecrets:
    SECRET_PATTERNS = [
        re.compile(r"AKIA[0-9A-Z]{16}"),                                  # AWS access key id
        re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----"),  # private key material
        re.compile(r"(?i)postgres(?:ql)?:\/\/[^:\s\"']+:[^@\s\"']+@"),     # creds in DB URL
        re.compile(r"(?i)\b(password|secret|api_key|apikey|token)\s*=\s*[\"'][^\"'\s]{6,}[\"']"),
    ]

    # Lines containing these markers are recognized as safe placeholders /
    # documentation examples rather than committed secrets.
    SAFE_MARKERS = (
        "example",
        "changeme",
        "your_password",
        "your-password",
        "<password>",
        "os.environ",
        "os.getenv",
        "getenv(",
        "settings.",
        "placeholder",
        "dummy",
        "test",
        "fake",
    )

    def test_no_hardcoded_secrets_in_repository_text_files(self):
        offending: list[str] = []
        for path in _repo_text_files_for_secret_scan():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                lowered = line.lower()
                if any(marker in lowered for marker in self.SAFE_MARKERS):
                    continue
                for pattern in self.SECRET_PATTERNS:
                    if pattern.search(line):
                        offending.append(f"{path}:{lineno}: {line.strip()[:120]}")

        assert not offending, (
            "Potential plaintext secret(s) found committed to the repository:\n"
            + "\n".join(offending)
        )

    def test_no_env_files_with_real_looking_values_committed(self):
        for env_path in REPO_ROOT.rglob(".env"):
            if any(part in {".git", ".venv", "venv", "node_modules"} for part in env_path.parts):
                continue
            text = env_path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if "=" not in line or line.strip().startswith("#"):
                    continue
                key, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                if not value:
                    continue
                assert value.lower() in {"changeme", "example", "placeholder"} or len(value) < 4, (
                    f"Committed .env file {env_path} appears to contain a real "
                    f"secret value for key {key.strip()!r}; secrets must never "
                    "be committed to the repository."
                )
