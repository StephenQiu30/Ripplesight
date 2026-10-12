"""Verify independent PG authority and restricted roles, never business databases."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from tests.integration.test_data_lifecycle import lifecycle_context as lifecycle_context
from tests.integration.test_recovery_replay import SCHEMA, _track
from tests.integration.test_restore_isolation import EmptyEvidenceInspector
from tests.journal_support import isolated_journal
from tests.unit.test_backup_restore import _manifest
from typer.testing import CliRunner

from backups.adapters.postgres import PostgresDumpAdapter
from backups.restore import BackupRestoreService
from backups.services import BackupService
from cli import commands as cli_commands
from core.config import Settings
from core.errors import AuthorityUnavailableError
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


@pytest.fixture
def journal_context():
    raw = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if raw is None:
        pytest.skip("isolated PostgreSQL test database is required")
    with isolated_journal(raw) as context:
        yield context


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
    final = command()
    receipt = context.writer.append(final)
    assert receipt.sequence == 10002 and receipt.digest == entry_digest(receipt)
    resources = frozenset({(final.resource_type, final.resource_id)})
    assert (
        context.reader.denied_resources(owner_id=final.owner_id, resources=resources) == resources
    )
    assert not context.reader.denied_resources(owner_id=uuid4(), resources=resources)
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
    with pytest.raises(AuthorityUnavailableError):
        context.reader.denied_resources(owner_id=uuid4(), resources=frozenset())


def test_online_empty_and_deny_committed_between_reads(journal_context):
    context = journal_context
    denied = command(resource_type="content_observation")
    resources = frozenset({(denied.resource_type, denied.resource_id)})
    assert not context.reader.denied_resources(owner_id=denied.owner_id, resources=resources)
    context.writer.append(denied)
    assert (
        context.reader.denied_resources(owner_id=denied.owner_id, resources=resources) == resources
    )


@pytest.mark.parametrize("defect", ["head", "gap", "irrelevant_digest"])
def test_online_rejects_incomplete_or_irrelevant_corrupt_chain(journal_context, defect):
    context = journal_context
    first, second = command(), command()
    context.writer.append(first)
    context.writer.append(second)
    with context.owner.begin() as connection:
        if defect == "head":
            connection.execute(text("UPDATE restriction_journal.head SET sequence=1"))
        elif defect == "gap":
            connection.execute(text("DELETE FROM restriction_journal.events WHERE sequence=1"))
        else:
            connection.execute(
                text("UPDATE restriction_journal.events SET digest=:bad WHERE sequence=2"),
                {"bad": "0" * 64},
            )
    with pytest.raises(AuthorityUnavailableError) as captured:
        context.reader.denied_resources(
            owner_id=first.owner_id, resources=frozenset({(first.resource_type, first.resource_id)})
        )
    assert captured.value.kind == "configuration"


def test_online_budget_exhaustion_issues_no_later_sql(journal_context, monkeypatch):
    from sqlalchemy import event

    from evidence import journal

    context = journal_context
    statements = []
    event.listen(
        context.reader._engine, "before_cursor_execute", lambda *_args: statements.append(_args[2])
    )
    times = iter([10.0, 41.0])
    monkeypatch.setattr(journal, "monotonic", lambda: next(times))
    with pytest.raises(AuthorityUnavailableError) as captured:
        context.reader.denied_resources(owner_id=uuid4(), resources=frozenset())
    assert captured.value.kind == "configuration" and statements == []


def test_actual_statement_timeout_is_configuration_failure(journal_context, monkeypatch):
    context = journal_context

    def slow_authority(connection, mode, **_kwargs):
        connection.exec_driver_sql("SET LOCAL statement_timeout=10")
        connection.execute(text("SELECT pg_sleep(0.1)"))

    monkeypatch.setattr(context.reader, "_authority", slow_authority)
    with pytest.raises(AuthorityUnavailableError) as captured:
        context.reader.denied_resources(owner_id=uuid4(), resources=frozenset())
    assert captured.value.kind == "configuration"


def test_online_refuses_standby_even_with_valid_pin_and_role(journal_context, monkeypatch):
    from sqlalchemy.engine import Connection

    context = journal_context
    actual = Connection.scalar

    def scalar(connection, statement, *args, **kwargs):
        if str(statement) == "SELECT pg_is_in_recovery()":
            return True
        return actual(connection, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "scalar", scalar)
    with pytest.raises(AuthorityUnavailableError) as captured:
        context.reader.denied_resources(owner_id=uuid4(), resources=frozenset())
    assert captured.value.kind == "configuration"


def test_online_rejects_duplicate_owner_operation_even_with_valid_chain(journal_context):
    context = journal_context
    original = command()
    first = context.writer.append(original)
    second = context.writer.append(command(owner_id=original.owner_id))
    changed = second.model_copy(update={"operation_id": first.operation_id})
    digest = entry_digest(changed)
    with context.owner.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE restriction_journal.events DROP CONSTRAINT "
            "events_owner_id_operation_id_key"
        )
        connection.execute(
            text(
                "UPDATE restriction_journal.events SET operation_id=:op, "
                "digest=:digest WHERE sequence=2"
            ),
            {"op": first.operation_id, "digest": digest},
        )
        connection.execute(
            text("UPDATE restriction_journal.head SET digest=:digest"), {"digest": digest}
        )
    with pytest.raises(AuthorityUnavailableError):
        context.reader.denied_resources(owner_id=uuid4(), resources=frozenset())


def test_budget_exhausted_during_validation_does_not_fetch_or_issue_sql(
    journal_context, monkeypatch
):
    from sqlalchemy import event

    from evidence import journal

    context = journal_context
    context.writer.append(command())
    expired = [False]
    statements_after_expiration = []
    actual = context.reader._entry

    def entry(row):
        result = actual(row)
        expired[0] = True
        return result

    monkeypatch.setattr(context.reader, "_entry", entry)
    monkeypatch.setattr(journal, "monotonic", lambda: 40.0 if expired[0] else 1.0)

    def observe(_connection, _cursor, statement, *_args):
        if expired[0]:
            statements_after_expiration.append(statement)

    event.listen(context.reader._engine, "before_cursor_execute", observe)
    with pytest.raises(AuthorityUnavailableError) as captured:
        context.reader.denied_resources(owner_id=uuid4(), resources=frozenset())
    assert captured.value.kind == "configuration" and not statements_after_expiration


@pytest.mark.parametrize("role", ["writer", "excess"])
def test_online_rejects_mutating_reader_roles(journal_context, role):
    context = journal_context
    reader = RestrictionJournal(
        database_url=context.urls[role],
        source_database_url=context.source,
        ledger_id=context.ledger_id,
        epoch=1,
    )
    try:
        with pytest.raises(AuthorityUnavailableError) as captured:
            reader.denied_resources(owner_id=uuid4(), resources=frozenset())
        assert captured.value.kind == "configuration"
    finally:
        reader.close()


def test_actual_connection_refusal_is_transient(journal_context):
    import socket

    context = journal_context
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        reader = RestrictionJournal(
            database_url=context.urls["reader"].set(port=reserved.getsockname()[1]),
            source_database_url=context.source,
            ledger_id=context.ledger_id,
            epoch=1,
        )
        try:
            with pytest.raises(AuthorityUnavailableError) as captured:
                reader.denied_resources(owner_id=uuid4(), resources=frozenset())
            assert captured.value.kind == "transient"
        finally:
            reader.close()


def test_online_budget_expiring_after_primary_check_never_queries_head(
    journal_context, monkeypatch
):
    from sqlalchemy import event

    from evidence import journal

    context = journal_context
    expired = [False]
    issued_after_deadline = []
    monkeypatch.setattr(journal, "monotonic", lambda: 40.0 if expired[0] else 1.0)

    def after(_connection, _cursor, statement, *_args):
        if statement == "SELECT pg_is_in_recovery()":
            expired[0] = True

    def before(_connection, _cursor, statement, *_args):
        if expired[0]:
            issued_after_deadline.append(statement)

    event.listen(context.reader._engine, "after_cursor_execute", after)
    event.listen(context.reader._engine, "before_cursor_execute", before)
    with pytest.raises(AuthorityUnavailableError) as captured:
        context.reader.denied_resources(owner_id=uuid4(), resources=frozenset())
    assert captured.value.kind == "configuration" and not issued_after_deadline


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
