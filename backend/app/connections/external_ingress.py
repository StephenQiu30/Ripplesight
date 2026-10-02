"""External item receipts share the original SourceRun and material writer transaction."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

from pydantic import JsonValue, ValidationError

from connections.editorial_models import (
    EditorialSourceProfile,
    EditorialSourceRun,
    EditorialSourceVersion,
)
from connections.editorial_schemas import ExternalIngressItem
from core.errors import ApplicationError
from events.heat import record_source_fetch_success_in_transaction
from sources.editorial_schemas import (
    EditorialCursor,
    EditorialMaterial,
    EditorialPage,
    EditorialRunResult,
)

if TYPE_CHECKING:
    from connections.editorial_services import EditorialSourceService, Guard, Sink


def prepare_external_materials(
    values: tuple[EditorialMaterial | dict[str, JsonValue], ...],
) -> tuple[tuple[EditorialMaterial, ...], tuple[ExternalIngressItem, ...]]:
    materials: list[EditorialMaterial] = []
    items: list[ExternalIngressItem] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(values):
        try:
            material = EditorialMaterial.model_validate(value)
        except ValidationError:
            items.append(
                ExternalIngressItem(index=index, status="rejected", reason="invalid_material")
            )
            continue
        duplicate_of = seen.get(material.identity_key)
        if duplicate_of is not None:
            items.append(
                ExternalIngressItem(
                    index=index,
                    identity_key=material.identity_key,
                    status="duplicate",
                    duplicate_of=duplicate_of,
                    reason="duplicate_input_pending",
                )
            )
            continue
        seen[material.identity_key] = index
        materials.append(material)
        items.append(
            ExternalIngressItem(index=index, identity_key=material.identity_key, status="pending")
        )
    return tuple(materials), tuple(items)


def same_batch_duplicate_receipt(
    duplicate: ExternalIngressItem, original: ExternalIngressItem
) -> ExternalIngressItem:
    if original.status == "rejected":
        return duplicate.model_copy(
            update={
                "status": "rejected",
                "reason": original.reason,
                "content_id": None,
                "content_version_id": None,
            }
        )
    return duplicate.model_copy(
        update={
            "content_id": original.content_id,
            "content_version_id": original.content_version_id,
            "reason": "same_batch_material"
            if original.content_id is not None
            else "duplicate_input_pending",
        }
    )


def apply_external_page_in_transaction(
    service: EditorialSourceService,
    *,
    run: EditorialSourceRun,
    profile: EditorialSourceProfile,
    version: EditorialSourceVersion,
    page: EditorialPage,
    guard: Guard | None,
    sink: Sink | None,
) -> EditorialRunResult:
    session = service._session
    if not session.in_transaction() or run.prepared_page is None:
        raise RuntimeError("external application requires caller transaction and prepared receipt")
    raw_items = run.prepared_page.get("external_items")
    items = (
        tuple(ExternalIngressItem.model_validate(value) for value in cast(list[object], raw_items))
        if raw_items is not None
        else prepare_external_materials(page.materials)[1]
    )
    materials = {material.identity_key: material for material in page.materials}
    results: list[ExternalIngressItem] = []
    first = EditorialCursor.model_validate(profile.cursor).initialized_at is None
    for item in items:
        if guard is not None and not guard(session, run.owner_id, run.job_id):
            raise ApplicationError("editorial_version_conflict")
        service._require_ready(profile, version, service._clock())
        if item.duplicate_of is not None:
            original = results[item.duplicate_of]
            results.append(same_batch_duplicate_receipt(item, original))
            continue
        if item.status == "rejected":
            results.append(item)
            continue
        material = materials.get(item.identity_key or "")
        if material is None:
            raise RuntimeError("prepared external item lost its fixed material")
        with session.begin_nested():
            applied = service._apply_material_in_transaction(
                p=profile, v=version, run=run, page=page, first=first, material=material, sink=sink
            )
            session.flush()
        results.append(
            item.model_copy(
                update={
                    "status": applied.status,
                    "change": applied.change,
                    "content_id": applied.content_id,
                    "content_version_id": applied.content_version_id,
                }
            )
        )
    if guard is not None and not guard(session, run.owner_id, run.job_id):
        raise ApplicationError("editorial_version_conflict")
    service._require_ready(profile, version, service._clock())
    now = service._clock()
    rejected = any(item.status == "rejected" for item in results)
    run.status, run.failure_code = (
        ("partial", "external_items_rejected") if rejected else ("succeeded", None)
    )
    run.updated_at, profile.updated_at = now, now
    run.prepared_page = {"external_items": [item.model_dump(mode="json") for item in results]}
    if rejected:
        service._failure_health(profile, version, run.failure_code, now, unknown=False)
    else:
        profile.cursor = page.cursor.model_dump(mode="json")
        profile.last_ok_at, profile.health, profile.failure_count, profile.last_failure_code = (
            now,
            "ok",
            0,
            None,
        )
        profile.next_fetch_at = now + timedelta(minutes=version.interval_minutes)
        record_source_fetch_success_in_transaction(
            session,
            owner_id=run.owner_id,
            source_key=profile.source_key,
            selector_kind="source",
            selector_ref=profile.source_key,
            completed_at=now,
        )
    return service._result(run)
