import { ApiRequestError } from "@/request";

export function topicStatusLabel(status: HotKeyAPI.MonitorTopicStatus) {
  return { active: "定时已启用", paused: "已暂停", archived: "已归档" }[status];
}

export function presentUpdatedTopic(
  original: HotKeyAPI.MonitorTopicView,
  updated?: HotKeyAPI.MonitorTopicView,
) {
  if (!updated || updated.id !== original.id) return original;
  return updated.current_version > original.current_version ||
    (updated.current_version === original.current_version &&
      Date.parse(updated.updated_at) >= Date.parse(original.updated_at))
    ? updated
    : original;
}

export type MonitorFailure = {
  message: string;
  code: string;
  httpStatus?: number;
  requestId?: string;
  forbidden: boolean;
};

export function readMonitorFailure(
  error: unknown,
  fallback: string,
): MonitorFailure {
  if (!(error instanceof ApiRequestError))
    return { message: fallback, code: "unexpected_error", forbidden: false };
  return {
    message: error.message,
    code: error.code ?? error.kind,
    httpStatus: error.status,
    requestId: error.requestId,
    forbidden: error.status === 401 || error.status === 403,
  };
}
