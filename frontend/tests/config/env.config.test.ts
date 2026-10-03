import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadRootWebEnvironment } from "../../env.config.mjs";

let repositoryRoot: string;

beforeEach(() => {
  repositoryRoot = mkdtempSync(join(tmpdir(), "hotkey-root-env-"));
  for (const key of [
    "HOTKEY_API_ORIGIN",
    "HOTKEY_WEB_ORIGIN",
    "HOTKEY_OPENAPI_URL",
    "NEXT_PUBLIC_SITE_ORIGIN",
    "HOTKEY_GITHUB_CLIENT_SECRET",
    "HOTKEY_AUTH_SMTP_PASSWORD",
    "UNTRUSTED_SETTING",
  ]) {
    vi.stubEnv(key, undefined);
  }
});

afterEach(() => {
  vi.unstubAllEnvs();
  rmSync(repositoryRoot, { recursive: true, force: true });
});

describe("root Web environment", () => {
  it("loads Web configuration without importing backend credentials", () => {
    writeFileSync(
      join(repositoryRoot, ".env"),
      [
        'HOTKEY_API_ORIGIN="http://127.0.0.1:8667"',
        "HOTKEY_WEB_ORIGIN=http://127.0.0.1:8666",
        "HOTKEY_OPENAPI_URL=https://api.hotkey.test/openapi.json",
        "NEXT_PUBLIC_SITE_ORIGIN=https://hotkey.test",
        "HOTKEY_GITHUB_CLIENT_SECRET=controlled-test-secret",
        "HOTKEY_AUTH_SMTP_PASSWORD=controlled-test-password",
        "UNTRUSTED_SETTING=do-not-import",
      ].join("\n"),
    );

    loadRootWebEnvironment(repositoryRoot);

    expect(process.env.HOTKEY_API_ORIGIN).toBe("http://127.0.0.1:8667");
    expect(process.env.HOTKEY_WEB_ORIGIN).toBe("http://127.0.0.1:8666");
    expect(process.env.HOTKEY_OPENAPI_URL).toBe(
      "https://api.hotkey.test/openapi.json",
    );
    expect(process.env.NEXT_PUBLIC_SITE_ORIGIN).toBe("https://hotkey.test");
    expect(process.env.HOTKEY_GITHUB_CLIENT_SECRET).toBeUndefined();
    expect(process.env.HOTKEY_AUTH_SMTP_PASSWORD).toBeUndefined();
    expect(process.env.UNTRUSTED_SETTING).toBeUndefined();
  });

  it("preserves explicitly injected container or command environment", () => {
    writeFileSync(
      join(repositoryRoot, ".env"),
      "HOTKEY_API_ORIGIN=http://127.0.0.1:8667\n",
    );
    vi.stubEnv("HOTKEY_API_ORIGIN", "http://backend:8080");

    loadRootWebEnvironment(repositoryRoot);

    expect(process.env.HOTKEY_API_ORIGIN).toBe("http://backend:8080");
  });

  it("starts from injected configuration when no root file exists", () => {
    vi.stubEnv("HOTKEY_WEB_ORIGIN", "https://hotkey.test");

    expect(() => loadRootWebEnvironment(repositoryRoot)).not.toThrow();
    expect(process.env.HOTKEY_WEB_ORIGIN).toBe("https://hotkey.test");
    expect(process.env.HOTKEY_API_ORIGIN).toBeUndefined();
  });
});
