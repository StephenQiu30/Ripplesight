from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from core.errors import (
    ApplicationError,
    DependencyUnavailableError,
    ErrorCategory,
    get_error_category,
)
from leaderboard.reads import LeaderboardReadService


def test_unpublished_board_is_absent_not_database_failure() -> None:
    service = LeaderboardReadService(Mock(spec=Session))
    service.session.scalar.return_value = None
    with pytest.raises(ApplicationError) as caught:
        service.board()
    assert caught.value.code == "leaderboard_not_published"
    assert get_error_category(caught.value.code) == ErrorCategory.NOT_FOUND
    service.session.scalar.assert_called_once()


def test_database_dependency_failure_is_not_reclassified_as_empty() -> None:
    service = LeaderboardReadService(Mock(spec=Session))
    failure = DependencyUnavailableError()
    service.session.scalar.side_effect = failure
    with pytest.raises(DependencyUnavailableError) as caught:
        service.board()
    assert caught.value is failure
    assert caught.value.code == "database_unavailable"
