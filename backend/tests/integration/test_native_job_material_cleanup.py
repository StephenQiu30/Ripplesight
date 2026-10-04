"""Original Job text is deleted transactionally; audit and independent inputs survive."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.test_analysis_observation_inputs import aliases, freeze, legacy_result, topic
from tests.integration.test_analysis_pipeline import analysis_case as analysis_case
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_native_identity import NOW

from analysis.models import ContentAnnotation
from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.reads import analysis_scope_inputs_readable_in_transaction
from analysis.schemas import AnalysisJobScope, AnalysisPromptItem
from content.lifecycle import purge_observation_dependants_in_transaction
from content.models import ContentObservation, ContentVersion
from jobs.schemas import JobAcceptanceInput, JobObservationContext
from jobs.services import JobService


def test_delete_alias_scrubs_only_its_frozen_analysis_job_text_and_preserves_audit(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            identifier = topic(session, owner)
            jobs = []
            scopes = []
            for selected in (a, b):
                manifest = freeze(session, owner, selected)
                scope = AnalysisJobScope(
                    topic_id=identifier,
                    topic_rule_version=1,
                    prompt_version=ANALYSIS_PROMPT_VERSION,
                    content_version_ids=(selected[1],),
                    prompt_items=(
                        AnalysisPromptItem(
                            content_id=selected[0],
                            content_version_id=selected[1],
                            title="固定原帖标题",
                            body="必须随原输入删除的正文副本",
                            comment_version_ids=(),
                        ),
                    ),
                    input_manifest=manifest,
                )
                accepted = JobService(session, clock=lambda: NOW).accept_in_transaction(
                    owner_id=owner,
                    command=JobAcceptanceInput(
                        operation_id=uuid4(),
                        kind="analysis.annotate",
                        observation=JobObservationContext(
                            configuration_ref=f"topic:{identifier}", configuration_version=1
                        ),
                        scope=scope.to_job_scope(),
                    ),
                )
                jobs.append(accepted.id)
                scopes.append(scope.to_job_scope())
            session.flush()
            before = {
                row["id"]: dict(row)
                for row in session.execute(
                    text("SELECT * FROM jobs WHERE id=ANY(:ids)"), {"ids": jobs}
                ).mappings()
            }
            counts = tuple(
                session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("jobs", "job_attempts")
            )
            outbox_before = tuple(
                dict(row)
                for row in session.execute(
                    text("SELECT * FROM outbox_messages WHERE aggregate_id=ANY(:ids) ORDER BY id"),
                    {"ids": jobs},
                ).mappings()
            )
            purge_observation_dependants_in_transaction(
                session, owner_id=owner, observation_id=a[2], now=NOW
            )
            session.flush()
            after = {
                row["id"]: dict(row)
                for row in session.execute(
                    text("SELECT * FROM jobs WHERE id=ANY(:ids)"), {"ids": jobs}
                ).mappings()
            }
            expected_a = dict(scopes[0])
            expected_a.pop("prompt_items")
            assert after[jobs[0]]["scope"] == expected_a
            assert after[jobs[1]]["scope"] == scopes[1]
            for job_id in jobs:
                assert {k: v for k, v in after[job_id].items() if k != "scope"} == {
                    k: v for k, v in before[job_id].items() if k != "scope"
                }
            assert counts == tuple(
                session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("jobs", "job_attempts")
            )
            assert outbox_before == tuple(
                dict(row)
                for row in session.execute(
                    text("SELECT * FROM outbox_messages WHERE aggregate_id=ANY(:ids) ORDER BY id"),
                    {"ids": jobs},
                ).mappings()
            )
            assert session.get(ContentObservation, b[2]) is not None
            assert session.get(ContentVersion, b[1]) is not None
            with pytest.raises(ValidationError):
                AnalysisJobScope.from_job_scope(after[jobs[0]]["scope"])
            assert analysis_scope_inputs_readable_in_transaction(
                session,
                owner_id=owner,
                scope=AnalysisJobScope.from_job_scope(after[jobs[1]]["scope"]),
                now=NOW,
            )


def test_delete_original_legacy_comment_scrubs_real_call_job_and_derived_summary(analysis_case):
    case = analysis_case
    job_id, scope, call_id, annotation_id = legacy_result(case)
    with case.sessions() as session, session.begin():
        comment_observation = session.scalar(
            select(ContentObservation).where(ContentObservation.content_id == case.comment_id)
        )
        before = dict(
            session.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": job_id})
            .mappings()
            .one()
        )
        purge_observation_dependants_in_transaction(
            session,
            owner_id=case.owner_id,
            observation_id=comment_observation.id,
            now=case.now,
        )
        session.flush()
        after = dict(
            session.execute(text("SELECT * FROM jobs WHERE id=:id"), {"id": job_id})
            .mappings()
            .one()
        )
        assert "prompt_items" not in after["scope"]
        assert {k: v for k, v in after.items() if k != "scope"} == {
            k: v for k, v in before.items() if k != "scope"
        }
        expected = dict(before["scope"])
        expected.pop("prompt_items")
        assert after["scope"] == expected
        assert session.get(ContentAnnotation, annotation_id) is None
        assert session.get(ContentVersion, case.version_id) is not None
        assert (
            session.scalar(text("SELECT job_id FROM ai_calls WHERE id=:id"), {"id": call_id})
            == job_id
        )
        restored = AnalysisJobScope.from_job_scope(after["scope"])
        assert restored.content_version_ids == scope.content_version_ids
        assert restored.prompt_items is None
        assert not analysis_scope_inputs_readable_in_transaction(
            session, owner_id=case.owner_id, scope=restored, now=case.now
        )
        assert "原评论" not in json.dumps(after["scope"], ensure_ascii=False)


def test_unproven_retained_prompt_is_scrubbed_without_crossing_owner_boundary(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            identifier = topic(session, owner)
            unproven = {
                "topic_id": str(identifier),
                "topic_rule_version": 1,
                "prompt_version": ANALYSIS_PROMPT_VERSION,
                "content_version_ids": json.dumps([str(a[1])]),
                "prompt_items": "无法证明原始引用的旧标题、正文和评论副本",
            }
            selected_jobs = []
            for job_owner in (owner, uuid4()):
                accepted = JobService(session, clock=lambda: NOW).accept_in_transaction(
                    owner_id=job_owner,
                    command=JobAcceptanceInput(
                        operation_id=uuid4(),
                        kind="analysis.annotate",
                        observation=JobObservationContext(
                            configuration_ref=f"topic:{identifier}", configuration_version=1
                        ),
                        scope=dict(unproven),
                    ),
                )
                selected_jobs.append(accepted.id)
            session.flush()
            purge_observation_dependants_in_transaction(
                session, owner_id=owner, observation_id=a[2], now=NOW
            )
            scopes = {
                row.id: row.scope
                for row in session.execute(
                    text("SELECT id,scope FROM jobs WHERE id=ANY(:ids)"),
                    {"ids": selected_jobs},
                )
            }
            assert "prompt_items" not in scopes[selected_jobs[0]]
            assert scopes[selected_jobs[1]] == unproven
            assert session.get(ContentObservation, b[2]) is not None
