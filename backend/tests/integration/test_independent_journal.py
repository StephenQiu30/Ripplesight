"""Verify independent PG authority and restricted roles, never business databases."""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from tests.conftest import validate_test_database_url
from tests.integration.test_data_lifecycle import lifecycle_context as lifecycle_context
from tests.integration.test_recovery_replay import SCHEMA, _track
from tests.integration.test_restore_isolation import EmptyEvidenceInspector
from tests.unit.test_backup_restore import _manifest
from typer.testing import CliRunner

from backups.adapters.postgres import PostgresDumpAdapter
from backups.restore import BackupRestoreService
from backups.services import BackupService
from cli import commands as cli_commands
from core.config import Settings
from evidence.journal import (
    DenialCommand,
    JournalConflictError,
    JournalExportLimitError,
    JournalUnavailableError,
    RestrictionJournal,
)
from evidence.journal_contract import entry_digest, genesis_digest
from evidence.schemas import DeletionReason

DDL = Path(__file__).resolve().parents[2] / "sql" / "journal.sql"


@dataclass
class JournalContext:
    source: URL
    owner: Engine
    ledger_id: UUID
    urls: dict[str, URL]
    writer: RestrictionJournal
    reader: RestrictionJournal


@pytest.fixture
def journal_context():
    raw = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if raw is None:
        pytest.skip("isolated PostgreSQL test database is required")
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


def command(**changes) -> DenialCommand:
    return DenialCommand(
        **{
            "owner_id": uuid4(),
            "operation_id": uuid4(),
            "resource_type": "content_item",
            "resource_id": uuid4(),
            "reason": DeletionReason.USER_REQUEST,
            **changes,
        }
    )


@pytest.mark.parametrize("change", [None, "resource_id", "resource_type", "reason"])
def test_concurrent_operation_identity_is_stable(journal_context, change):
    context = journal_context
    original = command()
    changed = (
        original
        if change is None
        else original.model_copy(
            update={
                change: {
                    "resource_id": uuid4(),
                    "resource_type": "report",
                    "reason": DeletionReason.AUTHORIZATION_REVOKED,
                }[change]
            }
        )
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(context.writer.append, item) for item in (original, changed)]
        receipts, conflicts = [], []
        for future in futures:
            try:
                receipts.append(future.result(timeout=10))
            except JournalConflictError as error:
                conflicts.append(error)
    if change is None:
        assert len(receipts) == 2 and receipts[0] == receipts[1] and not conflicts
    else:
        assert len(receipts) == len(conflicts) == 1
    exported = context.reader.export(_manifest())
    assert len(exported.snapshot.entries) == 1 and exported.checkpoint.head_sequence == 1
    assert receipts[0].digest == entry_digest(receipts[0])
    assert receipts[0].previous_digest == genesis_digest(exported.snapshot)


def test_distinct_operations_and_rollback_keep_continuous_head(journal_context):
    context = journal_context
    owner, resource = uuid4(), uuid4()
    commands = [command(owner_id=owner, resource_id=resource) for _ in range(12)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        receipts = list(pool.map(context.writer.append, commands))
    assert sorted(item.sequence for item in receipts) == list(range(1, 13))
    rolled_back = command()
    with context.writer._engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            text("""SELECT * FROM restriction_journal.append(
            :ledger, 1, :owner, :op, 'content_item', :resource, 'user_request')"""),
            {
                "ledger": context.ledger_id,
                "owner": rolled_back.owner_id,
                "op": rolled_back.operation_id,
                "resource": rolled_back.resource_id,
            },
        )
        transaction.rollback()
    assert (
        context.writer.receipt(owner_id=rolled_back.owner_id, operation_id=rolled_back.operation_id)
        is None
    )
    final = context.writer.append(rolled_back)
    assert final.sequence == 13
    exported = context.reader.export(_manifest())
    assert (
        exported.checkpoint.head_sequence == 13 and exported.checkpoint.head_digest == final.digest
    )


def test_actual_commit_unknown_is_read_back_without_new_operation(journal_context, monkeypatch):
    context = journal_context
    request = command()
    assert (
        context.writer.receipt(owner_id=request.owner_id, operation_id=request.operation_id) is None
    )
    dialect = context.writer._engine.dialect
    original = dialect.do_commit

    def unknown(connection):
        original(connection)
        raise psycopg.OperationalError("controlled-secret-must-not-be-exposed")

    with monkeypatch.context() as patch:
        patch.setattr(dialect, "do_commit", unknown)
        with pytest.raises(JournalUnavailableError) as error:
            context.writer.append(request)
        assert "controlled-secret" not in str(error.value)
    recovered = context.writer.receipt(owner_id=request.owner_id, operation_id=request.operation_id)
    assert recovered is not None and context.writer.append(request) == recovered
    assert context.reader.export(_manifest()).checkpoint.head_sequence == 1


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE restriction_journal.events SET reason='source_deleted'",
        "DELETE FROM restriction_journal.events",
        "TRUNCATE restriction_journal.events",
        "UPDATE restriction_journal.head SET sequence=0",
        "SELECT restriction_journal.initialize(gen_random_uuid(), 2)",
        "CREATE TABLE restriction_journal.bypass(id INTEGER)",
    ],
)
def test_runtime_writer_cannot_modify_history_or_reinitialize(journal_context, statement):
    context = journal_context
    context.writer.append(command())
    with pytest.raises(SQLAlchemyError), context.writer._engine.begin() as connection:
        connection.exec_driver_sql(statement)
    assert context.reader.export(_manifest()).checkpoint.head_sequence == 1


