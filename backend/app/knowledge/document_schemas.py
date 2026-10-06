from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from core.schemas import InputModel, OutputModel


class WorkspaceDocumentMetadata(OutputModel):
    path: str
    source_path: str
    title: str
    summary: str
    type: str
    status: str | None
    updated: str
    related: list[str]
    source_hash: str
    reading_hash: str


class WorkspaceSection(OutputModel):
    title: str
    anchor: str
    level: int
    content: str


class WorkspaceDocumentView(WorkspaceDocumentMetadata):
    snapshot_id: str
    source_revision: str
    markdown: str
    reading_markdown: str
    sections: list[WorkspaceSection]


class WorkspaceCatalogView(OutputModel):
    snapshot_id: str
    source_revision: str
    documents: list[WorkspaceDocumentMetadata]
    can_write: bool
    can_publish: bool


class WorkspaceSearchItem(OutputModel):
    path: str
    title: str
    anchor: str
    section_title: str
    snippet: str
    score: int


class WorkspaceSearchView(OutputModel):
    snapshot_id: str
    items: list[WorkspaceSearchItem]


class WorkspaceDraftView(OutputModel):
    path: str
    snapshot_id: str
    source_hash: str
    revision: int
    markdown: str
    base_markdown: str
    source_markdown: str | None = None
    current_source_hash: str | None = None
    conflicted: bool = False


class WorkspaceSaveInput(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    path: str = Field(min_length=1, max_length=300)
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    draft_revision: int = Field(ge=0)
    operation_id: UUID
    markdown: str = Field(max_length=200000)


class WorkspacePublishInput(InputModel):
    path: str = Field(min_length=1, max_length=300)
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    draft_revision: int = Field(ge=0)
    operation_id: UUID
    action: Literal["publish", "sync", "restore", "replace"] = "publish"
    replacement_path: str | None = Field(default=None, max_length=300)
    restore_snapshot_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class WorkspaceOperationView(OutputModel):
    status: Literal["pending", "published", "failed", "saved"]
    operation_id: UUID
    snapshot_id: str | None = None
    source_revision: str | None = None
    previous_revision: str | None = None
    published_path: str | None = None
    draft: WorkspaceDraftView | None = None
    code: str | None = None


class WorkspaceHistoryItem(OutputModel):
    snapshot_id: str
    source_revision: str
    source_hash: str


class WorkspaceHistoryView(OutputModel):
    items: list[WorkspaceHistoryItem]
