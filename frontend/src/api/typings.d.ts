declare namespace HotKeyAPI {
  type archiveMonitorTopicParams = {
    topic_id: string;
  };

  type cancelCollectionJobParams = {
    job_id: string;
  };

  type cloneMonitorTopicParams = {
    topic_id: string;
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

  type CollectionScanKind = "new_scan" | "refresh" | "backfill";

  type CommentManualRunInput = {
    /** Operation Id */
    operation_id: string;
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
    /** Discoveries */
    discoveries: ContentDiscoveryView[];
    /** Version History */
    version_history: ContentVersionHistoryView[];
    /** Visibility History */
    visibility_history: ContentVisibilityView[];
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
  };

  type ContentRelationType = "quote" | "repost";

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

  type DueAdmissionState = "pending" | "accepted" | "skipped" | "missed";

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

  type getCollectionCoverageParams = {
    window_id: string;
  };

  type getCollectionJobParams = {
    job_id: string;
  };

  type getContentRecordParams = {
    content_id: string;
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

  type getMonitorTopicParams = {
    topic_id: string;
  };

  type getReportParams = {
    report_id: string;
  };

  type HealthView = {
    /** Status */
    status: "ok" | "ready";
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

  type IdentityCredentialsInput = {
    /** Username */
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
  };

  type IdentityWorkspaceView = {
    owner: IdentityUserView;
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

  type KeywordInput = string;

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

  type listReportsParams = {
    topic_id?: string | null;
    date_from?: string | null;
    date_to?: string | null;
    kind?: ReportKind;
    cursor?: string | null;
    limit?: number;
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

  type NotificationTargetNameInput = string;

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

  type pauseMonitorTopicParams = {
    topic_id: string;
  };

  type PreviewSampleInput = string;

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

  type resumeMonitorTopicParams = {
    topic_id: string;
  };

  type retryCollectionJobParams = {
    job_id: string;
  };

  type runContentCommentsParams = {
    content_id: string;
  };

  type runMonitorTopicParams = {
    topic_id: string;
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
    /** Credential Configured */
    credential_configured: boolean;
    /** Credential Update Available */
    credential_update_available: boolean;
    /** Allowed Hosts */
    allowed_hosts: string[];
    /** Capabilities */
    capabilities: SourceCapabilityView[];
  };

  type SourceRolloutRole = "required" | "candidate";

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

  type updateMonitorTopicParams = {
    topic_id: string;
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

  type WebPageCollectionJobInput = {
    /** Operation Id */
    operation_id: string;
    /** Kind */
    kind: "webpage.collect";
    /** Url */
    url: string;
  };
}
