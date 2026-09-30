import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { proxy } from "./proxy";

describe("Demo navigation and CSP", () => {
  it.each(["/events", "/reports", "/monitors/new"])(
    "opens %s without a session cookie and preserves the CSP",
    (path) => {
      const response = proxy(new NextRequest(`https://hotkey.test${path}`));

      expect(response.status).toBe(200);
      expect(response.headers.get("location")).toBeNull();
      expect(response.headers.get("x-middleware-next")).toBe("1");
      expect(response.headers.get("content-security-policy")).toContain(
        "default-src 'self'",
      );
    },
  );

  it("uses a distinct CSP nonce for each page request", () => {
    const request = new NextRequest("https://hotkey.test/monitors/new");
    const first = proxy(request).headers.get("content-security-policy");
    const second = proxy(request).headers.get("content-security-policy");

    expect(first).toMatch(/'nonce-[^']+'/);
    expect(second).toMatch(/'nonce-[^']+'/);
    expect(first).not.toBe(second);
  });
});
