from __future__ import annotations

import io
import json
from functools import partial
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from tests.integration.test_ai_capability_routing import (
    _budgets,
    _settings,
)
from tests.integration.test_ai_capability_routing import engine as engine
from tests.integration.test_editorial_source_profiles import NOW, begin, job, material, page, setup

from ai.capability_routing import create_ai_client_for_frozen_model
from ai.capability_services import load_frozen_ai_routing_in_transaction
from ai.editorial_vision import prepare_editorial_vision_input
from ai.services import AiService
from analysis.editorial_models import EditorialRun, EditorialStage
from analysis.editorial_schemas import EditorialRunInput
from analysis.editorial_services import EditorialExecutor, EditorialService
from connections.editorial_models import EditorialSourceMaterialReceipt
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.schemas import ComponentPolicyInput, CostClass, JobAcceptedMessage
from jobs.services import ResourceBudgetService


def _image():
    buffer = io.BytesIO()
    Image.new("RGB", (48, 48), color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


def _grant(sessions, owner, source_key):
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE source_access_policies SET field_purposes=field_purposes || "
                "CAST(:fields AS jsonb) WHERE owner_id=:owner AND source_key=:key"
            ),
            dict(
                owner=owner,
                key=source_key,
                fields=json.dumps(
                    {
                        "url": "Independent admitted first image",
                        "vision": "Editorial understand image",
                    }
                ),
            ),
        )
        session.execute(
            text(
                "INSERT INTO evidence_retention_policies "
                "(id,owner_id,source_policy_id,source_policy_version,data_class,requested_days,"
                "effective_days,policy_version,created_at,updated_at) "
                "SELECT :id,owner_id,id,policy_version,'media',30,30,1,:now,:now "
                "FROM source_access_policies WHERE owner_id=:owner AND source_key=:key"
            ),
            dict(id=uuid4(), owner=owner, key=source_key, now=NOW),
        )


def _run(sessions, settings, owner, source_key, content_id, version_id):
    with sessions() as session:
        run = EditorialService(session, settings=settings, clock=lambda: NOW).request_run(
            owner_id=owner,
            content_id=content_id,
            source_key=source_key,
            command=EditorialRunInput(operation_id=uuid4(), content_version_id=version_id),
        )
        envelope = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": run.job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **envelope.payload,
                "message_id": envelope.id,
                "event_type": envelope.event_type,
                "schema_version": 2,
            }
        )
        session.rollback()
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: NOW).acquire(
            job_id=run.job_id, worker_id="controlled-vision"
        )
    return run, message, lease


def _setup(engine, *, media=True, image_budget=True):
    sessions = sessionmaker(engine, expire_on_commit=False)
    settings = _settings().model_copy(
        update={
            "ai_vision_requests_enabled": True,
            "ai_capability_models": {
                key: "named"
                for key in (
                    "prefilter",
                    "score",
                    "understand",
                    "structure",
                    "summarize",
                    "group",
                    "groupReview",
                    "digest",
                    "report",
                    "translate",
                    "monitor",
                )
            },
        }
    )
    with sessions() as session:
        source_service, owner, profile, _ = setup(session)
        collected, op = job(session, owner, profile)
        prepared = begin(source_service, owner, profile, collected, op)
        source_service.stage_page(
            owner_id=owner,
            run_id=prepared.result.run_id,
            page=page(
                material(
                    content_format="html",
                    body_html=(
                        '<p>Full controlled original source content<img src="/first.png">'
                        '<img src="/second.png"></p>'
                    ),
                )
            ),
        )
        assert source_service.apply_page(owner_id=owner, run_id=prepared.result.run_id).created == 1
        with session.begin():
            receipt = session.scalar(select(EditorialSourceMaterialReceipt))
            content_id, version_id = receipt.content_id, receipt.content_version_id
    if media:
        _grant(sessions, owner, profile.source_key)
    _budgets(engine, owner, NOW, "USD")
    if image_budget:
        with sessions() as session:
            ResourceBudgetService(session, clock=lambda: NOW).save_component_policy(
                owner_id=owner,
                command=ComponentPolicyInput(
                    component_key="ai.vision.fetch",
                    component_version="1",
                    cost_class=CostClass.ZERO_PRICE,
                    enabled_for_core=True,
                    terms_reference="Controlled HTTP replay only",
                    reviewed_at=NOW,
                ),
            )
    run, message, lease = _run(
        sessions, settings, owner, profile.source_key, content_id, version_id
    )
    return sessions, settings, owner, profile, run, message, lease


