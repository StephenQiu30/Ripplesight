"""Explicit operator-owned policy for comparing public report samples."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class PublicNegativeSurgePolicy(BaseModel):
    """No business defaults: calibration must be supplied before enabling evaluation."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    policy_id: str = Field(strict=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    calibration_reference: SecretStr
    min_valid_samples: int = Field(strict=True, gt=0)
    min_analysis_coverage: Decimal = Field(gt=0, le=1, allow_inf_nan=False)
    min_sources: int = Field(strict=True, gt=0)
    min_negative_count: int = Field(strict=True, gt=0)
    min_negative_count_increase: int = Field(strict=True, gt=0)
    min_ratio_increase: Decimal = Field(gt=0, le=1, allow_inf_nan=False)

    @field_validator("min_analysis_coverage", "min_ratio_increase", mode="before")
    @classmethod
    def require_numeric_proportion(cls, value: object) -> Decimal:
        """Keep exact JSON decimals and reject string/bool coercion."""
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError("numeric proportion required")
        return value if isinstance(value, Decimal) else Decimal(str(value))

    @field_validator("calibration_reference", mode="before")
    @classmethod
    def require_calibration_reference(cls, value: object) -> object:
        """Reject empty/nontext references without publishing a server-local path."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("nonempty calibration reference required")
        return value.strip()
