"""Account-owned feed configuration, independent of public editorial sources."""

from uuid import UUID

from fastapi import APIRouter, Response

from api.dependencies import (
    EditorialSourceServiceDependency,
    UserScopeDependency,
    UserWriteScopeDependency,
)
from connections.editorial_schemas import PersonalSourceInput
from core.schemas import ErrorView
from sources.editorial_schemas import EditorialProfileView

router = APIRouter(
    prefix="/sources/personal",
    tags=["个人来源"],
    responses={code: {"model": ErrorView} for code in (401, 403, 404, 409, 422, 500, 503)},
)


@router.get(
    "",
    operation_id="listPersonalSources",
    response_model=tuple[EditorialProfileView, ...],
    status_code=200,
)
def list_personal_sources(
    response: Response, service: EditorialSourceServiceDependency, owner: UserScopeDependency
) -> tuple[EditorialProfileView, ...]:
    response.headers["cache-control"] = "no-store"
    return service.list_profiles(owner_id=owner, personal=True)


@router.post(
    "", operation_id="createPersonalSource", response_model=EditorialProfileView, status_code=201
)
def create_personal_source(
    command: PersonalSourceInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: UserWriteScopeDependency,
) -> EditorialProfileView:
    response.headers["cache-control"] = "no-store"
    return service.save_profile(owner_id=owner, command=command.editorial_input(), personal=True)


@router.put(
    "/{profile_id}",
    operation_id="updatePersonalSource",
    response_model=EditorialProfileView,
    status_code=200,
)
def update_personal_source(
    profile_id: UUID,
    command: PersonalSourceInput,
    response: Response,
    service: EditorialSourceServiceDependency,
    owner: UserWriteScopeDependency,
) -> EditorialProfileView:
    response.headers["cache-control"] = "no-store"
    return service.save_profile(
        owner_id=owner, profile_id=profile_id, command=command.editorial_input(), personal=True
    )
