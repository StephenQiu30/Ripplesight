"""Body phase budgets on the original Job; local calls and target bounds stay distinct."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy.orm import Session, sessionmaker

from connections.editorial_body_admission import require_editorial_body_execution_in_transaction
from content.editorial_body import require_editorial_body_input_in_transaction
from core.errors import ApplicationError
from evidence.services import RetentionPolicyUnavailableError, SourceAccessUnavailableError
from jobs.execution import ExecutionLease, JobExecutionService
from jobs.schemas import (
    BudgetContext,
    BudgetDecisionStatus,
    BudgetMetric,
    BudgetReservationInput,
    UsageAttemptInput,
    UsageKind,
    UsageOutcome,
)
from jobs.services import ResourceBudgetError, ResourceBudgetService
from sources.contracts import WebPageResult
from sources.editorial_body import EditorialBodyAdmission
from sources.editorial_schemas import EditorialBodyTarget


class EditorialBodyRequestMeter:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        *,
        lease: ExecutionLease,
        source_ref: str,
        connection_id: UUID,
        max_target_requests: int,
        guard: Callable[[Session, UUID, UUID], bool],
        lease_seconds: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._sessions, self._lease, self._guard = sessions, lease, guard
        self._source, self._connection, self._maximum = (
            source_ref,
            connection_id,
            max_target_requests,
        )
        self._lease_seconds, self._clock = lease_seconds, clock
        if not 1 <= max_target_requests <= 20:
            raise ValueError("body target request bound must be reviewed and bounded")

    def _proof(self, session: Session, target: EditorialBodyTarget) -> EditorialBodyAdmission:
        if not self._guard(session, target.owner_id, target.job_id):
            raise ApplicationError("editorial_version_conflict")
        require_editorial_body_input_in_transaction(session, target=target, now=self._clock())
        return require_editorial_body_execution_in_transaction(
            session,
            owner_id=target.owner_id,
            profile_id=target.profile_id,
            configuration_version=target.configuration_version,
            revision=target.profile_revision,
            now=self._clock(),
        )

    def admission(self, target: EditorialBodyTarget) -> EditorialBodyAdmission | None:
        try:
            with self._sessions.begin() as session:
                return self._proof(session, target)
        except (ApplicationError, RetentionPolicyUnavailableError, SourceAccessUnavailableError):
            return None

    @staticmethod
    def _id(target: EditorialBodyTarget, kind: str) -> UUID:
        return uuid5(target.run_id, f"body:{target.feed_observation_id}:{kind}")

    def before_request(self, target: EditorialBodyTarget) -> bool:
        try:
            with self._sessions.begin() as session:
                self._proof(session, target)
                ledger = ResourceBudgetService(session, clock=self._clock)
                context = BudgetContext(
                    source_ref=self._source,
                    connection_ref=str(self._connection),
                    job_ref=str(target.job_id),
                )
                reserved: list[UUID] = []
                for kind, metric, units in (
                    ("collector", BudgetMetric.COLLECTOR_CALL, 1),
                    ("target-bound", BudgetMetric.NETWORK_REQUEST, self._maximum),
                ):
                    identifier = self._id(target, kind)
                    decision = ledger.reserve_budget_in_transaction(
                        owner_id=target.owner_id,
                        command=BudgetReservationInput(
                            reservation_id=identifier,
                            operation_id=target.operation_id,
                            metric=metric,
                            requested_units=units,
                            context=context,
                        ),
                    )
                    if decision.status is not BudgetDecisionStatus.RESERVED:
                        for previous in reserved:
                            ledger.settle_budget_reservation_in_transaction(
                                owner_id=target.owner_id, reservation_id=previous, actual_units=0
                            )
                        return False
                    reserved.append(identifier)
                _, allowed = JobExecutionService(
                    session, lease_seconds=self._lease_seconds, clock=self._clock
                ).begin_request_in_transaction(self._lease)
                if not allowed:
                    for identifier in reserved:
                        ledger.settle_budget_reservation_in_transaction(
                            owner_id=target.owner_id, reservation_id=identifier, actual_units=0
                        )
                    return False
                ledger.begin_attempt_in_transaction(
                    owner_id=target.owner_id,
                    command=UsageAttemptInput(
                        attempt_id=self._id(target, "usage"),
                        operation_id=target.operation_id,
                        component_key=f"collector.editorial_body.{target.profile_id.hex}",
                        usage_kind=UsageKind.COLLECTOR_CALL,
                        stage="body_extract",
                        started_at=self._clock(),
                    ),
                )
                return True
        except (
            ApplicationError,
            ResourceBudgetError,
            RetentionPolicyUnavailableError,
            SourceAccessUnavailableError,
        ):
            return False

    def settle(self, target: EditorialBodyTarget, result: WebPageResult) -> None:
        # No downstream telemetry: consume the reviewed upper bound conservatively.
        # This is quota consumption, never an assertion of observed target requests.
        units = self._maximum if result.collector_call_count else 0
        with self._sessions.begin() as session:
            ledger = ResourceBudgetService(session, clock=self._clock)
            for kind, actual in (
                ("collector", result.collector_call_count),
                ("target-bound", units),
            ):
                ledger.settle_budget_reservation_in_transaction(
                    owner_id=target.owner_id,
                    reservation_id=self._id(target, kind),
                    actual_units=actual,
                )
            ledger.finish_attempt_in_transaction(
                owner_id=target.owner_id,
                attempt_id=self._id(target, "usage"),
                outcome=UsageOutcome.SUCCEEDED if result.document else UsageOutcome.FAILED,
                finished_at=self._clock(),
            )
