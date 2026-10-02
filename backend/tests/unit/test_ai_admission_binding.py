import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai.services import AiService


def test_binding_composes_material_guards_and_cannot_replace_an_existing_epoch():
    engine = create_engine("sqlite://")
    events = []
    with Session(engine) as session:
        original = AiService(
            session, object(), guard=lambda current: events.append("lease"), execution_epoch=3
        )
        first = original.with_admission_guard(
            lambda current: events.append("first"), execution_epoch=3
        )
        second = first.with_admission_guard(lambda current: events.append("second"))
        with pytest.raises(ValueError, match="cannot change"):
            second.with_admission_guard(lambda current: None, execution_epoch=4)
        with pytest.raises(ValueError, match="must be positive"):
            AiService(session, object()).with_admission_guard(
                lambda current: None, execution_epoch=0
            )
        # Guard composition is immutable: binding another domain never modifies an existing service.
        assert original._admission_guard is None
        assert first._epoch == second._epoch == 3
        second._guard(session)
        second._admission_guard(session)
        assert events == ["lease", "first", "second"]
    engine.dispose()