@pytest.mark.parametrize(
    "defect",
    [
        "ledger",
        "epoch",
        "missing_head",
        "owner",
        "excess",
        "wrong_mode",
        "column_update",
        "database_create",
        "database_owner",
        "public_create",
        "journal_schema_create",
    ],
)
def test_authority_and_effective_permissions_fail_closed(journal_context, defect):
    context = journal_context
    url, ledger_id, epoch = context.urls["reader"], context.ledger_id, 1
    if defect == "ledger":
        ledger_id = uuid4()
    elif defect == "epoch":
        epoch = 2
    elif defect == "owner":
        url = context.owner.url
    elif defect == "excess":
        url = context.urls["excess"]
    elif defect == "wrong_mode":
        url = context.urls["writer"]
    elif defect == "column_update":
        with context.owner.begin() as connection:
            connection.exec_driver_sql(
                f'GRANT UPDATE(reason) ON restriction_journal.events TO "{url.username}"'
            )
    elif defect in {"database_create", "database_owner", "public_create", "journal_schema_create"}:
        with context.owner.begin() as connection:
            if defect == "database_create":
                connection.exec_driver_sql(
                    f'GRANT CREATE ON DATABASE "{url.database}" TO "{url.username}"'
                )
            elif defect == "database_owner":
                connection.exec_driver_sql(
                    f'ALTER DATABASE "{url.database}" OWNER TO "{url.username}"'
                )
            elif defect == "public_create":
                connection.exec_driver_sql("GRANT CREATE ON SCHEMA public TO PUBLIC")
            else:
                connection.exec_driver_sql(
                    f'GRANT CREATE ON SCHEMA restriction_journal TO "{url.username}"'
                )
    else:
        with context.owner.begin() as connection:
            connection.exec_driver_sql("DELETE FROM restriction_journal.head")
    client = RestrictionJournal(
        database_url=url, source_database_url=context.source, ledger_id=ledger_id, epoch=epoch
    )
    try:
        with pytest.raises(JournalUnavailableError):
            client.export(_manifest())
    finally:
        client.close()
    with pytest.raises(JournalUnavailableError):
        context.reader.append(command())


def test_temporary_relations_and_types_cannot_shadow_definer_contract(journal_context):
    context = journal_context
    url = context.urls["writer"]
    with context.owner.begin() as connection:
        connection.exec_driver_sql(
            f'GRANT TEMPORARY ON DATABASE "{url.database}" TO "{url.username}"'
        )
    with context.writer._engine.begin() as connection:
        connection.exec_driver_sql("CREATE TEMP TABLE head(fake INTEGER)")
        connection.exec_driver_sql("CREATE TEMP TABLE events(fake INTEGER)")
        connection.exec_driver_sql("CREATE DOMAIN pg_temp.text AS pg_catalog.text CHECK (false)")
        connection.execute(
            text("""SELECT * FROM restriction_journal.append(
                :ledger, 1, :owner, :operation, 'content_item', :resource, 'user_request')"""),
            {
                "ledger": context.ledger_id,
                "owner": uuid4(),
                "operation": uuid4(),
                "resource": uuid4(),
            },
        ).one()
    receipt = context.writer.append(command())
    assert receipt.sequence == 2
    assert context.reader.export(_manifest()).checkpoint.head_digest == receipt.digest


def test_export_is_one_read_snapshot_while_new_denial_commits(journal_context, monkeypatch):
    context = journal_context
    loaded, resume = Event(), Event()
    original = context.reader._authority

    def pause(connection, mode):
        head = original(connection, mode)
        loaded.set()
        assert resume.wait(10)
        return head

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=1) as pool:
        patch.setattr(context.reader, "_authority", pause)
        future = pool.submit(context.reader.export, _manifest())
        try:
            assert loaded.wait(10)
            context.writer.append(command())
        finally:
            resume.set()
        exported = future.result(timeout=10)
    assert exported.snapshot.entries == () and exported.checkpoint.head_sequence == 0
    assert context.reader.export(_manifest()).checkpoint.head_sequence == 1


