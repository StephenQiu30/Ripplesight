from __future__ import annotations

import re
from decimal import Decimal
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, StrictInt, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai.capability_schemas import AI_CAPABILITIES, AiModelServerSpec

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _BACKEND_ROOT.parent
BROWSER_EXECUTION_TIMEOUT_MAX_SECONDS = 45
BROWSER_CLOSE_TIMEOUT_SECONDS = 5
BROWSER_CLOSE_STEP_COUNT = 3
JOB_PROCESS_STARTUP_TIMEOUT_SECONDS = 3
JOB_PROCESS_HANDLER_SETUP_MARGIN_SECONDS = 5
JOB_PROCESS_TERMINATE_GRACE_SECONDS = 2
JOB_COMPLETION_MARGIN_SECONDS = 5
KAFKA_POLL_SAFETY_MARGIN_SECONDS = 5


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPOSITORY_ROOT / ".env",
        env_ignore_empty=True,
        env_prefix="HOTKEY_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "Ripplesight"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"

    workspace_document_tool_root: Path | None = None
    workspace_document_source_root: Path | None = None
    workspace_document_snapshot_root: Path | None = None
    workspace_document_read_user_ids: tuple[UUID, ...] = ()
    workspace_document_write_user_ids: tuple[UUID, ...] = ()
    workspace_document_publish_user_ids: tuple[UUID, ...] = ()

    web_origin: str = "http://127.0.0.1:8666"
    session_ttl_seconds: int = Field(default=43_200, ge=300, le=43_200)
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None
    auth_smtp_host: str | None = None
    auth_smtp_port: int = Field(default=587, ge=1, le=65535)
    auth_smtp_tls: Literal["starttls", "ssl"] = "starttls"
    auth_smtp_username: SecretStr | None = None
    auth_smtp_password: SecretStr | None = None
    auth_smtp_from_email: str | None = None
    email_code_hmac_key: SecretStr | None = None
    public_contact_owner_id: UUID | None = None
    public_publication_owner_id: UUID | None = None
    public_publication_categories: tuple[
        Literal["ai-models", "ai-products", "industry", "paper", "tip", "opinion"], ...
    ] = ()

    @field_validator("public_publication_categories")
    @classmethod
    def normalize_public_categories(cls, value: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(sorted(set(value)))

    @field_validator(
        "github_client_id",
        "github_client_secret",
        "auth_smtp_host",
        "auth_smtp_username",
        "auth_smtp_password",
        "auth_smtp_from_email",
        "email_code_hmac_key",
        "public_contact_owner_id",
        "public_publication_owner_id",
        mode="before",
    )
    @classmethod
    def normalize_optional_identity_setting(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("web_origin")
    @classmethod
    def validate_web_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("web origin must be a fixed HTTP(S) origin")
        return value.rstrip("/")

    @field_validator("email_code_hmac_key")
    @classmethod
    def validate_email_code_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode()) < 32:
            raise ValueError("email verification HMAC key requires at least 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_identity_configuration(self) -> Settings:
        if self.environment in {"staging", "production"} and not self.web_origin.startswith(
            "https://"
        ):
            raise ValueError("production web origin requires HTTPS")
        github = (self.github_client_id, self.github_client_secret)
        if any(github) and not all(github):
            raise ValueError("GitHub client configuration must be complete")
        smtp = (self.auth_smtp_host, self.auth_smtp_from_email, self.email_code_hmac_key)
        if any(smtp) and not all(smtp):
            raise ValueError("authentication email configuration must be complete")
        if bool(self.auth_smtp_username) != bool(self.auth_smtp_password):
            raise ValueError("authentication SMTP credentials must be paired")
        for value in (self.auth_smtp_host, self.auth_smtp_from_email):
            if value and any(character in value for character in "\r\n"):
                raise ValueError("authentication email configuration contains invalid characters")
        return self

    database_url: SecretStr
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=10, gt=0, le=60)

    source_credentials: dict[Literal["x", "douyin"], SecretStr] = Field(
        default_factory=dict, repr=False
    )

    @field_validator("source_credentials")
    @classmethod
    def validate_source_credentials(
        cls, value: dict[Literal["x", "douyin"], SecretStr]
    ) -> dict[Literal["x", "douyin"], SecretStr]:
        if any(not 32 <= len(secret.get_secret_value()) <= 65_536 for secret in value.values()):
            raise ValueError("source credentials must contain 32 to 65536 characters")
        return value

    redis_url: str = "redis://127.0.0.1:6379/0"
    kafka_bootstrap_servers: str = "127.0.0.1:9092"
    kafka_group_id: str = "hotkey-worker"
    kafka_delivery_timeout_seconds: int = Field(default=10, ge=1, le=60)
    kafka_max_poll_interval_seconds: int = Field(default=120, ge=30, le=43_200)

    job_lease_seconds: int = Field(default=75, ge=5, le=300)
    job_max_catchup_windows: int = Field(default=3, ge=1, le=100)

    firecrawl_enabled: bool = False
    firecrawl_base_url: str = "http://127.0.0.1:3002"
    firecrawl_timeout_seconds: int = Field(default=20, ge=1, le=20)
    firecrawl_max_response_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=2 * 1024 * 1024)

    browser_enabled: bool = False
    browser_ws_url: SecretStr = SecretStr("")
    browser_connect_timeout_seconds: int = Field(default=5, ge=1, le=10)
    browser_execution_timeout_seconds: int = Field(
        default=BROWSER_EXECUTION_TIMEOUT_MAX_SECONDS,
        ge=1,
        le=BROWSER_EXECUTION_TIMEOUT_MAX_SECONDS,
    )
    browser_state_dir: Path | None = None

    bilibili_chrome_owner_id: UUID | None = None
    bilibili_chrome_identity_env: Path = (
        Path.home() / "Library/Application Support/Framefetch/identity.env"
    )

    @field_validator("bilibili_chrome_owner_id", mode="before")
    @classmethod
    def empty_chrome_owner_is_unconfigured(cls, value: object) -> object:
        return None if value == "" else value

    mediacrawler_enabled: bool = False
    mediacrawler_dir: Path = Path("~/Desktop/StephenQiu/MediaCrawler")
    mediacrawler_output_dir: Path = _BACKEND_ROOT / "tmp" / "mediacrawler"
    mediacrawler_timeout_seconds: int = Field(default=220, ge=30, le=220)

    @field_validator("mediacrawler_dir", "mediacrawler_output_dir")
    @classmethod
    def expand_mediacrawler_path(cls, value: Path) -> Path:
        return value.expanduser()

    minio_endpoint: str = "127.0.0.1:9000"
    minio_secure: bool = False
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "hotkey-evidence"

    obsidian_vault_path: Path = Path("~/Desktop/Markdown/Obsidian")
    obsidian_root: str = "HotKey"
    obsidian_enabled: bool = False

    feishu_webhook_url: SecretStr | None = None
    feishu_secret: SecretStr | None = None
    web_base_url: str = "http://127.0.0.1:8666"
    notifications_enabled: bool = False
    notification_smtp_enabled: bool = False
    notification_smtp_host: str | None = None
    notification_smtp_port: int = Field(default=587, ge=1, le=65535)
    notification_smtp_tls: Literal["starttls", "ssl"] = "starttls"
    notification_smtp_username: SecretStr | None = None
    notification_smtp_password: SecretStr | None = None
    notification_smtp_from_email: str | None = None
    notification_smtp_timeout_seconds: int = Field(default=10, ge=1, le=10)

    @field_validator("notification_smtp_host")
    @classmethod
    def validate_smtp_host(cls, value: str | None) -> str | None:
        if value is not None and (
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", value)
            or ".." in value
        ):
            raise ValueError("SMTP host must be an explicit server hostname")
        return value

    @field_validator("notification_smtp_from_email")
    @classmethod
    def validate_smtp_from_email(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) > 254 or re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", value) is None
        ):
            raise ValueError("SMTP sender must be one bounded mailbox")
        return value

    operator_token: SecretStr | None = None
    feedback_hmac_secret: SecretStr | None = None
    editorial_external_tokens: dict[UUID, SecretStr] = Field(
        default_factory=dict, repr=False, exclude=True
    )
    editorial_ingress_hmac_secret: SecretStr | None = Field(default=None, repr=False, exclude=True)

    @field_validator("editorial_ingress_hmac_secret", mode="before")
    @classmethod
    def empty_ingress_secret(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("editorial_ingress_hmac_secret")
    @classmethod
    def validate_ingress_hmac_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            cls.validate_editorial_external_tokens({UUID(int=0): value})
        return value

    @field_validator("editorial_external_tokens")
    @classmethod
    def validate_editorial_external_tokens(
        cls, value: dict[UUID, SecretStr]
    ) -> dict[UUID, SecretStr]:
        for secret in value.values():
            token = secret.get_secret_value()
            lowered = token.lower().replace("_", "-")
            if (
                not 32 <= len(token) <= 512
                or any(character.isspace() for character in token)
                or len(set(token)) < 8
                or any(
                    word in lowered
                    for word in ("change-me", "changeme", "your-token", "replace-me")
                )
            ):
                raise ValueError("external ingress token must be a bounded non-placeholder secret")
        return value

    publication_indexing_enabled: bool = False
    indexnow_enabled: bool = False
    indexnow_external_requests_enabled: bool = False
    indexnow_key: SecretStr | None = None

    @field_validator("indexnow_key")
    @classmethod
    def validate_indexnow_key(cls, value: SecretStr | None) -> SecretStr | None:
        if (
            value is not None
            and re.fullmatch(r"[a-zA-Z0-9-]{8,128}", value.get_secret_value()) is None
        ):
            raise ValueError("IndexNow key requires 8 to 128 permitted characters")
        return value

    @model_validator(mode="after")
    def validate_indexnow_configuration(self) -> Settings:
        if self.indexnow_external_requests_enabled:
            host = urlsplit(self.web_base_url)
            private_address = False
            if host.hostname:
                try:
                    private_address = not ip_address(host.hostname).is_global
                except ValueError:
                    private_address = host.hostname.endswith((".localhost", ".local", ".internal"))
            if (
                not self.indexnow_enabled
                or not self.publication_indexing_enabled
                or self.indexnow_key is None
                or host.scheme != "https"
                or host.hostname in {None, "localhost", "127.0.0.1", "::1"}
                or host.path not in {"", "/"}
                or private_address
                or host.port not in {None, 443}
                or host.username
                or host.password
                or host.query
                or host.fragment
            ):
                raise ValueError(
                    "IndexNow external submission requires an indexable public HTTPS root"
                )
        return self

    publication_updates_enabled: bool = True
    source_icons_enabled: bool = False
    source_icons_external_requests_enabled: bool = False
    embeddings_enabled: bool = False
    embedding_model: str = Field(default="text-embedding-3-small", min_length=1, max_length=128)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: SecretStr | None = None
    embedding_dimensions: int = Field(default=0, ge=0, le=3072)
    embedding_timeout_seconds: int = Field(default=30, ge=1, le=60)
    embedding_currency: Literal["USD", "CNY"] | None = None
    embedding_input_rate_micros_per_million: Decimal | None = Field(
        default=None, ge=0, le=Decimal("1000000000000")
    )

    @field_validator("embedding_currency", "embedding_input_rate_micros_per_million", mode="before")
    @classmethod
    def empty_embedding_price_is_unknown(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_embedding_price(self) -> Settings:
        if (self.embedding_currency is None) != (
            self.embedding_input_rate_micros_per_million is None
        ):
            raise ValueError("embedding price requires its original currency and input rate")
        return self

    @field_validator("embedding_base_url")
    @classmethod
    def validate_embedding_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("embedding base URL must use HTTPS without credentials or query")
        try:
            address = ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("embedding base URL must not use a private IP")
        if parsed.hostname == "localhost" or parsed.hostname.endswith(
            (".localhost", ".local", ".internal")
        ):
            raise ValueError("embedding base URL must use a public host")
        return value.rstrip("/")

    media_mirror_enabled: bool = False
    media_mirror_allow_external_requests: bool = False
    media_mirror_image_max_bytes: int = Field(
        default=15 * 1024 * 1024, ge=1024, le=15 * 1024 * 1024
    )
    media_mirror_video_max_bytes: int = Field(
        default=64 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024
    )
    media_mirror_redirect_hosts: tuple[str, ...] = ()
    report_editions_enabled: bool = False
    operations_quiet_minutes: int = Field(default=360, ge=20, le=10080)
    operations_startup_grace_minutes: int = Field(default=20, ge=0, le=60)
    selectbench_enabled: bool = False
    codex_resets_enabled: bool = False
    editorial_sources_enabled: bool = False
    editorial_public_requests_enabled: bool = False
    editorial_x_authorized: bool = False
    editorial_mp_authorized: bool = False
    editorial_jina_authorized: bool = False
    editorial_x_token: SecretStr | None = None
    editorial_mp_key: SecretStr | None = None
    editorial_jina_key: SecretStr | None = None
    editorial_x_post_unit_usd_micros: int | None = Field(default=None, gt=0)
    editorial_paid_caps_cny_micros: dict[str, StrictInt] = Field(default_factory=dict)
    editorial_jina_cny_per_million_tokens: Decimal | None = Field(default=None, gt=0)

    @field_validator("editorial_paid_caps_cny_micros")
    @classmethod
    def validate_editorial_paid_caps(cls, value: dict[str, int]) -> dict[str, int]:
        if not set(value).issubset({"mp_history", "mp_article", "jina_listing"}) or any(
            isinstance(cap, bool) or not 1 <= cap <= 10**12 for cap in value.values()
        ):
            raise ValueError("editorial request costs require positive bounded approved caps")
        return value

    operations_maintenance_enabled: bool = False
    operations_backup_directory: Path | None = None
    operations_restore_database_url: SecretStr | None = None
    feedback_forward_enabled: bool = False
    operations_alerts_enabled: bool = False
    operations_webhook_url: SecretStr | None = None
    leaderboard_enabled: bool = False
    leaderboard_external_requests_enabled: bool = False
    leaderboard_artificial_analysis_api_key: SecretStr | None = None
    leaderboard_github_token: SecretStr | None = None
    leaderboard_max_requests_per_source: int = Field(default=1000, ge=1, le=1000)
    leaderboard_max_seconds_per_source: int = Field(default=600, ge=1, le=600)
    leaderboard_solver_seconds: int = Field(default=300, ge=1, le=300)

    @field_validator("operations_backup_directory")
    @classmethod
    def validate_operations_backup_directory(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        expanded = value.expanduser()
        if not expanded.is_absolute() or expanded == Path("/"):
            raise ValueError("operations backup directory must be an absolute non-root path")
        return expanded

    @field_validator("operations_restore_database_url")
    @classmethod
    def validate_operations_restore_database_url(
        cls, value: SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        if value is None:
            return None
        parsed = urlsplit(value.get_secret_value())
        database_name = parsed.path.removeprefix("/")
        business_url = info.data.get("database_url")
        if (
            parsed.scheme not in {"postgresql", "postgresql+psycopg"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or not re.fullmatch(r"hotkey_restore_[a-z0-9_]{1,48}", database_name)
            or parsed.query
            or parsed.fragment
            or (business_url is not None and value == business_url)
        ):
            raise ValueError(
                "restore verification requires a separate local hotkey_restore database"
            )
        if business_url is not None:
            business = urlsplit(business_url.get_secret_value())
            if (
                business.hostname in {"localhost", "127.0.0.1", "::1"}
                and (business.port or 5432) == (parsed.port or 5432)
                and business.path == parsed.path
            ):
                raise ValueError("restore verification cannot target the business database")
        return value

    @field_validator("web_base_url")
    @classmethod
    def validate_web_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid Web base URL")
        return value.rstrip("/")

    @field_validator("feishu_webhook_url", "operations_webhook_url")
    @classmethod
    def validate_feishu_webhook_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and value.get_secret_value():
            from notifications.feishu import validate_webhook_url

            validate_webhook_url(value.get_secret_value())
        return value

    @field_validator("obsidian_vault_path")
    @classmethod
    def expand_obsidian_vault_path(cls, value: Path) -> Path:
        return value.expanduser()

    @field_validator("obsidian_root")
    @classmethod
    def validate_obsidian_root(cls, value: str) -> str:
        if value in {"", ".", ".."} or not re.fullmatch(r"[^/\\\x00-\x1f\x7f]+", value):
            raise ValueError("Obsidian root must be a single safe directory name")
        return value

    collection_lookback_seconds: int = Field(default=86_400, ge=0, le=7 * 86_400)
    hotlist_interval_seconds: int = Field(default=1800, ge=600, le=86_400)

    @field_validator("ai_model_catalog")
    @classmethod
    def validate_ai_model_catalog(
        cls, value: dict[str, dict[str, Any]], info: ValidationInfo
    ) -> dict[str, dict[str, Any]]:
        if len(value) > 64 or any(
            re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key) is None for key in value
        ):
            raise ValueError("AI model catalog needs at most 64 bounded model keys")
        for key, spec in value.items():
            defaults = (
                {"reasoning_tokens": info.data.get("ai_reasoning_tokens", 0)}
                if key == "default"
                else {}
            )
            AiModelServerSpec.model_validate({**defaults, **spec})
        return value

    @field_validator("ai_capability_models")
    @classmethod
    def validate_ai_capability_models(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) - set(AI_CAPABILITIES) or any(
            re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", model) is None for model in value.values()
        ):
            raise ValueError("AI capability overrides must use registered capability/model keys")
        return value

    @property
    def ai_execution_timeout_seconds(self) -> int:
        return max(
            [self.ai_timeout_seconds]
            + [int(spec.get("timeout_seconds", 120)) for spec in self.ai_model_catalog.values()]
        )

    def job_process_execution_timeout_seconds(
        self, kind: str, source_key: str | None = None
    ) -> int:
        if kind in {"report.export", "content.export"}:
            return 120
        if kind == "source.hotlist":
            return 60
        if kind in {"keyword.search", "source.comments"}:
            return 240 if self.mediacrawler_enabled and source_key == "bilibili" else 90
        if kind in {
            "analysis.annotate",
            "events.cluster",
            "events.digest",
            "report.daily",
            "report.weekly",
            "report.edition",
        }:
            return max(600, self.ai_execution_timeout_seconds + 60)
        if kind in {
            "publication.republish",
            "publication.indexnow",
            "source.editorial.poll",
            "source.editorial.ingest",
            "source.editorial.x_group",
            "source.editorial.preview",
            "source.icons",
            "operations.maintenance",
        }:
            return 600
        if kind in {"events.heat", "notification.scan"}:
            return 300
        if kind in {"leaderboard.refresh", "publication.media_mirror"}:
            return 4200
        if kind == "monitor.codex_reset.tick":
            return 600 + 20 * self.ai_execution_timeout_seconds
        if kind == "analysis.editorial":
            vision_seconds = 120 if self.ai_vision_requests_enabled else 0
            return max(600, 5 * self.ai_execution_timeout_seconds + vision_seconds + 60)
        if kind == "analysis.selectbench":
            return 3 * self.ai_execution_timeout_seconds + 30
        if kind in {"events.consolidate", "events.signals"}:
            return 4 * self.ai_execution_timeout_seconds + 30
        if kind == "events.embed":
            return self.embedding_timeout_seconds + 30
        if kind == "analysis.translate":
            return max(600, 20 * self.ai_execution_timeout_seconds + 60)
        if kind in {"notification.send", "knowledge.export"}:
            return 60
        if kind != "webpage.collect":
            raise ValueError(f"unsupported job kind: {kind}")
        execution_seconds = self.firecrawl_timeout_seconds if self.firecrawl_enabled else 0
        if self.browser_enabled:
            browser_execution_seconds = (
                self.browser_execution_timeout_seconds
                + BROWSER_CLOSE_TIMEOUT_SECONDS * BROWSER_CLOSE_STEP_COUNT
            )
            execution_seconds = max(execution_seconds, browser_execution_seconds)
        return execution_seconds + JOB_PROCESS_HANDLER_SETUP_MARGIN_SECONDS

    @field_validator("firecrawl_base_url")
    @classmethod
    def validate_firecrawl_base_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as error:
            raise ValueError("invalid Firecrawl base URL") from error
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or port is None
        ):
            raise ValueError("invalid Firecrawl base URL")
        return value.removesuffix("/")

    @field_validator("browser_ws_url")
    @classmethod
    def validate_browser_ws_url(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        endpoint = value.get_secret_value()
        if not endpoint and not info.data.get("browser_enabled", False):
            return value
        try:
            parsed = urlsplit(endpoint)
            port = parsed.port
        except ValueError as error:
            raise ValueError("invalid browser WS URL") from error
        if (
            parsed.scheme not in {"ws", "wss"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or re.fullmatch(r"/ws/[0-9a-f]{48}", parsed.path) is None
            or parsed.query
            or parsed.fragment
            or port is None
        ):
            raise ValueError("invalid browser WS URL")
        return value

    @field_validator("browser_state_dir", mode="before")
    @classmethod
    def empty_browser_state_dir_is_unconfigured(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_execution_deadlines(self) -> Settings:
        required_lease_seconds = (
            JOB_PROCESS_STARTUP_TIMEOUT_SECONDS
            + max(
                self.job_process_execution_timeout_seconds("webpage.collect"),
                self.job_process_execution_timeout_seconds("source.hotlist"),
                self.job_process_execution_timeout_seconds("keyword.search", "bilibili")
                if self.mediacrawler_enabled
                else 0,
            )
            + JOB_PROCESS_TERMINATE_GRACE_SECONDS
            + JOB_COMPLETION_MARGIN_SECONDS
        )
        if self.mediacrawler_enabled and "job_lease_seconds" not in self.model_fields_set:
            self.job_lease_seconds = max(self.job_lease_seconds, required_lease_seconds)
        if self.job_lease_seconds < required_lease_seconds:
            raise ValueError(
                "job lease must include process startup, execution, termination, and completion"
            )
        longest_execution = max(
            600,
            self.job_process_execution_timeout_seconds("analysis.translate")
            if self.ai_enabled
            else 0,
            self.job_process_execution_timeout_seconds("analysis.editorial")
            if self.ai_enabled
            else 0,
            self.job_process_execution_timeout_seconds("leaderboard.refresh")
            if self.leaderboard_enabled or self.leaderboard_external_requests_enabled
            else 0,
            self.job_process_execution_timeout_seconds("monitor.codex_reset.tick")
            if self.codex_resets_enabled
            else 0,
            4200 if self.media_mirror_enabled or self.media_mirror_allow_external_requests else 0,
            self.job_process_execution_timeout_seconds("analysis.selectbench")
            if self.selectbench_enabled
            else 0,
            self.job_process_execution_timeout_seconds("events.consolidate")
            if self.ai_enabled and self.events_cluster_enabled
            else 0,
        )
        required_poll_seconds = max(
            self.job_lease_seconds + KAFKA_POLL_SAFETY_MARGIN_SECONDS,
            longest_execution
            + JOB_PROCESS_STARTUP_TIMEOUT_SECONDS
            + JOB_PROCESS_TERMINATE_GRACE_SECONDS
            + JOB_COMPLETION_MARGIN_SECONDS
            + KAFKA_POLL_SAFETY_MARGIN_SECONDS,
        )
        if "kafka_max_poll_interval_seconds" not in self.model_fields_set:
            self.kafka_max_poll_interval_seconds = max(
                self.kafka_max_poll_interval_seconds,
                required_poll_seconds,
            )
        if self.kafka_max_poll_interval_seconds < required_poll_seconds:
            raise ValueError(
                "Kafka max poll interval must cover the longest enabled job and margins"
            )
        return self

    ai_enabled: bool = False
    events_cluster_enabled: bool = False
    ai_model: str = "gpt-5.6-luna"
    ai_reasoning_tokens: StrictInt = Field(default=0, ge=0, le=28672)
    ai_model_catalog: dict[str, dict[str, Any]] = Field(
        default_factory=dict, exclude=True, repr=False
    )
    ai_capability_models: dict[str, str] = Field(default_factory=dict)
    ai_paid_requests_enabled: bool = False
    ai_openai_compatible_requests_enabled: bool = False
    ai_vision_requests_enabled: bool = False
    ai_command: str = "codex app-server"
    ai_timeout_seconds: int = Field(default=300, ge=1, le=900)
    ai_effort: str = "low"

    @field_validator("ai_reasoning_tokens", mode="before")
    @classmethod
    def parse_ai_reasoning_tokens(cls, value: object) -> object:
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
            return int(value)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
