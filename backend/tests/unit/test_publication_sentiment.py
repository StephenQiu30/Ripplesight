"""Exact sentiment input selection, capacity, windows and exclusion invariants."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from analysis import public_sentiment as provider
from analysis.dimensions import resolve_post_dimensions
from analysis.models import ContentAnnotation
from content.analysis_schemas import AnalysisObservationManifest
from publication.report_sentiment import merge_public_sentiment_samples, public_report_sentiment
from publication.schemas import PublicSentimentSample

NOW = datetime(2026, 10, 13, tzinfo=UTC)


def _row(ref, *, inputs=(), sentiment="negative", relevant=True, at=NOW):
    manifest = AnalysisObservationManifest(
        post_observations={ref.content_version_id: ref.observation_id},
        comment_observations={},
        input_observation_ids=tuple(sorted({ref.observation_id, *inputs}, key=str)),
    )
    result = resolve_post_dimensions(
        dict(
            content_version_id=str(ref.content_version_id),
            relevant=relevant,
            relevance_reason="fixed",
            summary="fixed",
            sentiment=sentiment,
            viewpoints=[],
        ),
        content_version_id=ref.content_version_id,
        ai_call_id=uuid4(),
        retry_index=0,
    )
    return ContentAnnotation(
        id=uuid4(),
        owner_id=uuid4(),
        content_id=ref.content_id,
        content_version_id=ref.content_version_id,
        topic_id=uuid4(),
        topic_rule_version=1,
        prompt_version="analysis.annotate.v2",
        input_manifest=manifest.model_dump(mode="json"),
        input_signature=manifest.signature,
        dimension_results=result.dimension_results.model_dump(mode="json"),
        relevant=result.relevant,
        relevance_reason=result.relevance_reason,
        summary=result.summary,
        sentiment=result.sentiment,
        viewpoints=list(result.viewpoints),
        status=result.status,
        result_state=result.result_state,
        error_code=result.error_code,
        created_at=at,
        updated_at=at,
    )


def _read(monkeypatch, rows, refs):
    queries = []
    session = SimpleNamespace(
        in_transaction=lambda: True, scalars=lambda query: queries.append(query) or rows
    )
    monkeypatch.setattr(
        provider,
        "readable_annotation_ids_in_transaction",
        lambda *a, annotations, **k: {row.id for row in annotations},
    )
    result = provider.read_public_report_sentiments_in_transaction(
        session, owner_id=uuid4(), topic_id=uuid4(), references=refs, now=NOW
    )
    return result, queries


@pytest.mark.parametrize("latest", ["failed", "invalid", "private", "signature", "future"])
def test_latest_exact_observation_never_falls_back(monkeypatch, latest):
    ref = provider.PublicReportAnalysisRef(uuid4(), uuid4(), uuid4())
    old = _row(ref, at=NOW - timedelta(seconds=1))
    row = _row(
        ref,
        inputs=(uuid4(),) if latest == "private" else (),
        sentiment=42 if latest in {"failed", "invalid"} else "positive",
    )
    if latest == "failed":
        raw = dict(row.dimension_results)
        raw["sentiment"] = {**raw["sentiment"], "state": "failed"}
        row.dimension_results = raw
    elif latest == "signature":
        row.input_signature = "0" * 64
    elif latest == "future":
        row.updated_at = NOW + timedelta(seconds=1)
    result, _ = _read(monkeypatch, [row, old], (ref,))
    expected = latest if latest in {"failed", "invalid"} else "unavailable"
    assert result[ref.content_id].state == expected and result[ref.content_id].label is None


def test_other_observation_does_not_hide_current_and_merged_call_ids_are_allowed(monkeypatch):
    ref = provider.PublicReportAnalysisRef(uuid4(), uuid4(), uuid4())
    other = provider.PublicReportAnalysisRef(ref.content_id, ref.content_version_id, uuid4())
    row = _row(ref)
    dimensions = dict(row.dimension_results)
    dimensions["sentiment"] = {**dimensions["sentiment"], "ai_call_id": str(uuid4())}
    row.dimension_results = dimensions
    result, _ = _read(monkeypatch, [_row(other), row], (ref,))
    assert result[ref.content_id].state == "valid" and result[ref.content_id].label == "negative"


@pytest.mark.parametrize("count", [2000, 2001])
def test_candidate_capacity_applies_to_entire_input_group(monkeypatch, count):
    ref = provider.PublicReportAnalysisRef(uuid4(), uuid4(), uuid4())
    row = _row(ref)
    result, queries = _read(monkeypatch, [row] * count, (ref,))
    assert result[ref.content_id].state == ("valid" if count == 2000 else "unavailable")
    assert queries[0].compile().params["param_1"] == 2001


def _sample(
    *, at=NOW, label="negative", state="valid", backfill=False, identifier=None, source="x"
):
    return PublicSentimentSample(
        content_id=identifier or uuid4(),
        source_key=source,
        discovered_at=at,
        backfill=backfill,
        state=state,
        label=label,
    )


def test_adjacent_windows_boundaries_unknown_times_and_mutually_exclusive_denominators():
    samples = [
        _sample(),
        _sample(at=NOW - timedelta(hours=24)),
        _sample(at=NOW - timedelta(hours=48)),
        _sample(backfill=True, state="failed", label=None),
        _sample(backfill=None),
        _sample(state="not_analyzed", label=None),
        _sample(label="neutral"),
        _sample(at=NOW + timedelta(microseconds=1)),
        _sample(at=None),
        _sample(at=NOW.replace(tzinfo=None)),
    ]
    view = public_report_sentiment(samples, now=NOW)
    assert view.current.sample_count == 5 and view.current.valid_count == 2
    assert view.current.negative_ratio == 0.5 and view.current.analysis_coverage == 0.4
    assert view.current.excluded_counts == {"backfill": 1, "unavailable": 1, "not_analyzed": 1}
    assert view.current.sample_count == view.current.valid_count + sum(
        view.current.excluded_counts.values()
    )
    assert view.previous.sample_count == view.previous.negative == 1
    assert view.time_unknown_count == 3
    empty = public_report_sentiment([], now=NOW)
    assert empty.current.negative_ratio is None and empty.current.analysis_coverage is None


@pytest.mark.parametrize("conflict", ["label", "state", "source_key", "backfill", "discovered_at"])
def test_global_duplicates_and_conflicts_remain_excluded(conflict):
    sample = _sample()
    changed = sample.model_copy(
        update={
            conflict: {
                "label": "positive",
                "state": "failed",
                "source_key": "hn",
                "backfill": True,
                "discovered_at": NOW - timedelta(hours=25),
            }[conflict]
        }
    )
    merged = {}
    merge_public_sentiment_samples(merged, [sample, sample])
    merge_public_sentiment_samples(merged, [changed, sample])
    view = public_report_sentiment(list(merged.values()), now=NOW, include_samples=False)
    assert len(merged) == 1 and view.samples == []
    assert view.current.valid_count == 0 and view.current.negative_ratio is None
    assert view.current.excluded_counts == ({} if conflict == "discovered_at" else {"conflict": 1})
    assert view.time_unknown_count == int(conflict == "discovered_at")


@pytest.mark.parametrize(
    "flags",
    [(None, False), (False, None), (True, None), (None, True), (True, False), (False, True)],
)
def test_backfill_metadata_conflict_is_deterministic_across_scan_orders(flags):
    sample = _sample(backfill=flags[0])
    other = sample.model_copy(update={"backfill": flags[1]})
    merged = {}
    merge_public_sentiment_samples(merged, [sample, other, sample, other])
    view = public_report_sentiment(list(merged.values()), now=NOW)
    assert view.current.excluded_counts == {"conflict": 1}
    assert view.current.valid_count == 0
