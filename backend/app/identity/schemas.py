from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, SecretStr, field_validator

from core.schemas import InputModel, OutputModel


class IdentityCredentialsInput(InputModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class IdentityUserView(OutputModel):
    id: UUID
    username: str
    email: str | None


class IdentitySessionView(OutputModel):
    user: IdentityUserView
    expires_at: datetime


class LoginOptionsView(OutputModel):
    password: bool
    github: bool
    email: bool


class EmailCodeInput(InputModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        from email_validator import EmailNotValidError, validate_email

        try:
            return validate_email(value.strip(), check_deliverability=False).normalized.lower()
        except EmailNotValidError as error:
            raise ValueError("invalid email address") from error


class VerifyEmailCodeInput(InputModel):
    challenge_id: UUID
    code: str = Field(pattern=r"^[0-9]{6}$")


class EmailChallengeView(OutputModel):
    challenge_id: UUID
    expires_at: datetime
    resend_after_seconds: int


class GithubAuthorizationInput(InputModel):
    return_to: str = Field(default="/topics", max_length=2048)


class GithubAuthorizationView(OutputModel):
    authorization_url: str


class IdentityCredentialsUpdateInput(IdentityCredentialsInput):
    current_password: SecretStr | None = Field(default=None, max_length=128)
    challenge_id: UUID | None = None
    code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
