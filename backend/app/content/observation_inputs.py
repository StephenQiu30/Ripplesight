"""Observation-level actual inputs, independent of another source's identical text version."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from content.models import ContentObservation, ContentObservationInput
from core.errors import ApplicationError


def observation_input_closure_in_transaction(
    session: Session, *, owner_id: UUID, observation_ids: tuple[UUID, ...]
) -> tuple[UUID, ...]:
    """Require a complete, explicitly proven graph for the exact original roots."""
    if not session.in_transaction() or not 1 <= len(observation_ids) <= 2000:
        raise ApplicationError("editorial_material_unavailable")
    result = observation_input_closures_in_transaction(
        session, owner_id=owner_id, observation_groups={"single": observation_ids}
    )["single"]
    if result is None:
        raise ApplicationError("editorial_material_unavailable")
    return result


def _load_observation_graph(
    session: Session, *, owner_id: UUID, roots: set[UUID]
) -> tuple[dict[UUID, set[UUID]], set[UUID]]:
    if len(roots) > 20000:
        raise ApplicationError("editorial_material_unavailable")
    graph: dict[UUID, set[UUID]] = {}
    invalid: set[UUID] = set()
    pending = set(roots)
    while pending:
        rows = tuple(
            session.scalars(
                select(ContentObservation)
                .where(ContentObservation.owner_id == owner_id, ContentObservation.id.in_(pending))
                .execution_options(populate_existing=True)
            )
        )
        missing = pending - {r.id for r in rows}
        invalid.update(missing)
        graph.update((identifier, set()) for identifier in missing)
        edges: dict[UUID, set[UUID]] = {}
        for output, original in session.execute(
            select(
                ContentObservationInput.output_observation_id,
                ContentObservationInput.input_observation_id,
            ).where(
                ContentObservationInput.owner_id == owner_id,
                ContentObservationInput.output_observation_id.in_(pending),
            )
        ):
            edges.setdefault(output, set()).add(original)
        for r in rows:
            deps = edges.get(r.id, set())
            # A version's equal text cannot prove this observation's actual inputs.
            if (
                r.input_basis not in {"source_v1", "observations_v1"}
                or (r.input_basis == "source_v1" and deps)
                or (r.input_basis == "observations_v1" and not deps)
            ):
                invalid.add(r.id)
            graph[r.id] = deps
        pending = {item for row in rows for item in graph[row.id] if item not in graph}
        if len(set(graph) | pending) > 20000:
            raise ApplicationError("editorial_material_unavailable")
    return graph, invalid


def _closure_for_roots(
    roots: tuple[UUID, ...],
    graph: dict[UUID, set[UUID]],
    invalid: set[UUID],
) -> tuple[UUID, ...] | None:
    reached: set[UUID] = set()
    pending = set(roots)
    while pending:
        identifier = pending.pop()
        if identifier in reached:
            continue
        if identifier in invalid or identifier not in graph:
            return None
        reached.add(identifier)
        if len(reached) > 2000:
            return None
        pending.update(graph[identifier] - reached)
    visiting: set[UUID] = set()
    done: set[UUID] = set()
    for identifier in reached:
        stack = [(identifier, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                visiting.remove(node)
                done.add(node)
                continue
            if node in done:
                continue
            if node in visiting:
                return None
            visiting.add(node)
            stack.append((node, True))
            stack.extend((dep, False) for dep in graph[node] if dep not in done)
    return tuple(sorted(reached, key=str))


def observation_input_closures_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    observation_groups: dict[str, tuple[UUID, ...]],
) -> dict[str, tuple[UUID, ...] | None]:
    """Batch graph reads, then independently validate each frozen output's closure."""
    if not session.in_transaction() or len(observation_groups) > 2000:
        raise ValueError("bounded observation groups require caller transaction")
    result: dict[str, tuple[UUID, ...] | None] = {}
    valid = []
    for key, roots in observation_groups.items():
        if not 1 <= len(roots) <= 2000 or len(set(roots)) != len(roots):
            result[key] = None
        else:
            valid.append((key, roots))
    for start in range(0, len(valid), 100):
        batch = dict(valid[start : start + 100])
        try:
            graph, invalid = _load_observation_graph(
                session, owner_id=owner_id, roots={i for roots in batch.values() for i in roots}
            )
        except ApplicationError:
            if len(batch) == 1:
                result.update((key, None) for key in batch)
            else:
                # The aggregate bound must not reject independent valid groups.
                for key, roots in batch.items():
                    result.update(
                        observation_input_closures_in_transaction(
                            session, owner_id=owner_id, observation_groups={key: roots}
                        )
                    )
            continue
        result.update(
            (key, _closure_for_roots(roots, graph, invalid)) for key, roots in batch.items()
        )
    return result


def freeze_observation_inputs_in_transaction(
    session: Session, *, owner_id: UUID, observation_ids: tuple[UUID, ...], now: datetime
) -> tuple[UUID, ...]:
    """Freeze only a complete graph whose exact inputs remain currently readable."""
    # Local import breaks the graph reader / permission reader dependency cycle.
    from content.observation_reading import readable_observation_groups_in_transaction

    closure = readable_observation_groups_in_transaction(
        session, owner_id=owner_id, observation_groups={"single": observation_ids}, now=now
    )["single"]
    if closure is None:
        raise ApplicationError("editorial_material_unavailable")
    return closure


def save_observation_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    output_observation_id: UUID,
    input_observation_ids: tuple[UUID, ...],
) -> None:
    """Persist immutable actual inputs; never supply proof to an unknown old output."""
    if (
        not session.in_transaction()
        or not 1 <= len(input_observation_ids) <= 2000
        or output_observation_id in input_observation_ids
    ):
        raise ValueError("bounded non-self observation inputs required")
    session.flush()
    output = session.scalar(
        select(ContentObservation)
        .where(
            ContentObservation.owner_id == owner_id, ContentObservation.id == output_observation_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if output is None or output.input_basis != "observations_v1":
        raise ApplicationError("editorial_material_unavailable")
    inputs = set(input_observation_ids)
    closure = observation_input_closure_in_transaction(
        session, owner_id=owner_id, observation_ids=tuple(inputs)
    )
    if output_observation_id in closure:
        raise ApplicationError("editorial_material_unavailable")
    existing = set(
        session.scalars(
            select(ContentObservationInput.input_observation_id).where(
                ContentObservationInput.owner_id == owner_id,
                ContentObservationInput.output_observation_id == output_observation_id,
            )
        )
    )
    if existing and existing != inputs:
        raise ApplicationError("idempotency_conflict")
    for identifier in sorted(inputs, key=str):
        session.execute(
            insert(ContentObservationInput)
            .values(
                owner_id=owner_id,
                output_observation_id=output_observation_id,
                input_observation_id=identifier,
            )
            .on_conflict_do_nothing()
        )
