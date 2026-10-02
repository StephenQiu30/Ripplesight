from __future__ import annotations

from ipaddress import ip_address
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Header, Query, Request, Response

from api.dependencies import (
    AuthenticatedIdentityDependency,
    CreatedIdentitySession,
    CsrfProtectedIdentityDependency,
    IdentityServiceDependency,
    require_same_origin,
)
from core.errors import ApplicationError
from core.schemas import ErrorView
from identity.schemas import (
    EmailChallengeView,
    EmailCodeInput,
    GithubAuthorizationInput,
    GithubAuthorizationView,
    IdentityCredentialsInput,
    IdentityCredentialsUpdateInput,
    IdentitySessionView,
    LoginOptionsView,
    VerifyEmailCodeInput,
)

router = APIRouter(prefix="/identity", tags=["identity"])
_AUTH_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorView},
    403: {"model": ErrorView},
    422: {"model": ErrorView},
    429: {"model": ErrorView},
    503: {"model": ErrorView},
    500: {"model": ErrorView},
}


def _client_ip(request: Request) -> str:
    # Uvicorn must not rewrite the TCP peer from visitor supplied forwarding headers.
    # Local development and the same-origin Web server share one conservative bucket.
    try:
        return str(ip_address(request.client.host)) if request.client else "unknown"
    except ValueError:
        return "unknown"


def _public_write(request: Request, csrf: str | None) -> None:
    require_same_origin(request)
    if csrf != "1":
        raise ApplicationError("csrf_invalid")


def _set_cookies(
    response: Response, service: IdentityServiceDependency, created: CreatedIdentitySession
) -> None:
    for name, value, http_only in (
        ("hotkey_session", created.session_token, True),
        ("hotkey_csrf", created.csrf_token, False),
    ):
        response.set_cookie(
            name,
            value,
            httponly=http_only,
            secure=service.cookie_secure,
            samesite="lax",
            path="/",
            max_age=service.settings.session_ttl_seconds,
            expires=created.view.expires_at,
        )
    response.headers["cache-control"] = "no-store"


def _clear_cookies(response: Response, service: IdentityServiceDependency) -> None:
    for name, http_only in (("hotkey_session", True), ("hotkey_csrf", False)):
        response.delete_cookie(
            name, httponly=http_only, secure=service.cookie_secure, samesite="lax", path="/"
        )
    response.headers["cache-control"] = "no-store"


@router.get(
    "/options",
    operation_id="getLoginOptions",
    response_model=LoginOptionsView,
    status_code=200,
    responses={500: {"model": ErrorView}},
)
def options(response: Response, service: IdentityServiceDependency) -> LoginOptionsView:
    response.headers["cache-control"] = "no-store"
    return service.options()


@router.post(
    "/sessions",
    operation_id="createIdentitySession",
    response_model=IdentitySessionView,
    status_code=200,
    responses=_AUTH_ERRORS,
)
def password_login(
    payload: IdentityCredentialsInput,
    request: Request,
    response: Response,
    service: IdentityServiceDependency,
    csrf: Annotated[str | None, Header(alias="X-HotKey-CSRF")] = None,
) -> IdentitySessionView:
    _public_write(request, csrf)
    created = service.login(
        username=payload.username,
        password=payload.password.get_secret_value(),
        client_ip=_client_ip(request),
    )
    _set_cookies(response, service, created)
    return created.view


@router.get(
    "/session",
    operation_id="getIdentitySession",
    response_model=IdentitySessionView,
    status_code=200,
    responses={401: {"model": ErrorView}, 422: {"model": ErrorView}, 500: {"model": ErrorView}},
)
def session(identity: AuthenticatedIdentityDependency) -> IdentitySessionView:
    return identity.view


@router.delete(
    "/session",
    operation_id="deleteIdentitySession",
    status_code=204,
    response_model=None,
    responses={
        401: {"model": ErrorView},
        403: {"model": ErrorView},
        422: {"model": ErrorView},
        500: {"model": ErrorView},
    },
)
def logout(
    response: Response,
    service: IdentityServiceDependency,
    identity: CsrfProtectedIdentityDependency,
) -> None:
    service.logout(identity)
    _clear_cookies(response, service)


