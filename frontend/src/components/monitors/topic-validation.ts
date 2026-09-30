import { ApiRequestError } from "@/request";

const TOPIC_FIELDS = [
  "name",
  "match_any",
  "match_all",
  "exclude",
  "source_keys",
  "collection_interval_seconds",
  "report_time",
  "notification_target_names",
] as const;

export type TopicFieldName = (typeof TOPIC_FIELDS)[number];
export type TopicFieldErrors = Partial<Record<TopicFieldName, string>>;

export function tryBeginTopicSubmission(lock: { current: boolean }): boolean {
  if (lock.current) return false;
  lock.current = true;
  return true;
}

export function readTopicFieldErrors(error: unknown): TopicFieldErrors {
  if (!(error instanceof ApiRequestError) || error.status !== 422) return {};
  const result: TopicFieldErrors = {};
  for (const detail of error.details ?? []) {
    const field = detail.location[1];
    if (
      typeof field === "string" &&
      TOPIC_FIELDS.includes(field as TopicFieldName)
    ) {
      result[field as TopicFieldName] ??= detail.message;
    }
  }
  return result;
}
