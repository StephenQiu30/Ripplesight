from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from sources.contracts import SourceStopReason
from sources.editorial_body import EditorialBodyAdmission, LocalEditorialBodyFetcher
from sources.editorial_body_review import EditorialBodyReview
from sources.editorial_schemas import (
    EditorialBodyConfiguration,
    EditorialBodyTarget,
    EditorialMaterial,
    EditorialSourceConfiguration,
)

NOW = datetime(2026, 10, 4, 3, tzinfo=UTC)


def configuration(**changes):
    return EditorialBodyConfiguration(
        enabled=True,
        allowed_hosts=("example.com",),
        review=EditorialBodyReview(
            read_reference="controlled-read",
            save_reference="controlled-save",
            fee_reference="controlled-zero",
            egress_reference="controlled-egress",
            request_bound_reference="controlled-target-bound",
            deployment_reference="controlled-runtime",
            reviewed_at=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(hours=1),
        ),
        **changes,
    )


def target(url="https://example.com/post"):
    return EditorialBodyTarget(
        owner_id=uuid4(),
        run_id=uuid4(),
        profile_id=uuid4(),
        configuration_version=2,
        profile_revision=2,
        job_id=uuid4(),
        operation_id=uuid4(),
        content_id=uuid4(),
        expected_content_version_id=uuid4(),
        feed_observation_id=uuid4(),
        material=EditorialMaterial(
            url=url, identity_key="guid:one", title="Original title", excerpt="Source summary"
        ),
    )


def admission(t):
    return EditorialBodyAdmission(
        profile_id=t.profile_id,
        configuration_version=t.configuration_version,
        profile_revision=t.profile_revision,
        configuration_sha256="a" * 64,
        proof_reference="server-policy:controlled",
        component_version="controlled-v1",
        reviewed_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
        allowed_hosts=frozenset({"example.com"}),
        read_allowed=True,
        save_allowed=True,
        zero_supplier_fee_verified=True,
        target_egress_verified=True,
    )


def factory(t, *, proof=None, allow=True, missing=None):
    calls, starts, settlements = [], [], []

    def transport(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "markdown": "# Complete source body\n" + "a" * 30,
                    "metadata": {"statusCode": 200, "url": t.target_url, "title": "Provider title"},
                },
            },
        )

    def before(item):
        starts.append(item)
        return allow

    kwargs = dict(
        admission=lambda _: proof or admission(t),
        before_request=before,
        settle=lambda item, result: settlements.append((item, result)),
    )
    if missing:
        kwargs[missing] = None
    return (
        LocalEditorialBodyFetcher(
            base_url="http://127.0.0.1:3002",
            configuration_sha256="a" * 64,
            transport=httpx.MockTransport(transport),
            clock=lambda: NOW,
            **kwargs,
        ),
        calls,
        starts,
        settlements,
    )


@pytest.mark.parametrize("missing", ["admission", "before_request", "settle"])
def test_missing_proof_or_resource_gate_never_calls_local_service(missing):
    t = target()
    fetcher, calls, starts, settlements = factory(t, missing=missing)
    result = fetcher.fetch(t, configuration())
    assert result.stop_reason == SourceStopReason.ACCESS_DENIED
    assert result.collector_call_count == 0 and calls == starts == settlements == []


@pytest.mark.parametrize(
    "changes",
    [
        {"expires_at": NOW},
        {"reviewed_at": NOW + timedelta(seconds=1)},
        {"configuration_sha256": "b" * 64},
        {"configuration_version": 3},
        {"profile_revision": 3},
        {"profile_id": uuid4()},
        {"read_allowed": False},
        {"save_allowed": False},
        {"zero_supplier_fee_verified": False},
        {"target_egress_verified": False},
        {"allowed_hosts": frozenset({"other.example"})},
    ],
)
def test_fixed_profile_rights_fee_and_egress_are_required(changes):
    t = target()
    fetcher, calls, starts, settlements = factory(t, proof=replace(admission(t), **changes))
    assert fetcher.fetch(t, configuration()).collector_call_count == 0
    assert calls == starts == settlements == []


def test_review_and_exact_target_host_are_required():
    t = target("https://other.example/post")
    fetcher, calls, starts, _ = factory(t)
    assert fetcher.fetch(t, configuration()).collector_call_count == 0
    assert (
        fetcher.fetch(t, configuration().model_copy(update={"review": None})).collector_call_count
        == 0
    )
    assert calls == starts == []


def test_budget_refusal_stops_before_request_and_does_not_settle_a_call():
    t = target()
    fetcher, calls, starts, settlements = factory(t, allow=False)
    result = fetcher.fetch(t, configuration())
    assert result.stop_reason == SourceStopReason.BUDGET_EXHAUSTED
    assert calls == settlements == [] and starts == [t]


def test_bounded_local_scrape_keeps_target_requests_unknown_and_settles_once():
    t = target()
    fetcher, calls, starts, settlements = factory(t)
    result = fetcher.fetch(t, configuration(max_content_characters=10))
    assert result.document is not None and result.document.text_scope == "truncated"
    assert len(result.document.text) == 10 and result.collector_call_count == 1
    assert result.target_request_count is None and len(calls) == 1 and starts == [t]
    assert settlements == [(t, result)]
    assert calls[0].url == "http://127.0.0.1:3002/v2/scrape"
    assert b'"formats":["markdown"]' in calls[0].content
    assert b'"timeout":20000' in calls[0].content


def test_response_byte_limit_stops_without_fallback():
    t = target()
    fetcher, calls, _, settlements = factory(t)
    result = fetcher.fetch(t, configuration(max_response_bytes=10))
    assert result.document is None and result.collector_call_count == 1
    assert len(calls) == 1 and len(settlements) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://api.firecrawl.dev",
        "http://localhost:3002",
        "http://127.0.0.1:3003",
        "http://127.0.0.1:3002/v2",
        "http://user@127.0.0.1:3002",
    ],
)
def test_body_service_is_fixed_to_the_local_endpoint(url):
    with pytest.raises(ValueError):
        LocalEditorialBodyFetcher(base_url=url, configuration_sha256="a" * 64)


def test_profile_body_is_explicit_bounded_and_does_not_enable_other_kinds():
    assert (
        EditorialSourceConfiguration(
            kind="rss", feed_url="https://example.com/feed", allowed_hosts=("example.com",)
        ).body_extraction
        is None
    )
    for limit in (
        dict(timeout_seconds=21),
        dict(max_response_bytes=2 * 1024 * 1024 + 1),
        dict(max_content_characters=100001),
        dict(max_fetches=21),
        dict(max_target_requests=21),
    ):
        with pytest.raises(ValidationError):
            configuration(**limit)
    with pytest.raises(ValidationError):
        configuration().model_validate(
            {**configuration().model_dump(), "allowed_hosts": ("127.0.0.1",)}
        )
    with pytest.raises(ValidationError):
        EditorialSourceConfiguration(kind="x_search", query="news", body_extraction=configuration())
