from __future__ import annotations

from typing import Annotated
from uuid import UUID

import typer
from pydantic import ValidationError

from core.config import get_settings
from core.errors import ApplicationError
from db.session import create_db_engine, create_session_factory
from identity.schemas import EmailCodeInput, IdentityCredentialsInput
from identity.services import IdentityService

identity_app = typer.Typer(no_args_is_help=True)


@identity_app.command("create-account")
def create_account(
    username: Annotated[str, typer.Option(help="Unique account username.")],
    user_id: Annotated[
        UUID | None, typer.Option(help="Explicit UUID to retain a legacy data owner.")
    ] = None,
    email: Annotated[
        str | None, typer.Option(help="Previously verified account email, if available.")
    ] = None,
) -> None:
    """Create a maintained account without bootstrap or secret output."""
    password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    try:
        credentials = IdentityCredentialsInput(username=username, password=password)
        normalized_email = EmailCodeInput(email=email).email if email else None
    except ValidationError:
        typer.echo("Account creation failed: invalid_credentials", err=True)
        raise typer.Exit(1) from None
    settings = get_settings()
    engine = create_db_engine(settings)
    try:
        with create_session_factory(engine)() as session:
            identifier = IdentityService(session, settings).create_account(
                username=credentials.username,
                password=credentials.password.get_secret_value(),
                user_id=user_id,
                email=normalized_email,
            )
    except ApplicationError as error:
        typer.echo(f"Account creation failed: {error.code}", err=True)
        raise typer.Exit(1) from None
    finally:
        engine.dispose()
    typer.echo(f"Account created: {identifier}")


@identity_app.command("reset-password")
def reset_password(
    user_id: Annotated[UUID, typer.Option(help="Exact account UUID to maintain.")],
) -> None:
    """Change the selected account password and revoke all previous sessions."""
    password = typer.prompt("New password", hide_input=True, confirmation_prompt=True)
    settings = get_settings()
    engine = create_db_engine(settings)
    try:
        with create_session_factory(engine)() as session:
            IdentityService(session, settings).reset_password(user_id=user_id, password=password)
    except ApplicationError as error:
        typer.echo(f"Password reset failed: {error.code}", err=True)
        raise typer.Exit(1) from None
    finally:
        engine.dispose()
    typer.echo("Password changed; previous sessions revoked")
