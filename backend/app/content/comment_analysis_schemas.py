"""Pure frozen text and parent-chain contracts for independent comment analysis."""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CommentContextText(BaseModel):
    """One exact readable observation and its bounded immutable text."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    content_id: UUID
    content_version_id: UUID
    observation_id: UUID
    text: str = Field(min_length=1, max_length=1500)
    truncated: bool = False


class CommentAnalysisContext(BaseModel):
    """Actual post and direct-parent-first chain; missing context is never invented."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    post: CommentContextText
    target: CommentContextText
    parents: tuple[CommentContextText, ...] = Field(default=(), max_length=8)
    next_parent_id: UUID | None = None
    parent_state: Literal[
        "root", "complete", "missing", "unavailable", "unresolved", "cycle", "depth_limit"
    ]

    @model_validator(mode="after")
    def distinct_context(self) -> Self:
        """Reject repeated identities and contradictory root contexts."""
        items = (self.post, self.target, *self.parents)
        if len({item.content_id for item in items}) != len(items):
            raise ValueError("comment context identities must be distinct")
        if self.parent_state == "root" and self.parents:
            raise ValueError("root comments cannot have parents")
        return self
