from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from api.dependencies import (
    AuthenticatedIdentityDependency,
    CsrfProtectedIdentityDependency,
    IdentityProfileServiceDependency,
)
from core.schemas import ErrorView
from identity.profile_schemas import IdentityAvatarInput, IdentityProfileInput
from identity.schemas import IdentitySessionView

router = APIRouter(prefix="/identity", tags=["identity"])
_WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorView} for code in (401, 403, 422, 500)
}


@router.put(
    "/profile",
    operation_id="updateIdentityProfile",
    summary="更新当前账户基本资料",
    status_code=200,
    response_model=IdentitySessionView,
    responses={**_WRITE_ERRORS, 409: {"model": ErrorView}},
)
def update_profile(
    command: IdentityProfileInput,
    response: Response,
    identity: CsrfProtectedIdentityDependency,
    service: IdentityProfileServiceDependency,
) -> IdentitySessionView:
    response.headers["cache-control"] = "no-store"
    return service.update_profile(identity, command)


@router.put(
    "/avatar",
    operation_id="uploadIdentityAvatar",
    summary="上传并替换当前账户头像",
    status_code=200,
    response_model=IdentitySessionView,
    responses=_WRITE_ERRORS,
)
def upload_avatar(
    command: IdentityAvatarInput,
    response: Response,
    identity: CsrfProtectedIdentityDependency,
    service: IdentityProfileServiceDependency,
) -> IdentitySessionView:
    response.headers["cache-control"] = "no-store"
    return service.upload_avatar(identity, command)


@router.get(
    "/avatar",
    operation_id="getIdentityAvatar",
    summary="读取当前账户头像",
    status_code=200,
    response_model=None,
    response_class=Response,
    responses={
        200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
        **{code: {"model": ErrorView} for code in (401, 404, 422, 500)},
    },
)
def avatar(
    identity: AuthenticatedIdentityDependency,
    service: IdentityProfileServiceDependency,
    sha256: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")],
) -> Response:
    return Response(
        service.read_avatar(identity, sha256),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
