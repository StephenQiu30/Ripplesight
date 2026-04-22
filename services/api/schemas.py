from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FeedbackSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str
    target_id: str
    feedback_type: str
    comment: str | None = None
