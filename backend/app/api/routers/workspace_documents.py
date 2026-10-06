import base64
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response

from api.dependencies import (
    UserScopeDependency,
    UserWriteScopeDependency,
    WorkspaceDocumentServiceDependency,
)
from core.schemas import ErrorView
from knowledge.document_schemas import (
    WorkspaceCatalogView,
    WorkspaceDocumentView,
    WorkspaceDraftView,
    WorkspaceHistoryView,
    WorkspaceOperationView,
    WorkspacePublishInput,
    WorkspaceSaveInput,
    WorkspaceSearchView,
)

router = APIRouter(prefix="/workspace/documents", tags=["项目文档"])
_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorView} for code in (401, 403, 404, 409, 422, 503)
}


Service = WorkspaceDocumentServiceDependency
PathQuery = Annotated[str, Query(min_length=1, max_length=300)]
SnapshotQuery = Annotated[str | None, Query(pattern=r"^[a-f0-9]{64}$")]


@router.get(
    "",
    operation_id="listWorkspaceDocuments",
    response_model=WorkspaceCatalogView,
    status_code=200,
    responses=_ERRORS,
)
def catalog(
    service: Service,
    owner: UserScopeDependency,
    snapshot_id: SnapshotQuery = None,
    history: bool = False,
) -> WorkspaceCatalogView:
    return WorkspaceCatalogView.model_validate(
        service.execute(owner, "list", snapshot_id=snapshot_id, history=history)
    )


@router.get(
    "/document",
    operation_id="getWorkspaceDocument",
    response_model=WorkspaceDocumentView,
    status_code=200,
    responses=_ERRORS,
)
def document(
    path: PathQuery,
    service: Service,
    owner: UserScopeDependency,
    snapshot_id: SnapshotQuery = None,
    history: bool = False,
) -> WorkspaceDocumentView:
    return WorkspaceDocumentView.model_validate(
        service.execute(owner, "read", path=path, snapshot_id=snapshot_id, history=history)
    )


@router.get(
    "/search",
    operation_id="searchWorkspaceDocuments",
    response_model=WorkspaceSearchView,
    status_code=200,
    responses=_ERRORS,
)
def search(
    query: Annotated[str, Query(min_length=1, max_length=200)],
    service: Service,
    owner: UserScopeDependency,
    snapshot_id: SnapshotQuery = None,
    history: bool = False,
) -> WorkspaceSearchView:
    return WorkspaceSearchView.model_validate(
        service.execute(owner, "search", query=query, snapshot_id=snapshot_id, history=history)
    )


@router.get(
    "/raw",
    operation_id="getWorkspaceDocumentRaw",
    response_class=Response,
    response_model=None,
    status_code=200,
    responses=_ERRORS,
)
def raw(
    path: PathQuery,
    service: Service,
    owner: UserScopeDependency,
    snapshot_id: SnapshotQuery = None,
    anchor: str | None = None,
    history: bool = False,
) -> Response:
    item = service.execute(
        owner, "raw", path=path, snapshot_id=snapshot_id, anchor=anchor, history=history
    )
    return Response(
        item["markdown"],
        media_type="text/markdown",
        headers={
            "x-workspace-snapshot": item["snapshot_id"],
            "x-content-sha256": item["source_hash"],
            "x-content-type-options": "nosniff",
        },
    )


@router.get(
    "/attachment",
    operation_id="getWorkspaceDocumentAttachment",
    response_class=Response,
    response_model=None,
    status_code=200,
    responses=_ERRORS,
)
def attachment(
    attachment_id: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")],
    service: Service,
    owner: UserScopeDependency,
    snapshot_id: SnapshotQuery = None,
    history: bool = False,
) -> Response:
    item = service.execute(
        owner, "attachment", attachment_id=attachment_id, snapshot_id=snapshot_id, history=history
    )
    return Response(
        base64.b64decode(item["body"], validate=True),
        media_type=item["mime"],
        headers={
            "x-content-type-options": "nosniff",
            "content-disposition": "inline" if item["mime"].startswith("image/") else "attachment",
        },
    )


@router.get(
    "/draft",
    operation_id="getWorkspaceDocumentDraft",
    response_model=WorkspaceDraftView,
    status_code=200,
    responses=_ERRORS,
)
def draft(
    path: PathQuery, service: Service, owner: UserScopeDependency, snapshot_id: SnapshotQuery = None
) -> WorkspaceDraftView:
    return WorkspaceDraftView.model_validate(
        service.execute(owner, "draft", path=path, snapshot_id=snapshot_id)
    )


@router.put(
    "/draft",
    operation_id="saveWorkspaceDocumentDraft",
    response_model=WorkspaceDraftView,
    status_code=200,
    responses=_ERRORS,
)
def save(
    command: WorkspaceSaveInput, service: Service, owner: UserWriteScopeDependency
) -> WorkspaceDraftView:
    return WorkspaceDraftView.model_validate(
        service.execute(owner, "save", **command.model_dump(mode="json"))
    )


@router.post(
    "/publish",
    operation_id="publishWorkspaceDocument",
    response_model=WorkspaceOperationView,
    status_code=200,
    responses=_ERRORS,
)
def publish(
    command: WorkspacePublishInput, service: Service, owner: UserWriteScopeDependency
) -> WorkspaceOperationView:
    fields = command.model_dump(mode="json")
    action = fields.pop("action")
    return WorkspaceOperationView.model_validate(service.execute(owner, action, **fields))


@router.get(
    "/history",
    operation_id="getWorkspaceDocumentHistory",
    response_model=WorkspaceHistoryView,
    status_code=200,
    responses=_ERRORS,
)
def history(path: PathQuery, service: Service, owner: UserScopeDependency) -> WorkspaceHistoryView:
    return WorkspaceHistoryView.model_validate(
        service.execute(owner, "history", path=path, history=True)
    )


@router.get(
    "/operations/{operation_id}",
    operation_id="getWorkspaceDocumentOperation",
    response_model=WorkspaceOperationView,
    status_code=200,
    responses=_ERRORS,
)
def operation(
    operation_id: UUID, service: Service, owner: UserScopeDependency
) -> WorkspaceOperationView:
    return WorkspaceOperationView.model_validate(
        service.execute(owner, "operation", operation_id=str(operation_id))
    )
