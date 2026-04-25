export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type Keyword = {
  id: number;
  keyword: string;
  query_template: string | null;
  enabled: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
};

export type Source = {
  id: number;
  name: string;
  source_type: string;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AiAnalysis = {
  id: number;
  hotspot_id: number;
  is_real: boolean | null;
  relevance_score: string;
  relevance_reason: string | null;
  keyword_mentioned: boolean;
  importance: string;
  summary: string | null;
  model_name: string | null;
  raw_response: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Hotspot = {
  id: number;
  title: string;
  url: string;
  source_id: number;
  keyword_id: number | null;
  author: string | null;
  snippet: string | null;
  published_at: string | null;
  fetched_at: string;
  status: string;
  raw_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  source?: Source | null;
  keyword?: Keyword | null;
  ai_analysis?: AiAnalysis | null;
};

export type CheckRun = {
  id: number;
  trigger_type: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  success_count: number;
  failure_count: number;
  error_summary: string | null;
  created_at: string;
  updated_at: string;
};

export type Notification = {
  id: number;
  hotspot_id: number | null;
  channel: string;
  recipient: string | null;
  status: string;
  error_message: string | null;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Setting = {
  key: string;
  value: Record<string, unknown>;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type Page<T> = {
  items: T[];
  limit: number;
  offset: number;
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