def test_online_sequence_exceeds_r1_bound_without_truncating_export(journal_context):
    context = journal_context
    with context.writer._engine.begin() as connection:
        connection.execute(
            text("""
            SELECT restriction_journal.append(:ledger, 1, :owner, md5(i::text)::uuid,
                'content_item', :resource, 'user_request') FROM generate_series(1,10001) s(i)
        """),
            {"ledger": context.ledger_id, "owner": uuid4(), "resource": uuid4()},
        ).all()
    receipt = context.writer.append(command())
    assert receipt.sequence == 10002 and receipt.digest == entry_digest(receipt)
    with pytest.raises(JournalExportLimitError):
        context.reader.export(_manifest())
    with context.owner.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM restriction_journal.events")) == 10002
        assert connection.scalar(text("SELECT epoch FROM restriction_journal.head")) == 1


def test_corrupted_history_rejected_and_schema_has_no_business_foreign_keys(journal_context):
    context = journal_context
    receipt = context.writer.append(command())
    with context.owner.begin() as connection:
        assert (
            connection.scalar(
                text("""SELECT count(*) FROM pg_constraint c
            JOIN pg_namespace n ON n.oid=c.connamespace
            WHERE n.nspname='restriction_journal' AND c.contype='f'""")
            )
            == 0
        )
        columns = connection.execute(
            text("""SELECT table_name, column_name, data_type
            FROM information_schema.columns WHERE table_schema='restriction_journal'
            ORDER BY table_name, ordinal_position""")
        ).all()
        assert (
            len(columns) == 16 and ("events", "occurred_at", "timestamp with time zone") in columns
        )
        connection.execute(
            text("UPDATE restriction_journal.events SET digest=:bad WHERE sequence=:seq"),
            {
                "bad": "0" * 64,
                "seq": receipt.sequence,
            },
        )
    with pytest.raises(JournalUnavailableError):
        context.reader.export(_manifest())


@pytest.mark.parametrize("defect", ["type", "reason", "owner", "pin"])
def test_direct_function_rejects_invalid_command_atomically(journal_context, defect):
    context = journal_context
    values = {
        "ledger": context.ledger_id,
        "owner": uuid4(),
        "operation": uuid4(),
        "type": "content_item",
        "resource": uuid4(),
        "reason": "user_request",
    }
    values[{"pin": "ledger"}.get(defect, defect)] = {
        "type": 'unsafe"type',
        "reason": "unsupported",
        "owner": None,
        "pin": uuid4(),
    }[defect]
    with pytest.raises(SQLAlchemyError), context.writer._engine.begin() as connection:
        connection.execute(
            text("""SELECT * FROM restriction_journal.append(
            :ledger, 1, :owner, :operation, :type, :resource, :reason)"""),
            values,
        )
    assert context.reader.export(_manifest()).checkpoint.head_sequence == 0


@pytest.mark.parametrize("wrong_pin", [False, True])
def test_real_cli_consumes_independent_authority_and_removes_private_export(
    journal_context,
    lifecycle_context,
    tmp_path,
    monkeypatch,
    wrong_pin,
):
    context, business = journal_context, lifecycle_context
    resource = uuid4()
    _track(business, business.owner_id, resource)
    candidate = BackupService(
        engine=business.engine,
        archive_writer=PostgresDumpAdapter(
            business.engine.url.render_as_string(hide_password=False)
        ),
        object_inspector=EmptyEvidenceInspector(),
        evidence_bucket="controlled-no-objects",
        schema_path=SCHEMA,
    ).create_candidate(tmp_path)
    context.writer.append(command(owner_id=business.owner_id, resource_id=resource))
    monkeypatch.setattr(
        cli_commands,
        "get_settings",
        lambda: Settings(
            database_url=business.engine.url.render_as_string(hide_password=False),
        ),
    )
    monkeypatch.setenv(
        "CONTROLLED_JOURNAL", context.urls["reader"].render_as_string(hide_password=False)
    )
    monkeypatch.setenv(
        "CONTROLLED_ISOLATION",
        business.engine.url.set(database="postgres").render_as_string(hide_password=False),
    )
    exported = []
    original = BackupRestoreService.verify_replay

    def verify(service, directory, *, snapshot_path, checkpoint_json):
        assert snapshot_path.stat().st_mode & 0o777 == 0o600
        assert snapshot_path.parent.stat().st_mode & 0o777 == 0o700
        exported.append(snapshot_path)
        result = original(
            service, directory, snapshot_path=snapshot_path, checkpoint_json=checkpoint_json
        )
        assert result.replayed_sequence == 1 and result.matched_resources == 1
        return result

    monkeypatch.setattr(BackupRestoreService, "verify_replay", verify)
    result = CliRunner().invoke(
        cli_commands.app,
        [
            "backup",
            "verify-journal",
            "--candidate",
            str(candidate.directory),
            "--ledger-id",
            str(uuid4() if wrong_pin else context.ledger_id),
            "--epoch",
            "1",
            "--journal-url-env",
            "CONTROLLED_JOURNAL",
            "--isolation-url-env",
            "CONTROLLED_ISOLATION",
        ],
    )
    if wrong_pin:
        assert result.exit_code == 1 and not exported
    else:
        assert result.exit_code == 0, result.output
        assert "service open permitted: false" in result.output
        assert len(exported) == 1 and not exported[0].exists()
    assert context.urls["reader"].password not in result.output
