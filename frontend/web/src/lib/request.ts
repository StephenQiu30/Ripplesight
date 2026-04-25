const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_BASE_URL || "http://localhost:8000";

export type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue | QueryValue[]>;

export type RequestOptions = {
  method?: string;
  params?: QueryParams;
  data?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  requestType?: "json" | "form" | string;
  [key: string]: unknown;
};

type ApiRequestOptions<TBody = unknown> = {
  method?: "GET" | "POST";
  query?: QueryParams;
  body?: TBody;
  signal?: AbortSignal;
};

function appendQueryPair(params: URLSearchParams, key: string, value: QueryValue | QueryValue[]) {
  if (value === undefined || value === null) {
    return;
  }
  const values = Array.isArray(value) ? value : [value];
  values.forEach((item) => {
    params.append(key, String(item));
  });
}

function toQueryString(query: QueryParams | undefined): string {
  if (!query) {
    return "";
  }
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    appendQueryPair(params, key, value);
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

function resolveBaseUrl(): string {
  if (typeof window === "undefined") {
    return DEFAULT_API_BASE.replace(/\/$/, "");
  }
  return "";
}

export async function requestJson<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const { body, query, signal } = options;
  const url = `${resolveBaseUrl()}${path}${toQueryString(query)}`;
  return request<T>(url, { method, signal, data: body });
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = "GET",
    params,
    data,
    headers: customHeaders,
    signal,
    requestType,
    ...rest
  } = options;

  const url = `${resolveBaseUrl()}${path}${toQueryString(params)}`;

  const headers = {
    Accept: "application/json",
    ...(customHeaders || {}),
  } as Record<string, string>;

  if (requestType !== "form" && data !== undefined) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  const response = await fetch(url, {
    method,
    signal,
    headers,
    body: data !== undefined ? JSON.stringify(data) : undefined,
    cache: "no-store",
    ...rest,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API request failed (${response.status}): ${text || response.statusText}`);
  }

  return (await response.json()) as T;
}
