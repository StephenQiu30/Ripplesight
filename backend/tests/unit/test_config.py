import pytest
from pydantic import ValidationError

from core.config import Settings


def test_settings_use_hotkey_environment_prefix(monkeypatch) -> None:
    monkeypatch.setenv("HOTKEY_APP_NAME", "HotKey Test")

    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test")

    assert settings.app_name == "HotKey Test"


def test_source_credentials_are_server_only_and_source_allowlisted(monkeypatch) -> None:
    secret = "controlled-credential-not-a-real-secret"
    monkeypatch.setenv("HOTKEY_SOURCE_CREDENTIALS", '{"x":"' + secret + '"}')
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")
    assert settings.source_credentials["x"].get_secret_value() == secret
    assert secret not in repr(settings)
    assert secret not in settings.model_dump_json()
    monkeypatch.setenv("HOTKEY_SOURCE_CREDENTIALS", '{"unknown":"' + secret + '"}')
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")


def test_firecrawl_is_disabled_and_bounded_by_default(monkeypatch) -> None:
    monkeypatch.setenv("HOTKEY_FIRECRAWL_ENABLED", "true")
    monkeypatch.setenv("HOTKEY_FIRECRAWL_BASE_URL", "http://127.0.0.1:3002/")
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")
    assert settings.firecrawl_enabled
    assert settings.firecrawl_base_url == "http://127.0.0.1:3002"
    assert settings.firecrawl_timeout_seconds == 20
    assert settings.firecrawl_max_response_bytes == 2 * 1024 * 1024

    monkeypatch.setenv("HOTKEY_FIRECRAWL_BASE_URL", "http://user:secret@127.0.0.1:3002")
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")


def test_browser_runtime_is_disabled_and_uses_fixed_internal_endpoint(monkeypatch) -> None:
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")
    assert not settings.browser_enabled
    assert settings.browser_ws_url.get_secret_value() == ""
    assert settings.browser_connect_timeout_seconds == 5

    monkeypatch.setenv("HOTKEY_BROWSER_ENABLED", "true")
    monkeypatch.setenv("HOTKEY_BROWSER_WS_URL", "ws://browser:3000/")
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")

    monkeypatch.setenv("HOTKEY_BROWSER_WS_URL", "ws://browser:3000/ws/" + "a" * 48)
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")
    assert settings.browser_enabled
    assert settings.browser_ws_url.get_secret_value().endswith("a" * 48)
    assert "a" * 48 not in repr(settings)
    assert "a" * 48 not in settings.model_dump_json()

    monkeypatch.setenv("HOTKEY_BROWSER_WS_URL", "ws://user:password@browser:3000/")
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")


def test_browser_state_directory_is_optional(monkeypatch) -> None:
    monkeypatch.setenv("HOTKEY_BROWSER_STATE_DIR", "")
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")
    assert settings.browser_state_dir is None


def test_mediacrawler_defaults_fit_the_long_process_deadline() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        mediacrawler_enabled=True,
    )
    assert settings.job_lease_seconds == 250
    assert settings.kafka_max_poll_interval_seconds == 615


def test_mediacrawler_requires_a_long_enough_lease_and_poll_window() -> None:
    with pytest.raises(ValidationError, match="job lease"):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            mediacrawler_enabled=True,
            job_lease_seconds=249,
        )
    with pytest.raises(ValidationError, match="Kafka max poll interval"):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            mediacrawler_enabled=True,
            kafka_max_poll_interval_seconds=254,
        )
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        mediacrawler_enabled=True,
        job_lease_seconds=250,
        kafka_max_poll_interval_seconds=615,
    )
    assert settings.job_process_execution_timeout_seconds("keyword.search", "bilibili") == 240
    assert settings.job_process_execution_timeout_seconds("source.comments", "bilibili") == 240
    assert settings.job_process_execution_timeout_seconds("keyword.search", "hackernews") == 90
    assert settings.job_process_execution_timeout_seconds("source.comments", "hackernews") == 90


def test_disabled_mediacrawler_keeps_existing_lease_and_source_deadlines() -> None:
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")
    assert settings.job_lease_seconds == 75
    assert settings.kafka_max_poll_interval_seconds == 615
    assert settings.job_process_execution_timeout_seconds("keyword.search", "bilibili") == 90
    with pytest.raises(ValidationError, match="job lease"):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            job_lease_seconds=69,
        )


def test_browser_deadline_fits_job_lease_and_kafka_poll_window() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        browser_enabled=True,
        browser_ws_url="ws://browser:3000/ws/" + "a" * 48,
    )

    assert settings.browser_execution_timeout_seconds == 45
    assert settings.job_process_execution_timeout_seconds("webpage.collect") == 65
    assert settings.job_lease_seconds == 75
    assert settings.kafka_max_poll_interval_seconds == 615


