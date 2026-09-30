import pytest

from tests.conftest import validate_test_database_url


@pytest.mark.parametrize(
    "url",
    (
        "postgresql+psycopg://tester@127.0.0.1/hotkey_test_demo_20261001",
        "postgresql+psycopg://tester@localhost/hotkey_test_ci",
        "postgresql+psycopg://tester@[::1]/hotkey_test_local",
    ),
)
def test_database_guard_accepts_explicit_local_test_databases(url: str) -> None:
    validate_test_database_url(url)


@pytest.mark.parametrize(
    "url",
    (
        "postgresql+psycopg://tester@127.0.0.1/hotkey-server",
        "postgresql+psycopg://tester@127.0.0.1/hotkey_test",
        "postgresql+psycopg://tester@127.0.0.1/hotkey_test_",
        "postgresql+psycopg://tester@external.example/hotkey_test_ci",
        "postgresql+psycopg://tester@127.0.0.1/hotkey_test_ci?host=external.example",
        "postgresql+psycopg://tester@127.0.0.1/hotkey_test_ci?service=shared",
        "sqlite:///hotkey_test_ci",
    ),
)
def test_database_guard_rejects_shared_or_redirected_databases(url: str) -> None:
    with pytest.raises(ValueError):
        validate_test_database_url(url)
