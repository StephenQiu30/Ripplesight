"""Pinned independent denials for maintenance and explicitly migrated online reads."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import monotonic
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import URL, RowMapping, make_url
from sqlalchemy.exc import ArgumentError, DBAPIError, SQLAlchemyError, TimeoutError

from core.errors import AuthorityUnavailableError
from evidence.journal_contract import (
    RecoveryCandidateBinding,
    RecoveryCheckpoint,
    RecoveryEntry,
    RecoveryLedgerError,
    RecoverySnapshot,
    VerifiedRecovery,
    entry_digest,
    genesis_digest,
    verify_recovery_snapshot,
)
from evidence.schemas import DeletionReason

if TYPE_CHECKING:
    from core.config import Settings


class JournalError(RuntimeError):
    """A journal operation did not produce usable authority evidence."""


class JournalUnavailableError(JournalError):
    """Confirmation is unknown or authority is invalid; never permission to allow."""


class JournalConflictError(JournalError):
    """An operation ID was already used with a different stable command."""


class JournalExportLimitError(JournalError):
    """A complete R1 export cannot fit its fixed bounds; nothing is truncated."""


class DenialCommand(BaseModel):
    """Stable caller identity, excluding server-assigned time/sequence/digests."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    owner_id: UUID
    operation_id: UUID
    resource_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    resource_id: UUID
    reason: DeletionReason


