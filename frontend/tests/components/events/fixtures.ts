export function publicItem(id = "public-item"): HotKeyAPI.PublicItemView {
  return {
    id,
    revision: 1,
    title: `公开报道 ${id}`,
    original_title: null,
    summary: "公开报道摘要",
    source: {
      key: "controlled",
      name: "受控来源",
      kind: "rss",
      first_party: true,
    },
    original_url: "https://source.example/item",
    reading_url: `/discover/items/${id}`,
    published_at: null,
    discovered_at: "2026-10-02T00:00:00Z",
    timeline_at: "2026-10-02T00:00:00Z",
    category: "industry",
    tags: [],
    score: null,
    selected: true,
    reason: null,
    event_id: "event",
    fact_id: "fact",
    indexable: false,
  };
}

export function member(id = "member"): HotKeyAPI.EventMemberReadView {
  return {
    id,
    content_id: `content-${id}`,
    content_version_id: `version-${id}`,
    source_key: "controlled",
    assignment_origin: "model",
    added_revision: 1,
    removed_revision: null,
    availability: "readable",
    content: {
      id: `content-${id}`,
      source_key: "controlled",
      object_type: "post",
      native_scope: null,
      external_id: id,
      identity_basis: null,
      current_visibility: null,
      representative_comment: null,
      representative_comment_state: "none",
      observation: {
        id: `observation-${id}`,
        observed_at: "2026-10-02T00:00:00Z",
        received_at: "2026-10-02T00:01:00Z",
        published_at: null,
        published_at_fractional_digits: null,
        canonical_url: "https://source.example/item",
        final_url: null,
        author_external_id: null,
        metrics: {
          like_count: 0,
          comment_count: null,
          repost_count: null,
          view_count: null,
          play_count: null,
          danmaku_count: null,
        },
        content_version: {
          id: `version-${id}`,
          text_scope: "full",
          text_origin: "source",
          text_origin_ref: null,
          title: `固定标题 ${id}`,
          body: `固定正文 ${id}`,
          truncation_reason: null,
          relations: [],
        },
      },
    },
  };
}

export function fact(
  id = "fact",
  memberId = "member",
): HotKeyAPI.EventFactView {
  return {
    id,
    revision: 1,
    relation: "root",
    root_fact_id: null,
    title: `事实 ${id}`,
    summary: "固定事实摘要",
    first_seen_at: "2026-10-02T00:00:00Z",
    first_seen_basis: "published",
    evidence_state: "complete",
    members: [
      {
        event_member_id: memberId,
        content_id: `content-${memberId}`,
        content_version_id: `version-${memberId}`,
        role: "primary",
        assignment_origin: "model",
        availability: "readable",
      },
    ],
  };
}

export function heat(
  window_end = "2026-10-02T01:00:00Z",
  value = 2,
): HotKeyAPI.EventAttentionView {
  return {
    event_id: "event",
    event_revision: 1,
    window_end,
    heat: value,
    eligible: true,
    participant_count: 2,
    editorial_participant_count: 1,
    signal_participant_count: 1,
    comparable_participant_count: 2,
    uncomparable_participant_count: 0,
    previous_heat: 0,
    comparable_heat: value,
    comparable_previous_heat: 0,
    trend: "unknown",
    trend_pct: null,
    complete: true,
    badges: [],
    source_names: ["受控来源"],
    roster: [],
    representative: null,
    interaction: null,
  };
}
