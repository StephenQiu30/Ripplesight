import {
  AxiosError,
  AxiosHeaders,
  type AxiosAdapter,
  type AxiosResponse,
} from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import request, { ApiRequestError } from "@/request";

const BODY_REQUEST_ID = "1d585580-ef30-449a-8716-56c0a015763a";
const HEADER_REQUEST_ID = "dc7deafc-1f20-4921-87e2-20c221d9c79b";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function responseAdapter(
  status: number,
  data: unknown,
  headers: Record<string, string> = {},
): AxiosAdapter {
  return async (config) => {
    const response: AxiosResponse = {
      config,
      data,
      headers: new AxiosHeaders(headers),
      status,
      statusText: String(status),
    };

    if (status >= 400) {
      throw new AxiosError(
        "GET https://secret.invalid/token=should-not-leak",
        "ERR_BAD_RESPONSE",
        config,
        undefined,
        response,
      );
    }

    return response;
  };
}

function transportErrorAdapter(code: string): AxiosAdapter {
  return async (config) => {
    throw new AxiosError(
      "GET https://secret.invalid/token=should-not-leak",
      code,
      config,
    );
  };
}

async function captureError(adapter: AxiosAdapter): Promise<ApiRequestError> {
  try {
    await request("/api/example", { adapter });
  } catch (error) {
    expect(error).toBeInstanceOf(ApiRequestError);
    return error as ApiRequestError;
  }
  throw new Error("expected request to fail");
}

describe("request transport", () => {
  it.each([
    {
      browser: false,
      origin: "http://backend.test:8080",
      expected: "http://backend.test:8080",
    },
    { browser: false, origin: undefined, expected: "http://127.0.0.1:8867" },
    { browser: true, origin: "http://backend.test:8080", expected: "/" },
  ])(
    "resolves the transport origin for $browser / $origin",
    async ({ browser, origin, expected }) => {
      vi.stubGlobal("window", browser ? {} : undefined);
      vi.stubEnv("HOTKEY_API_ORIGIN", origin);
      await request("/api/topics", {
        adapter: async (config) => {
          expect(config.baseURL).toBe(expected);
          return {
            config,
            data: {},
            headers: new AxiosHeaders(),
            status: 200,
            statusText: "OK",
          };
        },
      });
    },
  );

  it("uses the Demo write header without reading cookies or credentials", async () => {
    const readCookie = vi.fn(() => "hotkey_csrf=obsolete-session-token");
    vi.stubGlobal("document", {
      get cookie() {
        return readCookie();
      },
    });
    let mutationHeader: unknown;
    let readHeader: unknown;
    let credentials: unknown;

    await request<void>("/api/topics/topic-1/pause", {
      adapter: async (config) => {
        mutationHeader = config.headers.get("X-HotKey-CSRF");
        credentials = config.withCredentials;
        expect(config.headers.get("Cookie")).toBeUndefined();
        expect(config.headers.get("Authorization")).toBeUndefined();
        return {
          config,
          data: "",
          headers: new AxiosHeaders(),
          status: 204,
          statusText: "204",
        };
      },
      method: "POST",
    });
    await request<void>("/api/topics", {
      adapter: async (config) => {
        readHeader = config.headers.get("X-HotKey-CSRF");
        return {
          config,
          data: {},
          headers: new AxiosHeaders(),
          status: 200,
          statusText: "200",
        };
      },
      method: "GET",
    });

    expect(mutationHeader).toBe("1");
    expect(readHeader).toBeUndefined();
    expect(readCookie).not.toHaveBeenCalled();
    expect(credentials).not.toBe(true);
  });

  it("reads details and falls back to the body request id", async () => {
    const details = [
      {
        location: ["query", "limit"],
        message: "请输入有效整数",
        type: "int_parsing",
      },
    ];
    const error = await captureError(
      responseAdapter(422, {
        code: "validation_error",
        details,
        message: "请求参数校验失败",
        request_id: BODY_REQUEST_ID,
      }),
    );

    expect(error.kind).toBe("http");
    expect(error.code).toBe("validation_error");
    expect(error.details).toEqual(details);
    expect(error.requestId).toBe(BODY_REQUEST_ID);
    expect(error.status).toBe(422);
  });

  it("prefers a valid response header request id", async () => {
    const error = await captureError(
      responseAdapter(
        403,
        {
          code: "forbidden",
          message: "没有权限",
          request_id: BODY_REQUEST_ID,
        },
        { "x-request-id": HEADER_REQUEST_ID },
      ),
    );

    expect(error.requestId).toBe(HEADER_REQUEST_ID);
  });

  it.each([
    ["ERR_NETWORK", "network"],
    ["ECONNABORTED", "timeout"],
    ["ERR_CANCELED", "cancelled"],
  ] as const)(
    "classifies %s without exposing the axios message",
    async (code, kind) => {
      const error = await captureError(transportErrorAdapter(code));

      expect(error.kind).toBe(kind);
      expect(error.status).toBeUndefined();
      expect(error.requestId).toBeUndefined();
      expect(error.message).not.toContain("secret.invalid");
    },
  );

  it("classifies non-json failures as protocol errors", async () => {
    const error = await captureError(
      responseAdapter(502, "<html>token=should-not-leak</html>"),
    );

    expect(error.kind).toBe("protocol");
    expect(error.status).toBe(502);
    expect(error.message).not.toContain("should-not-leak");
  });

  it("does not parse 204 responses and preserves file payloads", async () => {
    const empty = await request<void>("/api/example", {
      adapter: responseAdapter(204, ""),
      method: "DELETE",
    });
    const file = new Blob(["hotkey"], { type: "text/plain" });
    const downloaded = await request<Blob>("/api/example", {
      adapter: responseAdapter(200, file),
      responseType: "blob",
    });

    expect(empty).toBeUndefined();
    expect(downloaded).toBe(file);
  });
});