class JournalHead(BaseModel):
    """Pinned identity and committed high water mark, not a service release."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    ledger_id: UUID
    epoch: int = Field(ge=1, le=9223372036854775807)
    normalization_version: Literal["resource_uuid.v1"]
    sequence: int = Field(ge=0, le=9223372036854775807)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def create_journal_reader(settings: Settings, *, source_database_url: URL) -> RestrictionJournal:
    """Require the independent reader configuration; never infer a business fallback."""
    if (
        settings.restriction_journal_read_url is None
        or settings.restriction_journal_ledger_id is None
        or settings.restriction_journal_epoch is None
    ):
        raise AuthorityUnavailableError()
    try:
        return RestrictionJournal(
            database_url=settings.restriction_journal_read_url.get_secret_value(),
            source_database_url=source_database_url,
            ledger_id=settings.restriction_journal_ledger_id,
            epoch=settings.restriction_journal_epoch,
        )
    except JournalUnavailableError as error:
        raise AuthorityUnavailableError() from error


class RestrictionJournal:
    """Own a connection pool for one explicitly pinned independent database.

    No method initializes a store, grants privileges, changes epoch or falls
    back to business data. The deployment supplies reader/writer roles; every
    transaction checks their effective permissions and the expected identity.
    """

    def __init__(
        self,
        *,
        database_url: str | URL,
        source_database_url: str | URL,
        ledger_id: UUID,
        epoch: int,
    ) -> None:
        try:
            target, source = make_url(database_url), make_url(source_database_url)
        except (ArgumentError, ValueError) as error:
            raise JournalUnavailableError("journal database settings are invalid") from error
        if (
            target.drivername != "postgresql+psycopg"
            or source.drivername != "postgresql+psycopg"
            or not target.database
            or not source.database
            or target.database == source.database
            or not target.username
            or not isinstance(ledger_id, UUID)
            or type(epoch) is not int
            or not 1 <= epoch <= 9223372036854775807
        ):
            raise JournalUnavailableError("explicit independent journal identity is required")
        if (source.database or "").startswith("hotkey_test_") and any(
            url.host not in {"127.0.0.1", "localhost", "::1"}
            or not (url.database or "").startswith("hotkey_test_")
            or bool(url.query)
            for url in (source, target)
        ):
            raise JournalUnavailableError("test journals require local isolated databases")
        self._ledger_id, self._epoch = ledger_id, epoch
        self._engine = create_engine(target, connect_args={"connect_timeout": 5}, pool_timeout=5)

    def close(self) -> None:
        """Release only this client's connections; never drop a database."""
        self._engine.dispose()

    def _authority(
        self,
        connection: Connection,
        mode: Literal["append", "export", "receipt", "online"],
        *,
        deadline: float | None = None,
    ) -> JournalHead:
        # Catalog checks must not resolve caller-created temporary types/relations.
        if mode == "online":
            if deadline is None:
                raise AuthorityUnavailableError()
            self._online_budget(connection, deadline)
        connection.exec_driver_sql("SET LOCAL search_path = pg_catalog, pg_temp")
        if mode == "online":
            if deadline is None:
                raise AuthorityUnavailableError()
            self._online_budget(connection, deadline)
            if connection.scalar(text("SELECT pg_is_in_recovery()")) is not False:
                raise JournalUnavailableError("online journal requires the primary database")
            self._online_budget(connection, deadline)
        row = (
            connection.execute(
                text("""
            SELECT h.*,
              (SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls
                FROM pg_roles WHERE rolname=current_user) AS unsafe_role,
              pg_has_role(current_user, pg_get_userbyid(c.relowner), 'MEMBER') AS owner_member,
              EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='restriction_journal' AND
                pg_has_role(current_user, pg_get_userbyid(p.proowner), 'MEMBER')) AS function_owner,
              has_database_privilege(current_user, current_database(), 'CREATE') AS database_create,
              (SELECT pg_has_role(current_user, pg_get_userbyid(datdba), 'MEMBER')
                FROM pg_database WHERE datname=current_database()) AS database_owner,
              EXISTS (SELECT 1 FROM pg_namespace n
                WHERE n.nspname !~ '^pg_(temp|toast_temp)_'
                AND has_schema_privilege(current_user, n.oid, 'CREATE')) AS schema_write,
              has_table_privilege(current_user, 'restriction_journal.head',
                'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS head_write,
              has_table_privilege(current_user, 'restriction_journal.events',
                'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS event_write,
              has_any_column_privilege(current_user, 'restriction_journal.head',
                'INSERT,UPDATE,REFERENCES') AS head_column_write,
              has_any_column_privilege(current_user, 'restriction_journal.events',
                'INSERT,UPDATE,REFERENCES') AS event_column_write,
              has_function_privilege(current_user,
                'restriction_journal.initialize(uuid,bigint)', 'EXECUTE') AS can_initialize,
              has_function_privilege(current_user,
                'restriction_journal.append(uuid,bigint,uuid,uuid,text,uuid,text)',
                'EXECUTE') AS can_append
            FROM restriction_journal.head h
            JOIN pg_class c ON c.oid='restriction_journal.head'::regclass WHERE h.slot=1
        """)
            )
            .mappings()
            .one_or_none()
        )
        if row is None or any(
            row[key] is not False
            for key in (
                "unsafe_role",
                "owner_member",
                "function_owner",
                "database_create",
                "database_owner",
                "schema_write",
                "head_write",
                "event_write",
                "head_column_write",
                "event_column_write",
                "can_initialize",
            )
        ):
            raise JournalUnavailableError("journal authority or runtime permissions are unsafe")
        if (mode == "append" and row["can_append"] is not True) or (
            mode in {"export", "online"} and row["can_append"] is not False
        ):
            raise JournalUnavailableError("journal reader and writer permissions must be separate")
        head = JournalHead.model_validate({key: row[key] for key in JournalHead.model_fields})
        if head.ledger_id != self._ledger_id or head.epoch != self._epoch:
            raise JournalUnavailableError("journal identity does not match its independent pin")
        return head

    @staticmethod
    def _online_budget(connection: Connection, deadline: float) -> None:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AuthorityUnavailableError()
        # SET is deliberately not streamed; the event SELECT alone owns its cursor.
        connection.exec_driver_sql(f"SET LOCAL statement_timeout = {max(1, int(remaining * 1000))}")

    def denied_resources(
        self, *, owner_id: UUID, resources: frozenset[tuple[str, UUID]]
    ) -> frozenset[tuple[str, UUID]]:
        """Verify the complete online chain before returning exact candidate denials.

        Uses a fresh restricted read snapshot on every call. The total ledger
        has no R1 export bound; only a batch and candidate matches stay in memory.
        No result authorizes another action or a later network boundary.

        Raises:
            AuthorityUnavailableError: No complete trusted answer was obtained.
        """
        deadline = monotonic() + 30
        if (
            not isinstance(owner_id, UUID)
            or len(resources) > 20000
            or any(
                not isinstance(key, str)
                or not key.isascii()
                or not 1 <= len(key) <= 64
                or not key[0].islower()
                or any(not (c.islower() or c.isdigit() or c == "_") for c in key)
                or not isinstance(identifier, UUID)
                for key, identifier in resources
            )
        ):
            raise AuthorityUnavailableError()
        try:
            with (
                self._engine.connect().execution_options(
                    isolation_level="REPEATABLE READ"
                ) as connection,
                connection.begin(),
            ):
                self._online_budget(connection, deadline)
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                head = self._authority(connection, "online", deadline=deadline)
                self._online_budget(connection, deadline)
                if (
                    connection.execute(
                        text("""
                    SELECT 1 FROM restriction_journal.events
                    GROUP BY owner_id, operation_id HAVING count(*) > 1 LIMIT 1
                """)
                    ).first()
                    is not None
                ):
                    raise AuthorityUnavailableError()
                previous = genesis_digest(
                    RecoverySnapshot(
                        format_version="ripplesight.recovery-ledger.v1",
                        ledger_id=head.ledger_id,
                        epoch=head.epoch,
                        normalization_version=head.normalization_version,
                        entries=(),
                    )
                )
                sequence = 0
                denied: set[tuple[str, UUID]] = set()
                self._online_budget(connection, deadline)
                with connection.execute(
                    text(
                        "SELECT * FROM restriction_journal.events ORDER BY sequence"
                    ).execution_options(stream_results=True, yield_per=256)
                ) as rows:
                    batches = rows.mappings().partitions(256)
                    while True:
                        self._online_budget(connection, deadline)
                        batch = next(batches, ())
                        if not batch:
                            break
                        for row in batch:
                            if monotonic() >= deadline:
                                raise AuthorityUnavailableError()
                            entry = self._entry(row)
                            if entry.sequence != sequence + 1 or entry.previous_digest != previous:
                                raise AuthorityUnavailableError()
                            sequence, previous = entry.sequence, entry.digest
                            key = (entry.resource_type, entry.resource_id)
                            if entry.owner_id == owner_id and key in resources:
                                denied.add(key)
                if sequence != head.sequence or previous != head.digest:
                    raise AuthorityUnavailableError()
                self._online_budget(connection, deadline)
                return frozenset(denied)
        except (JournalUnavailableError, ValueError) as error:
            raise AuthorityUnavailableError() from error
        except SQLAlchemyError as error:
            state = getattr(error.orig, "sqlstate", None) if isinstance(error, DBAPIError) else None
            transient = isinstance(error, TimeoutError) or (
                isinstance(error, DBAPIError) and (state is None or state.startswith("08"))
            )
            raise AuthorityUnavailableError(
                "transient" if transient else "configuration"
            ) from error

    @staticmethod
    def _entry(row: RowMapping) -> RecoveryEntry:
        values = dict(row)
        reason = values["reason"]
        if not isinstance(reason, str):
            raise JournalUnavailableError("journal event is invalid")
        values["reason"] = DeletionReason(reason)
        entry = RecoveryEntry.model_validate(values)
        if entry.digest != entry_digest(entry):
            raise JournalUnavailableError("journal event digest is invalid")
        return entry

    @contextmanager
    def _read(self, mode: Literal["export", "receipt"]) -> Iterator[tuple[Connection, JournalHead]]:
        with (
            self._engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection,
            connection.begin(),
        ):
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            yield connection, self._authority(connection, mode)

    def append(self, command: DenialCommand) -> RecoveryEntry:
        """Confirm one stable denial or return its original receipt.

        A transport/commit failure raises unavailable: confirmation may already
        exist. Read back or retry the same operation, never compensate to allow.
        """
        try:
            with self._engine.begin() as connection:
                self._authority(connection, "append")
                row = (
                    connection.execute(
                        text("""
                    SELECT * FROM restriction_journal.append(
                        :ledger, :epoch, :owner, :operation, :type, :resource, :reason
                    )
                """),
                        {
                            "ledger": self._ledger_id,
                            "epoch": self._epoch,
                            "owner": command.owner_id,
                            "operation": command.operation_id,
                            "type": command.resource_type,
                            "resource": command.resource_id,
                            "reason": command.reason.value,
                        },
                    )
                    .mappings()
                    .one()
                )
                receipt = self._entry(row)
            return receipt
        except SQLAlchemyError as error:
            if isinstance(error, DBAPIError) and getattr(error.orig, "sqlstate", None) == "RJ001":
                raise JournalConflictError(
                    "journal operation conflicts with its original command"
                ) from error
            raise JournalUnavailableError(
                "journal confirmation is unavailable; read back the original operation"
            ) from error
        except ValueError as error:
            raise JournalUnavailableError("journal receipt is invalid") from error

    def receipt(self, *, owner_id: UUID, operation_id: UUID) -> RecoveryEntry | None:
        """Read back an uncertain operation under the explicit authority pin."""
        try:
            with self._read("receipt") as (connection, _head):
                row = (
                    connection.execute(
                        text("""
                    SELECT * FROM restriction_journal.events
                    WHERE owner_id=:owner AND operation_id=:operation
                """),
                        {"owner": owner_id, "operation": operation_id},
                    )
                    .mappings()
                    .one_or_none()
                )
                return None if row is None else self._entry(row)
        except (SQLAlchemyError, ValueError) as error:
            raise JournalUnavailableError("journal readback is unavailable") from error

    def export(self, manifest: RecoveryCandidateBinding) -> VerifiedRecovery:
        """Read and verify one complete bounded snapshot for the R1 consumer.

        This binds a candidate, not its historical deletion coverage or any
        release permission. Concurrent appends cannot split this read snapshot.
        """
        try:
            with self._read("export") as (connection, head):
                if head.sequence > 10000:
                    raise JournalExportLimitError("complete journal exceeds the R1 export bound")
                entries = tuple(
                    self._entry(row)
                    for row in connection.execute(
                        text(
                            "SELECT * FROM restriction_journal.events ORDER BY sequence LIMIT 10001"
                        )
                    ).mappings()
                )
                snapshot = RecoverySnapshot(
                    format_version="ripplesight.recovery-ledger.v1",
                    ledger_id=head.ledger_id,
                    epoch=head.epoch,
                    normalization_version=head.normalization_version,
                    entries=entries,
                )
                if len(snapshot.model_dump_json().encode("utf-8")) > 16 * 1024 * 1024:
                    raise JournalExportLimitError("complete journal exceeds the R1 export size")
                checkpoint = RecoveryCheckpoint(
                    format_version="ripplesight.recovery-checkpoint.v1",
                    ledger_id=head.ledger_id,
                    epoch=head.epoch,
                    normalization_version=head.normalization_version,
                    backup_id=manifest.backup_id,
                    archive_sha256=manifest.database.archive_sha256,
                    schema_sha256=manifest.database.schema_sha256,
                    head_sequence=head.sequence,
                    head_digest=head.digest,
                )
                return verify_recovery_snapshot(
                    snapshot=snapshot, checkpoint=checkpoint, manifest=manifest
                )
        except (SQLAlchemyError, ValueError, RecoveryLedgerError) as error:
            raise JournalUnavailableError(
                "complete journal export is unavailable or inconsistent"
            ) from error
