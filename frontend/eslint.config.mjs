import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
// Enforce conventions at call sites; upstream UI primitives own their styling.
const groupContainers = new Map([
  ["SelectItem", ["SelectGroup", "SelectContent"]],
  ["SelectLabel", ["SelectGroup", "SelectContent"]],
  ["DropdownMenuItem", ["DropdownMenuGroup", "DropdownMenuContent"]],
  ["DropdownMenuLabel", ["DropdownMenuGroup", "DropdownMenuContent"]],
  ["DropdownMenuRadioItem", ["DropdownMenuRadioGroup", "DropdownMenuContent"]],
  ["TabsTrigger", ["TabsList", "Tabs"]],
]);
const iconOwners = new Set([
  "Button",
  "DropdownMenuItem",
  "DropdownMenuCheckboxItem",
  "DropdownMenuRadioItem",
  "SelectItem",
  "SelectTrigger",
  "Alert",
  "SidebarMenuButton",
  "SidebarMenuAction",
  "EmptyMedia",
]);

function staticStrings(node) {
  if (!node) return [];
  if (node.type === "Literal" && typeof node.value === "string")
    return [node.value];
  if (node.type === "JSXExpressionContainer")
    return staticStrings(node.expression);
  if (node.type === "TemplateLiteral")
    return node.quasis.map((part) => part.value.raw);
  if (node.type === "CallExpression")
    return node.arguments.flatMap(staticStrings);
  if (node.type === "ConditionalExpression")
    return [
      ...staticStrings(node.consequent),
      ...staticStrings(node.alternate),
    ];
  if (node.type === "LogicalExpression")
    return [...staticStrings(node.left), ...staticStrings(node.right)];
  if (node.type === "ArrayExpression")
    return node.elements.flatMap(staticStrings);
  if (node.type === "ObjectExpression")
    return node.properties.flatMap((property) => staticStrings(property.key));
  return [];
}

const conventions = {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      spacing: "shadcn：使用 flex/grid + gap，不使用 space-x/space-y。",
      color:
        "shadcn：使用语义颜色令牌，不在业务组件中硬编码颜色或覆写 dark 颜色。",
      classes: "shadcn：动态 className 使用 cn()，不拼接模板字符串。",
      group: "shadcn：{{item}} 必须位于 {{group}} 中。",
      icon: "shadcn：Button 中的图标必须标记 data-icon=inline-start 或 inline-end。",
      iconSize: "shadcn：控件内图标尺寸由组件负责，不添加 size/w/h 类。",
    },
  },
  create(context) {
    const components = new Map();
    const icons = new Set();
    const ancestors = (node) =>
      context.sourceCode
        .getAncestors(node)
        .filter((ancestor) => ancestor.type === "JSXElement")
        .map((ancestor) => components.get(ancestor.openingElement.name.name))
        .filter(Boolean)
        .reverse();
    return {
      ImportDeclaration(node) {
        const source = node.source.value;
        for (const specifier of node.specifiers) {
          if (specifier.type !== "ImportSpecifier") continue;
          if (source.startsWith("@/components/ui/"))
            components.set(specifier.local.name, specifier.imported.name);
          if (source === "lucide-react" || source === "@/components/ui/spinner")
            icons.add(specifier.local.name);
        }
      },
      JSXAttribute(node) {
        if (node.name.name !== "className") return;
        const expression = node.value?.expression;
        if (
          expression?.type === "TemplateLiteral" &&
          expression.expressions.length
        )
          context.report({ node, messageId: "classes" });
        const tokens = staticStrings(node.value).flatMap((value) =>
          value.split(/\s+/),
        );
        if (tokens.some((token) => /(?:^|:)-?space-[xy]-/.test(token)))
          context.report({ node, messageId: "spacing" });
        if (
          tokens.some(
            (token) =>
              /(?:^|:)(?:bg|text|border|ring|fill|stroke)-(?:black|white|(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d|\[(?:#|rgb|hsl|oklch))/.test(
                token,
              ) ||
              /(?:^|:)dark:.*(?:bg|text|border|ring|fill|stroke)-/.test(token),
          )
        )
          context.report({ node, messageId: "color" });
        if (
          icons.has(node.parent.name.name) &&
          ancestors(node.parent).some((name) => iconOwners.has(name)) &&
          tokens.some((token) => /(?:^|:)(?:size|w|h)-/.test(token))
        )
          context.report({ node, messageId: "iconSize" });
      },
      "JSXOpeningElement, JSXSelfClosingElement"(node) {
        const parents = ancestors(node);
        // The opening element's own JSXElement is also an ancestor.
        const ownName = components.get(node.name.name);
        if (ownName && parents[0] === ownName) parents.shift();
        const required = groupContainers.get(ownName);
        if (required) {
          const [group, container] = required;
          // Check only when a container is visible in this JSX tree. A local
          // wrapper can own the group for children passed from another scope.
          const boundary = parents.find(
            (name) => name === group || name === container,
          );
          if (boundary === container)
            context.report({
              node,
              messageId: "group",
              data: { item: ownName, group },
            });
        }
        if (icons.has(node.name.name) && parents.includes("Button")) {
          const marker = node.attributes.find(
            (attribute) => attribute.name?.name === "data-icon",
          );
          if (
            !marker ||
            !staticStrings(marker.value).some(
              (value) => value === "inline-start" || value === "inline-end",
            )
          )
            context.report({ node, messageId: "icon" });
        }
      },
    };
  },
};

const designSystem = { rules: { conventions } };

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
    plugins: { "design-system": designSystem },
    rules: {
      "design-system/conventions": "error",
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
            "JSXOpeningElement[name.type='JSXIdentifier'][name.name=/^[a-z]/]",
          message:
            "业务页面和布局必须组合 shadcn/Radix 及 UI 语义组件；原生标签仅允许在 src/components/ui 中实现。",
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