def test_browser_deadline_cannot_exceed_job_lease_budget() -> None:
    with pytest.raises(ValidationError, match="job lease"):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            browser_enabled=True,
            browser_ws_url="ws://browser:3000/ws/" + "a" * 48,
            job_lease_seconds=74,
        )


def test_job_lease_must_leave_kafka_poll_margin() -> None:
    with pytest.raises(ValidationError, match="Kafka max poll interval"):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            job_lease_seconds=75,
            kafka_max_poll_interval_seconds=79,
        )


def test_disabled_webpage_runtimes_still_reserve_hotlist_deadline_budget() -> None:
    with pytest.raises(ValidationError, match="job lease"):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            firecrawl_enabled=False,
            browser_enabled=False,
            job_lease_seconds=15,
            kafka_max_poll_interval_seconds=30,
        )
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        firecrawl_enabled=False,
        browser_enabled=False,
        job_lease_seconds=70,
    )

    assert not settings.browser_enabled
    assert settings.job_process_execution_timeout_seconds("webpage.collect") == 5
    assert settings.job_process_execution_timeout_seconds("source.hotlist") == 60


def test_firecrawl_timeout_includes_process_and_finalization_margins() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        firecrawl_enabled=True,
        job_lease_seconds=70,
    )

    assert settings.job_process_execution_timeout_seconds("webpage.collect") == 25
    with pytest.raises(ValidationError, match="job lease"):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            firecrawl_enabled=True,
            job_lease_seconds=69,
        )


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("keyword.search", 90),
        ("source.comments", 90),
        ("source.hotlist", 60),
        ("analysis.annotate", 600),
        ("report.daily", 600),
        ("report.weekly", 600),
        ("notification.send", 60),
        ("knowledge.export", 60),
    ],
)
def test_job_process_deadline_depends_on_job_kind(kind: str, expected: int) -> None:
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")

    assert settings.job_process_execution_timeout_seconds(kind) == expected


def test_unknown_job_kind_has_no_implicit_process_deadline() -> None:
    settings = Settings(database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test")

    with pytest.raises(ValueError, match="unsupported job kind"):
        settings.job_process_execution_timeout_seconds("unknown.task")


def test_migrated_jobs_keep_explicit_bounded_execution_deadlines() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        ai_timeout_seconds=25,
        embedding_timeout_seconds=12,
    )
    assert settings.job_process_execution_timeout_seconds("events.consolidate") == 130
    assert settings.job_process_execution_timeout_seconds("events.embed") == 42
    assert settings.job_process_execution_timeout_seconds("source.icons") == 600
    assert not settings.embeddings_enabled and not settings.source_icons_enabled


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",
        "https://127.0.0.1/v1",
        "https://[::1]/v1",
        "https://localhost/v1",
        "https://models.internal/v1",
        "https://user:secret@api.example.com/v1",
        "https://api.example.com/v1?key=secret",
    ],
)
def test_embedding_endpoint_rejects_private_and_credential_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            embedding_base_url=url,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"indexnow_key": "short"},
        {"indexnow_key": "x" * 129},
        {"indexnow_key": "not/a/key"},
        {"web_base_url": "http://example.com"},
        {"web_base_url": "https://127.0.0.1"},
        {"web_base_url": "https://site.internal"},
        {"web_base_url": "https://example.com/subpath"},
    ],
)
def test_indexnow_external_submission_requires_a_public_root_and_valid_key(
    overrides: dict[str, str],
) -> None:
    values = {
        "indexnow_enabled": True,
        "indexnow_external_requests_enabled": True,
        "publication_indexing_enabled": True,
        "indexnow_key": "controlled-public-proof-key",
        "web_base_url": "https://example.com",
        **overrides,
    }
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            **values,
        )


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [("ai_enabled", 6075), ("leaderboard_enabled", 4215)],
)
def test_long_business_jobs_require_a_real_kafka_poll_window(enabled: str, expected: int) -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        **{enabled: True},
    )
    assert settings.kafka_max_poll_interval_seconds == expected
    with pytest.raises(ValidationError, match="Kafka max poll interval"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            kafka_max_poll_interval_seconds=expected - 1,
            **{enabled: True},
        )


@pytest.mark.parametrize("cap", [True, "100", 0, -1, 10**12 + 1])
def test_paid_caps_require_explicit_integer_prices(cap) -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            editorial_paid_caps_cny_micros={"jina_listing": cap},
        )


