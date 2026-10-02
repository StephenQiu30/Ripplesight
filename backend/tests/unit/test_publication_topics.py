from datetime import UTC, datetime

from publication.listing import PublicationListingMember
from publication.topics import (
    industry_topics,
    topic_indexable,
    topic_match_tags_for_slug,
    topic_summaries,
)
from tests.unit.test_publication_groups import member


def test_company_topics_only_accept_subject_evidence_and_keep_upstream_index_thresholds() -> None:
    now = datetime(2026, 10, 2, tzinfo=UTC)
    incidental = member(at=now)
    subject = member(at=now)
    directory = topic_summaries(
        (
            PublicationListingMember(incidental.projection, ("OpenAI",)),
            PublicationListingMember(subject.projection, ("entity:openai",)),
        ),
        now=now,
    )
    openai = next(topic for topic in directory.topics if topic.slug == "openai")
    assert openai.total == 1 and openai.recent == 1 and not openai.indexable
    assert topic_match_tags_for_slug("openai") == ("entity:openai",)
    assert topic_match_tags_for_slug("unknown") is None
    assert len({topic.slug for topic in industry_topics()}) == len(industry_topics())
    assert not topic_indexable(total=19, recent=1)
    assert not topic_indexable(total=49, recent=0)
    assert topic_indexable(total=20, recent=1)
    assert topic_indexable(total=50, recent=0)
