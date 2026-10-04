"""Alerts use existing notification scan, jobs and delivery admission; no provider I/O."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.config import Settings
from core.errors import ApplicationError
from monitors.services import current_topic_rule_matches_in_transaction
from notifications.alert_models import AlertEvaluation, AlertRule, AlertRuleVersion
from notifications.alert_schemas import (
    AlertEvaluationView,
    AlertMetric,
    AlertRuleInput,
    AlertRuleView,
    AlertTargetView,
)
from notifications.email_subscription import email_target_eligible_in_transaction
from notifications.models import NotificationDelivery, NotificationTarget
from notifications.schemas import NotificationSubjectMaterial


def _hash(value: object) -> bytes:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).digest()


def _target_reason(
    session: Session, *, owner_id: UUID, target: NotificationTarget | None, revision: int
) -> str | None:
    if target is None or target.owner_id != owner_id:
        return "alert_target_unavailable"
    if (
        target.revision != revision
        or not target.enabled
        or "alert" not in target.subscriptions
        or not email_target_eligible_in_transaction(session, owner_id=owner_id, target=target)
    ):
        return "alert_target_stale"
    accepted = session.scalar(
        select(NotificationDelivery.id)
        .where(
            NotificationDelivery.owner_id == owner_id,
            NotificationDelivery.target_id == target.id,
            NotificationDelivery.target_revision == revision,
            NotificationDelivery.status == "succeeded",
            NotificationDelivery.sent_at.is_not(None),
            NotificationDelivery.provider_receipt["status"].astext.in_(
                ("accepted", "smtp_accepted")
            ),
        )
        .limit(1)
    )
    return None if accepted else "alert_target_unverified"


def _facts(
    session: Session, *, owner_id: UUID, version: AlertRuleVersion, end: datetime, now: datetime
) -> tuple[float | None, str | None, dict[str, object]]:
    if version.metric == "negative_count":
        from analysis.alert_reading import load_negative_alert_facts_in_transaction

        facts = load_negative_alert_facts_in_transaction(
            session,
            owner_id=owner_id,
            topic_id=version.topic_id,
            topic_rule_version=version.topic_rule_version,
            start=end - timedelta(hours=1),
            end=end,
            now=now,
        )
        return facts.value, facts.reason, facts.manifest
    from events.alert_reading import load_heat_alert_facts_in_transaction

    assert version.event_id is not None
    heat = load_heat_alert_facts_in_transaction(
        session,
        owner_id=owner_id,
        topic_id=version.topic_id,
        event_id=version.event_id,
        end=end,
        now=now,
    )
    return heat.value, heat.reason, heat.manifest


def _inputs_readable(
    session: Session, *, owner_id: UUID, manifest: dict[str, object], now: datetime
) -> bool:
    if manifest.get("metric") == "negative_count":
        from analysis.alert_reading import negative_alert_inputs_readable_in_transaction

        return negative_alert_inputs_readable_in_transaction(
            session, owner_id=owner_id, manifest=manifest, now=now
        )
    if manifest.get("metric") == "heat_increment":
        from events.alert_reading import heat_alert_inputs_readable_in_transaction

        return heat_alert_inputs_readable_in_transaction(
            session, owner_id=owner_id, manifest=manifest, now=now
        )
    return False


class AlertService:
    def __init__(
        self, session: Session, settings: Settings, *, clock: Callable[[], datetime] | None = None
    ):
        self._session, self._settings, self._clock = (
            session,
            settings,
            clock or (lambda: datetime.now(UTC)),
        )

    def _readiness(self, rule: AlertRule, version: AlertRuleVersion, now: datetime) -> str | None:
        if not self._settings.notifications_enabled:
            return "notification_disabled"
        if not current_topic_rule_matches_in_transaction(
            self._session,
            owner_id=rule.owner_id,
            topic_id=version.topic_id,
            version=version.topic_rule_version,
        ):
            return "alert_topic_stale"
        target = self._session.scalar(
            select(NotificationTarget).where(
                NotificationTarget.owner_id == rule.owner_id,
                NotificationTarget.id == version.target_id,
            )
        )
        reason = _target_reason(
            self._session, owner_id=rule.owner_id, target=target, revision=version.target_revision
        )
        if reason:
            return reason
        _, reason, _ = _facts(
            self._session,
            owner_id=rule.owner_id,
            version=version,
            end=datetime.fromtimestamp(int(now.timestamp()) // 300 * 300, UTC),
            now=now,
        )
        return reason

    def _view(self, rule: AlertRule, version: AlertRuleVersion, now: datetime) -> AlertRuleView:
        reason = self._readiness(rule, version, now)
        return AlertRuleView(
            id=rule.id,
            name=version.name,
            revision=version.version,
            enabled=version.enabled,
            topic_id=version.topic_id,
            topic_rule_version=version.topic_rule_version,
            event_id=version.event_id,
            metric=cast(AlertMetric, version.metric),
            threshold=version.threshold,
            cooldown_seconds=version.cooldown_seconds,
            target_id=version.target_id,
            target_revision=version.target_revision,
            readiness="blocked" if reason else "ready",
            reason=reason,
            last_trigger_at=rule.last_trigger_at,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    def list_rules(self, *, owner_id: UUID) -> list[AlertRuleView]:
        self._session.rollback()
        with self._session.begin():
            return [
                self._view(rule, version, self._clock())
                for rule, version in self._session.execute(
                    select(AlertRule, AlertRuleVersion)
                    .join(
                        AlertRuleVersion,
                        (AlertRuleVersion.rule_id == AlertRule.id)
                        & (AlertRuleVersion.version == AlertRule.revision),
                    )
                    .where(AlertRule.owner_id == owner_id)
                    .order_by(AlertRule.created_at.desc(), AlertRule.id)
                    .limit(100)
                )
            ]

    def targets(self, *, owner_id: UUID) -> list[AlertTargetView]:
        self._session.rollback()
        with self._session.begin():
            result = []
            for target in self._session.scalars(
                select(NotificationTarget)
                .where(NotificationTarget.owner_id == owner_id)
                .order_by(NotificationTarget.name)
                .limit(100)
            ):
                reason = (
                    "notification_disabled"
                    if not self._settings.notifications_enabled
                    else _target_reason(
                        self._session, owner_id=owner_id, target=target, revision=target.revision
                    )
                )
                result.append(
                    AlertTargetView(
                        id=target.id,
                        name=target.name,
                        revision=target.revision,
                        eligible=reason is None,
                        reason=reason,
                    )
                )
            return result

    def save(
        self, *, owner_id: UUID, command: AlertRuleInput, rule_id: UUID | None = None
    ) -> AlertRuleView:
        self._session.rollback()
        now = self._clock()
        request_hash = _hash(
            {
                "rule_id": str(rule_id) if rule_id else None,
                "command": command.model_dump(mode="json"),
            }
        )
        with self._session.begin():
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"alert-save:{owner_id}:{command.operation_id}"},
            )
            prior = self._session.scalar(
                select(AlertRuleVersion).where(
                    AlertRuleVersion.owner_id == owner_id,
                    AlertRuleVersion.operation_id == command.operation_id,
                )
            )
            if prior:
                if prior.request_hash != request_hash:
                    raise ApplicationError("idempotency_conflict")
                rule = self._session.get(AlertRule, prior.rule_id)
                assert rule is not None
                return self._view(rule, prior, now)
            if not current_topic_rule_matches_in_transaction(
                self._session,
                owner_id=owner_id,
                topic_id=command.topic_id,
                version=command.topic_rule_version,
                require_active=False,
            ):
                raise ApplicationError("alert_configuration_conflict")
            if command.event_id is not None:
                from events.alert_reading import event_alert_candidate_in_transaction

                if not event_alert_candidate_in_transaction(
                    self._session,
                    owner_id=owner_id,
                    topic_id=command.topic_id,
                    event_id=command.event_id,
                ):
                    raise ApplicationError("alert_configuration_conflict")
            target = self._session.scalar(
                select(NotificationTarget).where(
                    NotificationTarget.owner_id == owner_id,
                    NotificationTarget.id == command.target_id,
                )
            )
            if target is None or target.revision != command.target_revision:
                raise ApplicationError("alert_configuration_conflict")
            if rule_id is None:
                if command.expected_revision != 0:
                    raise ApplicationError("alert_configuration_conflict")
                if self._session.scalar(
                    select(AlertRule.id).where(AlertRule.owner_id == owner_id).offset(99).limit(1)
                ):
                    raise ApplicationError("invalid_alert_input")
                rule = AlertRule(
                    id=uuid4(),
                    owner_id=owner_id,
                    name=command.name,
                    revision=1,
                    enabled=command.enabled,
                    last_trigger_at=None,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(rule)
            else:
                rule = self._session.scalar(
                    select(AlertRule)
                    .where(AlertRule.owner_id == owner_id, AlertRule.id == rule_id)
                    .with_for_update()
                )
                if rule is None:
                    raise ApplicationError("resource_not_found")
                if rule.revision != command.expected_revision:
                    raise ApplicationError("alert_configuration_conflict")
                rule.revision += 1
                rule.name, rule.enabled, rule.updated_at = command.name, command.enabled, now
            version = AlertRuleVersion(
                rule_id=rule.id,
                version=rule.revision,
                owner_id=owner_id,
                operation_id=command.operation_id,
                request_hash=request_hash,
                name=command.name,
                topic_id=command.topic_id,
                topic_rule_version=command.topic_rule_version,
                event_id=command.event_id,
                metric=command.metric,
                threshold=command.threshold,
                cooldown_seconds=command.cooldown_seconds,
                target_id=command.target_id,
                target_revision=command.target_revision,
                enabled=command.enabled,
                created_at=now,
            )
            self._session.add(version)
            self._session.flush()
            reason = self._readiness(rule, version, now)
            if command.enabled and reason:
                raise ApplicationError("alert_prerequisite_unavailable", context={"reason": reason})
            return self._view(rule, version, now)

    def history(
        self, *, owner_id: UUID, rule_id: UUID, limit: int = 50
    ) -> list[AlertEvaluationView]:
        self._session.rollback()
        with self._session.begin():
            if (
                self._session.scalar(
                    select(AlertRule.id).where(
                        AlertRule.owner_id == owner_id, AlertRule.id == rule_id
                    )
                )
                is None
            ):
                raise ApplicationError("resource_not_found")
            result = []
            for row in self._session.scalars(
                select(AlertEvaluation)
                .where(AlertEvaluation.owner_id == owner_id, AlertEvaluation.rule_id == rule_id)
                .order_by(AlertEvaluation.window_end.desc(), AlertEvaluation.id)
                .limit(limit)
            ):
                view = AlertEvaluationView.model_validate(row, from_attributes=True)
                if row.value is not None and (
                    _hash(row.input_manifest) != row.input_hash
                    or not _inputs_readable(
                        self._session,
                        owner_id=owner_id,
                        manifest=row.input_manifest,
                        now=self._clock(),
                    )
                ):
                    view = view.model_copy(
                        update={
                            "status": "withdrawn",
                            "value": None,
                            "reason": "alert_input_unavailable",
                        }
                    )
                result.append(view)
            return result


def evaluate_alert_rules_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    target_id: UUID,
    target_revision: int,
    scan_at: datetime,
    now: datetime,
    after: UUID | None = None,
    limit: int = 50,
) -> UUID | None:
    if (
        not session.in_transaction()
        or scan_at.utcoffset() is None
        or now.utcoffset() is None
        or int(scan_at.timestamp()) % 300
        or not 1 <= limit <= 100
    ):
        raise ValueError("alert evaluation requires bounded fixed five-minute caller transaction")
    from notifications.admission import enqueue_subject_in_transaction

    query = (
        select(AlertRule, AlertRuleVersion)
        .join(
            AlertRuleVersion,
            (AlertRuleVersion.rule_id == AlertRule.id)
            & (AlertRuleVersion.version == AlertRule.revision),
        )
        .where(
            AlertRule.owner_id == owner_id,
            AlertRule.enabled.is_(True),
            AlertRuleVersion.target_id == target_id,
            AlertRuleVersion.target_revision == target_revision,
            AlertRuleVersion.created_at <= scan_at,
        )
        .order_by(AlertRule.id)
        .limit(limit + 1)
        .with_for_update(of=AlertRule)
    )
    if after is not None:
        query = query.where(AlertRule.id > after)
    rows = tuple(session.execute(query))
    target = session.scalar(
        select(NotificationTarget)
        .where(NotificationTarget.owner_id == owner_id, NotificationTarget.id == target_id)
        .with_for_update()
    )
    for rule, version in rows[:limit]:
        if (
            session.scalar(
                select(AlertEvaluation.id).where(
                    AlertEvaluation.owner_id == owner_id,
                    AlertEvaluation.rule_id == rule.id,
                    AlertEvaluation.rule_version == version.version,
                    AlertEvaluation.window_end == scan_at,
                )
            )
            is not None
        ):
            continue
        reason = _target_reason(session, owner_id=owner_id, target=target, revision=target_revision)
        if not current_topic_rule_matches_in_transaction(
            session,
            owner_id=owner_id,
            topic_id=version.topic_id,
            version=version.topic_rule_version,
        ):
            reason = "alert_topic_stale"
        value: float | None = None
        manifest: dict[str, object] = {}
        status = "blocked" if reason else "unknown"
        cooldown_until = None
        if reason is None:
            value, reason, manifest = _facts(
                session, owner_id=owner_id, version=version, end=scan_at, now=now
            )
            if value is not None:
                unresolved = session.scalar(
                    select(NotificationDelivery.id)
                    .join(AlertEvaluation, AlertEvaluation.id == NotificationDelivery.subject_id)
                    .where(
                        NotificationDelivery.owner_id == owner_id,
                        AlertEvaluation.owner_id == owner_id,
                        AlertEvaluation.rule_id == rule.id,
                        NotificationDelivery.subject_kind == "alert",
                        NotificationDelivery.status.in_(("unknown", "sending")),
                    )
                    .limit(1)
                )
                cooldown_until = (
                    rule.last_trigger_at + timedelta(seconds=version.cooldown_seconds)
                    if rule.last_trigger_at
                    else None
                )
                if unresolved:
                    status, reason = "cooldown", "alert_delivery_unknown"
                elif cooldown_until is not None and scan_at < cooldown_until:
                    status, reason = "cooldown", "alert_cooldown"
                elif value < version.threshold:
                    status, reason, cooldown_until = "below_threshold", None, None
                else:
                    status, reason = "triggered", None
                    rule.last_trigger_at = scan_at
                    rule.updated_at = max(rule.updated_at, now)
                    cooldown_until = scan_at + timedelta(seconds=version.cooldown_seconds)
        # Expired cooldown boundaries are not reused as a future deadline.
        if cooldown_until is not None and cooldown_until <= scan_at:
            cooldown_until = None
        evaluation = AlertEvaluation(
            id=uuid4(),
            owner_id=owner_id,
            rule_id=rule.id,
            rule_version=version.version,
            window_start=scan_at - timedelta(hours=1),
            window_end=scan_at,
            status=status,
            reason=reason,
            value=value,
            input_manifest=manifest,
            input_hash=_hash(manifest),
            cooldown_until=cooldown_until,
            created_at=now,
        )
        session.add(evaluation)
        session.flush()
        if status == "triggered":
            material = load_alert_notification_in_transaction(
                session,
                owner_id=owner_id,
                evaluation_id=evaluation.id,
                revision=version.version,
                now=now,
            )
            if material is not None:
                accepted = enqueue_subject_in_transaction(
                    session, owner_id=owner_id, material=material, now=now, target_ids=(target_id,)
                )
                if not accepted:
                    evaluation.status, evaluation.reason = "blocked", "alert_delivery_not_admitted"
    return rows[limit - 1][0].id if len(rows) > limit else None


def load_alert_notification_in_transaction(
    session: Session, *, owner_id: UUID, evaluation_id: UUID, revision: int, now: datetime
) -> NotificationSubjectMaterial | None:
    evaluation = session.scalar(
        select(AlertEvaluation).where(
            AlertEvaluation.owner_id == owner_id, AlertEvaluation.id == evaluation_id
        )
    )
    if (
        evaluation is None
        or evaluation.status != "triggered"
        or evaluation.rule_version != revision
        or evaluation.window_end + timedelta(minutes=5) <= now
    ):
        return None
    rule = session.scalar(
        select(AlertRule)
        .where(AlertRule.owner_id == owner_id, AlertRule.id == evaluation.rule_id)
        .with_for_update()
    )
    version = session.scalar(
        select(AlertRuleVersion).where(
            AlertRuleVersion.owner_id == owner_id,
            AlertRuleVersion.rule_id == evaluation.rule_id,
            AlertRuleVersion.version == revision,
        )
    )
    if (
        rule is None
        or version is None
        or not rule.enabled
        or rule.revision != revision
        or not current_topic_rule_matches_in_transaction(
            session,
            owner_id=owner_id,
            topic_id=version.topic_id,
            version=version.topic_rule_version,
        )
    ):
        return None
    target = session.scalar(
        select(NotificationTarget)
        .where(NotificationTarget.owner_id == owner_id, NotificationTarget.id == version.target_id)
        .with_for_update()
    )
    if (
        _target_reason(session, owner_id=owner_id, target=target, revision=version.target_revision)
        or _hash(evaluation.input_manifest) != evaluation.input_hash
        or not _inputs_readable(
            session, owner_id=owner_id, manifest=evaluation.input_manifest, now=now
        )
    ):
        return None
    label = (
        "已采集材料有效情感负面计数"
        if version.metric == "negative_count"
        else "同公式一小时可比热度增量"
    )
    return NotificationSubjectMaterial(
        kind="alert",
        subject_id=evaluation.id,
        revision=revision,
        dedupe_key=f"alert:{evaluation.id}",
        occurred_at=evaluation.window_end,
        fingerprint=_hash(
            {
                "rule_id": str(rule.id),
                "rule_version": revision,
                "input_hash": evaluation.input_hash.hex(),
                "value": evaluation.value,
                "threshold": version.threshold,
                "window_end": evaluation.window_end.astimezone(UTC).isoformat(),
            }
        ).hex(),
        title=f"突发告警 · {version.name}",
        text=(
            f"{label}: {evaluation.value}; 阈值: {version.threshold}。"
            f"窗口: {evaluation.window_start.isoformat()} 至 {evaluation.window_end.isoformat()}。"
        ),
        reading_url="/alerts",
        expires_at=evaluation.window_end + timedelta(minutes=5),
    )


def purge_alert_content_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: tuple[UUID, ...],
    observation_ids: tuple[UUID, ...],
) -> None:
    def _uses(value: object, identifiers: set[str]) -> bool:
        if isinstance(value, str):
            return value in identifiers
        if isinstance(value, dict):
            return any(_uses(item, identifiers) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(_uses(item, identifiers) for item in value)
        return False

    identifiers = {str(i) for i in (*content_version_ids, *observation_ids)}
    for evaluation in session.scalars(
        select(AlertEvaluation).where(AlertEvaluation.owner_id == owner_id).with_for_update()
    ):
        if _uses(evaluation.input_manifest, identifiers):
            evaluation.status, evaluation.reason = "withdrawn", "alert_input_deleted"
            evaluation.input_manifest = {}
            evaluation.input_hash = _hash({})
            session.query(NotificationDelivery).filter(
                NotificationDelivery.owner_id == owner_id,
                NotificationDelivery.subject_kind == "alert",
                NotificationDelivery.subject_id == evaluation.id,
            ).delete(synchronize_session=False)
