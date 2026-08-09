"""Unit tests for app.security.secrets."""

import pytest

from app.security.secrets import SecretsLoader, get_secrets_loader


@pytest.fixture(autouse=True)
def _clear_secrets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SECRETS_PROVIDER",
        "DATABASE_PASSWORD",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "AWS_SECRET_ID",
        "AWS_REGION",
    ):
        monkeypatch.delenv(var, raising=False)


def test_secrets_loader_retrieves_database_password_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Database password should be read from DATABASE_PASSWORD env var."""
    monkeypatch.setenv("DATABASE_PASSWORD", "super-secret-pw")
    loader = SecretsLoader()
    secret = loader.get_database_password()
    assert secret.password == "super-secret-pw"


def test_secrets_loader_retrieves_s3_credentials_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3 credentials should be read from their respective env vars."""
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "secret-key-value")
    loader = SecretsLoader()
    secret = loader.get_s3_credentials()
    assert secret.access_key_id == "AKIAEXAMPLE"
    assert secret.secret_access_key == "secret-key-value"


def test_secrets_loader_returns_none_when_not_configured() -> None:
    """Missing env vars should result in None values, not exceptions."""
    loader = SecretsLoader()
    db_secret = loader.get_database_password()
    s3_secret = loader.get_s3_credentials()
    assert db_secret.password is None
    assert s3_secret.access_key_id is None
    assert s3_secret.secret_access_key is None


def test_get_secrets_loader_factory_returns_loader_instance() -> None:
    """The factory function should return a usable SecretsLoader instance."""
    loader = get_secrets_loader()
    assert isinstance(loader, SecretsLoader)


def test_secrets_loader_generic_get_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generic get_secret should retrieve arbitrary env-backed secrets."""
    monkeypatch.setenv("CUSTOM_SECRET", "custom-value")
    loader = SecretsLoader()
    value = loader.get_secret("custom_secret", "CUSTOM_SECRET")
    assert value == "custom-value"
