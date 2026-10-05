"""Original source run persists filtering counts and bounded excerpts across replay."""

import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_editorial_source_profiles import NOW, begin, job, setup
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_sources import admitted_http

from connections.editorial_models import EditorialSourceMaterialReceipt, EditorialSourceRun
from content.models import ContentObservation
from sources.editorial_registry import EditorialSourceRegistry


@pytest.mark.parametrize("all_filtered", [False, True])
def test_filters_are_persisted_once_without_retaining_rejected_materials(engine, all_filtered):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = setup(
            session,
            kind="json_list",
            configuration={
                "url": "https://example.com/list",
                "allowed_hosts": ["example.com"],
                "title_paths": ["title"],
                "summary_paths": ["summary"],
                "url_template": "https://example.com/{id}",
                "require_any_terms": ["AI"],
                "summary_max_chars": 300,
                "ingest_noise_filter": {"drop_markers": ["spam"]},
            },
        )
        accepted, operation = job(session, owner, profile)
        prepared = begin(service, owner, profile, accepted, operation)
        listing = json.dumps(
            [
                {
                    "id": 1,
                    "title": "Unrelated" if all_filtered else "AI update",
                    "summary": "字" * 500,
                },
                {"id": 2, "title": "daily", "summary": "said"},
                {"id": 3, "title": "AI spam"},
            ]
        )
        http, _ = admitted_http(lambda request: httpx.Response(200, text=listing))
        registry = EditorialSourceRegistry(
            http=http, clock=lambda: NOW, source_added_at=prepared.source_added_at
        )
        try:
            page = registry.collect(prepared.profile, prepared.cursor, prepared.known)
        finally:
            registry.close()
        created = int(not all_filtered)
        assert page.status == "complete" and page.filtered == 3 - created
        staged = service.stage_page(owner_id=owner, run_id=prepared.result.run_id, page=page)
        assert staged.found == created and staged.filtered == 3 - created
        result = service.apply_page(owner_id=owner, run_id=prepared.result.run_id)
        assert result.status == "succeeded" and result.created == created
        assert result.filtered == 3 - created
        session.expire_all()
        assert service.apply_page(owner_id=owner, run_id=result.run_id) == result
        assert service.list_runs(owner_id=owner, profile_id=profile.id) == (result,)
        with session.begin():
            run = session.get(EditorialSourceRun, result.run_id)
            assert run.prepared_page == {"_filter_receipt": {"filtered": 3 - created}}
            assert len(list(session.scalars(select(ContentObservation)))) == created
            receipts = list(session.scalars(select(EditorialSourceMaterialReceipt)))
            assert len(receipts) == created
            if receipts:
                assert receipts[0].material_metadata["summary_truncated"] is True
