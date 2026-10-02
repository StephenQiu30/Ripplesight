from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from analysis.editorial_schemas import SourceKind, Tier
from events.fact_schemas import VerdictRelation
from events.relations import RelationReportInput


class SelectBenchCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    stratum: str | None = Field(default=None, max_length=128)
    gold: Literal["select", "reject", "either"]
    decision: Literal["select", "reject"] | None = None
    score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    relevance: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=2000)
    error_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if not self.case_id.strip() or not self.title.strip():
            raise ValueError("case identity and title cannot be blank")
        if (self.decision is None) != (self.error_code is not None):
            raise ValueError(
                "missing decision requires an explicit error, valid decision cannot have an error"
            )
        if self.decision is None and self.score is not None:
            raise ValueError("failed cases cannot carry a score")
        return self


class SelectBenchImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    label: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    prompt_version: str = Field(min_length=1, max_length=100)
    split: str | None = Field(default=None, max_length=64)
    seed: int | None = None
    models: dict[str, list[SelectBenchCaseInput]] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def require_identical_gold(self) -> Self:
        if not self.label.strip() or not self.reason.strip() or not self.prompt_version.strip():
            raise ValueError("report identity cannot be blank")
        expected = None
        total = 0
        for name, cases in self.models.items():
            if not name.strip() or len(name) > 200 or not 1 <= len(cases) <= 5000:
                raise ValueError("model report is outside limits")
            total += len(cases)
            actual = {case.case_id: (case.title, case.stratum, case.gold) for case in cases}
            if len(actual) != len(cases) or (expected is not None and actual != expected):
                raise ValueError("models must evaluate the same unique gold cases")
            expected = actual
        if total > 10000:
            raise ValueError("report exceeds 10000 model-case results")
        return self


class SelectBenchRunView(BaseModel):
    id: UUID
    operation_id: UUID
    label: str
    prompt_version: str
    split: str | None
    seed: int | None
    sample_size: int
    models: list[str]
    summary: dict[str, object]
    gold_fingerprint: str
    created_at: datetime
    replayed: bool = False
    kind: Literal["selection", "relation"] = "selection"


class SelectBenchCaseView(BaseModel):
    case_id: str
    title: str
    stratum: str | None
    gold: Literal["select", "reject", "either"]
    by_model: dict[str, SelectBenchCaseInput]


class SelectBenchCasesView(BaseModel):
    run: SelectBenchRunView
    items: list[SelectBenchCaseView]
    next_cursor: str | None
    strata: dict[str, int]


class SelectBenchGoldCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=100000)
    gold: Literal["select", "reject", "either"]
    stratum: str | None = Field(default=None, max_length=128)
    split: str | None = Field(default=None, max_length=64)
    source_name: str = Field(default="黄金集", min_length=1, max_length=200)
    source_kind: SourceKind = "rss"
    tier: Tier = "T2"
    first_party: bool = False
    published_at: datetime | None = None
    author: str | None = Field(default=None, max_length=300)
    url: str = Field(default="", max_length=2048)
    quoted_text: str = Field(default="", max_length=100000)
    quoted_author: str = Field(default="", max_length=300)

    @field_validator("published_at")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("gold publication time must have a timezone")
        return value


class SelectBenchGoldInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    label: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    models: list[str] = Field(min_length=1, max_length=5)
    cases: list[SelectBenchGoldCaseInput] = Field(min_length=1, max_length=5000)
    sample_size: int = Field(default=100, ge=1, le=100)
    split: str | None = Field(default=None, max_length=64)
    seed: int = 42

    @model_validator(mode="after")
    def validate_gold(self) -> Self:
        if not self.label.strip() or not self.reason.strip():
            raise ValueError("evaluation identity cannot be blank")
        if len(set(self.models)) != len(self.models) or any(
            not value.strip() or len(value) > 128 for value in self.models
        ):
            raise ValueError("model names must be unique and bounded")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("gold case identifiers must be unique")
        if not any(self.split is None or case.split == self.split for case in self.cases):
            raise ValueError("requested split contains no cases")
        if sum(len(case.body) + len(case.quoted_text) for case in self.cases) > 10000000:
            raise ValueError("gold material exceeds 10 million characters")
        return self


class SelectBenchAcceptedView(BaseModel):
    run: SelectBenchRunView
    job_ids: list[UUID]
    replayed: bool = False


class RelationGoldCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(min_length=1, max_length=200)
    a: RelationReportInput
    b: RelationReportInput
    gold_relation: VerdictRelation
    stratum: str | None = Field(default=None, max_length=128)
    split: str | None = Field(default=None, max_length=64)


class RelationPredictionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(min_length=1, max_length=200)
    relation: VerdictRelation | None = None
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    difference: str | None = Field(default=None, max_length=400)
    error_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")

    @model_validator(mode="after")
    def validate_prediction(self) -> Self:
        if self.relation is None:
            if not self.error_code or self.confidence is not None:
                raise ValueError("missing relation must preserve error")
        elif self.confidence is None or self.error_code is not None:
            raise ValueError("valid relation requires confidence without error")
        return self


class RelationBenchGoldInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    label: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    models: list[str] = Field(min_length=1, max_length=5)
    cases: list[RelationGoldCaseInput] = Field(min_length=1, max_length=5000)
    sample_size: int = Field(default=100, ge=1, le=100)
    split: str | None = Field(default=None, max_length=64)
    seed: int = 42

    @model_validator(mode="after")
    def validate_cases(self) -> Self:
        if not self.label.strip() or not self.reason.strip():
            raise ValueError("evaluation identity cannot be blank")
        if len(set(self.models)) != len(self.models) or any(
            not model.strip() or len(model) > 128 for model in self.models
        ):
            raise ValueError("invalid model names")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate case identity")
        if not any(self.split is None or case.split == self.split for case in self.cases):
            raise ValueError("requested split has no cases")
        return self


class RelationBenchImportInput(RelationBenchGoldInput):
    predictions: dict[str, list[RelationPredictionInput]] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def identical_cases(self) -> Self:
        if set(self.predictions) != set(self.models):
            raise ValueError("predictions must include every model")
        expected = {case.case_id for case in self.cases}
        for results in self.predictions.values():
            if len(results) != len(expected) or {case.case_id for case in results} != expected:
                raise ValueError("models must compare the same unique cases")
        return self


class RelationBenchCaseView(BaseModel):
    case: RelationGoldCaseInput
    by_model: dict[str, RelationPredictionInput]


class RelationBenchCasesView(BaseModel):
    run: SelectBenchRunView
    items: list[RelationBenchCaseView]
    next_cursor: str | None
    strata: dict[str, int]
