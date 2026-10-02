from uuid import uuid4

from publication.notification_reading import notification_dedupe_key


def test_same_occurrence_reports_share_key_but_developments_do_not_share_story_root_key() -> None:
    occurrence, development, first, sibling, progress = (uuid4() for _ in range(5))
    assert notification_dedupe_key(content_id=first, fact_id=occurrence) == notification_dedupe_key(
        content_id=sibling, fact_id=occurrence
    )
    # development can refer to occurrence as root_fact_id; canonical occurrence IDs differ.
    assert notification_dedupe_key(
        content_id=progress, fact_id=development
    ) != notification_dedupe_key(content_id=first, fact_id=occurrence)
    assert notification_dedupe_key(content_id=first, fact_id=None) == f"item:{first}"
