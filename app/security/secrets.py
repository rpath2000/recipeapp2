"""
Secrets management utilities.

Loads sensitive configuration values (database password, S3 credentials,
etc.) from environment variables by default, with optional retrieval
from AWS Secrets Manager when configured.

Design goals:
- Never hardcode secrets in source code.
- Prefer environment variables (the application's standard config
  mechanism), matching the shared database configuration pattern used
  by `app.models.database` (DATABASE_URL).
- Support pulling structured secrets (JSON blobs) from AWS Secrets
  Manager when `SECRETS_PROVIDER=aws` is set, without adding a hard
  dependency: `boto3` is imported lazily only when needed.
- Never log secret values.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("app.security.secrets")

SECRETS_PROVIDER_ENV = "SECRETS_PROVIDER"
AWS_SECRET_ID_ENV = "AWS_SECRET_ID"
AWS_REGION_ENV = "AWS_REGION"


@dataclass(frozen=True)
class DatabaseSecret:
    """Database credential secret."""

    password: Optional[str]


@dataclass(frozen=True)
class S3Secret:
    """S3 access credential secret."""

    access_key_id: Optional[str]
    secret_access_key: Optional[str]


class SecretsLoadError(RuntimeError):
    """Raised when secrets cannot be loaded from the configured provider."""


class SecretsLoader:
    """
    Loads application secrets from environment variables or, when
    configured, AWS Secrets Manager.

    Provider selection is controlled by the `SECRETS_PROVIDER`
    environment variable:
      - "env" (default): read individual environment variables directly.
      - "aws": fetch a JSON secret blob from AWS Secrets Manager
        (identified by `AWS_SECRET_ID`) and read keys from it, falling
        back to environment variables for any missing keys.
    """

    def __init__(self) -> None:
        self._provider = os.environ.get(SECRETS_PROVIDER_ENV, "env").strip().lower()
        self._aws_secret_cache: Optional[dict] = None

    def _fetch_aws_secret_blob(self) -> dict:
        """
        Fetch and cache the JSON secret blob from AWS Secrets Manager.

        Lazily imports boto3 so this module remains importable in
        environments where boto3 is not installed and AWS is not used.
        """
        if self._aws_secret_cache is not None:
            return self._aws_secret_cache

        secret_id = os.environ.get(AWS_SECRET_ID_ENV)
        if not secret_id:
            raise SecretsLoadError(
                f"{AWS_SECRET_ID_ENV} must be set when {SECRETS_PROVIDER_ENV}=aws"
            )

        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise SecretsLoadError(
                "boto3 is required to load secrets from AWS Secrets Manager"
            ) from exc

        region = os.environ.get(AWS_REGION_ENV)
        client = boto3.client("secretsmanager", region_name=region)

        try:
            response = client.get_secret_value(SecretId=secret_id)
        except Exception as exc:  # noqa: BLE001 - surface as SecretsLoadError
            logger.error(
                "aws_secrets_fetch_failed",
                extra={"event": "aws_secrets_fetch_failed", "secret_id": secret_id},
            )
            raise SecretsLoadError(
                f"Failed to fetch secret '{secret_id}' from AWS Secrets Manager"
            ) from exc

        raw = response.get("SecretString") or ""
        try:
            blob = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise SecretsLoadError(
                f"Secret '{secret_id}' is not valid JSON"
            ) from exc

        self._aws_secret_cache = blob
        logger.info(
            "aws_secrets_fetch_succeeded",
            extra={"event": "aws_secrets_fetch_succeeded", "secret_id": secret_id},
        )
        return blob

    def _get_value(self, key: str, env_var: str) -> Optional[str]:
        """
        Resolve a single secret value by key, honoring the configured
        provider, falling back to the environment variable.
        """
        if self._provider == "aws":
            try:
                blob = self._fetch_aws_secret_blob()
            except SecretsLoadError:
                blob = {}
            value = blob.get(key)
            if value is not None:
                return str(value)

        return os.environ.get(env_var)

    def get_database_password(self) -> DatabaseSecret:
        """Load the database password secret."""
        password = self._get_value("database_password", "DATABASE_PASSWORD")
        logger.info(
            "secret_loaded",
            extra={"event": "secret_loaded", "secret_name": "database_password"},
        )
        return DatabaseSecret(password=password)

    def get_s3_credentials(self) -> S3Secret:
        """Load the S3 access credentials secret."""
        access_key_id = self._get_value("s3_access_key_id", "S3_ACCESS_KEY_ID")
        secret_access_key = self._get_value(
            "s3_secret_access_key", "S3_SECRET_ACCESS_KEY"
        )
        logger.info(
            "secret_loaded",
            extra={"event": "secret_loaded", "secret_name": "s3_credentials"},
        )
        return S3Secret(
            access_key_id=access_key_id, secret_access_key=secret_access_key
        )

    def get_secret(self, key: str, env_var: str) -> Optional[Any]:
        """
        Generic secret retrieval for ad-hoc secret keys not covered by
        the dedicated helper methods above.

        Args:
            key: The key name within the AWS Secrets Manager JSON blob.
            env_var: The environment variable name to fall back to (or
                use directly, when provider is "env").

        Returns:
            The secret value as a string, or None if not found.
        """
        value = self._get_value(key, env_var)
        logger.info(
            "secret_loaded", extra={"event": "secret_loaded", "secret_name": key}
        )
        return value


def get_secrets_loader() -> SecretsLoader:
    """Factory returning a fresh SecretsLoader instance."""
    return SecretsLoader()
