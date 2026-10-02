declare namespace HotKeyAPI {
  type AccessView = {
    /** Domestic */
    domestic: boolean;
    /** Weights Url */
    weights_url: string | null;
  };

  type AiCapabilityChoice = {
    /** Key */
    key:
      | "prefilter"
      | "score"
      | "understand"
      | "summarize"
      | "structure"
      | "group"
      | "groupReview"
      | "digest"
      | "report"
      | "translate"
      | "monitor";
    /** Label */
    label: string;
    /** Env */
    env: string;
    /** Default Model */
    default_model?: string;
    current: FrozenAiModel;
    /** Source */
    source: "admin" | "env" | "default";
  };

  type AiCostCircuitAckInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Version */
    expected_version: number;
    /** Call Id */
    call_id: string;
    /** Reason */
    reason: string;
  };

  type AiCostCircuitView = {
    /** Call Id */
    call_id: string;
    /** Provider */
    provider: string;
    /** Model */
    model: string;
    /** Currency */
    currency: "USD" | "CNY";
    /** Cost Actual Micros */
    cost_actual_micros: number;
    /** Cost Cap Micros */
    cost_cap_micros: number;
    /** Acknowledged */
    acknowledged: boolean;
    /** Created At */
    created_at: string;
  };

  type AiModelChoice = {
    /** Key */
    key: string;
    /** Provider */
    provider: string;
    /** Model */
    model: string;
    /** Vision */
    vision: boolean;
    /** Configured */
    configured: boolean;
    /** Component Key */
    component_key: string;
    /** Currency */
    currency: "USD" | "CNY" | null;
    /** Input Rate Micros Per Million */
    input_rate_micros_per_million: string | null;
    /** Output Rate Micros Per Million */
    output_rate_micros_per_million: string | null;
  };

  type AiModelConfigurationView = {
    /** Version */
    version: number;
    /** Created At */
    created_at: string | null;
    /** Capabilities */
    capabilities: AiCapabilityChoice[];
    /** Choices */
    choices: AiModelChoice[];
    /** Calls Enabled */
    calls_enabled: boolean;
    /** Paid Requests Enabled */
    paid_requests_enabled: boolean;
    /** Compatible Requests Enabled */
    compatible_requests_enabled: boolean;
  };

  type AiModelOverview = {
    /** Days */
    days: number;
    configuration: AiModelConfigurationView;
    /** Usage */
    usage: AiModelUsageView[];
    /** History */
    history: OperatorAuditView[];
    /** Cost Circuits */
    cost_circuits?: AiCostCircuitView[];
  };

  type AiModelSwitchInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Version */
    expected_version: number;
    /** Capability */
    capability:
      | "prefilter"
      | "score"
      | "understand"
      | "summarize"
      | "structure"
      | "group"
      | "groupReview"
      | "digest"
      | "report"
      | "translate"
      | "monitor";
    /** Model Key */
    model_key?: string | null;
    /** Reason */
    reason: string;
    /** Actor */
    actor?: string;
  };

  type AiModelUsageView = {
    /** Capability */
    capability:
      | "prefilter"
      | "score"
      | "understand"
      | "summarize"
      | "structure"
      | "group"
      | "groupReview"
      | "digest"
      | "report"
      | "translate"
      | "monitor"
      | string;
    /** Purpose */
    purpose: string;
    /** Provider */
    provider: string;
    /** Model */
    model: string;
    /** Prompt Version */
    prompt_version: string;
    /** Calls */
    calls: number;
    /** Succeeded */
    succeeded: number;
    /** Failed */
    failed: number;
    /** Unknown */
    unknown: number;
    /** Running */
    running?: number;
    /** Latency P50 Ms */
    latency_p50_ms: number | null;
    /** Latency P95 Ms */
    latency_p95_ms: number | null;
    /** Input Tokens */
    input_tokens: number;
    /** Cached Input Tokens */
    cached_input_tokens: number;
    /** Output Tokens */
    output_tokens: number;
    /** Currency */
    currency: string | null;
    /** Cost Estimate Micros */
    cost_estimate_micros: number | null;
    /** Cost Actual Micros */
    cost_actual_micros: number | null;
    /** Cost Cap Micros */
    cost_cap_micros: number | null;
  };

  type AnnotationResultState = "pending" | "failed" | "invalid" | "valid";

  type AnnotationStatus = "annotated" | "unanalyzed";

  type archiveMonitorTopicParams = {
    topic_id: string;
  };

  type AttentionRosterView = {
    /** Participant Key */
    participant_key: string;
    /** Source Id */
    source_id: string;
    /** Source Name */
    source_name: string;
    /** Mode */
    mode: "editorial" | "signal" | "isolated";
    /** Tier */
    tier: "T1" | "T1_5" | "T2" | null;
    /** First Party */
    first_party: boolean;
    /** Source Time */
    source_time: string;
    /** Content Id */
    content_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Title */
    title: string | null;
    /** Canonical Url */
    canonical_url: string | null;
    /** Fact Id */
    fact_id: string | null;
  };

  type AttentionSourceInput = {
    /** Source Key */
    source_key: string;
    /** Selector Kind */
    selector_kind: "source" | "author" | "native_scope" | "canonical_host";
    /** Selector Ref */
    selector_ref: string;
    /** Name */
    name: string;
    /** Mode */
    mode: "editorial" | "signal" | "isolated";
    /** Group Key */
    group_key?: string | null;
    /** Owner Entity Key */
    owner_entity_key?: string | null;
    /** First Party */
    first_party?: boolean;
    /** Tier */
    tier?: "T1" | "T1_5" | "T2" | null;
    /** Scheduled */
    scheduled?: boolean;
    /** Enabled */
    enabled?: boolean;
    /** Interval Seconds */
    interval_seconds?: number;
    /** Expected Revision */
    expected_revision?: number | null;
  };

  type AttentionSourceView = {
    /** Id */
    id: string;
    /** Source Key */
    source_key: string;
    /** Selector Kind */
    selector_kind: string;
    /** Selector Ref */
    selector_ref: string;
    /** Name */
    name: string;
    /** Revision */
    revision: number;
    /** Mode */
    mode: "editorial" | "signal" | "isolated";
    /** Group Key */
    group_key: string | null;
    /** Owner Entity Key */
    owner_entity_key: string | null;
    /** First Party */
    first_party: boolean;
    /** Tier */
    tier: "T1" | "T1_5" | "T2" | null;
    /** Scheduled */
    scheduled: boolean;
    /** Enabled */
    enabled: boolean;
    /** Interval Seconds */
    interval_seconds: number;
    /** Last Successful Fetch At */
    last_successful_fetch_at: string | null;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
  };

  type AuditResolutionInput = {
    /** Operation Id */
    operation_id: string;
    /** Reason */
    reason: string;
    /** Outcome */
    outcome: "delivered" | "not_delivered";
  };

  type BoardMetaView = {
    /** Key */
    key: "overall" | "coding" | "reasoning" | "knowledge" | "professional";
    /** Name */
    name: string;
    /** Description */
    description: string;
    /** How To Read */
    how_to_read: string;
    /** Source Count */
    source_count: number;
    /** Operator Count */
    operator_count: number;
    /** Model Count */
    model_count: number;
    /** Solver Optimal */
    solver_optimal: boolean;
    /** Connected Components */
    connected_components: number;
    /** Score Definition */
    score_definition: string;
    /** Display Method */
    display_method: string;
    /** Max Optimization Gap */
    max_optimization_gap: number;
    /** Observed Weighted Agreement */
    observed_weighted_agreement: number;
  };

  type BoardTabView = {
    /** Key */
    key: "overall" | "coding" | "reasoning" | "knowledge" | "professional";
    /** Name */
    name: string;
    /** Href */
    href: string;
  };

  type BoardView = {
    run: RunView;
    board: BoardMetaView;
    /** Tabs */
    tabs: BoardTabView[];
    /** Entries */
    entries: RankingEntryView[];
    /** Filter Entries */
    filter_entries: RankingEntryView[];
    /** Pending */
    pending: PendingModelView[];
  };

  type BooleanCondition = {
    /** Path */
    path: string;
    /** Equals */
    equals: boolean;
  };

  type BrandView = {
    /** Src */
    src: string | null;
    /** Monogram */
    monogram: string;
    /** Raster */
    raster?: boolean;
  };

  type BudgetMetric =
    | "network_request"
    | "collector_call"
    | "analysis_attempt"
    | "concurrency_slot"
    | "x_api_usd_micros"
    | "provider_cny_micros"
    | "provider_usd_micros";

  type BudgetPolicyInput = {
    /** Budget Key */
    budget_key: string;
    metric: BudgetMetric;
    scope_kind: BudgetScopeKind;
    /** Scope Reference */
    scope_reference?: string | null;
    /** Limit Units */
    limit_units: number;
    /** Window Seconds */
    window_seconds: number;
    /** Window Anchor At */
    window_anchor_at: string;
    /** Enabled */
    enabled: boolean;
  };

  type BudgetPolicyView = {
    /** Budget Key */
    budget_key: string;
    metric: BudgetMetric;
    scope_kind: BudgetScopeKind;
    /** Scope Reference */
    scope_reference?: string | null;
    /** Limit Units */
    limit_units: number;
    /** Window Seconds */
    window_seconds: number;
    /** Window Anchor At */
    window_anchor_at: string;
    /** Enabled */
    enabled: boolean;
    /** Id */
    id: string;
    /** Owner Id */
    owner_id: string;
    /** Policy Version */
    policy_version: number;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
  };

  type BudgetScopeKind = "global" | "source" | "connection" | "job";

  type BudgetUpdateInput = {
    /** Operation Id */
    operation_id: string;
    /** Reason */
    reason: string;
    /** Expected Policy Version */
    expected_policy_version: number;
    policy: BudgetPolicyInput;
  };

  type BudgetView = {
    /** Key */
    key: string;
    /** Name */
    name: string;
    /** Weight */
    weight: number;
    /** Sources */
    sources: string[];
  };

  type BudgetWindowUsageView = {
    /** Budget Policy Id */
    budget_policy_id: string;
    /** Budget Key */
    budget_key: string;
    metric: BudgetMetric;
    scope_kind: BudgetScopeKind;
    /** Scope Reference */
    scope_reference: string | null;
    /** Limit Units */
    limit_units: number;
    /** Window Seconds */
    window_seconds: number;
    /** Window Anchor At */
    window_anchor_at: string;
    /** Enabled */
    enabled: boolean;
    /** Policy Version */
    policy_version: number;
    /** Window Start */
    window_start: string | null;
    /** Window End */
    window_end: string | null;
    /** Used Units */
    used_units: number;
    /** Reserved Units */
    reserved_units: number;
    /** Remaining Units */
    remaining_units: number | null;
    /** Next Window At */
    next_window_at: string | null;
  };

  type CalendarMark = {
    /** Date */
    date: string;
    /** Event Id */
    event_id: string;
    kind: ResetKind;
    /** State */
    state: "confirmed" | "likely" | "pending";
    /** Label */
    label: string;
  };

  type cancelCollectionJobParams = {
    job_id: string;
  };

  type CategoryRankView = {
    /** Key */
    key: "overall" | "coding" | "reasoning" | "knowledge" | "professional";
    /** Name */
    name: string;
    /** Rank */
    rank: number | null;
    /** Score */
    score: number | null;
    /** Source Count */
    source_count: number;
    /** On Board */
    on_board: boolean;
  };

  type cloneMonitorTopicParams = {
    topic_id: string;
  };

  type CodexConfigurationInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Enabled */
    enabled?: boolean;
    configuration?: MonitorConfiguration;
  };

  type CodexEventReviewInput = {
    patch: EventPatch;
    review: ReviewInput;
  };

  type CodexGapReviewInput = {
    /** Action */
    action: "retry" | "acknowledge";
    review: ReviewInput;
  };

  type CodexPostRelinkInput = {
    /** From Event Id */
    from_event_id: string;
    /** To Event Id */
    to_event_id?: string | null;
    /** Target Expected Revision */
    target_expected_revision?: number | null;
    review: ReviewInput;
  };

  type CodexPostReviewInput = {
    /** Action */
    action: "skip" | "reviewed" | "retry";
    review: ReviewInput;
  };

  type CodexTickInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Lookback Hours */
    lookback_hours?: number | null;
  };

  type CollectionCoverageAnalysisView = {
    /** Pending Count */
    pending_count: number | null;
    /** Failed Count */
    failed_count: number | null;
    /** Invalid Count */
    invalid_count: number | null;
    /** Valid Count */
    valid_count: number | null;
  };

  type CollectionCoverageAttemptView = {
    /** Attempt Id */
    attempt_id: string;
    /** Collection Cycle No */
    collection_cycle_no: number;
    /** Started At */
    started_at: string;
    /** Finished At */
    finished_at: string | null;
    /** Outcome */
    outcome: string | null;
  };

  type CollectionCoverageBudgetView = {
    /** Budget Key */
    budget_key: string;
    /** Policy Version */
    policy_version: number;
    /** Limit Units */
    limit_units: number;
    /** Reserved Units */
    reserved_units: number;
    /** Consumed Units */
    consumed_units: number;
  };

  type CollectionCoverageGapView = {
    /** Starts At */
    starts_at: string;
    /** Ends At */
    ends_at: string;
    /** Reason */
    reason: string;
  };

  type CollectionCoverageMetricsView = {
    /** Metric Version */
    metric_version: string;
    /** Start */
    start: string;
    /** End */
    end: string;
    /** Cutoff At */
    cutoff_at: string;
    /** Sources */
    sources: CollectionSourceMetricView[];
    /** Analysis Status */
    analysis_status: string;
  };

  type CollectionCoverageResultStatus =
    | "pending"
    | "not_attempted"
    | "complete"
    | "empty"
    | "partial"
    | "failed"
    | "stopped";

  type CollectionCoverageView = {
    /** Window Id */
    window_id: string;
    /** Source Key */
    source_key: string;
    capability: SourceCapability;
    /** Topic Id */
    topic_id: string | null;
    /** Due At */
    due_at: string;
    /** Window Start */
    window_start: string;
    /** Window End */
    window_end: string;
    admission_state: DueAdmissionState;
    /** Admission Reason */
    admission_reason: string | null;
    /** Current Connection Version */
    current_connection_version: number | null;
    /** Job Connection Version */
    job_connection_version: number | null;
    /** Job Id */
    job_id: string | null;
    job_status: JobStatus | null;
    /** Attempts */
    attempts: CollectionCoverageAttemptView[] | null;
    /** Started At */
    started_at: string | null;
    /** Finished At */
    finished_at: string | null;
    /** Last Success At */
    last_success_at: string | null;
    coverage_status: CollectionCoverageResultStatus;
    /** Terminal Evidence */
    terminal_evidence: string | null;
    /** Stop Reason */
    stop_reason: string | null;
    /** Request Count */
    request_count: number | null;
    /** Request Attempt Count */
    request_attempt_count: number | null;
    /** Page Count */
    page_count: number | null;
    /** Observed Count */
    observed_count: number | null;
    /** Inserted Count */
    inserted_count: number | null;
    /** Deduplicated Count */
    deduplicated_count: number | null;
    analysis: CollectionCoverageAnalysisView | null;
    /** Budgets */
    budgets: CollectionCoverageBudgetView[] | null;
    /** Gaps */
    gaps: CollectionCoverageGapView[];
    /** Content Ids */
    content_ids: string[] | null;
    /** Snapshot Ids */
    snapshot_ids: string[] | null;
  };

  type CollectionMetricExclusionView = {
    /** Reason */
    reason: "quiet" | "rate_limited";
    /** Starts At 被排除到期点 (包含) */
    starts_at: string;
    /** Ends At 被排除到期点后 1 微秒 (不包含) */
    ends_at: string;
    /** Evidence Id */
    evidence_id: string;
  };

  type CollectionScanKind = "new_scan" | "refresh" | "backfill";

  type CollectionSourceMetricView = {
    /** Source Key */
    source_key: string;
    capability: SourceCapability;
    timing: CollectionTimingMetricView;
    hotlist: HotlistBucketMetricView | null;
    /** Exclusions */
    exclusions: CollectionMetricExclusionView[];
  };

  type CollectionTimingMetricView = {
    /** Target Seconds */
    target_seconds: number;
    /** Due Count */
    due_count: number;
    /** Excluded Count */
    excluded_count: number;
    /** Sample Count */
    sample_count: number;
    /** Finished Count */
    finished_count: number;
    /** Timeout Count */
    timeout_count: number;
    /** Median Seconds */
    median_seconds: number | null;
    /** Median Lower Bound Seconds */
    median_lower_bound_seconds: number | null;
    /** Result */
    result: "passed" | "failed" | "indeterminate" | "no_samples";
  };

  type CommentManualRunInput = {
    /** Operation Id */
    operation_id: string;
  };

  type CommentRunReadinessView = {
    /** Supported */
    supported: boolean;
    /** Available */
    available: boolean;
    /** Reason */
    reason:
      | "comments_not_ready"
      | "comments_budget_exhausted"
      | "comments_rate_limited"
      | null;
  };

  type ComparisonRowView = {
    /** Source Key */
    source_key: string;
    /** Source Name */
    source_name: string;
    /** Official Url */
    official_url: string | null;
    /** Mine */
    mine: string;
    /** Theirs */
    theirs: string;
    /** Weight */
    weight: number;
  };

  type ComparisonView = {
    model: ModelRefView;
    /** Rank */
    rank: number;
    /** Net */
    net: number;
    /** Shared Weight */
    shared_weight: number;
    /** Shared Count */
    shared_count: number;
    /** Has Page */
    has_page: boolean;
    /** Rows */
    rows: ComparisonRowView[];
  };

  type completeGithubLoginParams = {
    code?: string | null;
    state?: string | null;
    error?: string | null;
  };

  type ContactImageInput = {
    /** Mime */
    mime: "image/png" | "image/jpeg" | "image/webp" | "image/gif";
    /** Data Base64 */
    data_base64: string;
  };

  type ContentAnalysisTopicView = {
    /** Topic Id */
    topic_id: string;
    /** Topic Name */
    topic_name: string;
    /** Current Rule Version */
    current_rule_version: number;
  };

  type ContentAnnotationReadView = {
    /** Id */
    id: string;
    /** Topic Id */
    topic_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Topic Rule Version */
    topic_rule_version: number;
    /** Prompt Version */
    prompt_version: string;
    status: AnnotationStatus;
    result_state: AnnotationResultState;
    /** Relevant */
    relevant: boolean | null;
    /** Relevance Reason */
    relevance_reason: string | null;
    sentiment: Sentiment | null;
    /** Summary */
    summary: string | null;
    /** Viewpoints */
    viewpoints: string[];
    /** Error Code */
    error_code: string | null;
    /** Updated At */
    updated_at: string;
  };

  type ContentCommentView = {
    /** Content Id */
    content_id: string;
    /** External Id */
    external_id: string | null;
    /** Root Content Id */
    root_content_id: string | null;
    /** Parent Content Id */
    parent_content_id: string | null;
    /** Reply Target Content Id */
    reply_target_content_id: string | null;
    /** Parent Relation Status */
    parent_relation_status: "root" | "observed" | "unavailable" | "unresolved";
    latest_observation: ContentObservationView | null;
    /** Has Replies */
    has_replies: boolean;
  };

  type ContentDiscoveryView = {
    /** Job Id */
    job_id: string;
    /** Configuration Ref */
    configuration_ref: string;
    /** Configuration Version */
    configuration_version: number;
    /** First Observed At */
    first_observed_at: string;
    scan_kind: CollectionScanKind | null;
  };

  type ContentMetricView = {
    /** Like Count */
    like_count: number | null;
    /** Comment Count */
    comment_count: number | null;
    /** Repost Count */
    repost_count: number | null;
    /** View Count */
    view_count: number | null;
    /** Play Count */
    play_count: number | null;
    /** Danmaku Count */
    danmaku_count: number | null;
  };

  type ContentObservationView = {
    /** Id */
    id: string;
    /** Observed At */
    observed_at: string;
    /** Received At */
    received_at: string;
    /** Published At */
    published_at: string | null;
    /** Published At Fractional Digits */
    published_at_fractional_digits: number | null;
    /** Canonical Url */
    canonical_url: string | null;
    /** Final Url */
    final_url: string | null;
    /** Author External Id */
    author_external_id: string | null;
    metrics: ContentMetricView;
    content_version: ContentVersionView | null;
  };

  type ContentRecordDetailView = {
    /** Id */
    id: string;
    /** Source Key */
    source_key: string;
    /** Object Type */
    object_type: "post" | "comment" | "webpage";
    /** Native Scope */
    native_scope: string | null;
    /** External Id */
    external_id: string;
    /** Identity Basis */
    identity_basis: "guid" | "url_fallback" | null;
    latest_observation: ContentObservationView;
    current_visibility: ContentVisibilityView | null;
    /** Discovery Count */
    discovery_count: number;
    /** Timeline At */
    timeline_at?: string | null;
    /** Timeline Basis */
    timeline_basis?: "published_at" | "first_observed_at" | null;
    /** Analysis State */
    analysis_state?:
      "missing" | "pending" | "failed" | "invalid" | "valid" | null;
    /** Analysis Relevant */
    analysis_relevant?: boolean | null;
    /** Discoveries */
    discoveries: ContentDiscoveryView[];
    /** Version History */
    version_history: ContentVersionHistoryView[];
    /** Visibility History */
    visibility_history: ContentVisibilityView[];
    /** Analysis Topics */
    analysis_topics: ContentAnalysisTopicView[];
    /** Annotations */
    annotations: ContentAnnotationReadView[];
    /** Analysis Prompt Version */
    analysis_prompt_version: string;
  };

  type ContentRecordSummaryView = {
    /** Id */
    id: string;
    /** Source Key */
    source_key: string;
    /** Object Type */
    object_type: "post" | "comment" | "webpage";
    /** Native Scope */
    native_scope: string | null;
    /** External Id */
    external_id: string;
    /** Identity Basis */
    identity_basis: "guid" | "url_fallback" | null;
    latest_observation: ContentObservationView;
    current_visibility: ContentVisibilityView | null;
    /** Discovery Count */
    discovery_count: number;
    /** Timeline At */
    timeline_at?: string | null;
    /** Timeline Basis */
    timeline_basis?: "published_at" | "first_observed_at" | null;
    /** Analysis State */
    analysis_state?:
      "missing" | "pending" | "failed" | "invalid" | "valid" | null;
    /** Analysis Relevant */
    analysis_relevant?: boolean | null;
  };

  type ContentRelationType = "quote" | "repost";

  type ContentRuleSampleView = {
    /** Content Id */
    content_id: string;
    /** Observation Id */
    observation_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Source Key */
    source_key: string;
    /** Title */
    title: string | null;
    /** Body Excerpt */
    body_excerpt: string | null;
    /** Excerpt Truncated */
    excerpt_truncated: boolean;
    /** Published At */
    published_at: string | null;
    /** Observed At */
    observed_at: string;
    /** Matched */
    matched: boolean;
    /** Matched Any */
    matched_any: string[];
    /** Matched All */
    matched_all: string[];
    /** Excluded By */
    excluded_by: string[];
  };

  type ContentSamplePreviewInput = {
    /** Match Any */
    match_any: KeywordInput[];
    /** Match All */
    match_all: KeywordInput[];
    /** Exclude */
    exclude: KeywordInput[];
    /** Source Keys */
    source_keys?: SourceKeyInput[];
  };

  type ContentSamplePreviewView = {
    rules: MonitorRuleSetView;
    /** Rule Basis */
    rule_basis: string;
    /** Source Keys */
    source_keys: string[];
    /** Starts At */
    starts_at: string;
    /** Ends At */
    ends_at: string;
    /** Sample Limit */
    sample_limit: number;
    /** Sample Status */
    sample_status: "available" | "insufficient_samples";
    /** Truncated */
    truncated: boolean;
    /** Samples */
    samples: ContentRuleSampleView[];
    /** External Requests */
    external_requests: number;
    /** Model Requests */
    model_requests: number;
  };

  type ContentTextOrigin = "source" | "machine_extracted";

  type ContentTextScope = "full" | "summary" | "truncated" | "media_only";

  type ContentTruncationReason = "source_limit" | "collector_limit";

  type ContentVersionHistoryView = {
    content_version: ContentVersionView;
    /** First Observed At */
    first_observed_at: string;
    /** Last Observed At */
    last_observed_at: string;
    /** Observation Count */
    observation_count: number;
  };

  type ContentVersionRelationView = {
    relation_type: ContentRelationType;
    /** Target Native Scope */
    target_native_scope: string | null;
    /** Target External Id */
    target_external_id: string;
    /** Target Author External Id */
    target_author_external_id: string | null;
    /** Target Content Id */
    target_content_id: string | null;
  };

  type ContentVersionView = {
    /** Id */
    id: string;
    text_scope: ContentTextScope;
    text_origin: ContentTextOrigin;
    /** Text Origin Ref */
    text_origin_ref: string | null;
    /** Title */
    title: string | null;
    /** Body */
    body: string | null;
    truncation_reason: ContentTruncationReason | null;
    /** Relations */
    relations: ContentVersionRelationView[];
  };

  type ContentVisibilityBasis =
    | "content_returned"
    | "source_tombstone"
    | "http_gone"
    | "access_denied"
    | "authentication_required"
    | "not_found"
    | "timeout"
    | "rate_limited"
    | "upstream_error"
    | "protocol_error";

  type ContentVisibilityStatus =
    "visible" | "deleted" | "restricted" | "transient_failure" | "unknown";

  type ContentVisibilityView = {
    /** Id */
    id: string;
    /** Observed At */
    observed_at: string;
    /** Received At */
    received_at: string;
    status: ContentVisibilityStatus;
    basis: ContentVisibilityBasis;
  };

  type ContextPost = {
    /** Id */
    id: string;
    /** Author */
    author: string;
    /** Relation */
    relation: "reply" | "quote";
    /** Original Text */
    original_text: string;
    /** Text Zh */
    text_zh?: string | null;
    /** Published At */
    published_at?: string | null;
    /** Url */
    url: string;
  };

  type correctCodexResetEventParams = {
    monitor_id: string;
    event_id: string;
  };

  type correctEditorialRunParams = {
    run_id: string;
  };

  type correctReportEditionParams = {
    edition_id: string;
  };

  type CoverageWindowStatus = "pending" | "running" | "confirmed" | "partial";

  type CoverageWindowView = {
    /** Id */
    id: string;
    /** Starts At */
    starts_at: string;
    /** Ends At */
    ends_at: string;
    status: CoverageWindowStatus;
    /** Stop Reason */
    stop_reason: string | null;
    /** Page Count */
    page_count: number;
  };

  type DeliveryResolutionInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Outcome */
    outcome: "delivered" | "not_delivered";
  };

  type DeliveryStatus =
    "pending" | "sending" | "succeeded" | "failed" | "unknown";

  type DetailConfiguration = {
    /** Max Fetches */
    max_fetches?: number;
    /** Published At Selector */
    published_at_selector?: string | null;
    /** Published At Regex */
    published_at_regex?: string | null;
    /** Published At Utc Offset */
    published_at_utc_offset?: string;
    /** Published At Authoritative */
    published_at_authoritative?: boolean;
    /** Upgrade Date Precision */
    upgrade_date_precision?: boolean;
    /** Title Selector */
    title_selector?: string | null;
    /** Title Regex */
    title_regex?: string | null;
    /** Title Authoritative */
    title_authoritative?: boolean;
    /** Summary Selector */
    summary_selector?: string | null;
  };

  type DictionaryInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Version */
    expected_version: number;
    /** Kind */
    kind: "glossary" | "entities" | "categories";
    /** Content */
    content: Record<string, any>;
    /** Reason */
    reason: string;
  };

  type DictionaryView = {
    /** Id */
    id: string;
    /** Kind */
    kind: "glossary" | "entities" | "categories";
    /** Version */
    version: number;
    /** Content */
    content: Record<string, any>;
    /** Created At */
    created_at: string;
  };

  type DueAdmissionState = "pending" | "accepted" | "skipped" | "missed";

  type EditionContentView = {
    /** Title */
    title: string;
    /** Lead */
    lead: string;
    /** Highlights */
    highlights: string[];
    /** Sections */
    sections: EditionSectionView[];
    /** Flashes */
    flashes: string[];
    /** Themes */
    themes: EditionThemeView[];
    /** Entries */
    entries: ReportPublicationCandidate[];
    metrics: EditionMetricsView;
  };

  type EditionCorrectionInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Title */
    title: string;
    /** Lead */
    lead: string;
    /** Highlights */
    highlights: string[];
    /** Themes */
    themes: EditionThemeInput[];
    /** Reason */
    reason: string;
  };

  type EditionDetailView = {
    /** Id */
    id: string;
    /** Kind */
    kind: "daily" | "weekly" | "monthly";
    /** Key */
    key: string;
    /** Revision */
    revision: number;
    /** Status */
    status: "queued" | "running" | "complete" | "failed" | "unknown" | "stale";
    /** Generator */
    generator: "template" | "model" | "manual";
    /** Window Start */
    window_start: string;
    /** Window End */
    window_end: string;
    /** Title */
    title: string | null;
    /** Valid */
    valid: boolean;
    /** Failure Code */
    failure_code: string | null;
    /** Created At */
    created_at: string;
    /** Job Id */
    job_id: string | null;
    content: EditionContentView | null;
    /** Body Markdown */
    body_markdown: string | null;
    /** Ai Call Id */
    ai_call_id: string | null;
    /** Reason */
    reason: string;
    /** Historical Revision */
    historical_revision: boolean;
  };

  type EditionMetricsView = {
    /** Selected Count */
    selected_count: number;
    /** Facts Count */
    facts_count: number;
    /** Sources Count */
    sources_count: number;
    /** First Party Count */
    first_party_count: number;
    /** Models Released */
    models_released: number;
    /** Repeats Suppressed */
    repeats_suppressed: number;
    /** Backfill Unknown Count */
    backfill_unknown_count: number;
    /** Daily Editions Covered */
    daily_editions_covered: number;
  };

  type EditionRequestInput = {
    /** Operation Id */
    operation_id: string;
    /** Kind */
    kind: "daily" | "weekly" | "monthly";
    /** Key */
    key: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
  };

  type EditionSectionView = {
    /** Label */
    label: string;
    /** Content Ids */
    content_ids: string[];
  };

  type EditionSummaryView = {
    /** Id */
    id: string;
    /** Kind */
    kind: "daily" | "weekly" | "monthly";
    /** Key */
    key: string;
    /** Revision */
    revision: number;
    /** Status */
    status: "queued" | "running" | "complete" | "failed" | "unknown" | "stale";
    /** Generator */
    generator: "template" | "model" | "manual";
    /** Window Start */
    window_start: string;
    /** Window End */
    window_end: string;
    /** Title */
    title: string | null;
    /** Valid */
    valid: boolean;
    /** Failure Code */
    failure_code: string | null;
    /** Created At */
    created_at: string;
  };

  type EditionThemeInput = {
    /** Heading */
    heading: string;
    /** Summary */
    summary: string;
    /** Content Ids */
    content_ids: string[];
  };

  type EditionThemeView = {
    /** Heading */
    heading: string;
    /** Summary */
    summary: string;
    /** Content Ids */
    content_ids: string[];
  };

  type EditorialEntityGuardView = {
    /** Outcome */
    outcome: "pass" | "fallback";
    /** Unsupported Title Entity Ids */
    unsupported_title_entity_ids: string[];
    /** Unsupported Summary Entity Ids */
    unsupported_summary_entity_ids: string[];
  };

  type EditorialGroupBacklogExpected = {
    /** Profile Id */
    profile_id: string;
    /** Configuration Version */
    configuration_version: number;
    /** Revision */
    revision: number;
  };

  type EditorialGroupBacklogMember = {
    /** Profile Id */
    profile_id: string;
    /** Source Key */
    source_key: string;
    /** Name */
    name: string;
    /** Configuration Version */
    configuration_version: number;
    /** Revision */
    revision: number;
    /** Enabled */
    enabled: boolean;
  };

  type EditorialGroupBacklogReviewInput = {
    /** Operation Id */
    operation_id: string;
    /** Group Sha256 */
    group_sha256: string;
    /** Reason */
    reason: string;
    /** Actor */
    actor: string;
    /** Action */
    action: string;
    /** Expected Members */
    expected_members: EditorialGroupBacklogExpected[];
  };

  type EditorialGroupBacklogReviewResult = {
    /** Group Sha256 */
    group_sha256: string;
    /** Members */
    members: EditorialGroupBacklogMember[];
  };

  type EditorialGroupBacklogView = {
    /** Group Sha256 */
    group_sha256: string;
    /** Query */
    query: string;
    /** State */
    state: "pending" | "held" | "blocked_configuration";
    /** Members */
    members: EditorialGroupBacklogMember[];
  };

  type EditorialMaterial = {
    /** Url */
    url: string;
    /** Identity Key */
    identity_key: string;
    /** Title */
    title: string;
    /** Author */
    author?: string | null;
    /** Language */
    language?: string | null;
    /** External Id */
    external_id?: string | null;
    /** Published At */
    published_at?: string | null;
    /** Source Updated At */
    source_updated_at?: string | null;
    /** Excerpt */
    excerpt?: string | null;
    /** Body Text */
    body_text?: string | null;
    /** Body Html */
    body_html?: string | null;
    /** Body Markdown */
    body_markdown?: string | null;
    /** Content Format */
    content_format?: "text" | "html" | "markdown";
    /** Body Status */
    body_status?: "ok" | "pending" | "none";
    /** Media */
    media?: string[];
    /** Media Details */
    media_details?: EditorialSourceMedia[];
    /** Categories */
    categories?: string[];
    /** Metadata */
    metadata?: Record<string, any>;
  };

  type EditorialOverrideInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Manual Version */
    expected_manual_version: number;
    /** Action */
    action?: "replace" | "clear";
    /** Clear Fields */
    clear_fields?: (
      | "selected"
      | "title_zh"
      | "summary_zh"
      | "category"
      | "reason_zh"
      | "tags"
      | "silent"
    )[];
    /** Selected */
    selected?: boolean | null;
    /** Title Zh */
    title_zh?: string | null;
    /** Summary Zh */
    summary_zh?: string | null;
    /** Category */
    category?:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    /** Reason Zh */
    reason_zh?: string | null;
    /** Tags */
    tags?: string[] | null;
    /** Silent */
    silent?: boolean | null;
    /** Reason */
    reason: string;
  };

  type EditorialPollInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
  };

  type EditorialPreviewItem = {
    /** Title */
    title: string;
    /** Url */
    url: string;
    /** Published At */
    published_at: string | null;
    /** Excerpt */
    excerpt: string;
  };

  type EditorialPreviewJobView = {
    job: JobStatusView;
    preview: EditorialSourcePreviewView | null;
  };

  type EditorialPreviewReviewInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Preview Operation Id */
    preview_operation_id: string;
  };

  type EditorialPreviewReviewView = {
    /** Job Id */
    job_id: string;
    /** Profile Id */
    profile_id: string;
    /** Preview Operation Id */
    preview_operation_id: string;
    /** Review Operation Id */
    review_operation_id: string;
    /** Revision */
    revision: number;
    /** Reviewed */
    reviewed?: boolean;
    /** Status */
    status?: string;
  };

  type EditorialProfileInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision?: number;
    /** Name */
    name: string;
    /** Reason */
    reason: string;
    /** Enabled */
    enabled?: boolean;
    configuration: EditorialSourceConfiguration;
    participation_mode?: ParticipationMode;
    /** Tier */
    tier?: "T1" | "T1_5" | "T2" | "T3";
    /** First Party */
    first_party?: boolean;
    /** Connection Id */
    connection_id?: string | null;
    /** Connection Version */
    connection_version?: number | null;
    /** Policy Version */
    policy_version: number;
    /** Interval Minutes */
    interval_minutes?: number;
  };

  type EditorialProfileView = {
    /** Id */
    id: string;
    /** Source Key */
    source_key: string;
    /** Name */
    name: string;
    /** Enabled */
    enabled: boolean;
    /** Revision */
    revision: number;
    /** Configuration Version */
    configuration_version: number;
    configuration: EditorialSourceConfiguration;
    participation_mode: ParticipationMode;
    /** Tier */
    tier: "T1" | "T1_5" | "T2" | "T3";
    /** First Party */
    first_party: boolean;
    /** Connection Id */
    connection_id: string | null;
    /** Connection Version */
    connection_version: number | null;
    /** Policy Version */
    policy_version: number;
    /** Interval Minutes */
    interval_minutes: number;
    /** Health */
    health: "unknown" | "ok" | "degraded" | "failing";
    /** Failure Count */
    failure_count: number;
    /** Last Fetch At */
    last_fetch_at: string | null;
    /** Last Ok At */
    last_ok_at: string | null;
    /** Next Fetch At */
    next_fetch_at: string | null;
    /** Has Backlog */
    has_backlog: boolean;
    /** Has Unknown Run */
    has_unknown_run?: boolean;
  };

  type EditorialRemotePreviewInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
  };

  type EditorialResultView = {
    prefilter?: PrefilterOutput | null;
    /** Scores */
    scores?: number[];
    /** Threshold */
    threshold?: number | null;
    /** Score */
    score?: number | null;
    /** Selected */
    selected?: boolean;
    /** Relevance */
    relevance: "pass" | "block" | "unknown";
    writing?: EditorialWritingView | null;
    structure?: StructureOutput | null;
    /** Body Complete */
    body_complete?: boolean;
    /** Manual */
    manual?: boolean;
    /** Tags Override */
    tags_override?: string[] | null;
    /** Silent */
    silent?: boolean;
    /** Manual Overrides */
    manual_overrides?: Record<string, any>;
  };

  type EditorialRunInput = {
    /** Operation Id */
    operation_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Expected Manual Version */
    expected_manual_version?: number;
    /** Stages */
    stages?: "selection" | "all";
  };

  type EditorialRunResult = {
    /** Run Id */
    run_id: string;
    /** Status */
    status:
      | "running"
      | "succeeded"
      | "partial"
      | "unknown"
      | "failed"
      | "blocked"
      | "cancelled";
    /** Configuration Version */
    configuration_version: number;
    /** Found */
    found?: number;
    /** Created */
    created?: number;
    /** Revised */
    revised?: number;
    /** Reason */
    reason?: string | null;
  };

  type EditorialRunReviewInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Actor */
    actor: string;
    /** Action */
    action: "acknowledge_unknown" | "retry_failed";
  };

  type EditorialRunView = {
    /** Id */
    id: string;
    /** Job Id */
    job_id: string | null;
    /** Content Id */
    content_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Source Key */
    source_key: string;
    /** Source Revision */
    source_revision: number;
    /** Prompt Version */
    prompt_version: string;
    /** Manual Version */
    manual_version: number;
    /** Status */
    status:
      | "queued"
      | "running"
      | "complete"
      | "blocked"
      | "failed"
      | "unknown"
      | "stale";
    result: EditorialResultView | null;
    /** Failure Code */
    failure_code: string | null;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
  };

  type EditorialSamplePreviewInput = {
    /** Operation Id */
    operation_id: string;
    /** Reason */
    reason: string;
    configuration: EditorialSourceConfiguration;
    /** Sample */
    sample: string;
  };

  type EditorialSourceConfiguration = {
    kind: EditorialSourceKind;
    /** Allowed Hosts */
    allowed_hosts?: string[];
    /** Allow Url Prefixes */
    allow_url_prefixes?: string[];
    /** Deny Url Prefixes */
    deny_url_prefixes?: string[];
    ingest_noise_filter?: NoiseFilter | null;
    item_url_prefix_rewrite?: PrefixRewrite | null;
    /** Sort By Published At */
    sort_by_published_at?: boolean;
    detail?: DetailConfiguration | null;
    /** Fetch Public Content */
    fetch_public_content?: boolean;
    /** Initial Backfill Limit */
    initial_backfill_limit?: number;
    /** Initial Backfill Months */
    initial_backfill_months?: number;
    /** Feed Url */
    feed_url?: string | null;
    /** Summary Is Body */
    summary_is_body?: boolean;
    /** Preserve Url Fragment */
    preserve_url_fragment?: boolean;
    /** Allow Categories */
    allow_categories?: string[];
    /** Deny Categories */
    deny_categories?: string[];
    /** Url */
    url?: string | null;
    /** Base Url */
    base_url?: string | null;
    /** Parse Mode */
    parse_mode?: "html" | "markdown" | "docusaurus_changelog";
    /** Adapter */
    adapter?: string | null;
    /** Cache Tolerance Seconds */
    cache_tolerance_seconds?: number;
    /** Links Start Line */
    links_start_line?: boolean;
    /** Item Selector */
    item_selector?: string | null;
    /** Link Selector */
    link_selector?: string | null;
    /** Title Selector */
    title_selector?: string | null;
    /** Published At Selector */
    published_at_selector?: string | null;
    /** Published At Regex */
    published_at_regex?: string | null;
    /** Published At Utc Offset */
    published_at_utc_offset?: string;
    /** Mode */
    mode?: "json" | "html_json_key" | "html_window_var";
    /** Method */
    method?: "GET" | "POST";
    /** Headers */
    headers?: Record<string, any>;
    body_json?: JsonValue | null;
    /** Json Key */
    json_key?: string | null;
    /** Window Var */
    window_var?: string | null;
    /** Items Path */
    items_path?: string | null;
    /** Items Object Values */
    items_object_values?: boolean;
    /** Title Paths */
    title_paths?: string[];
    /** Summary Paths */
    summary_paths?: string[];
    /** Author Paths */
    author_paths?: string[];
    /** Published At Path */
    published_at_path?: string;
    /** Published At Unit */
    published_at_unit?: "iso" | "epoch_ms" | "epoch_s" | "yyyymmdd";
    /** External Id Path */
    external_id_path?: string | null;
    /** Url Template */
    url_template?: string | null;
    /** Url Template Fallback */
    url_template_fallback?: string | null;
    /** Raw Drop Keys */
    raw_drop_keys?: string[];
    require_boolean?: BooleanCondition | null;
    min_numeric?: NumericCondition | null;
    /** Query */
    query?: string | null;
    /** Search Type */
    search_type?: "Latest" | "Top";
    /** Wxid */
    wxid?: string | null;
    /** Ghid */
    ghid?: string | null;
    /** Nickname */
    nickname?: string | null;
  };

  type EditorialSourceInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Tier */
    tier: "T1" | "T1_5" | "T2" | "EXCLUDE_MP" | "UNGRADED";
    /** Source Kind */
    source_kind:
      | "rss"
      | "web_list"
      | "json_list"
      | "x_search"
      | "mp_account"
      | "external"
      | "other";
    /** Name */
    name: string;
    /** First Party */
    first_party?: boolean;
    /** Owner Entity Id */
    owner_entity_id?: string | null;
    /** Tags */
    tags?: string[];
    /** Enabled */
    enabled?: boolean;
  };

  type EditorialSourceKind =
    "rss" | "web_list" | "json_list" | "x_search" | "mp_account" | "external";

  type EditorialSourceMedia = {
    /** Url */
    url: string;
    /** Kind */
    kind?: "image" | "video" | "audio" | "unknown";
    /** Alt */
    alt?: string | null;
  };

  type EditorialSourcePreviewView = {
    /** Mode */
    mode: "sample" | "remote";
    /** Status */
    status: "complete" | "partial" | "blocked" | "unknown";
    kind: EditorialSourceKind;
    /** Count */
    count: number;
    /** Ms */
    ms: number;
    /** Requests */
    requests: number;
    /** Items */
    items: EditorialPreviewItem[];
    /** Reason */
    reason?: string | null;
  };

  type EditorialSourceView = {
    /** Source Key */
    source_key: string;
    /** Revision */
    revision: number;
    /** Tier */
    tier: "T1" | "T1_5" | "T2" | "EXCLUDE_MP" | "UNGRADED";
    /** Source Kind */
    source_kind:
      | "rss"
      | "web_list"
      | "json_list"
      | "x_search"
      | "mp_account"
      | "external"
      | "other";
    /** Name */
    name: string;
    /** First Party */
    first_party: boolean;
    /** Owner Entity Id */
    owner_entity_id: string | null;
    /** Tags */
    tags: string[];
    /** Enabled */
    enabled: boolean;
  };

  type EditorialWritingView = {
    /** Title Zh */
    title_zh: string;
    /** Summary Zh */
    summary_zh: string;
    identity_guard: EditorialEntityGuardView;
    /** Kind */
    kind: "understand" | "summarize" | "verbatim" | "none" | "manual";
    /** Reason Zh */
    reason_zh?: string | null;
    /** Item Type */
    item_type?:
      | "model_release"
      | "product_launch"
      | "tool_or_prompt"
      | "research_paper"
      | "industry_event"
      | "opinion_analysis"
      | "tutorial_explainer"
      | null;
    /** Author Role */
    author_role?: "principal" | "observer" | "relayer" | null;
    /** Tags */
    tags?: string[] | null;
  };

  type EmailChallengeView = {
    /** Challenge Id */
    challenge_id: string;
    /** Expires At */
    expires_at: string;
    /** Resend After Seconds */
    resend_after_seconds: number;
  };

  type EmailCodeInput = {
    /** Email */
    email: string;
  };

  type ErrorView = {
    /** Code */
    code: string;
    /** Message */
    message: string;
    /** Request Id */
    request_id: string;
    /** Details */
    details?: ValidationErrorItem[] | null;
  };

  type Estimate = {
    /** Starts At */
    starts_at: string;
    /** Ends At */
    ends_at: string;
    /** Basis */
    basis: "model" | "source" | "source_day" | "history";
    /** Label */
    label: string;
    /** Reason */
    reason: string;
  };

  type EventAttentionHistoryView = {
    /** Event Id */
    event_id: string;
    /** Event Revision */
    event_revision: number;
    /** Items */
    items: EventAttentionView[];
  };

  type EventAttentionView = {
    /** Formula Version */
    formula_version?: string;
    /** Event Id */
    event_id?: string | null;
    /** Event Revision */
    event_revision?: number | null;
    /** Window End */
    window_end: string;
    /** Heat */
    heat: number;
    /** Eligible */
    eligible: boolean;
    /** Participant Count */
    participant_count: number;
    /** Editorial Participant Count */
    editorial_participant_count: number;
    /** Signal Participant Count */
    signal_participant_count: number;
    /** Comparable Participant Count */
    comparable_participant_count: number;
    /** Uncomparable Participant Count */
    uncomparable_participant_count: number;
    /** Previous Heat */
    previous_heat: number;
    /** Comparable Heat */
    comparable_heat: number;
    /** Comparable Previous Heat */
    comparable_previous_heat: number;
    /** Trend */
    trend: "new" | "up" | "down" | "flat" | "unknown";
    /** Trend Pct */
    trend_pct: number | null;
    /** Complete */
    complete: boolean;
    /** Badges */
    badges: ("new" | "surge" | "rising")[];
    /** Source Names */
    source_names: string[];
    /** Roster */
    roster: AttentionRosterView[];
    representative: AttentionRosterView | null;
    interaction?: EventInteractionView | null;
  };

  type EventCommentReadView = {
    /** Id */
    id: string;
    /** Root Content Id */
    root_content_id: string | null;
    /** Parent Content Id */
    parent_content_id: string | null;
    /** Parent Relation Status */
    parent_relation_status: "root" | "observed" | "unavailable" | "unresolved";
    observation: ContentObservationView;
  };

  type EventContentReadView = {
    /** Id */
    id: string;
    /** Source Key */
    source_key: string;
    /** Object Type */
    object_type: "post" | "comment" | "webpage";
    /** Native Scope */
    native_scope: string | null;
    /** Collection Scope */
    collection_scope?: string | null;
    /** External Id */
    external_id: string;
    /** Identity Basis */
    identity_basis: "guid" | "url_fallback" | null;
    observation: ContentObservationView;
    current_visibility: ContentVisibilityView | null;
    representative_comment: EventCommentReadView | null;
    /** Representative Comment State */
    representative_comment_state: "none" | "readable" | "unavailable";
  };

  type EventCorrectionInput = {
    /** Operation Id */
    operation_id: string;
    /** Kind */
    kind: "merge" | "split" | "move" | "detach" | "merge_facts" | "regroup";
    /** Reason */
    reason: string;
    /** Expected Revisions */
    expected_revisions: Record<string, any>;
    /** Target Event Id */
    target_event_id?: string | null;
    /** Content Ids */
    content_ids?: string[];
    /** Fact Ids */
    fact_ids?: string[];
    /** Target Fact Id */
    target_fact_id?: string | null;
  };

  type EventCorrectionView = {
    /** Operation Id */
    operation_id: string;
    /** Kind */
    kind: string;
    /** Event Revisions */
    event_revisions: Record<string, any>;
    /** Target Event Id */
    target_event_id: string | null;
    /** Affected Content Ids */
    affected_content_ids: string[];
    /** Created Fact Ids */
    created_fact_ids: string[];
    /** Replayed */
    replayed?: boolean;
  };

  type EventFactMemberView = {
    /** Content Id */
    content_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Event Member Id */
    event_member_id: string;
    /** Role */
    role: "primary" | "report" | "mention";
    /** Assignment Origin */
    assignment_origin: "model" | "manual" | "legacy";
    /** Availability */
    availability: "readable" | "unavailable";
  };

  type EventFactPageView = {
    /** Event Id */
    event_id: string;
    /** Event Revision */
    event_revision: number;
    /** Facts */
    facts: EventFactView[];
  };

  type EventFactView = {
    /** Id */
    id: string;
    /** Revision */
    revision: number;
    relation: FactRelation;
    /** Root Fact Id */
    root_fact_id: string | null;
    /** Title */
    title: string | null;
    /** Summary */
    summary: string | null;
    /** First Seen At */
    first_seen_at: string;
    /** First Seen Basis */
    first_seen_basis: "published" | "discovered";
    /** Evidence State */
    evidence_state: "complete" | "partial";
    /** Members */
    members: EventFactMemberView[];
  };

  type EventHotPageView = {
    /** Window End */
    window_end: string;
    /** Items */
    items: EventAttentionView[];
  };

  type EventInteractionView = {
    /** Formula Version */
    formula_version?: string;
    /** Score */
    score: number | null;
    /** Post Count */
    post_count: number;
    /** Components */
    components: Record<string, any>;
    /** Unknown Masks */
    unknown_masks: Record<string, any>;
    /** Rising State */
    rising_state?: "rising" | "steady" | "insufficient";
    /** Current Increment */
    current_increment?: number | null;
    /** Baseline Increment */
    baseline_increment?: number | null;
  };

  type EventMemberPageView = {
    /** Items */
    items: EventMemberReadView[];
    /** Next Cursor */
    next_cursor: string | null;
    /** Event Id */
    event_id: string;
    /** Revision */
    revision: number;
    /** Current Revision */
    current_revision: number;
    /** Redirected From Event Id */
    redirected_from_event_id?: string | null;
    /** Evidence State */
    evidence_state: "complete" | "partial";
  };

  type EventMemberReadView = {
    /** Id */
    id: string;
    /** Content Id */
    content_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Source Key */
    source_key: string;
    /** Assignment Origin */
    assignment_origin: "model" | "manual";
    /** Added Revision */
    added_revision: number;
    /** Removed Revision */
    removed_revision: number | null;
    /** Availability */
    availability: "readable" | "unavailable";
    content: EventContentReadView | null;
  };

  type EventPatch = {
    kind?: ResetKind | null;
    /** Status */
    status?: "announced" | "confirmed" | null;
    schedule?: Schedule | null;
    scope?: ResetScope | null;
    /** Confirmed At */
    confirmed_at?: string | null;
    /** Occurred On */
    occurred_on?: string | null;
    /** Confirmation Basis */
    confirmation_basis?: "source_post" | "receipt_review" | null;
    /** Withdrawn */
    withdrawn?: boolean | null;
  };

  type EventReadView = {
    /** Id */
    id: string;
    /** Topic Id */
    topic_id: string;
    /** Revision */
    revision: number;
    /** Title */
    title: string | null;
    /** Summary */
    summary: string | null;
    /** First Seen At */
    first_seen_at: string;
    /** First Seen Basis */
    first_seen_basis: "published" | "discovered";
    /** Status */
    status: "active" | "merged";
    /** Merged Into Id */
    merged_into_id: string | null;
    /** Redirected From Event Id */
    redirected_from_event_id?: string | null;
    /** Evidence State */
    evidence_state: "complete" | "partial";
    /** Derived Text Available */
    derived_text_available: boolean;
    /** Latest Progress */
    latest_progress?: string | null;
    /** Phase */
    phase?: "active" | "watching" | "settled";
    /** Member Count */
    member_count: number;
    /** Readable Member Count */
    readable_member_count: number;
    /** Source Counts */
    source_counts: Record<string, any>;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
  };

  type EventRelatedItemView = {
    event: EventReadView;
    /** Supporting Report Count */
    supporting_report_count: number;
  };

  type EventRelatedPageView = {
    /** Event Id */
    event_id: string;
    /** Items */
    items: EventRelatedItemView[];
  };

  type EvidenceGroupView = {
    /** Key */
    key: string;
    /** Name */
    name: string;
    /** Items */
    items: EvidenceItemView[];
  };

  type EvidenceItemView = {
    /** Unit */
    unit: string;
    /** Source Key */
    source_key: string;
    /** Source Name */
    source_name: string;
    /** Official Url */
    official_url: string | null;
    /** Protocol */
    protocol: string;
    /** Snapshot Id */
    snapshot_id: string;
    /** Raw Score */
    raw_score: number;
    /** Display */
    display: string;
    /** Source Rank */
    source_rank: number | null;
    /** Source Model Name */
    source_model_name: string;
    /** Configuration Key */
    configuration_key: string;
    /** Configuration Label */
    configuration_label: string;
    /** Selection Reason */
    selection_reason: string;
    /** Upstream At */
    upstream_at: string | null;
    /** Verified At */
    verified_at: string | null;
    /** Measured At */
    measured_at: string | null;
    /** Carried Forward */
    carried_forward: boolean;
    /** Components */
    components: Record<string, any>;
  };

  type ExternalEditorialInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Configuration Version */
    configuration_version: number;
    /** Materials */
    materials: (EditorialMaterial | Record<string, any>)[];
  };

  type ExternalIngressItem = {
    /** Index */
    index: number;
    /** Identity Key */
    identity_key?: string | null;
    /** Status */
    status: "pending" | "succeeded" | "duplicate" | "rejected";
    /** Change */
    change?: "created" | "revised" | "unchanged" | null;
    /** Content Id */
    content_id?: string | null;
    /** Content Version Id */
    content_version_id?: string | null;
    /** Duplicate Of */
    duplicate_of?: number | null;
    /** Reason */
    reason?: string | null;
  };

  type ExternalIngressReceipt = {
    job: JobView;
    /** Profile Id */
    profile_id: string;
    /** Run Id */
    run_id: string;
    /** Configuration Version */
    configuration_version: number;
    /** Received */
    received: number;
    /** Items */
    items: ExternalIngressItem[];
  };

  type FactOutput = {
    /** Title */
    title: string;
    /** Subject */
    subject?: string | null;
    /** Action */
    action?: string | null;
    /** Object */
    object?: string | null;
    /** Occurredat */
    occurredAt?: string | null;
  };

  type FactRelation =
    "root" | "development" | "background" | "roundup" | "unreviewed";

  type FeedbackInput = {
    /** Operation Id */
    operation_id: string;
    /** Content */
    content: string;
    /** Email */
    email?: string | null;
    /** Page Url */
    page_url?: string | null;
    screenshot?: ScreenshotInput | null;
  };

  type FeedbackSubmissionView = {
    /** Id */
    id: string;
    /** Operation Id */
    operation_id: string;
    /** Status */
    status: string;
    /** Replayed */
    replayed?: boolean;
  };

  type FeedbackUpdateInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Status */
    status: "new" | "reviewing" | "resolved" | "rejected" | "deleted";
    /** Note */
    note?: string | null;
    /** Banned */
    banned?: boolean | null;
  };

  type FeedbackUpdateView = {
    /** Id */
    id: string;
    /** Revision */
    revision: number;
    /** Status */
    status: string;
    /** Replayed */
    replayed?: boolean;
  };

  type FeedbackView = {
    /** Id */
    id: string;
    /** Revision */
    revision: number;
    /** Content */
    content: string | null;
    /** Email */
    email: string | null;
    /** Page Url */
    page_url: string | null;
    /** Status */
    status: "new" | "reviewing" | "resolved" | "rejected" | "deleted";
    /** Note */
    note: string | null;
    /** Source Ref */
    source_ref: string;
    /** Banned */
    banned: boolean;
    /** Attachment Id */
    attachment_id: string | null;
    /** Attachment Mime */
    attachment_mime: string | null;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
    /** Forwarded At */
    forwarded_at: string | null;
    /** Forward Error */
    forward_error: string | null;
  };

  type FrozenAiModel = {
    /** Key */
    key: string;
    /** Provider */
    provider: string;
    /** Model */
    model: string;
    /** Component Key */
    component_key: string;
    /** Vision */
    vision: boolean;
    /** Catalog Sha256 */
    catalog_sha256: string;
  };

  type FxQuoteView = {
    /** As Of */
    as_of: string;
    /** Rate */
    rate: number;
    /** Source Name */
    source_name: string;
    /** Source Url */
    source_url: string | null;
  };

  type getAiModelOverviewParams = {
    days?: number;
  };

  type getCategoryFullRssParams = {
    category:
      "ai-models" | "ai-products" | "industry" | "paper" | "tip" | "opinion";
  };

  type getCategoryRssParams = {
    category:
      "ai-models" | "ai-products" | "industry" | "paper" | "tip" | "opinion";
  };

  type getCodexResetSnapshotParams = {
    include_withdrawn?: boolean;
  };

  type getCollectionCoverageMetricsParams = {
    /** UTC 到期范围起点 (包含) */
    start: string;
    /** UTC 到期范围终点 (不包含); 最多 31 天 */
    end: string;
    source_key?: string | null;
    capability?: SourceCapability | null;
    topic_id?: string | null;
  };

  type getCollectionCoverageParams = {
    window_id: string;
  };

  type getCollectionJobParams = {
    job_id: string;
  };

  type getContentCommentRunReadinessParams = {
    content_id: string;
  };

  type getContentRecordParams = {
    content_id: string;
  };

  type getContentTranslationParams = {
    run_id: string;
  };

  type getCurrentEditorialRunParams = {
    content_id: string;
  };

  type getEditionMarkdownParams = {
    kind: "daily" | "weekly" | "monthly";
    key: string;
  };

  type getEditionRssParams = {
    kind: "daily" | "weekly" | "monthly";
  };

  type getEditorialRunParams = {
    run_id: string;
  };

  type getEditorialSourceIconParams = {
    profile_id: string;
  };

  type getEditorialSourcePreviewParams = {
    job_id: string;
  };

  type getEditorialSourceProfileParams = {
    profile_id: string;
  };

  type getEventHeatParams = {
    event_id: string;
  };

  type getEventParams = {
    event_id: string;
  };

  type getExternalEditorialIngressReceiptParams = {
    profile_id: string;
    run_id: string;
  };

  type getHistoricalHotlistSnapshotParams = {
    source_key: string;
    snapshot_id: string;
    cursor?: number | null;
    limit?: number;
  };

  type getHotlistSnapshotParams = {
    source_key: string;
    cursor?: number | null;
    limit?: number;
  };

  type getLeaderboardBoardParams = {
    board: "overall" | "coding" | "reasoning" | "knowledge" | "professional";
    domestic?: boolean;
    open_weights?: boolean;
  };

  type getLeaderboardModelParams = {
    slug: string;
  };

  type getLeaderboardSourceParams = {
    source_key: string;
  };

  type getMonitorTopicParams = {
    topic_id: string;
  };

  type getOperatorFeedbackAttachmentParams = {
    attachment_id: string;
  };

  type getOperatorRelationBenchParams = {
    run_id: string;
    cursor?: string | null;
    limit?: number;
    disagree?: boolean;
    errors?: boolean;
  };

  type getOperatorSelectBenchParams = {
    run_id: string;
    model?: string | null;
    outcome?: "tp" | "fp" | "tn" | "fn" | "either" | "error" | null;
    stratum?: string | null;
    disagree?: boolean;
    cursor?: string | null;
    limit?: number;
  };

  type getPublicationEditionPosterParams = {
    kind: "daily" | "weekly" | "monthly";
    key: string;
  };

  type getPublicationEditionPosterPngParams = {
    kind: "daily" | "weekly" | "monthly";
    key: string;
  };

  type getPublicationEditionShareImageParams = {
    kind: "daily" | "weekly" | "monthly";
    key: string;
  };

  type getPublicationEditionSitemapShardParams = {
    shard: number;
  };

  type getPublicationItemPosterParams = {
    content_id: string;
  };

  type getPublicationItemPosterPngParams = {
    content_id: string;
  };

  type getPublicationItemShareImageParams = {
    content_id: string;
  };

  type getPublicationJsonLdParams = {
    content_id: string;
  };

  type getPublicationMarkdownParams = {
    content_id: string;
  };

  type getPublicationMediaMirrorRunParams = {
    run_id: string;
  };

  type getPublicationMediaParams = {
    file_id: string;
    mode:
      | "original"
      | "avatar"
      | "card"
      | "thumb"
      | "full"
      | "og"
      | "avatar-48"
      | "avatar-96"
      | "image-336"
      | "image-720"
      | "image-1200"
      | "image-1600";
  };

  type getPublicationRepublishRunParams = {
    run_id: string;
  };

  type getPublicationSitemapShardParams = {
    shard: number;
  };

  type getPublicationStoryPosterParams = {
    event_id: string;
  };

  type getPublicationStoryPosterPngParams = {
    event_id: string;
  };

  type getPublicationStoryShareImageParams = {
    event_id: string;
  };

  type getPublicationStorySitemapShardParams = {
    shard: number;
  };

  type getPublicationTopicShareImageParams = {
    slug: string;
  };

  type getPublicationTopicSitemapShardParams = {
    shard: number;
  };

  type getPublicContactImageParams = {
    sha256: string;
  };

  type getPublicDailyCalendarParams = {
    month: string;
  };

  type getPublicEditionNavigationParams = {
    kind: "daily" | "weekly" | "monthly";
    key: string;
  };

  type getPublicEditionParams = {
    kind: "daily" | "weekly" | "monthly";
    key: string;
  };

  type getPublicFactReportsParams = {
    fact_id: string;
    limit?: number;
    cursor?: string | null;
    revision?: string | null;
    window?: "24h" | "7d";
    channel?: "all" | "news" | "x" | "firstParty";
    category?:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    source_key?: string | null;
    tag?: string | null;
    topic?: string | null;
  };

  type getPublicHotStoriesParams = {
    limit?: number;
  };

  type getPublicPageShareImageParams = {
    page:
      | "site"
      | "all"
      | "hot"
      | "daily"
      | "weekly"
      | "monthly"
      | "topics"
      | "leaderboard"
      | "codex-reset"
      | "about"
      | "terms"
      | "privacy"
      | "changelog"
      | "feedback"
      | "agent"
      | "contact";
  };

  type getPublicPublicationItemParams = {
    content_id: string;
  };

  type getPublicReadingTimelineParams = {
    limit?: number;
    cursor?: string | null;
    window?: "24h" | "7d";
    channel?: "all" | "news" | "x" | "firstParty";
    category?:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    source_key?: string | null;
    tag?: string | null;
    topic?: string | null;
  };

  type getPublicSourceAvatarParams = {
    source_key: string;
    mode: "avatar-48" | "avatar-96";
  };

  type getPublicSourceIconParams = {
    source_key: string;
  };

  type getPublicStoryDevelopmentsParams = {
    event_id: string;
    limit?: number;
    cursor?: string | null;
    revision?: string | null;
    window?: "24h" | "7d";
    channel?: "all" | "news" | "x" | "firstParty";
    category?:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    source_key?: string | null;
    tag?: string | null;
    topic?: string | null;
  };

  type getPublicStoryParams = {
    event_id: string;
  };

  type getPublicTopicPageParams = {
    slug: string;
    page?: number;
  };

  type getReportEditionParams = {
    edition_id: string;
  };

  type getReportParams = {
    report_id: string;
  };

  type getSelectedPublicationChangesParams = {
    epoch: string;
    since: number;
    limit?: number;
  };

  type getSelectedPublicationSnapshotParams = {
    limit?: number;
    cursor?: string | null;
  };

  type getSitePublicationItemParams = {
    content_id: string;
  };

  type getSitePublicationMediaParams = {
    file_id: string;
    mode:
      | "original"
      | "avatar"
      | "card"
      | "thumb"
      | "full"
      | "og"
      | "avatar-48"
      | "avatar-96"
      | "image-336"
      | "image-720"
      | "image-1200"
      | "image-1600";
  };

  type GithubAuthorizationInput = {
    /** Return To */
    return_to?: string;
  };

  type GithubAuthorizationView = {
    /** Authorization Url */
    authorization_url: string;
  };

  type HealthView = {
    /** Status */
    status: "ok" | "ready";
  };

  type HotlistBucketMetricView = {
    /** Interval Seconds */
    interval_seconds: number;
    /** Expected Count */
    expected_count: number;
    /** Recorded Count */
    recorded_count: number;
    /** Success Count */
    success_count: number;
    /** Missing Count */
    missing_count: number;
    /** Success Ratio */
    success_ratio: number | null;
    /** Cadence Consistent */
    cadence_consistent: boolean;
    /** Phase Verified */
    phase_verified: boolean;
  };

  type HotlistEntryView = {
    /** Rank */
    rank: number;
    /** Title */
    title: string;
    /** Url */
    url: string;
    /** Summary */
    summary: string | null;
    /** Heat */
    heat: string | null;
    /** Published At */
    published_at: string | null;
    /** Content Id */
    content_id: string | null;
    /** Previous Rank */
    previous_rank: number | null;
    /** Rank Delta */
    rank_delta: number | null;
    /** Rank Change */
    rank_change: "new" | "up" | "down" | "same";
    /** Matched */
    matched: boolean;
    /** Matched Topic Names */
    matched_topic_names: string[];
  };

  type HotlistSnapshotSummaryView = {
    /** Snapshot Id */
    snapshot_id: string;
    /** Source Key */
    source_key: string;
    /** Observed At */
    observed_at: string;
    /** Due At */
    due_at: string;
    /** Entry Count */
    entry_count: number;
    /** Previous Snapshot Id */
    previous_snapshot_id: string | null;
    /** Gap Count */
    gap_count: number;
  };

  type HotlistSnapshotView = {
    /** Snapshot Id */
    snapshot_id: string;
    /** Source Key */
    source_key: string;
    /** Observed At */
    observed_at: string;
    /** Due At */
    due_at: string;
    /** Operation Id */
    operation_id: string;
    /** Entry Count */
    entry_count: number;
    /** Previous Snapshot Id */
    previous_snapshot_id: string | null;
    /** Gap Count */
    gap_count: number;
    /** Items */
    items: HotlistEntryView[];
    /** Next Cursor */
    next_cursor: number | null;
  };

  type HotlistSourceView = {
    /** Source Key */
    source_key: string;
    /** Latest Observed At */
    latest_observed_at: string | null;
  };

  type IdentityCredentialsUpdateInput = {
    /** Username */
    username: string;
    /** Password */
    password: string;
    /** Current Password */
    current_password?: string | null;
    /** Challenge Id */
    challenge_id?: string | null;
    /** Code */
    code?: string | null;
  };

  type IdentityPasswordLoginInput = {
    /** Username 已验证邮箱或已有用户名 */
    username: string;
    /** Password */
    password: string;
  };

  type IdentitySessionView = {
    user: IdentityUserView;
    /** Expires At */
    expires_at: string;
  };

  type IdentityUserView = {
    /** Id */
    id: string;
    /** Username */
    username: string;
    /** Email */
    email: string | null;
    /** Has Password */
    has_password: boolean;
  };

  type ingestExternalEditorialSourceParams = {
    profile_id: string;
  };

  type JobAcceptanceStatus = "queued";

  type JobAcceptedView = {
    /** Job Id */
    job_id: string;
    status: JobAcceptanceStatus;
  };

  type JobCancellationView = {
    /** Requested At */
    requested_at: string;
    /** Deadline At */
    deadline_at: string | null;
    /** Timed Out */
    timed_out: boolean;
  };

  type JobContinuousFailureIssueView = {
    /** Source Key */
    source_key: string;
    source_capability: SourceCapability;
    /** Configuration Ref */
    configuration_ref: string;
    /** Configuration Version */
    configuration_version: number;
    /** Latest Failed Job Id */
    latest_failed_job_id: string;
    failure: JobFailureView;
    /** Consecutive Failure Threshold */
    consecutive_failure_threshold: number;
  };

  type JobControlStatus =
    | "queued"
    | "running"
    | "cancelling"
    | "succeeded"
    | "partially_succeeded"
    | "failed"
    | "cancelled";

  type JobDelayReason =
    | "internal_queue"
    | "rate_limited"
    | "budget_exhausted"
    | "transient_failure"
    | "manual_retry"
    | "other";

  type JobFailureCategory =
    | "transient"
    | "rate_limited"
    | "authentication_required"
    | "permission_denied"
    | "invalid_response"
    | "parse_error"
    | "invalid_input"
    | "configuration_unavailable";

  type JobFailureView = {
    /** Error Code */
    error_code: string;
    category: JobFailureCategory;
    /** Occurred At */
    occurred_at: string;
    /** Next Action */
    next_action: string;
    /** Manual Retry Allowed */
    manual_retry_allowed: boolean;
  };

  type JobHistoryItemView = {
    /** Id */
    id: string;
    /** Kind */
    kind: string;
    /** Source Key */
    source_key: string | null;
    source_capability: SourceCapability | null;
    status: JobControlStatus;
    /** Requests Sent */
    requests_sent: number;
    /** Items Saved */
    items_saved: number;
    /** Created At */
    created_at: string;
    /** Started At */
    started_at: string | null;
    /** Completed At */
    completed_at: string | null;
    /** Next Run At */
    next_run_at: string | null;
  };

  type JobObservationContext = {
    /** Configuration Ref */
    configuration_ref: string;
    /** Configuration Version */
    configuration_version: number;
    /** Source Key */
    source_key?: string | null;
    source_capability?: SourceCapability | null;
  };

  type JobProgressView = {
    stage: JobStage | null;
    /** Requests Sent */
    requests_sent: number;
    /** Items Saved */
    items_saved: number;
    /** Updated At */
    updated_at: string | null;
  };

  type JobStage = "request" | "parse" | "save" | "analysis";

  type JobStatus =
    | "queued"
    | "running"
    | "succeeded"
    | "partially_succeeded"
    | "failed"
    | "cancelled";

  type JobStatusView = {
    /** Id */
    id: string;
    /** Operation Id */
    operation_id: string;
    /** Kind */
    kind: string;
    observation: JobObservationContext;
    status: JobControlStatus;
    progress: JobProgressView;
    cancellation: JobCancellationView | null;
    failure: JobFailureView | null;
    /** Result Content Id */
    result_content_id: string | null;
    /** Retry Count */
    retry_count: number;
    /** Collection Cycle No */
    collection_cycle_no: number;
    /** Collection Cycle Started At */
    collection_cycle_started_at: string | null;
    /** Collection Cycle Requests Sent */
    collection_cycle_requests_sent: number;
    /** Collection Cycle Pending */
    collection_cycle_pending: boolean;
    /** Latest Attempt Started At */
    latest_attempt_started_at: string | null;
    /** Latest Attempt Finished At */
    latest_attempt_finished_at: string | null;
    /** Queue Wait Us */
    queue_wait_us: number | null;
    /** Attempt Elapsed Us */
    attempt_elapsed_us: number | null;
    /** Total Elapsed Us */
    total_elapsed_us: number | null;
    /** Collection Budget Remaining Us */
    collection_budget_remaining_us: number | null;
    /** Next Run At */
    next_run_at: string | null;
    /** Scheduled For At */
    scheduled_for_at: string | null;
    /** Started At */
    started_at: string | null;
    /** Completed At */
    completed_at: string | null;
    /** Created At */
    created_at: string;
    source_freshness?: SourceFreshnessView | null;
    /** Coverage Windows */
    coverage_windows?: CoverageWindowView[];
  };

  type JobView = {
    /** Id */
    id: string;
    /** Owner Id */
    owner_id: string;
    /** Operation Id */
    operation_id: string;
    /** Kind */
    kind: string;
    observation: JobObservationContext;
    status: JobStatus;
    /** Scheduled For At */
    scheduled_for_at: string | null;
    /** Started At */
    started_at: string | null;
    /** Completed At */
    completed_at: string | null;
    /** Created At */
    created_at: string;
  };

  type JsonValue = Record<string, any>;

  type KeywordInput = string;

  type listCodexResetPostsParams = {
    page?: number;
    filter_key?: "all" | "relevant" | "pending" | "review";
  };

  type listCodexResetScanGapsParams = {
    monitor_id: string;
  };

  type listCollectionCoverageParams = {
    /** UTC 到期范围起点 (包含) */
    start: string;
    /** UTC 到期范围终点 (不包含); 最多比起点晚 31 天 */
    end: string;
    source_key?: string | null;
    capability?: SourceCapability | null;
    topic_id?: string | null;
    limit?: number;
    /** 上一页返回的不透明游标 */
    cursor?: string | null;
  };

  type listCollectionJobsParams = {
    cursor?: string | null;
    limit?: number;
  };

  type listContentCommentsParams = {
    content_id: string;
    root_id?: string | null;
    parent_id?: string | null;
    cursor?: string | null;
    limit?: number;
  };

  type listContentRecordsParams = {
    cursor?: string | null;
    limit?: number;
    topic_id?: string | null;
    source_key?: string | null;
    starts_at?: string | null;
    ends_at?: string | null;
    analysis_state?:
      "missing" | "pending" | "failed" | "invalid" | "valid" | null;
    /** 最多 6 个空白分隔词项, 按 AND 字面搜索标题与正文 */
    q?: string | null;
  };

  type listEditorialSourceRunsParams = {
    profile_id: string;
    limit?: number;
  };

  type listEventFactsParams = {
    event_id: string;
    revision?: number | null;
  };

  type listEventHeatHistoryParams = {
    event_id: string;
    limit?: number;
  };

  type listEventMembersParams = {
    event_id: string;
    revision?: number | null;
    cursor?: string | null;
    limit?: number;
  };

  type listEventsParams = {
    cursor?: string | null;
    limit?: number;
    topic_id?: string | null;
    source_key?: string | null;
    starts_at?: string | null;
    ends_at?: string | null;
    query?: string | null;
  };

  type listHotEventsParams = {
    topic_id?: string | null;
  };

  type listHotlistSnapshotsParams = {
    source_key: string;
    cursor?: string | null;
    limit?: number;
  };

  type listMonitorTopicsParams = {
    include_archived?: boolean;
    cursor?: string | null;
    limit?: number;
  };

  type listOperatorAuditParams = {
    cursor?: string | null;
    limit?: number;
  };

  type listOperatorFeedbackParams = {
    cursor?: string | null;
    limit?: number;
    state?: "new" | "reviewing" | "resolved" | "rejected" | "deleted" | null;
  };

  type listOperatorNotificationDeliveriesParams = {
    cursor?: string | null;
    limit?: number;
  };

  type listPublicEditionCatalogueParams = {
    kind?: "daily" | "weekly" | "monthly";
    before_key?: string | null;
    limit?: number;
  };

  type listPublicItemsParams = {
    window?: "24h" | "7d";
    mode?: "selected" | "all";
    by?: "timeline" | "published";
    category?:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    channel?: "news" | "x" | "firstParty" | null;
    source_key?: string | null;
    tag?: string | null;
    topic?: string | null;
    q?: string | null;
    search_order?: "relevance" | "time";
    limit?: number;
    cursor?: string | null;
  };

  type listRelatedEventsParams = {
    event_id: string;
  };

  type listReportEditionRevisionsParams = {
    edition_id: string;
    limit?: number;
  };

  type listReportEditionsParams = {
    kind?: "daily" | "weekly" | "monthly";
    before_key?: string | null;
    limit?: number;
  };

  type listReportsParams = {
    topic_id?: string | null;
    date_from?: string | null;
    date_to?: string | null;
    kind?: ReportKind;
    cursor?: string | null;
    limit?: number;
  };

  type LoginOptionsView = {
    /** Password */
    password: boolean;
    /** Github */
    github: boolean;
    /** Email */
    email: boolean;
  };

  type MaintenanceAcceptedView = {
    /** Job Id */
    job_id: string;
    /** Audit Id */
    audit_id: string;
    /** Replayed */
    replayed?: boolean;
  };

  type MaintenanceFindingView = {
    /** Key */
    key: string;
    /** Severity */
    severity: "now" | "today" | "digest";
    /** Title */
    title: string;
    /** Detail */
    detail: string;
  };

  type MaintenanceInput = {
    /** Operation Id */
    operation_id: string;
    /** Action */
    action:
      | "lifecycle_sweep"
      | "recover"
      | "alerts"
      | "digest"
      | "source_health"
      | "feedback_forward"
      | "backup"
      | "verify_backup"
      | "retention"
      | "watchdog";
    /** Reason */
    reason: string;
    /** Backup Id */
    backup_id?: string | null;
  };

  type MaintenanceScheduleView = {
    /** Action */
    action: string;
    /** Interval Seconds */
    interval_seconds: number;
    /** Enabled */
    enabled: boolean;
    latest_audit: OperatorAuditView | null;
  };

  type MaintenanceStateView = {
    /** Schedules */
    schedules: MaintenanceScheduleView[];
    /** Findings */
    findings: MaintenanceFindingView[];
    /** Backups */
    backups: OperatorAuditView[];
  };

  type McpError = {
    /** Code */
    code: number;
    /** Message */
    message: string;
  };

  type McpResponse = {
    /** Jsonrpc */
    jsonrpc?: string;
    /** Id */
    id: string | number | null;
    /** Result */
    result?: Record<string, any> | null;
    error?: McpError | null;
  };

  type MediaMirrorInput = {
    /** Operation Id */
    operation_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Policy Revision */
    policy_revision: number;
  };

  type MediaMirrorRunView = {
    /** Id */
    id: string;
    /** Job Id */
    job_id: string;
    /** Content Id */
    content_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Policy Revision */
    policy_revision: number;
    /** Status */
    status:
      | "queued"
      | "running"
      | "complete"
      | "partial"
      | "unknown"
      | "failed"
      | "stale"
      | "cancelled";
    /** Candidate Count */
    candidate_count: number;
    /** Available Count */
    available_count: number;
    /** Unavailable Count */
    unavailable_count: number;
    /** Reason */
    reason: string | null;
    /** Replayed */
    replayed: boolean;
  };

  type MediaRenditionView = {
    /** Mode */
    mode: string;
    /** Reading Url */
    reading_url: string;
    /** Mime Type */
    mime_type: string;
    /** Width */
    width: number | null;
    /** Height */
    height: number | null;
    /** Frame Count */
    frame_count: number;
    /** Byte Count */
    byte_count: number;
  };

  type MissingEvidenceView = {
    /** Key */
    key: string;
    /** Name */
    name: string;
    /** Reason */
    reason?: string | null;
  };

  type ModelDetailView = {
    run: RunView;
    /** Historical */
    historical: boolean;
    model: ModelRefView;
    /** Context Window Tokens */
    context_window_tokens: number | null;
    /** Weights Url */
    weights_url: string | null;
    price: PriceView | null;
    overall: CategoryRankView;
    overall_stability: StabilityView | null;
    /** Categories */
    categories: CategoryRankView[];
    /** Metric Count */
    metric_count: number;
    /** Evidence */
    evidence: EvidenceGroupView[];
    /** Excluded */
    excluded: MissingEvidenceView[];
    /** Unmeasured */
    unmeasured: MissingEvidenceView[];
    /** Comparisons */
    comparisons: ComparisonView[];
  };

  type ModelRefView = {
    /** Slug */
    slug: string;
    /** Name */
    name: string;
    /** Provider */
    provider: string | null;
    /** Released At */
    released_at: string | null;
    brand: BrandView;
  };

  type MonitorConfiguration = {
    /** Author */
    author?: string;
    /** Source Key */
    source_key?: string;
    /** Author External Id */
    author_external_id?: string | null;
    /** Connection Id */
    connection_id?: string | null;
    /** Connection Version */
    connection_version?: number | null;
    /** Normal Interval Seconds */
    normal_interval_seconds?: number;
    /** Hot Interval Seconds */
    hot_interval_seconds?: number;
    /** Max Pages */
    max_pages?: number;
  };

  type MonitorExpansionPreviewView = {
    /** Local Alias External Queries */
    local_alias_external_queries: number;
    /** Local Alias Budget Units */
    local_alias_budget_units: number;
    /** Upstream Status */
    upstream_status: string;
    /** Upstream External Queries */
    upstream_external_queries: null;
    /** Upstream Budget Units */
    upstream_budget_units: null;
  };

  type MonitorRulePreviewSampleView = {
    /** Sample Index */
    sample_index: number;
    /** Matched */
    matched: boolean;
    /** Matched Any */
    matched_any: string[];
    /** Matched All */
    matched_all: string[];
    /** Excluded By */
    excluded_by: string[];
  };

  type MonitorRuleSetView = {
    /** Match Any */
    match_any: string[];
    /** Match All */
    match_all: string[];
    /** Exclude */
    exclude: string[];
  };

  type MonitorTopicCreateInput = {
    /** Match Any */
    match_any: KeywordInput[];
    /** Match All */
    match_all: KeywordInput[];
    /** Exclude */
    exclude: KeywordInput[];
    /** Name */
    name: string;
    /** Source Keys */
    source_keys?: SourceKeyInput[];
    /** Collection Interval Seconds */
    collection_interval_seconds?: number;
    /** Report Time */
    report_time?: string;
    /** Weekly Report Enabled */
    weekly_report_enabled?: boolean;
    /** Notification Target Names */
    notification_target_names?: NotificationTargetNameInput[];
  };

  type MonitorTopicPreviewInput = {
    /** Match Any */
    match_any: KeywordInput[];
    /** Match All */
    match_all: KeywordInput[];
    /** Exclude */
    exclude: KeywordInput[];
    /** Sample Titles */
    sample_titles: PreviewSampleInput[];
  };

  type MonitorTopicPreviewView = {
    rules: MonitorRuleSetView;
    /** Samples */
    samples: MonitorRulePreviewSampleView[];
    expansion: MonitorExpansionPreviewView;
  };

  type MonitorTopicReadinessStatus =
    "pending_source_selection" | "pending_source_readiness" | "ready";

  type MonitorTopicRunInput = {
    /** Operation Id */
    operation_id: string;
    /** Source Keys */
    source_keys: SourceKeyInput[];
  };

  type MonitorTopicRunSourceView = {
    /** Source Key */
    source_key: string;
    /** Job Ids */
    job_ids: string[];
    /** Skip Reason */
    skip_reason:
      "source_unavailable" | "quiet" | "budget" | "rate_limited" | null;
  };

  type MonitorTopicRunView = {
    /** Operation Id */
    operation_id: string;
    /** Topic Id */
    topic_id: string;
    /** Topic Version */
    topic_version: number;
    /** Sources */
    sources: MonitorTopicRunSourceView[];
  };

  type MonitorTopicStatus = "paused" | "active" | "archived";

  type MonitorTopicUpdateInput = {
    /** Match Any */
    match_any: KeywordInput[];
    /** Match All */
    match_all: KeywordInput[];
    /** Exclude */
    exclude: KeywordInput[];
    /** Name */
    name: string;
    /** Source Keys */
    source_keys?: SourceKeyInput[];
    /** Collection Interval Seconds */
    collection_interval_seconds?: number;
    /** Report Time */
    report_time?: string;
    /** Weekly Report Enabled */
    weekly_report_enabled?: boolean;
    /** Notification Target Names */
    notification_target_names?: NotificationTargetNameInput[];
    /** Expected Version */
    expected_version: number;
  };

  type MonitorTopicView = {
    /** Id */
    id: string;
    /** Name */
    name: string;
    status: MonitorTopicStatus;
    readiness_status: MonitorTopicReadinessStatus;
    /** Current Version */
    current_version: number;
    rules: MonitorRuleSetView;
    /** Source Keys */
    source_keys: string[];
    /** Collection Interval Seconds */
    collection_interval_seconds: number;
    /** Report Time */
    report_time: string;
    /** Report Timezone */
    report_timezone: string;
    /** Weekly Report Enabled */
    weekly_report_enabled: boolean;
    /** Notification Target Names */
    notification_target_names: string[];
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
  };

  type MonitorView = {
    /** Id */
    id: string;
    /** Enabled */
    enabled: boolean;
    /** Revision */
    revision: number;
    /** Configuration Version */
    configuration_version: number;
    configuration: MonitorConfiguration;
  };

  type NoiseFilter = {
    /** Drop Markers */
    drop_markers?: string[];
    /** Drop Markers Title Only */
    drop_markers_title_only?: string[];
    /** Keep If Matches */
    keep_if_matches?: string[];
  };

  type NotificationChannel = "feishu" | "email";

  type NotificationDeliveryView = {
    /** Id */
    id: string;
    /** Revision */
    revision: number;
    /** Target Id */
    target_id: string;
    /** Target Revision */
    target_revision: number;
    subject_kind: NotificationSubjectKind;
    /** Subject Id */
    subject_id: string;
    /** Subject Revision */
    subject_revision: number;
    status: DeliveryStatus;
    /** Attempt Count */
    attempt_count: number;
    /** Last Error Code */
    last_error_code: string | null;
    /** Sent At */
    sent_at: string | null;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
    /** Provider Receipt */
    provider_receipt: Record<string, any>;
  };

  type NotificationSubjectKind =
    "report" | "edition" | "selected" | "codex_reset";

  type NotificationTargetNameInput = string;

  type NumericCondition = {
    /** Path */
    path: string;
    /** Min */
    min: number;
  };

  type OperationsHealthView = {
    /** Generated At */
    generated_at: string;
    /** Heartbeats */
    heartbeats: ProcessHeartbeatView[];
    /** Failure Issues */
    failure_issues: JobContinuousFailureIssueView[];
    /** Budgets */
    budgets: BudgetWindowUsageView[];
    /** Feedback New Count */
    feedback_new_count: number;
    /** Feedback Reviewing Count */
    feedback_reviewing_count: number;
    /** Maintenance Enabled */
    maintenance_enabled: boolean;
    /** Feedback Forward Enabled */
    feedback_forward_enabled: boolean;
    /** Backup Configured */
    backup_configured: boolean;
  };

  type OperatorAuditView = {
    /** Id */
    id: string;
    /** Operation Id */
    operation_id: string;
    /** Action */
    action: string;
    /** Target Ref */
    target_ref: string;
    /** Actor */
    actor: string;
    /** Reason */
    reason: string;
    /** Status */
    status: string;
    /** Before State */
    before_state: Record<string, any>;
    /** After State */
    after_state: Record<string, any>;
    /** Job Id */
    job_id: string | null;
    /** Error Code */
    error_code: string | null;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
  };

  type OutageView = {
    /** Post Id */
    post_id: string;
    /** Published At */
    published_at: string;
    /** Original Text */
    original_text: string;
    /** Translation Zh */
    translation_zh: string | null;
    /** Recovered At */
    recovered_at: string | null;
    /** Reset Event Id */
    reset_event_id: string | null;
    /** Url */
    url: string;
  };

  type overridePublicationParams = {
    content_id: string;
  };

  type PageViewCollectionCoverageView_ = {
    /** Items */
    items: CollectionCoverageView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewContentCommentView_ = {
    /** Items */
    items: ContentCommentView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewContentRecordSummaryView_ = {
    /** Items */
    items: ContentRecordSummaryView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewEventReadView_ = {
    /** Items */
    items: EventReadView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewFeedbackView_ = {
    /** Items */
    items: FeedbackView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewHotlistSnapshotSummaryView_ = {
    /** Items */
    items: HotlistSnapshotSummaryView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewHotlistSourceView_ = {
    /** Items */
    items: HotlistSourceView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewJobHistoryItemView_ = {
    /** Items */
    items: JobHistoryItemView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewMonitorTopicView_ = {
    /** Items */
    items: MonitorTopicView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewNotificationDeliveryView_ = {
    /** Items */
    items: NotificationDeliveryView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewOperatorAuditView_ = {
    /** Items */
    items: OperatorAuditView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewReportSummaryView_ = {
    /** Items */
    items: ReportSummaryView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PageViewSourcePlatformView_ = {
    /** Items */
    items: SourcePlatformView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type ParticipationMode = "editorial" | "hot_signal" | "isolated";

  type pauseMonitorTopicParams = {
    topic_id: string;
  };

  type PendingModelView = {
    model: ModelRefView;
    /** Sources */
    sources: number;
  };

  type pollCodexResetMonitorParams = {
    monitor_id: string;
  };

  type pollEditorialSourceParams = {
    profile_id: string;
  };

  type PrefilterOutput = {
    /** Label */
    label: "PASS" | "BLOCK" | "UNKNOWN";
    /** Reason */
    reason: string;
  };

  type PrefixRewrite = {
    /** From Prefix */
    from_prefix: string;
    /** To Prefix */
    to_prefix: string;
  };

  type PresentationStatus =
    | "announced"
    | "in_progress"
    | "confirmed"
    | "expired_unconfirmed"
    | "likely_completed"
    | "withdrawn";

  type PreviewSampleInput = string;

  type previewStoredEditorialSourceParams = {
    profile_id: string;
  };

  type PriceView = {
    /** Currency */
    currency: string;
    /** Input Price */
    input_price: number | null;
    /** Output Price */
    output_price: number | null;
    /** Cached Input Price */
    cached_input_price: number | null;
    /** Cny Input Price */
    cny_input_price: number | null;
    /** Cny Output Price */
    cny_output_price: number | null;
    /** Cny Cached Input Price */
    cny_cached_input_price: number | null;
    /** Verified On */
    verified_on: string;
    /** Source Url */
    source_url: string;
    /** Unit */
    unit?: string;
  };

  type ProcessHeartbeatView = {
    /** Role */
    role: string;
    /** Instance Id */
    instance_id: string;
    /** Pid */
    pid: number;
    /** State */
    state: "alive" | "stopping" | "error" | "stale";
    /** Last Seen At */
    last_seen_at: string;
    /** Started At */
    started_at: string;
    /** Age Seconds */
    age_seconds: number;
    /** Detail */
    detail: Record<string, any>;
  };

  type PublicationOverrideInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Visibility */
    visibility: "public" | "summary-only" | "withdrawn";
    /** Seo Indexed */
    seo_indexed?: boolean;
    /** Seo Excluded */
    seo_excluded?: boolean;
    /** Reason */
    reason: string;
  };

  type PublicAttentionView = {
    /** Formula Version */
    formula_version: string;
    /** Window End */
    window_end: string;
    /** Last Source Time */
    last_source_time: string;
    /** Heat */
    heat: number;
    /** Eligible */
    eligible: boolean;
    /** Participant Count */
    participant_count: number;
    /** Editorial Participant Count */
    editorial_participant_count: number;
    /** Signal Participant Count */
    signal_participant_count: number;
    /** Comparable Participant Count */
    comparable_participant_count: number;
    /** Uncomparable Participant Count */
    uncomparable_participant_count: number;
    /** Comparable Heat */
    comparable_heat: number;
    /** Comparable Previous Heat */
    comparable_previous_heat: number;
    /** Previous Heat */
    previous_heat: number;
    /** Trend */
    trend: "new" | "up" | "down" | "flat" | "unknown";
    /** Trend Pct */
    trend_pct: number | null;
    /** Complete */
    complete: boolean;
    /** Badges */
    badges: ("new" | "surge" | "rising")[];
  };

  type PublicBodyView = {
    /** Original */
    original: string;
    /** Original Format */
    original_format?: "text" | "html" | "markdown";
    /** Original Html */
    original_html?: string | null;
    /** Body Sha256 */
    body_sha256?: string | null;
    /** Outline */
    outline?: PublicOutlineEntry[];
    /** Media */
    media?: PublicMediaView[];
    /** Translated */
    translated?: string | null;
    /** Translation Complete */
    translation_complete?: boolean;
    /** Translation State */
    translation_state?:
      | "not_requested"
      | "queued"
      | "running"
      | "complete"
      | "partial"
      | "unknown"
      | "failed"
      | "stale";
    /** Translation Revision */
    translation_revision?: number | null;
  };

  type PublicContactView = {
    /** Enabled */
    enabled: boolean;
    /** Title */
    title: string | null;
    /** Text */
    text: string | null;
    /** Url */
    url: string | null;
    /** Wechat Qr Url */
    wechat_qr_url: string | null;
    /** Feishu Qr Url */
    feishu_qr_url: string | null;
    /** Revision */
    revision: number;
  };

  type PublicDailyCalendarView = {
    /** Month */
    month: string;
    /** Entries */
    entries: PublicEditionIndexView[];
  };

  type PublicDevelopmentsPage = {
    /** Event Id */
    event_id: string;
    /** Revision */
    revision: string;
    /** Developments */
    developments: PublicDevelopmentView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PublicDevelopmentView = {
    /** Fact Id */
    fact_id: string;
    /** Title */
    title: string;
    /** Anchor At */
    anchor_at: string;
    /** Report Count */
    report_count: number;
    representative: PublicItemView;
  };

  type PublicEditionCatalogueView = {
    /** Kind */
    kind: "daily" | "weekly" | "monthly";
    /** Entries */
    entries: PublicEditionIndexView[];
    /** Next Before Key */
    next_before_key: string | null;
  };

  type PublicEditionIndexView = {
    /** Kind */
    kind: "daily" | "weekly" | "monthly";
    /** Key */
    key: string;
    /** Title */
    title: string;
    /** Revision */
    revision: number;
    /** Created At */
    created_at: string;
    /** Reading Url */
    reading_url: string;
    /** Indexable */
    indexable?: boolean;
  };

  type PublicEditionNavigationView = {
    current: PublicEditionIndexView | null;
    previous: PublicEditionIndexView | null;
    next: PublicEditionIndexView | null;
  };

  type PublicEditionSectionView = {
    /** Label */
    label: string;
    /** Content Ids */
    content_ids: string[];
  };

  type PublicEditionThemeView = {
    /** Heading */
    heading: string;
    /** Summary */
    summary: string;
    /** Content Ids */
    content_ids: string[];
  };

  type PublicEditionView = {
    /** Id */
    id: string;
    /** Kind */
    kind: "daily" | "weekly" | "monthly";
    /** Key */
    key: string;
    /** Revision */
    revision: number;
    /** Title */
    title: string;
    /** Lead */
    lead: string;
    /** Window Start */
    window_start: string;
    /** Window End */
    window_end: string;
    /** Created At */
    created_at: string;
    /** Highlights */
    highlights: string[];
    /** Sections */
    sections: PublicEditionSectionView[];
    /** Flashes */
    flashes: string[];
    /** Themes */
    themes: PublicEditionThemeView[];
    /** Entries */
    entries: PublicItemView[];
    /** Metrics */
    metrics: Record<string, any>;
    /** Body Markdown */
    body_markdown: string;
    /** Indexable */
    indexable?: boolean;
    /** Canonical Url */
    canonical_url?: string | null;
  };

  type PublicFactReportsPage = {
    /** Fact Id */
    fact_id: string;
    /** Revision */
    revision: string;
    /** Reports */
    reports: PublicItemView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type PublicItemDetailView = {
    /** Id */
    id: string;
    /** Revision */
    revision: number;
    /** Title */
    title: string;
    /** Original Title */
    original_title: string | null;
    /** Summary */
    summary: string | null;
    source: PublicSourceView;
    /** Original Url */
    original_url: string;
    /** Reading Url */
    reading_url: string;
    /** Published At */
    published_at: string | null;
    /** Discovered At */
    discovered_at: string;
    /** Timeline At */
    timeline_at: string;
    /** Category */
    category:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    /** Tags */
    tags: string[];
    /** Score */
    score: number | null;
    /** Selected */
    selected: boolean;
    /** Reason */
    reason: string | null;
    /** Event Id */
    event_id: string | null;
    /** Fact Id */
    fact_id: string | null;
    /** Indexable */
    indexable: boolean;
    /** Reading Mode */
    reading_mode: "full" | "summary-only";
    body: PublicBodyView | null;
    /** Site Fulltext */
    site_fulltext: boolean;
    /** Syndicate Fulltext */
    syndicate_fulltext: boolean;
    /** Markdown Available */
    markdown_available: boolean;
    /** License Name */
    license_name: string;
    /** License Url */
    license_url: string | null;
    quoted_post?: PublicQuotedPostView | null;
    /** Related Stories */
    related_stories?: PublicRelatedStoryView[];
  };

  type PublicItemsPage = {
    /** Items */
    items: PublicItemView[];
    /** Next Cursor */
    next_cursor: string | null;
    /** Snapshot At */
    snapshot_at: string;
  };

  type PublicItemView = {
    /** Id */
    id: string;
    /** Revision */
    revision: number;
    /** Title */
    title: string;
    /** Original Title */
    original_title: string | null;
    /** Summary */
    summary: string | null;
    source: PublicSourceView;
    /** Original Url */
    original_url: string;
    /** Reading Url */
    reading_url: string;
    /** Published At */
    published_at: string | null;
    /** Discovered At */
    discovered_at: string;
    /** Timeline At */
    timeline_at: string;
    /** Category */
    category:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    /** Tags */
    tags: string[];
    /** Score */
    score: number | null;
    /** Selected */
    selected: boolean;
    /** Reason */
    reason: string | null;
    /** Event Id */
    event_id: string | null;
    /** Fact Id */
    fact_id: string | null;
    /** Indexable */
    indexable: boolean;
  };

  type PublicMediaView = {
    /** Key */
    key: string;
    /** Kind */
    kind: "image" | "video" | "audio" | "unknown";
    /** Original Url */
    original_url: string;
    /** Alt */
    alt: string;
    /** Reading Url */
    reading_url: string | null;
    /** State */
    state:
      | "original_link"
      | "available"
      | "pending"
      | "running"
      | "unknown"
      | "failed"
      | "stale"
      | "cancelled"
      | "unavailable";
    /** Width */
    width?: number | null;
    /** Height */
    height?: number | null;
    /** Renditions */
    renditions?: MediaRenditionView[];
  };

  type PublicOutlineEntry = {
    /** Id */
    id: string;
    /** Title */
    title: string;
    /** Level */
    level: number;
  };

  type PublicQuotedPostView = {
    item: PublicItemView;
    /** Author */
    author: string | null;
    body: PublicBodyView | null;
  };

  type PublicReadingFilters = {
    /** Window */
    window?: "24h" | "7d";
    /** Channel */
    channel?: "all" | "news" | "x" | "firstParty";
    /** Category */
    category?:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    /** Source Key */
    source_key?: string | null;
    /** Tag */
    tag?: string | null;
    /** Topic */
    topic?: string | null;
  };

  type PublicReadingGroupView = {
    /** Fact Id */
    fact_id: string;
    /** Event Id */
    event_id: string | null;
    /** Additional Source Count */
    additional_source_count: number;
    /** Report Count */
    report_count: number;
    /** Development Count */
    development_count: number;
    latest_development: PublicDevelopmentView | null;
  };

  type PublicRelatedStoryView = {
    /** Id */
    id: string;
    /** Revision */
    revision: number;
    /** Title */
    title: string;
    /** Summary */
    summary: string | null;
    /** Reading Url */
    reading_url: string;
    /** Supporting Reports */
    supporting_reports: number;
  };

  type PublicRelatedTopicView = {
    /** Slug */
    slug: string;
    /** Name */
    name: string;
  };

  type PublicSiteFeatures = {
    /** Editorial Analysis */
    editorial_analysis: boolean;
    /** Model Leaderboard */
    model_leaderboard: boolean;
    /** Codex Monitor */
    codex_monitor: boolean;
    /** Notifications */
    notifications: boolean;
    /** Smtp */
    smtp: boolean;
    /** Media Mirror */
    media_mirror: boolean;
    /** Feedback */
    feedback: boolean;
    /** External Indexing */
    external_indexing: boolean;
  };

  type PublicSiteMetaView = {
    /** Name */
    name: string;
    /** Version */
    version: string;
    /** Environment */
    environment: string;
    /** Description */
    description: string;
    /** Public Base Url */
    public_base_url: string;
    /** Robots Index */
    robots_index?: boolean;
    features: PublicSiteFeatures;
  };

  type PublicSiteStatisticsView = {
    /** Visible Items */
    visible_items: number;
    /** Selected Items */
    selected_items: number;
    /** Visible Sources */
    visible_sources: number;
    /** Latest Publication At */
    latest_publication_at: string | null;
    /** Snapshot At */
    snapshot_at: string;
  };

  type PublicSourceView = {
    /** Key */
    key: string;
    /** Name */
    name: string;
    /** Kind */
    kind: string;
    /** First Party */
    first_party: boolean;
    /** Icon Url */
    icon_url?: string | null;
  };

  type PublicStoriesPage = {
    /** Stories */
    stories: PublicStoryView[];
    /** Ranking Basis */
    ranking_basis: "heat" | "recent_without_heat";
    /** Next Cursor */
    next_cursor?: string | null;
  };

  type PublicStoryView = {
    /** Id */
    id: string;
    /** Revision */
    revision: number;
    /** Title */
    title: string;
    /** Summary */
    summary: string;
    /** Latest Progress */
    latest_progress: string | null;
    /** Phase */
    phase: "active" | "watching" | "settled";
    /** First Seen At */
    first_seen_at: string;
    /** Heat */
    heat?: number | null;
    attention?: PublicAttentionView | null;
    /** Reports */
    reports: PublicItemView[];
    /** Indexable */
    indexable?: boolean;
    /** Canonical Url */
    canonical_url?: string | null;
  };

  type PublicTimelineCardView = {
    /** Key */
    key: string;
    /** Anchor At */
    anchor_at: string;
    item: PublicItemView;
    group: PublicReadingGroupView | null;
  };

  type PublicTimelinePage = {
    filters: PublicReadingFilters;
    /** Cards */
    cards: PublicTimelineCardView[];
    /** Next Cursor */
    next_cursor: string | null;
    /** Refresh At */
    refresh_at: string | null;
    /** Day Counts */
    day_counts?: Record<string, any>;
    /** Snapshot At */
    snapshot_at: string;
  };

  type PublicTopicDirectoryView = {
    /** Topics */
    topics: PublicTopicSummaryView[];
    /** Refresh At */
    refresh_at: string | null;
  };

  type PublicTopicPageView = {
    topic: PublicTopicSummaryView;
    /** Related */
    related: PublicRelatedTopicView[];
    /** Items */
    items: PublicItemView[];
    /** Page */
    page: number;
    /** Page Count */
    page_count: number;
    /** Refresh At */
    refresh_at: string | null;
  };

  type PublicTopicSummaryView = {
    /** Slug */
    slug: string;
    /** Name */
    name: string;
    /** Group */
    group: "company" | "field" | "genre";
    /** Definition */
    definition: string;
    /** Total */
    total: number;
    /** Recent */
    recent: number;
    /** Indexable */
    indexable: boolean;
    /** Latest At */
    latest_at: string | null;
  };

  type PublishResultView = {
    /** Content Id */
    content_id: string;
    /** Changed */
    changed: boolean;
    /** Revision */
    revision: number;
    /** Selected */
    selected: boolean;
    /** Visibility */
    visibility: "public" | "summary-only" | "withdrawn";
    /** Ledger */
    ledger: "upsert" | "remove" | null;
    /** Reduced */
    reduced: boolean;
  };

  type RankingEntryView = {
    /** Rank */
    rank: number;
    /** Score */
    score: number;
    model: ModelRefView;
    /** Source Count */
    source_count: number;
    /** Operator Count */
    operator_count: number;
    /** Coverage */
    coverage: number;
    /** Confidence */
    confidence: "HIGH" | "MEDIUM" | "LOW";
    stability: StabilityView | null;
    price: PriceView | null;
    access: AccessView;
  };

  type readEditorialSourceIconParams = {
    profile_id: string;
    mode: "avatar-48" | "avatar-96";
  };

  type refreshEditorialSourceIconParams = {
    profile_id: string;
  };

  type RelationBenchCasesView = {
    run: SelectBenchRunView;
    /** Items */
    items: RelationBenchCaseView[];
    /** Next Cursor */
    next_cursor: string | null;
    /** Strata */
    strata: Record<string, any>;
  };

  type RelationBenchCaseView = {
    case: RelationGoldCaseInput;
    /** By Model */
    by_model: Record<string, any>;
  };

  type RelationBenchGoldInput = {
    /** Operation Id */
    operation_id: string;
    /** Label */
    label: string;
    /** Reason */
    reason: string;
    /** Models */
    models: string[];
    /** Cases */
    cases: RelationGoldCaseInput[];
    /** Sample Size */
    sample_size?: number;
    /** Split */
    split?: string | null;
    /** Seed */
    seed?: number;
  };

  type RelationBenchImportInput = {
    /** Operation Id */
    operation_id: string;
    /** Label */
    label: string;
    /** Reason */
    reason: string;
    /** Models */
    models: string[];
    /** Cases */
    cases: RelationGoldCaseInput[];
    /** Sample Size */
    sample_size?: number;
    /** Split */
    split?: string | null;
    /** Seed */
    seed?: number;
    /** Predictions */
    predictions: Record<string, any>;
  };

  type RelationGoldCaseInput = {
    /** Case Id */
    case_id: string;
    a: RelationReportInput;
    b: RelationReportInput;
    gold_relation: VerdictRelation;
    /** Stratum */
    stratum?: string | null;
    /** Split */
    split?: string | null;
  };

  type RelationPredictionInput = {
    /** Case Id */
    case_id: string;
    relation?: VerdictRelation | null;
    /** Confidence */
    confidence?: number | null;
    /** Difference */
    difference?: string | null;
    /** Error Code */
    error_code?: string | null;
  };

  type RelationReportInput = {
    /** Title */
    title: string;
    /** Source */
    source: string;
    /** First Party */
    first_party?: boolean;
    /** Published At */
    published_at?: string | null;
    /** Summary */
    summary?: string | null;
    /** Frame */
    frame?: Record<string, any> | null;
  };

  type relinkCodexResetPostParams = {
    monitor_id: string;
    post_id: string;
  };

  type ReportCitationView = {
    /** Citation */
    citation: string;
    /** Title */
    title: string;
    /** Url */
    url: string | null;
  };

  type ReportDetailView = {
    /** Id */
    id: string;
    /** Topic Id */
    topic_id: string;
    /** Topic Name */
    topic_name: string;
    kind: ReportKind;
    /** Window Start */
    window_start: string;
    /** Window End */
    window_end: string;
    /** Version */
    version: number;
    generator: ReportGenerator;
    /** Cutoff At */
    cutoff_at: string;
    /** Body Markdown */
    body_markdown: string;
    /** Citations */
    citations: ReportCitationView[];
  };

  type ReportGenerator = "template" | "model";

  type ReportKind = "daily" | "weekly";

  type ReportPublicationCandidate = {
    /** Content Id */
    content_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Editorial Run Id */
    editorial_run_id: string;
    /** Manual Version */
    manual_version: number;
    /** Source Profile Revision */
    source_profile_revision: number;
    /** Policy Revision */
    policy_revision: number;
    /** Publication Revision */
    publication_revision: number;
    /** Event Id */
    event_id?: string | null;
    /** Event Revision */
    event_revision?: number | null;
    /** Fact Id */
    fact_id?: string | null;
    /** Root Fact Id */
    root_fact_id?: string | null;
    /** Fact Revision */
    fact_revision?: number | null;
    /** Topic Id */
    topic_id?: string | null;
    /** Title Zh */
    title_zh: string;
    /** Summary Zh */
    summary_zh: string;
    /** Source Key */
    source_key: string;
    /** Source Name */
    source_name: string;
    /** Source Kind */
    source_kind: string;
    /** First Party */
    first_party: boolean;
    /** Url */
    url: string;
    /** Category */
    category:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    /** Tags */
    tags: string[];
    /** Score */
    score: number | null;
    /** Timeline At */
    timeline_at: string;
    /** Backfill */
    backfill: boolean | null;
    /** Root Title */
    root_title?: string | null;
  };

  type ReportSummaryView = {
    /** Id */
    id: string;
    /** Topic Id */
    topic_id: string;
    /** Topic Name */
    topic_name: string;
    kind: ReportKind;
    /** Window Start */
    window_start: string;
    /** Window End */
    window_end: string;
    /** Version */
    version: number;
    generator: ReportGenerator;
  };

  type RepublishInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Policy Revision */
    expected_policy_revision: number;
  };

  type republishPublicationSourceParams = {
    source_key: string;
  };

  type RepublishRunView = {
    /** Id */
    id: string;
    /** Job Id */
    job_id: string;
    /** Source Key */
    source_key: string;
    /** Policy Revision */
    policy_revision: number;
    /** Status */
    status: "queued" | "running" | "completed" | "failed" | "cancelled";
    /** After Content Id */
    after_content_id: string | null;
    /** Processed Count */
    processed_count: number;
    /** Failure Code */
    failure_code: string | null;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
  };

  type requestContentTranslationParams = {
    content_id: string;
  };

  type requestEditorialRunParams = {
    content_id: string;
    source_key: string;
  };

  type requestPublicationMediaMirrorParams = {
    content_id: string;
  };

  type ResetAction = "announce" | "progress" | "confirm" | "amend" | "withdraw";

  type ResetEventPost = {
    /** Post Id */
    post_id: string;
    /** External Id */
    external_id: string;
    /** Published At */
    published_at: string;
    action: ResetAction;
    /** Stage */
    stage: string;
    /** Excerpt */
    excerpt: string;
    /** Excerpt Zh */
    excerpt_zh: string;
    /** Original Text */
    original_text: string;
    /** Translation Zh */
    translation_zh: string | null;
    /** Url */
    url: string;
    /** Context */
    context: ContextPost[];
  };

  type ResetEventView = {
    /** Id */
    id: string;
    kind: ResetKind;
    /** Status */
    status: "announced" | "confirmed";
    /** Revision */
    revision: number;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
    /** Withdrawn */
    withdrawn?: boolean;
    /** In Progress */
    in_progress?: boolean;
    /** Kind Explicit */
    kind_explicit?: boolean;
    /** Time Inferred */
    time_inferred?: boolean;
    /** Confirmed At */
    confirmed_at?: string | null;
    /** Occurred On */
    occurred_on?: string | null;
    /** Confirmation Basis */
    confirmation_basis?: "source_post" | "receipt_review" | null;
    schedule?: Schedule | null;
    estimate?: Estimate | null;
    scope?: ResetScope;
    /** Reported At */
    reported_at?: string | null;
    presentation_status?: PresentationStatus;
    /** Title */
    title?: string;
    /** Posts */
    posts?: ResetEventPost[];
  };

  type ResetHealth = {
    /** Status */
    status: "unknown" | "attention" | "delayed" | "healthy";
    /** Enabled */
    enabled: boolean;
    /** Last Attempt At */
    last_attempt_at: string | null;
    /** Last Collected At */
    last_collected_at: string | null;
    /** Last Verified At */
    last_verified_at: string | null;
    /** Pending Count */
    pending_count: number;
    /** Review Count */
    review_count: number;
    /** Held Window Count */
    held_window_count: number;
  };

  type ResetKind = "direct_reset" | "reset_credit";

  type ResetPostView = {
    /** Id */
    id: string;
    /** External Id */
    external_id: string;
    /** Published At */
    published_at: string;
    /** Text */
    text: string;
    /** Translation Zh */
    translation_zh: string | null;
    /** Url */
    url: string;
    /** Context */
    context: ContextPost[];
    /** Processed At */
    processed_at: string | null;
    /** Needs Review */
    needs_review: boolean;
    /** Reviewed */
    reviewed: boolean;
    /** Review Version */
    review_version: number;
    /** Failure Count */
    failure_count: number;
    /** Failure Code */
    failure_code: string | null;
    /** Event Ids */
    event_ids?: string[];
  };

  type ResetScope = {
    /** Audience Source */
    audience_source?: string | null;
    /** Plans */
    plans?: string[] | null;
    /** Audience Zh */
    audience_zh?: string | null;
    /** Products Zh */
    products_zh?: string | null;
  };

  type ResetSnapshot = {
    /** Schema Version */
    schema_version?: number;
    /** Timezone */
    timezone?: string;
    /** Today */
    today: string;
    /** Checked At */
    checked_at: string | null;
    /** History From */
    history_from: string | null;
    /** Events */
    events: ResetEventView[];
    /** Activities */
    activities: ResetPostView[];
    monitor: ResetHealth;
    outage: OutageView | null;
    /** Calendar */
    calendar: CalendarMark[];
    statistics: ResetStatistics;
    current: ResetEventView | null;
    last_landed: ResetEventView | null;
    /** Confirm Minutes */
    confirm_minutes: number[];
    /** Version */
    version: string;
  };

  type ResetStatistics = {
    /** Resets 90 */
    resets_90: number;
    /** Credits 90 */
    credits_90: number;
    /** Median Interval Days */
    median_interval_days: number | null;
    /** Last Reset Date */
    last_reset_date: string | null;
  };

  type ResetVersionView = {
    /** Version */
    version: string;
    /** Checked At */
    checked_at: string | null;
    /** Today */
    today: string;
  };

  type resolveOperatorDeliveryParams = {
    audit_id: string;
  };

  type resolveOperatorNotificationDeliveryParams = {
    delivery_id: string;
  };

  type resumeMonitorTopicParams = {
    topic_id: string;
  };

  type retryCollectionJobParams = {
    job_id: string;
  };

  type reviewCodexResetPostParams = {
    monitor_id: string;
    post_id: string;
  };

  type reviewCodexResetScanGapParams = {
    monitor_id: string;
    gap_id: string;
  };

  type reviewEditorialSourcePreviewParams = {
    job_id: string;
  };

  type reviewEditorialSourceRunParams = {
    profile_id: string;
    run_id: string;
  };

  type ReviewInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Actor */
    actor: string;
  };

  type RulesView = {
    run: RunView | null;
    /** Methodology Version */
    methodology_version: string;
    /** Score Definition */
    score_definition: string;
    /** Display Method */
    display_method: string;
    /** Tie Policy */
    tie_policy: string;
    /** Budgets */
    budgets: BudgetView[];
    /** Anchors */
    anchors: string[];
    /** Configuration Policy */
    configuration_policy: string;
    /** Carry Forward Days */
    carry_forward_days: number;
    /** Release Window Months */
    release_window_months: number;
    /** Overall Minimum Models */
    overall_minimum_models?: number;
    /** Overall Minimum Anchors */
    overall_minimum_anchors?: number;
    /** Category Minimum Models */
    category_minimum_models?: number;
    /** Category Minimum Anchors */
    category_minimum_anchors?: number;
  };

  type runContentCommentsParams = {
    content_id: string;
  };

  type runMonitorTopicParams = {
    topic_id: string;
  };

  type RunView = {
    /** Id */
    id: string;
    /** Methodology Version */
    methodology_version: string;
    /** Generated At */
    generated_at: string;
    /** Calculated At */
    calculated_at: string | null;
    /** Fingerprint */
    fingerprint: string;
    fx: FxQuoteView | null;
  };

  type saveEditorialSourceParams = {
    source_key: string;
  };

  type savePublicationSourcePolicyParams = {
    source_key: string;
  };

  type ScanGapView = {
    /** Id */
    id: string;
    /** Configuration Version */
    configuration_version: number;
    /** Monitor Revision */
    monitor_revision: number;
    /** Query */
    query: string;
    /** Has Resume Token */
    has_resume_token: boolean;
    /** Stop At Id */
    stop_at_id: string | null;
    /** Before Id */
    before_id: string | null;
    /** Starts At */
    starts_at: string | null;
    /** Ends At */
    ends_at: string | null;
    /** State */
    state: "pending" | "held" | "complete";
    /** Failure Code */
    failure_code: string | null;
    /** Created At */
    created_at: string;
    /** Updated At */
    updated_at: string;
  };

  type Schedule = {
    precision: SchedulePrecision;
    /** Starts At */
    starts_at: string;
    /** Ends At */
    ends_at: string;
    /** Label */
    label: string;
  };

  type SchedulePrecision =
    "exact" | "approximate" | "deadline" | "date" | "window";

  type ScreenshotInput = {
    /** Mime */
    mime: "image/png" | "image/jpeg" | "image/webp" | "image/gif";
    /** Data Base64 */
    data_base64: string;
  };

  type SelectBenchAcceptedView = {
    run: SelectBenchRunView;
    /** Job Ids */
    job_ids: string[];
    /** Replayed */
    replayed?: boolean;
  };

  type SelectBenchCaseInput = {
    /** Case Id */
    case_id: string;
    /** Title */
    title: string;
    /** Stratum */
    stratum?: string | null;
    /** Gold */
    gold: "select" | "reject" | "either";
    /** Decision */
    decision?: "select" | "reject" | null;
    /** Score */
    score?: number | null;
    /** Relevance */
    relevance?: string | null;
    /** Category */
    category?: string | null;
    /** Reason */
    reason?: string | null;
    /** Error Code */
    error_code?: string | null;
  };

  type SelectBenchCasesView = {
    run: SelectBenchRunView;
    /** Items */
    items: SelectBenchCaseView[];
    /** Next Cursor */
    next_cursor: string | null;
    /** Strata */
    strata: Record<string, any>;
  };

  type SelectBenchCaseView = {
    /** Case Id */
    case_id: string;
    /** Title */
    title: string;
    /** Stratum */
    stratum: string | null;
    /** Gold */
    gold: "select" | "reject" | "either";
    /** By Model */
    by_model: Record<string, any>;
  };

  type SelectBenchGoldCaseInput = {
    /** Case Id */
    case_id: string;
    /** Title */
    title: string;
    /** Body */
    body?: string;
    /** Gold */
    gold: "select" | "reject" | "either";
    /** Stratum */
    stratum?: string | null;
    /** Split */
    split?: string | null;
    /** Source Name */
    source_name?: string;
    /** Source Kind */
    source_kind?:
      | "rss"
      | "web_list"
      | "json_list"
      | "x_search"
      | "mp_account"
      | "external"
      | "other";
    /** Tier */
    tier?: "T1" | "T1_5" | "T2" | "EXCLUDE_MP" | "UNGRADED";
    /** First Party */
    first_party?: boolean;
    /** Published At */
    published_at?: string | null;
    /** Author */
    author?: string | null;
    /** Url */
    url?: string;
    /** Quoted Text */
    quoted_text?: string;
    /** Quoted Author */
    quoted_author?: string;
  };

  type SelectBenchGoldInput = {
    /** Operation Id */
    operation_id: string;
    /** Label */
    label: string;
    /** Reason */
    reason: string;
    /** Models */
    models: string[];
    /** Cases */
    cases: SelectBenchGoldCaseInput[];
    /** Sample Size */
    sample_size?: number;
    /** Split */
    split?: string | null;
    /** Seed */
    seed?: number;
  };

  type SelectBenchImportInput = {
    /** Operation Id */
    operation_id: string;
    /** Label */
    label: string;
    /** Reason */
    reason: string;
    /** Prompt Version */
    prompt_version: string;
    /** Split */
    split?: string | null;
    /** Seed */
    seed?: number | null;
    /** Models */
    models: Record<string, any>;
  };

  type SelectBenchRunView = {
    /** Id */
    id: string;
    /** Operation Id */
    operation_id: string;
    /** Label */
    label: string;
    /** Prompt Version */
    prompt_version: string;
    /** Split */
    split: string | null;
    /** Seed */
    seed: number | null;
    /** Sample Size */
    sample_size: number;
    /** Models */
    models: string[];
    /** Summary */
    summary: Record<string, any>;
    /** Gold Fingerprint */
    gold_fingerprint: string;
    /** Created At */
    created_at: string;
    /** Replayed */
    replayed?: boolean;
    /** Kind */
    kind?: "selection" | "relation";
  };

  type SelectedChangesPage = {
    /** Epoch */
    epoch: string;
    /** Sequence */
    sequence: number;
    /** Changes */
    changes: SelectedChangeView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type SelectedChangeView = {
    /** Sequence */
    sequence: number;
    /** Operation */
    operation: "upsert" | "remove";
    /** Content Id */
    content_id: string;
    /** Changed At */
    changed_at: string;
    item: PublicItemView | null;
  };

  type SelectedSnapshotView = {
    /** Epoch */
    epoch: string;
    /** Sequence */
    sequence: number;
    /** Items */
    items: PublicItemView[];
    /** Next Cursor */
    next_cursor: string | null;
  };

  type Sentiment = "positive" | "neutral" | "negative";

  type SiteConfigurationInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Contact Enabled */
    contact_enabled?: boolean;
    /** Contact Title */
    contact_title?: string;
    /** Contact Text */
    contact_text?: string;
    /** Contact Url */
    contact_url?: string | null;
    /** Wechat Qr Action */
    wechat_qr_action?: "keep" | "replace" | "clear";
    wechat_image?: ContactImageInput | null;
    /** Feishu Qr Action */
    feishu_qr_action?: "keep" | "replace" | "clear";
    feishu_image?: ContactImageInput | null;
  };

  type SiteConfigurationView = {
    /** Revision */
    revision: number;
    /** Contact Enabled */
    contact_enabled: boolean;
    /** Contact Title */
    contact_title: string;
    /** Contact Text */
    contact_text: string;
    /** Contact Url */
    contact_url: string | null;
    /** Wechat Qr Url */
    wechat_qr_url: string | null;
    /** Feishu Qr Url */
    feishu_qr_url: string | null;
    /** Updated At */
    updated_at: string | null;
  };

  type SourceCapability =
    | "search"
    | "author_posts"
    | "comments"
    | "replies"
    | "page_content"
    | "hotlist";

  type SourceCapabilityStatus =
    | "unconfigured"
    | "pending_verification"
    | "available"
    | "authentication_required"
    | "restricted"
    | "disabled";

  type SourceCapabilityView = {
    capability: SourceCapability;
    /** Display Name */
    display_name: string;
    manual: SourceEntryPointView;
    scheduled: SourceEntryPointView;
  };

  type SourceConnectionStatus = "active" | "disabled";

  type SourceConnectionUpdateInput = {
    /** Expected Version */
    expected_version: number;
    status: SourceConnectionStatus;
    /** Owner Confirmed */
    owner_confirmed?: boolean;
    /** Allowed Hosts */
    allowed_hosts?: string[];
  };

  type SourceConnectionView = {
    /** Id */
    id: string;
    /** Source Key */
    source_key: string;
    status: SourceConnectionStatus;
    /** Version */
    version: number;
    /** Allowed Hosts */
    allowed_hosts: string[];
    /** Updated At */
    updated_at: string;
  };

  type SourceDetailView = {
    run: RunView | null;
    source: SourceSummaryView;
    /** Full Name */
    full_name: string;
    /** Area */
    area: string | null;
    /** Official Url */
    official_url: string | null;
    /** What */
    what: string;
    /** Usage */
    usage: string;
    /** Limits */
    limits: string;
    /** License */
    license: string;
    /** Attribution */
    attribution: string | null;
    /** Upstream At */
    upstream_at: string | null;
    /** Synced At */
    synced_at: string | null;
    /** Collected */
    collected: boolean;
    /** System Rows */
    system_rows: boolean;
    /** Rows */
    rows: SourceRowView[];
    /** Rows Note */
    rows_note: string | null;
  };

  type SourceEntryPointView = {
    status: SourceCapabilityStatus;
    /** Last Checked At */
    last_checked_at: string | null;
    /** Last Persisted Success At */
    last_persisted_success_at: string | null;
    stop_reason: SourceStopReason | null;
    /** Next Action */
    next_action: string;
  };

  type SourceFreshnessView = {
    /** Last Attempt At */
    last_attempt_at: string | null;
    /** Last Success At */
    last_success_at: string | null;
    delay_reason: JobDelayReason | null;
    /** Delay Since At */
    delay_since_at: string | null;
    /** Delay Duration Us */
    delay_duration_us: number | null;
  };

  type SourceGroupView = {
    /** Key */
    key: string;
    /** Name */
    name: string;
    /** Blurb */
    blurb: string;
    /** Sources */
    sources: SourceSummaryView[];
  };

  type SourceIconRefreshInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    /** Action */
    action?: "refresh" | "retry_unknown";
  };

  type SourceIconVariant = {
    /** Mode */
    mode: "avatar-48" | "avatar-96";
    /** Url */
    url: string;
    /** Sha256 */
    sha256: string;
    /** Mime Type */
    mime_type: "image/webp" | "image/jpeg" | "image/svg+xml";
    /** Width */
    width: 48 | 96;
    /** Height */
    height: 48 | 96;
  };

  type SourceIconView = {
    /** Profile Id */
    profile_id: string;
    /** Configuration Version */
    configuration_version: number;
    /** Status */
    status:
      | "not_configured"
      | "ready"
      | "missing"
      | "blocked"
      | "unknown"
      | "running"
      | "obsolete";
    /** Checked At */
    checked_at: string | null;
    /** Next Retry At */
    next_retry_at: string | null;
    /** Failure Code */
    failure_code?: string | null;
    /** Variants */
    variants?: SourceIconVariant[];
  };

  type SourceKeyInput = string;

  type SourcePlatformStatus =
    | "unconfigured"
    | "pending_verification"
    | "available"
    | "authentication_required"
    | "restricted"
    | "disabled"
    | "partial";

  type SourcePlatformView = {
    /** Source Key */
    source_key: string;
    /** Display Name */
    display_name: string;
    rollout_role: SourceRolloutRole;
    status: SourcePlatformStatus;
    /** Connection Version */
    connection_version: number | null;
    /** Has Credentials */
    has_credentials: boolean;
    /** Connection Id */
    connection_id: string | null;
    connection_status: SourceConnectionStatus | null;
    safety_stop_reason?: SourceStopReason | null;
    /** Safety Stopped At */
    safety_stopped_at?: string | null;
    /** Safety Trigger Job Id */
    safety_trigger_job_id?: string | null;
    /** Credential Configured */
    credential_configured: boolean;
    /** Credential Update Available */
    credential_update_available: boolean;
    /** Allowed Hosts */
    allowed_hosts: string[];
    /** Capabilities */
    capabilities: SourceCapabilityView[];
  };

  type SourcePolicyInput = {
    /** Operation Id */
    operation_id: string;
    /** Expected Revision */
    expected_revision: number;
    /** Participation Mode */
    participation_mode?: "editorial" | "hot_signal" | "isolated";
    /** Body Format */
    body_format?: "text" | "html" | "markdown";
    /** Site Fulltext */
    site_fulltext?: boolean;
    /** Syndicate Fulltext */
    syndicate_fulltext?: boolean;
    /** Indexable */
    indexable?: boolean;
    /** Release Delay Seconds */
    release_delay_seconds?: number;
    /** License Name */
    license_name: string;
    /** License Url */
    license_url?: string | null;
    /** Reason */
    reason: string;
  };

  type SourcePolicyView = {
    /** Source Key */
    source_key: string;
    /** Revision */
    revision: number;
    /** Participation Mode */
    participation_mode: "editorial" | "hot_signal" | "isolated";
    /** Body Format */
    body_format?: "text" | "html" | "markdown";
    /** Site Fulltext */
    site_fulltext: boolean;
    /** Syndicate Fulltext */
    syndicate_fulltext: boolean;
    /** Indexable */
    indexable: boolean;
    /** Release Delay Seconds */
    release_delay_seconds: number;
    /** License Name */
    license_name: string;
    /** License Url */
    license_url: string | null;
    /** Updated At */
    updated_at: string;
  };

  type SourceRolloutRole = "required" | "candidate";

  type SourceRowView = {
    /** Source Rank */
    source_rank: number | null;
    /** Source Model Name */
    source_model_name: string;
    /** Model Slug */
    model_slug: string | null;
    /** Provider */
    provider: string | null;
    /** Display */
    display: string;
    /** Configuration Label */
    configuration_label: string;
    /** Excluded */
    excluded: string | null;
  };

  type SourceStopReason =
    | "end_of_results"
    | "source_empty"
    | "rate_limited"
    | "authentication_required"
    | "access_denied"
    | "not_found"
    | "unsupported"
    | "cancelled"
    | "budget_exhausted"
    | "upstream_error"
    | "protocol_error"
    | "cursor_expired"
    | "cursor_loop";

  type SourceSummaryView = {
    /** Key */
    key: string;
    /** Status */
    status: string;
    /** Name */
    name: string;
    /** Operator */
    operator: string;
    /** Description */
    description: string;
    brand: BrandView;
    /** Weight */
    weight: number;
    /** Family Key */
    family_key: string | null;
    /** Category Key */
    category_key: string | null;
    /** Collected */
    collected: boolean;
  };

  type SourcesView = {
    run: RunView | null;
    /** Groups */
    groups: SourceGroupView[];
  };

  type StabilityView = {
    /** From Rank */
    from_rank: number;
    /** To Rank */
    to_rank: number;
    /** Fixed From */
    fixed_from: number;
    /** Fixed To */
    fixed_to: number;
    /** Scenarios */
    scenarios: number;
    /** Sensitive */
    sensitive: boolean;
    /** Incomplete */
    incomplete: number;
    /** Ordinal Rank */
    ordinal_rank: number;
    /** Unavailable */
    unavailable: number;
  };

  type StructureOutput = {
    /** Category */
    category:
      | "ai-models"
      | "ai-products"
      | "industry"
      | "paper"
      | "tip"
      | "opinion"
      | null;
    /** Tags */
    tags: string[];
    /** Subjects */
    subjects: string[];
    fact: FactOutput | null;
  };

  type TargetInput = {
    /** Name */
    name: string;
    channel: NotificationChannel;
    /** Recipients */
    recipients?: string[];
    /** Secret Env */
    secret_env?: string | null;
    /** Enabled */
    enabled?: boolean;
    /** Subscriptions */
    subscriptions?: NotificationSubjectKind[];
  };

  type TargetSaveInput = {
    /** Operation Id */
    operation_id: string;
    /** Target Id */
    target_id?: string | null;
    /** Expected Revision */
    expected_revision: number;
    /** Reason */
    reason: string;
    target: TargetInput;
  };

  type TargetView = {
    /** Id */
    id: string;
    /** Name */
    name: string;
    channel: NotificationChannel;
    /** Recipients */
    recipients: string[];
    /** Secret Env */
    secret_env: string | null;
    /** Enabled */
    enabled: boolean;
    /** Revision */
    revision: number;
    /** Enabled At */
    enabled_at: string | null;
    /** Subscriptions */
    subscriptions: NotificationSubjectKind[];
    /** Created At */
    created_at: string;
  };

  type TranslationRequestInput = {
    /** Operation Id */
    operation_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Policy Revision */
    policy_revision: number;
    /** Expected Revision */
    expected_revision?: number;
    /** Reason */
    reason: string;
  };

  type TranslationRunView = {
    /** Body Html */
    body_html?: string | null;
    /** Status */
    status?:
      | "not_requested"
      | "queued"
      | "running"
      | "complete"
      | "partial"
      | "unknown"
      | "failed"
      | "stale";
    /** Revision */
    revision?: number | null;
    /** Reason */
    reason?: string;
    /** Complete */
    complete?: boolean;
    /** Translated Segments */
    translated_segments?: number;
    /** Total Segments */
    total_segments?: number;
    /** Id */
    id: string;
    /** Content Id */
    content_id: string;
    /** Content Version Id */
    content_version_id: string;
    /** Policy Revision */
    policy_revision: number;
    /** Job Id */
    job_id: string;
    /** Created At */
    created_at: string;
  };

  type updateEditorialSourceProfileParams = {
    profile_id: string;
  };

  type updateMonitorTopicParams = {
    topic_id: string;
  };

  type updateOperatorFeedbackParams = {
    feedback_id: string;
  };

  type updateSourceConnectionParams = {
    source_key: string;
  };

  type ValidationErrorItem = {
    /** Location */
    location: (string | number)[];
    /** Message */
    message: string;
    /** Type */
    type: string;
  };

  type VerdictRelation =
    "SAME_OCCURRENCE" | "SAME_STORY" | "UNRELATED" | "ROUNDUP";

  type VerifyEmailCodeInput = {
    /** Challenge Id */
    challenge_id: string;
    /** Code */
    code: string;
  };

  type WebPageCollectionJobInput = {
    /** Operation Id */
    operation_id: string;
    /** Kind */
    kind: "webpage.collect";
    /** Url */
    url: string;
  };
}