@router.post(
    "/email/challenges",
    operation_id="sendEmailLoginCode",
    response_model=EmailChallengeView,
    status_code=200,
    responses=_AUTH_ERRORS,
)
def email_challenge(
    payload: EmailCodeInput,
    request: Request,
    response: Response,
    service: IdentityServiceDependency,
    session_cookie: Annotated[
        str | None, Cookie(alias="hotkey_session", include_in_schema=False)
    ] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias="hotkey_csrf", include_in_schema=False)] = None,
    csrf: Annotated[str | None, Header(alias="X-HotKey-CSRF")] = None,
) -> EmailChallengeView:
    require_same_origin(request)
    identity = None
    if session_cookie:
        try:
            identity = service.authenticate(session_cookie)
        except ApplicationError as failure:
            if failure.code != "invalid_session" or csrf != "1":
                raise
            _clear_cookies(response, service)
    if identity:
        service.validate_csrf(identity, cookie=csrf_cookie, header=csrf)
    else:
        _public_write(request, csrf)
    response.headers["cache-control"] = "no-store"
    return service.send_email_code(
        email=payload.email, client_ip=_client_ip(request), identity=identity
    )


@router.post(
    "/email/sessions",
    operation_id="verifyEmailLoginCode",
    response_model=IdentitySessionView,
    status_code=200,
    responses=_AUTH_ERRORS,
)
def email_login(
    payload: VerifyEmailCodeInput,
    request: Request,
    response: Response,
    service: IdentityServiceDependency,
    csrf: Annotated[str | None, Header(alias="X-HotKey-CSRF")] = None,
) -> IdentitySessionView:
    _public_write(request, csrf)
    created = service.verify_email(
        challenge_id=payload.challenge_id, code=payload.code, client_ip=_client_ip(request)
    )
    _set_cookies(response, service, created)
    return created.view


@router.post(
    "/github/authorize",
    operation_id="startGithubLogin",
    response_model=GithubAuthorizationView,
    status_code=200,
    responses={
        403: {"model": ErrorView},
        422: {"model": ErrorView},
        429: {"model": ErrorView},
        503: {"model": ErrorView},
        500: {"model": ErrorView},
    },
)
def github_start(
    payload: GithubAuthorizationInput,
    request: Request,
    response: Response,
    service: IdentityServiceDependency,
    csrf: Annotated[str | None, Header(alias="X-HotKey-CSRF")] = None,
) -> GithubAuthorizationView:
    _public_write(request, csrf)
    url, binding = service.start_github(return_to=payload.return_to, client_ip=_client_ip(request))
    response.set_cookie(
        "hotkey_oauth",
        binding,
        httponly=True,
        secure=service.cookie_secure,
        samesite="lax",
        path="/",
        max_age=300,
    )
    response.headers["cache-control"] = "no-store"
    return GithubAuthorizationView(authorization_url=url)


@router.get(
    "/github/callback",
    operation_id="completeGithubLogin",
    response_model=None,
    status_code=303,
    response_class=Response,
    responses={
        303: {
            "description": "完成或取消授权后跳转至安全站内页面",
            "headers": {"Location": {"schema": {"type": "string"}}},
        },
        422: {"model": ErrorView},
        500: {"model": ErrorView},
    },
)
def github_callback(
    service: IdentityServiceDependency,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=256)] = None,
    error: Annotated[str | None, Query(max_length=128)] = None,
    binding: Annotated[str | None, Cookie(alias="hotkey_oauth", include_in_schema=False)] = None,
) -> Response:
    response = Response(status_code=303, headers={"cache-control": "no-store"})
    try:
        if error is not None or code is None or state is None or binding is None:
            if state and binding:
                service.cancel_github(state=state, binding=binding)
            raise ApplicationError("invalid_oauth_state")
        created, destination = service.complete_github(code=code, state=state, binding=binding)
        _set_cookies(response, service, created)
        response.headers["location"] = destination
    except ApplicationError as failure:
        safe_codes = {
            "invalid_oauth_state",
            "github_authentication_failed",
            "identity_link_conflict",
            "github_login_unavailable",
            "auth_dependency_unavailable",
        }
        result = failure.code if failure.code in safe_codes else "github_authentication_failed"
        response.headers["location"] = f"/login?error={result}"
    response.delete_cookie(
        "hotkey_oauth", path="/", httponly=True, secure=service.cookie_secure, samesite="lax"
    )
    return response


@router.put(
    "/credentials",
    operation_id="updateIdentityCredentials",
    status_code=204,
    response_model=None,
    responses={**_AUTH_ERRORS, 409: {"model": ErrorView}},
)
def update_credentials(
    payload: IdentityCredentialsUpdateInput,
    request: Request,
    response: Response,
    service: IdentityServiceDependency,
    identity: CsrfProtectedIdentityDependency,
) -> None:
    service.update_credentials(identity=identity, command=payload, client_ip=_client_ip(request))
    _clear_cookies(response, service)
