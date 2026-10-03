import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseEnv } from "node:util";

const WEB_ENVIRONMENT_KEYS = [
  "HOTKEY_API_ORIGIN",
  "HOTKEY_WEB_ORIGIN",
  "HOTKEY_OPENAPI_URL",
  "NEXT_PUBLIC_SITE_ORIGIN",
];

export function loadRootWebEnvironment(
  repositoryRoot = resolve(process.cwd(), ".."),
) {
  const envFile = resolve(repositoryRoot, ".env");
  if (!existsSync(envFile)) return;

  const values = parseEnv(readFileSync(envFile, "utf8"));
  for (const key of WEB_ENVIRONMENT_KEYS) {
    if (process.env[key] === undefined && values[key] !== undefined) {
      process.env[key] = values[key];
    }
  }
}