def _execute(
    sessions, settings, owner, run, message, lease, requests, image_handler, monkeypatch, *, now=NOW
):
    monkeypatch.setattr(
        "analysis.editorial_services.prepare_editorial_vision_input",
        partial(
            prepare_editorial_vision_input,
            transport=httpx.MockTransport(image_handler),
            resolver=lambda hostname: ("8.8.8.8",),
        ),
    )
    outputs = {
        "PrefilterOutput": {"label": "PASS", "reason": "Model release"},
        "ScoreOutput": {"attentionScore": 90},
        "StructureOutput": {
            "category": "ai-models",
            "tags": ["模型"],
            "subjects": ["openai"],
            "fact": None,
        },
        "UnderstandOutput": {
            "itemType": "model_release",
            "authorRole": "principal",
            "tags": ["模型"],
            "editorialJudgment": "公开发布新模型",
            "titleZh": "模型发布",
            "summaryZh": "公开发布具有新能力的模型,展示了使用方式。",
        },
    }

    def provider(req):
        payload = json.loads(req.content)
        requests.append(payload)
        schema = json.loads(payload["messages"][0]["content"].split("schema: ", 1)[1])
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(outputs[schema["title"]])}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    with sessions.begin() as session:
        routing = load_frozen_ai_routing_in_transaction(
            session, owner_id=owner, job_id=message.job_id
        )
    client = create_ai_client_for_frozen_model(
        settings,
        routing.for_purpose("editorial.understand"),
        transport=httpx.MockTransport(provider),
    )
    worker = EditorialExecutor(sessions, settings, clock=lambda: now)
    try:
        with sessions() as session:
            return worker.execute(
                message,
                lease,
                ai=AiService(
                    session,
                    client,
                    settings=settings,
                    clock=lambda: now,
                    guard=lambda current: worker._ai_guard(current, message, lease, run.id),
                    execution_epoch=lease.epoch,
                ),
            )
    finally:
        client.close()


def test_actual_first_image_reaches_understand_and_replay_does_not_fetch_or_pay(
    engine, monkeypatch
):
    sessions, settings, owner, _profile, run, message, lease = _setup(engine)
    requests, images = [], []

    def image(req):
        images.append(str(req.url))
        return httpx.Response(200, content=_image(), headers={"content-type": "image/png"})

    _execute(sessions, settings, owner, run, message, lease, requests, image, monkeypatch)
    _execute(sessions, settings, owner, run, message, lease, requests, image, monkeypatch)
    assert images == ["https://8.8.8.8/first.png"] and len(requests) == 5
    content = requests[-1]["messages"][-1]["content"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    with sessions() as session:
        stored = session.get(EditorialRun, run.id)
        assert stored.status == "complete" and stored.input_manifest["vision"]["mode"] == "image"
        assert len(stored.input_manifest["vision"]["image_sha256"]) == 64
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 5
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM resource_usage_attempts a "
                    "JOIN resource_component_policies p ON p.id=a.component_policy_id "
                    "WHERE p.component_key='ai.vision.fetch'"
                )
            )
            == 1
        )


@pytest.mark.parametrize("media,image_budget", [(False, True), (True, False)])
def test_image_permission_or_budget_denial_is_known_failed_and_manual_new_run_works(
    engine,
    monkeypatch,
    media,
    image_budget,
):
    sessions, settings, owner, profile, run, message, lease = _setup(
        engine, media=media, image_budget=image_budget
    )
    requests, images = [], []

    def image(req):
        images.append(str(req.url))
        return httpx.Response(200, content=_image(), headers={"content-type": "image/png"})

    with pytest.raises(JobExecutionFailure, match="editorial_unavailable"):
        _execute(sessions, settings, owner, run, message, lease, requests, image, monkeypatch)
    assert images == [] and len(requests) == 4
    with sessions() as session:
        stage = session.scalar(
            select(EditorialStage).where(EditorialStage.stage_key == "understand")
        )
        stored = session.get(EditorialRun, run.id)
        assert stage.status == stored.status == "failed" and stage.ai_call_id is None
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 4
    if not media:
        _grant(sessions, owner, profile.source_key)
    if not image_budget:
        with sessions() as session:
            ResourceBudgetService(session, clock=lambda: NOW).save_component_policy(
                owner_id=owner,
                command=ComponentPolicyInput(
                    component_key="ai.vision.fetch",
                    component_version="1",
                    cost_class=CostClass.ZERO_PRICE,
                    enabled_for_core=True,
                    terms_reference="Reviewed controlled replay",
                    reviewed_at=NOW,
                ),
            )
    manual, manual_message, manual_lease = _run(
        sessions, settings, owner, profile.source_key, run.content_id, run.content_version_id
    )
    _execute(
        sessions,
        settings,
        owner,
        manual,
        manual_message,
        manual_lease,
        requests,
        image,
        monkeypatch,
    )
    assert len(images) == 1 and len(requests) == 9
    assert isinstance(requests[-1]["messages"][-1]["content"], list)


