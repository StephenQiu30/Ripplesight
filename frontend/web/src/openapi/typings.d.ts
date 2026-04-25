declare namespace API {
  type DailyDigest = {
    id: string;
    digest_date: string;
    title: string;
    highlights: string[];
    event_ids: string[];
    generated_at: string;
    delivery_status: string;
  };

  type ErrorResponse = {
    code: string;
    message: string;
    details?: Record<string, any>;
    request_id: string;
  };

  type FeedbackRecord = {
    id?: string;
    target_type: string;
    target_id: string;
    feedback_type: string;
    comment?: string;
    created_at?: string;
  };

  type getEventsEventIdParams = {
    event_id: string;
  };

  type getEventsParams = {
    page?: number;
    page_size?: number;
    topic?: string;
    source_type?: string;
    from_date?: string;
    to_date?: string;
  };

  type getSearchParams = {
    q: string;
    page?: number;
    page_size?: number;
  };

  type getSourcesParams = {
    page?: number;
    page_size?: number;
    enabled?: boolean;
  };

  type HotspotEvent = {
    id: string;
    event_title: string;
    summary_zh: string;
    topic_tags?: string[];
    score: number;
    status: string;
    first_seen_at: string;
    last_seen_at: string;
    source_count: number;
    evidence_links: string[];
  };

  type KeywordRule = {
    id: string;
    keyword: string;
    category: string;
    query_template?: string;
    priority: number;
    enabled: boolean;
  };

  type MonitoredAccount = {
    id: string;
    platform: "x";
    handle: string;
    display_name?: string;
    account_type: string;
    weight: number;
    enabled: boolean;
  };

  type PageMeta = {
    page: number;
    page_size: number;
    total: number;
  };

  type PaginatedHotspotEvent = {
    items: HotspotEvent[];
    meta: PageMeta;
  };

  type PaginatedSourceConfig = {
    items: SourceConfig[];
    meta: PageMeta;
  };

  type RawContentItem = {
    id: string;
    source_config_id: string;
    external_id: string;
    title?: string;
    content_excerpt?: string;
    url: string;
    author?: string;
    published_at: string;
    language?: string;
    ingested_at: string;
  };

  type SourceConfig = {
    id: string;
    name: string;
    source_type: string;
    access_method: string;
    language?: string;
    region?: string;
    weight: number;
    poll_interval_minutes: number;
    enabled: boolean;
  };
}
