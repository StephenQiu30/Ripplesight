"""Owned independent test authority; callers always clean up its DB, roles and clients."""

import re
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from psycopg import sql
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

from evidence.journal import RestrictionJournal

DDL = Path(__file__).resolve().parents[1] / "sql" / "journal.sql"


def validate_test_database_url(value: str) -> None:
    parsed = make_url(value)
    if (
        parsed.drivername != "postgresql+psycopg"
        or parsed.host not in {"127.0.0.1", "localhost", "::1"}
        or not re.fullmatch(r"hotkey_test_[a-z0-9_]+", parsed.database or "")
        or parsed.query
    ):
        raise ValueError("isolated local test database required")


@dataclass
class JournalContext:
    source: URL
    owner: Engine
    ledger_id: UUID
    urls: dict[str, URL]
    writer: RestrictionJournal
    reader: RestrictionJournal


@contextmanager
def isolated_journal(raw: str):
    validate_test_database_url(raw)
    source = make_url(raw)
    database = "hotkey_test_journal_" + uuid4().hex[:20]
    admin = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
    owner = create_engine(source.set(database=database))
    roles, created_roles, clients = {}, [], []
    created = False
    ledger_id = uuid4()
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database}" WITH ALLOW_CONNECTIONS false')
            created = True
            connection.exec_driver_sql(f'REVOKE ALL ON DATABASE "{database}" FROM PUBLIC')
            for kind in ("reader", "writer", "excess"):
                name = "hotkey_test_jr_" + kind + "_" + uuid4().hex[:16]
                password = secrets.token_hex(24)
                connection.connection.driver_connection.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(name), sql.Literal(password)
                    )
                )
                created_roles.append(name)
                roles[kind] = source.set(database=database, username=name, password=password)
                connection.exec_driver_sql(f'GRANT CONNECT ON DATABASE "{database}" TO "{name}"')
            connection.exec_driver_sql(f'ALTER DATABASE "{database}" ALLOW_CONNECTIONS true')
        with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.connection.driver_connection.execute(DDL.read_text())
            connection.execute(
                text("SELECT restriction_journal.initialize(:id, 1)"), {"id": ledger_id}
            )
            for kind, url in roles.items():
                name = url.username
                connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA restriction_journal TO "{name}"')
                connection.exec_driver_sql(
                    f'GRANT SELECT ON ALL TABLES IN SCHEMA restriction_journal TO "{name}"'
                )
                if kind != "reader":
                    connection.exec_driver_sql(
                        "GRANT EXECUTE ON FUNCTION restriction_journal.append("
                        f'uuid,bigint,uuid,uuid,text,uuid,text) TO "{name}"'
                    )
                if kind == "excess":
                    connection.exec_driver_sql(
                        f'GRANT UPDATE ON restriction_journal.events TO "{name}"'
                    )
        for kind in ("writer", "reader"):
            clients.append(
                RestrictionJournal(
                    database_url=roles[kind],
                    source_database_url=source,
                    ledger_id=ledger_id,
                    epoch=1,
                )
            )
        yield JournalContext(source, owner, ledger_id, roles, *clients)
    finally:
        for client in clients:
            client.close()
        owner.dispose()
        try:
            with admin.connect() as connection:
                if created:
                    connection.exec_driver_sql(f'DROP DATABASE "{database}" WITH (FORCE)')
                for name in reversed(created_roles):
                    connection.exec_driver_sql(f'DROP ROLE "{name}"')
        finally:
            admin.dispose()