def test_restore_cannot_target_business_database_using_another_loopback_alias() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://test:test@localhost:5432/hotkey_restore_same",
            operations_restore_database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_restore_same",
        )


def test_media_long_job_extends_derived_kafka_window_and_rejects_explicit_short_window() -> None:
    url = "postgresql+psycopg://test:test@127.0.0.1/hotkey_test"
    settings = Settings(database_url=url, media_mirror_enabled=True)
    assert settings.job_process_execution_timeout_seconds("publication.media_mirror") == 4200
    assert settings.kafka_max_poll_interval_seconds >= 4215
    with pytest.raises(ValidationError):
        Settings(database_url=url, media_mirror_enabled=True, kafka_max_poll_interval_seconds=615)


def test_capability_catalog_extends_actual_execution_deadline_without_exposing_secrets() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        ai_enabled=True,
        ai_model_catalog={
            "reasoner": {
                "transport": "openai_compatible",
                "provider_key": "controlled",
                "model": "reasoner",
                "base_url": "https://models.example.com/v1",
                "api_key": "controlled-private-key",
                "timeout_seconds": 600,
            }
        },
        ai_capability_models={"groupReview": "reasoner"},
    )
    assert settings.ai_execution_timeout_seconds == 600
    assert settings.job_process_execution_timeout_seconds("events.signals") == 2430
    assert settings.job_process_execution_timeout_seconds("analysis.translate") == 12060
    assert settings.kafka_max_poll_interval_seconds == 12075
    assert "controlled-private-key" not in repr(settings)
    assert "controlled-private-key" not in settings.model_dump_json()


@pytest.mark.parametrize(
    "spec",
    [
        {"timeout_seconds": 601},
        {"base_url": "https://user:private@models.example.com/v1"},
        {"extra": {"headers": {"Authorization": "private"}}},
        {"currency": "CNY"},
    ],
)
def test_capability_catalog_rejects_unbounded_or_ambiguous_provider_configuration(spec) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            ai_model_catalog={
                "candidate": {
                    "transport": "openai_compatible",
                    "provider_key": "controlled",
                    "model": "candidate",
                    **spec,
                }
            },
        )


@pytest.mark.parametrize(
    "price",
    [
        {"embedding_currency": "USD"},
        {"embedding_input_rate_micros_per_million": 1},
        {"embedding_currency": "CNY", "embedding_input_rate_micros_per_million": -1},
        {"embedding_currency": "USD", "embedding_input_rate_micros_per_million": "NaN"},
    ],
)
def test_embedding_requires_a_finite_rate_in_its_original_currency(price) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            **price,
        )


def test_unknown_embedding_price_and_explicit_free_price_are_distinct() -> None:
    common = {"_env_file": None, "database_url": "postgresql+psycopg://t:t@127.0.0.1/hotkey_test"}
    unknown = Settings(**common, embedding_currency="", embedding_input_rate_micros_per_million="")
    assert unknown.embedding_currency is None
    assert unknown.embedding_input_rate_micros_per_million is None
    free = Settings(**common, embedding_currency="USD", embedding_input_rate_micros_per_million=0)
    assert free.embedding_currency == "USD"
    assert free.embedding_input_rate_micros_per_million == 0


def test_approved_first_image_fetch_fits_the_editorial_process_deadline() -> None:
    common = {
        "_env_file": None,
        "database_url": "postgresql+psycopg://t:t@127.0.0.1/hotkey_test",
        "ai_enabled": True,
    }
    text = Settings(**common)
    vision = Settings(**common, ai_vision_requests_enabled=True)
    assert not text.ai_vision_requests_enabled
    assert vision.job_process_execution_timeout_seconds("analysis.editorial") == (
        text.job_process_execution_timeout_seconds("analysis.editorial") + 120
    )
    assert vision.kafka_max_poll_interval_seconds >= (
        vision.job_process_execution_timeout_seconds("analysis.editorial") + 15
    )


@pytest.mark.parametrize(
    "token", ["x", "a" * 31, "a" * 513, " " + "a" * 32, "change-me" * 8, "a" * 32]
)
def test_external_ingress_tokens_reject_weak_placeholder_and_secret_leaks(token: str) -> None:
    from uuid import uuid4

    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
            editorial_external_tokens={uuid4(): token},
        )


def test_external_ingress_token_is_server_only() -> None:
    from uuid import uuid4

    token = "controlled-external-token-valid-20261002-unique"
    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        editorial_external_tokens={uuid4(): token},
    )
    assert token not in repr(settings) and token not in settings.model_dump_json()
