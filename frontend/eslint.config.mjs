import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const requestMessage = "业务请求必须调用 src/api 中的 Umi OpenAPI 生成函数。";
const httpLibraries =
  "^(?:axios|ky|got|superagent|undici|node-fetch|cross-fetch|umi-request|@umijs/request|(?:node:)?(?:http|https|http2|net|tls))(?:/.*)?$";
const requestModule = "^(?:@/|\\.{1,2}/)(?:.*/)?request(?:\\.[cm]?[jt]s)?$";
const transportTests = [
  "src/request.test.ts",
  "src/app/api/\\[\\[...path\\]\\]/route.test.ts",
];
const proxyRoute = "src/app/api/\\[\\[...path\\]\\]/route.ts";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{js,jsx,ts,tsx,mjs,mts,cjs,cts}"],
    ignores: ["src/request.ts", ...transportTests],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            { regex: httpLibraries, message: requestMessage },
            {
              regex: requestModule,
              allowImportNames: [
                "ApiRequestError",
                "ApiRequestErrorKind",
                "RequestOptions",
              ],
              message: requestMessage,
            },
          ],
        },
      ],
      "no-restricted-syntax": [
        "error",
        ...[httpLibraries, requestModule].map((pattern) => ({
          selector: `ImportExpression[source.value=/${pattern.replaceAll("/", "\\/")}/]`,
          message: requestMessage,
        })),
        {
          selector:
            "MemberExpression[property.name='sendBeacon'], MemberExpression[property.value='sendBeacon']",
          message: requestMessage,
        },
      ],
    },
  },
  {
    files: ["src/**/*.{js,jsx,ts,tsx,mjs,mts,cjs,cts}"],
    ignores: ["src/request.ts", proxyRoute, ...transportTests],
    rules: {
      "no-restricted-globals": [
        "error",
        {
          checkGlobalObject: true,
          globals: ["fetch", "XMLHttpRequest", "WebSocket", "EventSource"].map(
            (name) => ({
              name,
              message: requestMessage,
            }),
          ),
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "src/api/**",
  ]),
]);

export default eslintConfig;