def test_unknown_image_http_is_held_and_never_automatically_repeats(engine, monkeypatch):
    sessions, settings, owner, _profile, run, message, lease = _setup(engine)
    requests, images = [], []

    def unknown(req):
        images.append(req)
        raise httpx.ReadTimeout("controlled unknown image response", request=req)

    for _ in range(2):
        with pytest.raises(JobExecutionFailure, match="editorial_timeout"):
            _execute(sessions, settings, owner, run, message, lease, requests, unknown, monkeypatch)
    assert len(images) == 1 and len(requests) == 4
    with sessions() as session:
        assert session.get(EditorialRun, run.id).status == "unknown"


def test_known_unsupported_image_uses_one_text_call_without_claiming_vision(engine, monkeypatch):
    sessions, settings, owner, _profile, run, message, lease = _setup(engine)
    requests, images = [], []

    def unsupported(req):
        images.append(req)
        return httpx.Response(
            200,
            content=b'<svg xmlns="http://www.w3.org/2000/svg" '
            b'width="48" height="48"><rect width="48" height="48"/></svg>',
            headers={"content-type": "image/svg+xml"},
        )

    _execute(sessions, settings, owner, run, message, lease, requests, unsupported, monkeypatch)
    assert len(images) == 1 and len(requests) == 5
    assert isinstance(requests[-1]["messages"][-1]["content"], str)
    with sessions() as session:
        assert session.get(EditorialRun, run.id).input_manifest["vision"]["mode"] == (
            "text_unsupported_image"
        )


def test_media_permission_withdrawn_during_fetch_prevents_any_understand_model_call(
    engine,
    monkeypatch,
):
    sessions, settings, owner, _profile, run, message, lease = _setup(engine)
    requests, images = [], []

    def withdrawn(req):
        images.append(req)
        with sessions.begin() as session:
            session.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
                {"owner": owner},
            )
        return httpx.Response(200, content=_image(), headers={"content-type": "image/png"})

    with pytest.raises(JobExecutionFailure):
        _execute(sessions, settings, owner, run, message, lease, requests, withdrawn, monkeypatch)
    assert len(images) == 1 and len(requests) == 4
    with sessions() as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM ai_calls WHERE purpose='editorial.understand'")
            )
            == 0
        )


def test_admitted_image_process_boundary_is_settled_on_new_epoch_without_image_or_model_repayment(
    engine, monkeypatch
):
    from datetime import timedelta

    from publication.media_mirror_meter import MediaRequestMeter

    sessions, settings, owner, _profile, run, message, lease = _setup(engine)
    requests, images = [], []
    original_before = MediaRequestMeter.before

    def interrupted(self, file_id, kind, index):
        assert original_before(self, file_id, kind, index)
        raise SystemExit("Controlled boundary after durable image admission")

    monkeypatch.setattr(MediaRequestMeter, "before", interrupted)
    with pytest.raises(SystemExit, match="durable image admission"):
        _execute(
            sessions,
            settings,
            owner,
            run,
            message,
            lease,
            requests,
            lambda req: images.append(req.url),
            monkeypatch,
        )
    assert len(requests) == 4 and not images
    with sessions() as session:
        assert session.scalar(text("SELECT sum(reserved_units) FROM resource_budget_windows")) > 0
        stage = session.scalar(
            select(EditorialStage).where(EditorialStage.stage_key == "understand")
        )
        assert stage.status == "running" and stage.ai_call_id is None
        later = NOW + timedelta(seconds=settings.job_lease_seconds + 1)
        session.rollback()
        resumed = JobExecutionService(session, lease_seconds=30, clock=lambda: later).acquire(
            job_id=message.job_id, worker_id="image-new-epoch"
        )
    monkeypatch.setattr(MediaRequestMeter, "before", original_before)
    with pytest.raises(JobExecutionFailure, match="editorial_result_unknown"):
        _execute(
            sessions,
            settings,
            owner,
            run,
            message,
            resumed,
            requests,
            lambda req: images.append(req.url),
            monkeypatch,
            now=later,
        )
    assert len(requests) == 4 and not images
    with sessions() as session:
        assert session.scalar(text("SELECT sum(reserved_units) FROM resource_budget_windows")) == 0
        stage = session.scalar(
            select(EditorialStage).where(EditorialStage.stage_key == "understand")
        )
        assert stage.status == "unknown" and stage.ai_call_id is None
        usage = session.execute(
            text(
                "SELECT a.outcome,r.actual_units FROM resource_usage_attempts a "
                "JOIN resource_component_policies p ON p.id=a.component_policy_id "
                "JOIN resource_budget_reservations r ON r.reservation_id=a.attempt_id "
                "WHERE p.component_key='ai.vision.fetch'"
            )
        ).all()
        assert usage and all(row.outcome == "failed" and row.actual_units == 1 for row in usage)
