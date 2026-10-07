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
export default designSystem;
