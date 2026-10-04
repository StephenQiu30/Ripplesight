"""Pure schemas for the exact post/comment observations in one analysis prompt batch."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisObservationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["analysis-observations-v1"] = "analysis-observations-v1"
    post_observations: dict[UUID, UUID] = Field(min_length=1, max_length=30)
    comment_observations: dict[UUID, UUID] = Field(default_factory=dict, max_length=1530)
    input_observation_ids: tuple[UUID, ...] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def exact_distinct_inputs(self) -> Self:
        roots = {*self.post_observations.values(), *self.comment_observations.values()}
        if (
            set(self.post_observations).intersection(self.comment_observations)
            or len(roots) != len(self.post_observations) + len(self.comment_observations)
            or tuple(sorted(set(self.input_observation_ids), key=str)) != self.input_observation_ids
            or not roots.issubset(self.input_observation_ids)
        ):
            raise ValueError("analysis observations require distinct exact version references")
        return self

    @property
    def signature(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
