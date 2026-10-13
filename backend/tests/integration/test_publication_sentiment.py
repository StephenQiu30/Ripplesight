"""Controlled producer-to-public-API proof; no real model or platform is contacted."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text
from tests.integration import test_publication_home as home_fixture
from tests.integration.test_analysis_annotations import _seed_analysis_job
from tests.integration.test_publication import editorial_client as editorial_client

from analysis.models import ContentAnnotation
from analysis.public_sentiment import (
    PublicReportAnalysisRef,
    read_public_report_sentiments_in_transaction,
)
from analysis.services import AnalysisService, resolve_annotation_results
from content.analysis_inputs import freeze_analysis_observation_inputs_in_transaction
from content.analysis_schemas import AnalysisObservationManifest
from content.schemas import AnalysisPostContentView
from publication.schemas import PublicationOverrideInput
from publication.services import PublicationService


def _seed(client, monkeypatch, count=2):
    from tests.integration.test_publication import NOW

    monkeypatch.setattr(home_fixture, "NOW", NOW)
    owner, posts, events = home_fixture._seed_events(client, count)
    with client.app.state.session_factory.begin() as session:
        # The reused old fixture omits scan_kind; explicitly seed known new-scan
        # provenance rather than treating an unknown backfill flag as false.
        session.execute(
            text(
                'UPDATE jobs SET scope=scope || \'{"scan_kind":"new_scan"}\'::jsonb WHERE '
                "owner_id=:owner AND source_key IS NOT NULL"
            ),
            {"owner": owner},
        )
    return owner, posts, events, NOW


def _annotate(
    client,
    owner,
    post,
    now,
    *,
    sentiment="negative",
    relevant=True,
    private_sibling=None,
    created_at=None,
    rule=1,
):
    sessions = client.app.state.session_factory
    version = post.latest_observation.content_version
    observation = post.latest_observation.id
    material = AnalysisPostContentView(
        content_id=post.id,
        content_version_id=version.id,
        observation_id=observation,
        title=version.title,
        body=version.body,
    )
    with sessions.begin() as session:
        topic = session.execute(
            text("SELECT id FROM monitor_topics WHERE owner_id=:owner"), {"owner": owner}
        ).scalar_one()
        inputs = {version.id: observation}
        batch = [material]
        if private_sibling:
            other = private_sibling.latest_observation
            inputs[other.content_version.id] = other.id
            batch.append(
                AnalysisPostContentView(
                    content_id=private_sibling.id,
                    content_version_id=other.content_version.id,
                    observation_id=other.id,
                    title=other.content_version.title,
                    body=other.content_version.body,
                )
            )
        manifest = freeze_analysis_observation_inputs_in_transaction(
            session, owner_id=owner, post_observations=inputs, comment_observations={}, now=now
        )
        job = _seed_analysis_job(
            session,
            owner_id=owner,
            topic_id=topic,
            posts=tuple(batch),
            now=now,
            rule_version=rule,
            prompt_version="analysis.annotate.v2",
            input_manifest=manifest,
        )
        call = uuid4()
        session.execute(
            text(
                "INSERT INTO ai_calls "
                "(id,owner_id,purpose,provider,model,prompt_version,input_fingerprint,status"
                ",input_tokens,cached_input_tokens,output_tokens,reasoning_output_tokens,dur"
                "ation_ms,job_id,created_at) VALUES "
                "(:id,:owner,'analysis.annotate','test','controlled','analysis.annotate.v2',"
                ":fingerprint,'succeeded',0,0,0,0,0,:job,:now)"
            ),
            dict(id=call, owner=owner, fingerprint=call.bytes * 2, job=job, now=now),
        )
        results = resolve_annotation_results(
            expected_content_version_ids=(version.id,),
            raw_items=[
                dict(
                    content_version_id=str(version.id),
                    relevant=relevant,
                    relevance_reason="受控分析依据",
                    summary="受控分析摘要",
                    sentiment=sentiment,
                    viewpoints=[],
                )
            ],
            ai_call_id=call,
        )
        AnalysisService(session).persist_results_in_transaction(
            owner_id=owner,
            topic_id=topic,
            topic_rule_version=rule,
            prompt_version="analysis.annotate.v2",
            posts={item.content_version_id: item for item in batch},
            results=results,
            input_manifest=manifest,
            created_at=created_at or now,
        )
    return topic


def test_persisted_dimensions_reach_home_and_detail_without_writes(editorial_client, monkeypatch):
    client = editorial_client
    owner, posts, events, now = _seed(client, monkeypatch)
    topic = _annotate(client, owner, posts[0], now)
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        # Pausing collection does not revoke a published report's analysis.
        session.execute(
            text("UPDATE monitor_topics SET status='paused' WHERE id=:id"), {"id": topic}
        )
        before = {
            name: session.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
            for name in ("ai_calls", "jobs", "publication_records", "content_annotations")
        }
    response = client.get("/api/publication/home?limit=1")
    assert response.status_code == 200, response.text
    view = response.json()
    assert len(view["stories"]) == 1
    samples = view["sentiment"]
    assert samples["samples"] == [] and samples["comparison_state"] == "not_calibrated"
    current = samples["current"]
    assert current["sample_count"] == 2 and current["valid_count"] == current["negative"] == 1, (
        current,
        [s["sentiment"]["samples"] for s in view["stories"]],
    )
    assert current["excluded_counts"] == {"not_analyzed": 1}
    assert current["negative_ratio"] == 1 and current["analysis_coverage"] == 0.5
    assert view["overview"]["negative_surge_count"] is None
    detail = client.get(f"/api/publication/stories/{events[0]}")
    assert detail.status_code == 200, detail.text
    evidence = detail.json()["sentiment"]["samples"]
    assert evidence[0]["label"] == "negative" and evidence[0]["content_id"] == str(posts[0].id)
    assert not {"annotation_id", "ai_call_id", "input_manifest", "error_code"} & evidence[0].keys()
    with sessions.begin() as session:
        after = {
            name: session.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
            for name in before
        }
    assert before == after


@pytest.mark.parametrize(
    "state,expected", [(None, "not_analyzed"), ("broken", "invalid"), ("negative", "valid")]
)
def test_optional_dimension_states_do_not_become_neutral(
    editorial_client, monkeypatch, state, expected
):
    owner, posts, events, now = _seed(editorial_client, monkeypatch, 1)
    _annotate(editorial_client, owner, posts[0], now, sentiment=state)
    view = editorial_client.get(f"/api/publication/stories/{events[0]}").json()["sentiment"]
    assert view["samples"][0]["state"] == expected
    assert view["current"]["neutral"] == 0
    assert view["current"]["valid_count"] == int(expected == "valid")


def test_private_batch_latest_result_cannot_resurrect_old_public_label(
    editorial_client, monkeypatch
):
    owner, posts, events, now = _seed(editorial_client, monkeypatch)
    _annotate(editorial_client, owner, posts[0], now, created_at=now - timedelta(seconds=10))
    _annotate(editorial_client, owner, posts[0], now, private_sibling=posts[1])
    with editorial_client.app.state.session_factory.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=posts[1].id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=1,
                visibility="withdrawn",
                reason="controlled private sibling",
            ),
            now=now,
        )
    response = editorial_client.get(f"/api/publication/stories/{events[0]}")
    assert response.status_code == 200, response.text
    sample = response.json()["sentiment"]["samples"][0]
    assert sample["state"] == "unavailable" and sample["label"] is None
    assert response.json()["sentiment"]["current"]["negative_ratio"] is None


@pytest.mark.parametrize("mutation", ["signature", "flat", "future", "withdraw", "rule"])
def test_current_proof_revocation_and_corruption_exclude_labels(
    editorial_client, monkeypatch, mutation
):
    owner, posts, _events, now = _seed(editorial_client, monkeypatch, 1)
    topic = _annotate(editorial_client, owner, posts[0], now)
    with editorial_client.app.state.session_factory.begin() as session:
        row = session.scalar(
            select(ContentAnnotation).where(
                ContentAnnotation.owner_id == owner,
                ContentAnnotation.prompt_version == "analysis.annotate.v2",
            )
        )
        if mutation == "signature":
            row.input_signature = "0" * 64
        elif mutation == "flat":
            row.sentiment = "positive"
        elif mutation == "future":
            row.updated_at = now + timedelta(days=1)
        elif mutation == "withdraw":
            PublicationService(session).override_in_transaction(
                owner_id=owner,
                actor_id=owner,
                content_id=posts[0].id,
                command=PublicationOverrideInput(
                    operation_id=uuid4(),
                    expected_revision=1,
                    visibility="withdrawn",
                    reason="controlled revoke",
                ),
                now=now,
            )
        else:
            session.execute(
                text(
                    "INSERT INTO "
                    "monitor_topic_versions(topic_id,version,created_by,match_any,match_all,excl"
                    "ude,created_at) VALUES (:id,2,:owner,'[\"AI\"]','[]','[]',:now)"
                ),
                dict(id=topic, owner=owner, now=now),
            )
            session.execute(
                text("UPDATE monitor_topics SET current_version=2 WHERE id=:id"), dict(id=topic)
            )
    response = editorial_client.get("/api/publication/home")
    assert response.status_code == 200, response.text
    current = response.json()["sentiment"]["current"]
    assert current["valid_count"] == 0 and current["negative_ratio"] is None
    assert current["sample_count"] == int(mutation != "withdraw")


def test_provider_owner_isolation(editorial_client, monkeypatch):
    owner, posts, _, now = _seed(editorial_client, monkeypatch, 1)
    topic = _annotate(editorial_client, owner, posts[0], now)
    post = posts[0]
    with editorial_client.app.state.session_factory.begin() as session:
        result = read_public_report_sentiments_in_transaction(
            session,
            owner_id=uuid4(),
            topic_id=topic,
            references=(
                PublicReportAnalysisRef(
                    post.id, post.latest_observation.content_version.id, post.latest_observation.id
                ),
            ),
            now=now,
        )
    assert result[post.id].state == "not_analyzed"


@pytest.mark.parametrize("count", [2000, 2001])
def test_real_candidate_capacity_preserves_event_but_excludes_whole_analysis_group(
    editorial_client, monkeypatch, count
):
    owner, posts, events, now = _seed(editorial_client, monkeypatch, 1)
    _annotate(editorial_client, owner, posts[0], now)
    with editorial_client.app.state.session_factory.begin() as session:
        original = session.scalar(
            select(ContentAnnotation).where(
                ContentAnnotation.owner_id == owner,
                ContentAnnotation.prompt_version == "analysis.annotate.v2",
            )
        )
        base = {
            column.name: getattr(original, column.name)
            for column in ContentAnnotation.__table__.columns
        }
        values = []
        for _ in range(count - 1):
            manifest = AnalysisObservationManifest.model_validate(original.input_manifest)
            manifest = manifest.model_copy(
                update={
                    "input_observation_ids": tuple(
                        sorted((*manifest.input_observation_ids, uuid4()), key=str)
                    )
                }
            )
            values.append(
                {
                    **base,
                    "id": uuid4(),
                    "input_manifest": manifest.model_dump(mode="json"),
                    "input_signature": manifest.signature,
                    "created_at": now - timedelta(seconds=1),
                }
            )
        # Extra controlled persisted candidates model many historical input batches;
        # the newest real producer result still wins below the safety capacity.
        session.execute(insert(ContentAnnotation), values)
    response = editorial_client.get(f"/api/publication/stories/{events[0]}")
    assert response.status_code == 200, response.text
    view = response.json()["sentiment"]
    assert view["current"]["sample_count"] == 1
    assert view["current"]["valid_count"] == int(count == 2000)
    assert view["samples"][0]["state"] == ("valid" if count == 2000 else "unavailable")
