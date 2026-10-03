import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const requestMessage = "业务请求必须调用 src/api 中的 Umi OpenAPI 生成函数。";
const httpLibraries =
  "^(?:axios|ky|got|superagent|undici|node-fetch|cross-fetch|umi-request|@umijs/request|(?:node:)?(?:http|https|http2|net|tls))(?:/.*)?$";
const requestModule = "^(?:@/|\\.{1,2}/)(?:.*/)?request(?:\\.[cm]?[jt]s)?$";
const testLibraries =
  "^(?:vitest|@testing-library/[^/]+|(?:node:)?test)(?:/.*)?$";
const testDirectory = "(?:^|/)tests(?:/|$)";
const testMessage = "测试只能放在独立 tests 目录，业务源码不得导入测试依赖。";
const proxyRoute = "src/app/api/\\[\\[...path\\]\\]/route.ts";
const testImports = [
  { regex: testLibraries, message: testMessage },
  { regex: testDirectory, message: testMessage },
];
const businessImports = [
  ...testImports,
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
];

function dynamicImportRestrictions(patterns) {
  return patterns.map(({ regex, message }) => ({
    selector: `ImportExpression[source.value=/${regex.replaceAll("/", "\\/")}/]`,
    message,
  }));
}

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{js,jsx,ts,tsx,mjs,mts,cjs,cts}"],
    ignores: ["src/request.ts"],
    rules: {
      "no-restricted-imports": ["error", { patterns: businessImports }],
      "no-restricted-syntax": [
        "error",
        ...dynamicImportRestrictions(businessImports),
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
    ignores: ["src/request.ts", proxyRoute],
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
  {
    files: ["src/request.ts"],
    rules: {
      "no-restricted-imports": ["error", { patterns: testImports }],
      "no-restricted-syntax": [
        "error",
        ...dynamicImportRestrictions(testImports),
      ],
    },
  },
  {
    files: ["src/**/*.tsx"],
    ignores: ["src/components/ui/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        ...dynamicImportRestrictions(businessImports),
        {
          selector:
            "MemberExpression[property.name='sendBeacon'], MemberExpression[property.value='sendBeacon']",
          message: requestMessage,
        },
        {
          selector:
            "JSXOpeningElement[name.name=/^(button|input|select|option|textarea|details|summary|dialog|table|thead|tbody|tfoot|tr|th|td|caption|hr|progress|label|fieldset|legend)$/]",
          message:
            "页面控件必须组合 src/components/ui 中的官方 shadcn/ui + Radix 组件。",
        },
        {
          selector:
            "JSXOpeningElement[name.name=/^(div|span|p)$/] > JSXAttribute[name.name='role'][value.value=/^(button|checkbox|switch|tab|dialog|alert)$/]",
          message: "使用对应的 shadcn/Radix 交互组件，不手写交互角色。",
        },
      ],
    },
  },
  {
    files: ["**/*.{test,spec}.{js,jsx,ts,tsx,mjs,mts,cjs,cts}"],
    ignores: ["tests/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        { selector: "Program", message: testMessage },
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
