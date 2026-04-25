import {
  getEvents,
  getEventsEventId,
} from "@/openapi/events";
import { postFeedback } from "@/openapi/feedback";
import { getSearch } from "@/openapi/search";
import { getSources } from "@/openapi/sources";
import { getXAccounts, getXKeywords } from "@/openapi/xConfig";
import { getDigestsToday } from "@/openapi/digests";

export type HotspotEvent = API.HotspotEvent;
export type PaginatedResponse<T> = {
  items: T[];
  meta: API.PageMeta;
};

export async function listEvents(params: {
  page?: number | string;
  page_size?: number | string;
  topic?: string;
  source_type?: string;
  from_date?: string;
  to_date?: string;
}): Promise<API.PaginatedHotspotEvent> {
  return getEvents({
    ...params,
    page: params.page !== undefined ? Number(params.page) : undefined,
    page_size: params.page_size !== undefined ? Number(params.page_size) : undefined,
    topic: params.topic?.trim() || undefined,
    source_type: params.source_type?.trim() || undefined,
    from_date: params.from_date?.trim() || undefined,
    to_date: params.to_date?.trim() || undefined,
  });
}

export async function getEventById(eventId: string): Promise<API.HotspotEvent> {
  return getEventsEventId({ event_id: eventId });
}

export async function searchEvents(params: {
  q: string;
  page?: number | string;
  page_size?: number | string;
}): Promise<PaginatedResponse<API.HotspotEvent>> {
  return getSearch({
    ...params,
    q: params.q,
    page: params.page !== undefined ? Number(params.page) : undefined,
    page_size: params.page_size !== undefined ? Number(params.page_size) : undefined,
  });
}

export async function getTodayDigest(): Promise<API.DailyDigest> {
  return getDigestsToday();
}

export async function submitFeedback(payload: {
  target_type: API.FeedbackRecord["target_type"];
  target_id: string;
  feedback_type: API.FeedbackRecord["feedback_type"];
  comment?: string;
}) {
  return postFeedback({
    ...payload,
    comment: payload.comment?.trim() || undefined,
  });
}

export async function listSources(params?: {
  page?: number | string;
  page_size?: number | string;
  enabled?: boolean;
}): Promise<API.PaginatedSourceConfig> {
  if (!params) {
    return getSources({});
  }

  return getSources({
    ...params,
    page: params.page !== undefined ? Number(params.page) : undefined,
    page_size: params.page_size !== undefined ? Number(params.page_size) : undefined,
  });
}

export async function listKeywordRules(): Promise<PaginatedResponse<API.KeywordRule>> {
  return getXKeywords();
}

export async function listMonitoredAccounts(): Promise<PaginatedResponse<API.MonitoredAccount>> {
  return getXAccounts();
}
